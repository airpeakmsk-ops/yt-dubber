"""bot/backup.py — слой безопасности данных бота.

Бэкап входных xlsx + parquet-артефактов перед заменой, откат из бэкапа
при падении пайплайна, валидация присланного файла до запуска, ротация.

Правило: лучше откатиться и сказать «не вышло», чем оставить
полу-обновлённую боевую таблицу (CONTEXT LOCKED — backup-before-step).

Публичный API:
  backup_artifacts(file_type, config) -> Path   — снапшот ВСЕХ parquet + xlsx
  restore_artifacts(bak, config)                — откат из снапшота
  validate_xlsx(path, file_type) -> None        — fail-closed проверка файла

Константы:
  BACKUP_KEEP = 5   — хранить последние N снапшотов на тип файла
"""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.config import Config

# Монотонный счётчик — уникальность имени даже при нескольких вызовах
# в одну секунду (и даже если ротация удалила dir с тем же timestamp).
_counter_lock = threading.Lock()
_counter: int = 0

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

BACKUP_KEEP: int = 5

# Все parquet-артефакты, которые могут измениться при любом типе файла.
# Бэкапим ВЕСЬ набор — дёшево (<300КБ), исключает Pitfall 7 (пропущенный файл).
_ALL_PARQUET: list[str] = [
    "master.parquet",
    "master_cost.parquet",
    "ostatki.parquet",
    "prikhod_ledger.parquet",
    "prikhody.parquet",
    "prodazhi.parquet",
]

# Входные xlsx по типу файла (относительно project_root).
# invoice — добавляется в папку, не заменяет существующий файл → бэкап не нужен.
_INPUT_XLSX: dict[str, str] = {
    "ledger": "приходы остатки.xlsx",
    "weekly": "остатки по неделям.xlsx",
}


# ---------------------------------------------------------------------------
# Внутренние хелперы
# ---------------------------------------------------------------------------

def _get_paths(config: "Config") -> tuple[Path, Path]:
    """Вернуть (INTERIM, BAK_DIR) для данного конфига."""
    interim = config.project_root / "data" / "interim"
    bak_dir = interim / "_bak_bot"
    return interim, bak_dir


def _unique_bak_name(file_type: str, bak_dir: Path) -> str:
    """Уникальное имя директории снапшота: {type}_{timestamp}_{seq}.

    Монотонный глобальный счётчик (_counter) гарантирует уникальность даже:
    - при нескольких вызовах в одну секунду,
    - если ротация удалила директорию с тем же timestamp (создание той же
      строки base приводило бы к перезаписи старых снапшотов).
    """
    global _counter
    ts = int(time.time())
    with _counter_lock:
        _counter += 1
        seq = _counter
    return f"{file_type}_{ts}_{seq:04d}"


def _rotate(file_type: str, bak_dir: Path) -> None:
    """Удалить старейшие снапшоты типа file_type, оставив BACKUP_KEEP штук.

    Снапшоты других типов не трогать (Open Question 2, рекомендация RESEARCH).
    """
    snapshots = sorted(bak_dir.glob(f"{file_type}_*"))
    excess = len(snapshots) - BACKUP_KEEP
    if excess > 0:
        for old in snapshots[:excess]:
            shutil.rmtree(old, ignore_errors=True)


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

def backup_artifacts(file_type: str, config: "Config") -> Path:
    """Создать снапшот ВСЕХ parquet + входного xlsx (если применимо).

    Параметры:
        file_type: "ledger" | "weekly" | "invoice"
        config:    Config — project_root берём отсюда (кросс-платформенно).

    Возвращает:
        Path к директории снапшота (INTERIM/_bak_bot/{type}_{ts}).

    Алгоритм:
        1. Создать директорию снапшота.
        2. Скопировать каждый существующий parquet из _ALL_PARQUET.
        3. Для ledger/weekly — скопировать входной xlsx.
        4. Выполнить ротацию (оставить BACKUP_KEEP снапшотов этого типа).
    """
    interim, bak_dir = _get_paths(config)
    bak_dir.mkdir(parents=True, exist_ok=True)

    # Уникальное имя (устойчиво к двум вызовам в одну секунду)
    snap_name = _unique_bak_name(file_type, bak_dir)
    bak = bak_dir / snap_name
    bak.mkdir(parents=True)

    # Шаг 2: скопировать все существующие parquet
    for name in _ALL_PARQUET:
        src = interim / name
        if src.exists():
            shutil.copy2(src, bak / name)

    # Шаг 3: скопировать входной xlsx (только для ledger и weekly)
    xlsx_name = _INPUT_XLSX.get(file_type)
    if xlsx_name is not None:
        src_xlsx = config.project_root / xlsx_name
        if src_xlsx.exists():
            shutil.copy2(src_xlsx, bak / xlsx_name)

    # Шаг 4: ротация — удалить старейшие, оставить BACKUP_KEEP
    _rotate(file_type, bak_dir)

    return bak


def restore_artifacts(bak: Path, config: "Config") -> None:
    """Восстановить parquet и входной xlsx из снапшота bak.

    Параметры:
        bak:    Path к директории снапшота (возвращена backup_artifacts).
        config: Config — project_root берём отсюда.

    Для каждого файла в bak:
        *.parquet → copy2 обратно в INTERIM.
        *.xlsx    → copy2 в правильный входной путь (по имени файла).
    """
    interim, _ = _get_paths(config)

    for src in bak.iterdir():
        if src.suffix == ".parquet":
            dest = interim / src.name
            shutil.copy2(src, dest)
        elif src.suffix in (".xlsx", ".xls"):
            # Восстанавливаем входной xlsx по имени файла в project_root
            dest = config.project_root / src.name
            shutil.copy2(src, dest)


def validate_xlsx(path: Path, file_type: str) -> None:
    """Быстрая fail-closed проверка входного xlsx через python_calamine.

    Не выполняет полный парсинг (Don't Hand-Roll) — только открывает
    книгу и проверяет количество строк первого листа.

    Параметры:
        path:      Path к файлу для проверки.
        file_type: тип ("ledger" | "weekly" | "invoice") — зарезервировано
                   для будущих тип-специфичных порогов.

    Raises:
        ValueError: если файл не читается как xlsx или содержит < 12 строк.
    """
    _MIN_ROWS = 12  # минимум строк для непустого файла 1С

    try:
        import python_calamine  # уже движок пайплайна; на VPS — в venv

        wb = python_calamine.CalamineWorkbook.from_path(str(path))
        sheet_name = wb.sheet_names[0]
        sheet = wb.get_sheet_by_name(sheet_name)
        rows = sheet.to_python()
        if len(rows) < _MIN_ROWS:
            raise ValueError(
                f"Слишком мало строк ({len(rows)}) — возможно пустой файл или не тот тип. "
                f"Ожидается минимум {_MIN_ROWS} строк для файла типа '{file_type}'."
            )
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(
            f"Файл не читается как xlsx/1С: {e}"
        ) from e
