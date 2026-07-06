"""bot/pipeline.py — синхронный оркестратор пайплайна складской аналитики.

run_pipeline(file_type, tmp_path) -> int
  Вызывается ботом через asyncio.to_thread (синхронная функция).
  Реализует карту «тип файла → шаги пайплайна»:
    ledger  : write_artifacts → build_master → compute_cost → report (полный цикл)
    weekly  : ТОЛЬКО report (parquet не пересобираются — BOT-02, приходная/себест не трогается)
    invoice : copy → build_master → compute_cost → report (себестоимость пересчитана)
    other   : ValueError (type-branching: unknown явно отклонён — CODE_DOMAIN правило)

  Обёртка backup→try→restore-on-error:
    - backup_artifacts(file_type, config)  до любых изменений
    - restore_artifacts(bak, config)       при любом исключении; Sheet не трогается до полного успеха
    - validate_xlsx(path, file_type)       fail-closed ДО бэкапа
    config берётся из load_config() (project_root для backup/restore — кросс-платформенно).

  GOOGLE_APPLICATION_CREDENTIALS выставлен из env/.env (через bot.config) ДО вызова report.main();
  Windows-fallback из sheets_client НЕ используется.

  sys.path bootstrap: PROJECT_ROOT вставлен в sys.path чтобы src/ импортировался как пакет
  при запуске `python bot/pipeline.py`, через `-m`, и под pytest.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import sys

# sys.path bootstrap — PROJECT_ROOT (родитель bot/) нужен для `from src.*` импортов.
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bot.backup import backup_artifacts, restore_artifacts, validate_xlsx  # noqa: E402
from bot.config import load_config  # noqa: E402

# PROJECT_ROOT для реальных данных (не из bot_config — pipeline может запускаться
# и без бота, и через бот с Config.project_root).
PROJECT_ROOT = _PROJECT_ROOT

# Паттерн курса в имени файла-накладной (из parse_prikhody._RATE_RE):
#   «11 приход 103,79» → 103.79;  «7 приход курс 94» → 94.0.
# Если совпадает — файл идёт в корень «поступления товаров/»,
# иначе — в «поступления товаров/в рублях/».
_RATE_RE = re.compile(r"(?:приход|курс)\s+([\d,\.]+)")


# ---------------------------------------------------------------------------
# Прокси-функции src/* (монкипатчируются в тестах)
# ---------------------------------------------------------------------------

def _write_artifacts(path: pathlib.Path | None = None) -> tuple[int, int]:
    """Обёртка parse_ledger.write_artifacts — пишет prodazhi + prikhod_ledger parquet."""
    from src.parse_ledger import write_artifacts as _wa
    return _wa(path=path)


def _build_master() -> None:
    """Обёртка build_master.main."""
    from src.build_master import main as _bm
    _bm()


def _compute_cost() -> None:
    """Обёртка compute_cost.main."""
    from src.compute_cost import main as _cc
    _cc()


def _report_main() -> int:
    """Обёртка report_to_sheets.main — финал всегда; возвращает N строк «Отчёт»."""
    # Убедиться что GOOGLE_APPLICATION_CREDENTIALS выставлена ДО вызова.
    # На VPS выставляется load_dotenv() в bot.config при импорте; при тестировании мокается.
    from src.report_to_sheets import main as _rm
    return _rm()


# ---------------------------------------------------------------------------
# Внутренние шаги пайплайна
# ---------------------------------------------------------------------------

def _run_ledger(tmp_path: pathlib.Path) -> None:
    """Леджер: скопировать → записать parquet → пересобрать master → пересчитать cost."""
    dest = PROJECT_ROOT / "приходы остатки.xlsx"
    shutil.copy2(tmp_path, dest)
    n_sales, _n_eans = _write_artifacts(dest)
    # Guard вырожденного/битого леджера: 0 строк продаж = файл выгружен неверно
    # (без дат движений / за пустой период / лишняя группировка «Документ движения»).
    # Явная ошибка вместо тихой перезаписи отчёта нулями (raise → бэкап восстановит).
    if n_sales == 0:
        raise ValueError(
            "Леджер не содержит продаж (0 строк реализации). Проверьте настройки "
            "выгрузки 1С: Группировки строк = только «Номенклатура» + «Номенклатура.Артикул»; "
            "Дополнительные поля = «Период» (даёт дату движения); Период = «не установлен»."
        )
    _build_master()
    _compute_cost()


def _run_weekly(tmp_path: pathlib.Path) -> None:
    """Недельные остатки: только скопировать файл.

    Parquet НЕ пересобираются — приходная/себест часть не затрагивается (BOT-02).
    build_master и compute_cost НЕ вызываются.
    """
    dest = PROJECT_ROOT / "остатки по неделям.xlsx"
    shutil.copy2(tmp_path, dest)


def _run_invoice(tmp_path: pathlib.Path) -> None:
    """Накладная: определить подпапку, скопировать → пересобрать master → пересчитать cost.

    Если в имени файла есть маркер курса (паттерн «приход XX,YY» или «курс XX,YY»)
    → корень «поступления товаров/».
    Иначе (накладная в рублях без курса) → «поступления товаров/в рублях/».
    """
    stem = tmp_path.stem
    has_rate = bool(_RATE_RE.search(stem))
    if has_rate:
        dest_dir = PROJECT_ROOT / "поступления товаров"
    else:
        dest_dir = PROJECT_ROOT / "поступления товаров" / "в рублях"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / tmp_path.name
    shutil.copy2(tmp_path, dest)
    _build_master()
    _compute_cost()


# ---------------------------------------------------------------------------
# Публичный оркестратор
# ---------------------------------------------------------------------------

def run_pipeline(file_type: str, tmp_path: pathlib.Path) -> int:
    """Оркестратор пайплайна.

    Args:
        file_type: «ledger» | «weekly» | «invoice» — тип входящего файла.
        tmp_path:  Путь к временному файлу, скачанному ботом из Telegram.

    Returns:
        N — число строк, записанных в лист «Отчёт» (для ответа боту).

    Raises:
        ValueError:  если file_type неизвестен (type-branching: покрыть ВСЕ типы явно).
        Exception:   любое исключение из шагов пайплайна — пробрасывается после restore.
    """
    # Fail-closed: валидировать ДО любых изменений (backup/restore тоже не нужен при ошибке валидации).
    validate_xlsx(tmp_path, file_type)

    # Config нужен backup/restore (project_root). Загружаем из env/.env (bot.config).
    config = load_config()

    bak = backup_artifacts(file_type, config)
    try:
        if file_type == "ledger":
            _run_ledger(tmp_path)
        elif file_type == "weekly":
            _run_weekly(tmp_path)
        elif file_type == "invoice":
            _run_invoice(tmp_path)
        else:
            raise ValueError(f"Unknown file_type: {file_type!r}")

        return _report_main()

    except Exception:
        restore_artifacts(bak, config)
        raise
