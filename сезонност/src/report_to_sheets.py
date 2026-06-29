"""report_to_sheets — orchestrator: собрать отчёт (Phase 4) → записать в Sheets.

Связывает офлайн-сборку (build_report.build_report_df + df_to_rows) с тонким
сетевым слоем (sheets_client.get_client + write_report). Phase 4 расширение:
  1. Пишет лист «Отчёт» (84 колонки, предсортированный, 1300 строк).
  2. Применяет цветовую заливку одним ws.batch_format() через apply_formatting.
  3. Пишет лист «Сезонность» (12 глобальных индексов) через write_report.

build_rows() / build_season_rows() — чистые офлайн-функции, тестируемы в pytest.
main() — касается сети; запускать вручную после human-verify gate (Editor-доступ).
НА ИМПОРТЕ МОДУЛЯ main() НЕ ВЫЗЫВАЕТСЯ.
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd

# Allow `python src/report_to_sheets.py` to run standalone (project root on path).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.build_report import build_report_df, df_to_rows  # noqa: E402
from src.sheets_client import get_client, write_report   # noqa: E402
from src.apply_formatting import format_sheet             # noqa: E402
from src.seasonality import compute_global_seasonal_index # noqa: E402
from src.report_metrics import RU_MONTHS                  # noqa: E402
from src.order_finalize import (                          # noqa: E402
    apply_report_order_adjustment,
    build_coverage_block,
    build_order_rows,
    move_excluded_to_bottom,
    parse_already_ordered,
    parse_dealer_wants,
    parse_exclude,
    parse_factory_avail,
)

# LOCKED targets (зафиксировано пользователем / research'ем).
SHEET_ID = "1ncF3ElaK8OWRfnajrdkiK9WcNQQ9r0UTKhx_xSaBtSE"
WORKSHEET_TITLE = "Отчёт"
SEASON_TITLE = "Сезонность"
ORDER_TITLE = "ближайший заказ"

# Листы-входы, которые ведёт пользователь (мы их только читаем).
EXCLUDE_TITLE = "исключить"
ALREADY_TITLE = "уже заказано"
DEALER_TITLE = "надо дилерам, еще не заказано"
FACTORY_TITLE = "доступный остаток завода"


def _safe_values(ss, title: str) -> list[list]:
    """Прочитать все значения листа; [] если листа нет (вход не обязателен)."""
    try:
        return ss.worksheet(title).get_all_values()
    except Exception:  # WorksheetNotFound и пр.
        return []

# Ordered RU month names (Jan=1..Dec=12) for «Сезонность» sheet.
_MONTH_NAMES_BY_NUM: dict[int, str] = {v: k for k, v in RU_MONTHS.items()}

INTERIM = pathlib.Path("data/interim")
PRODAZHI_PATH = INTERIM / "prodazhi.parquet"


def build_rows() -> tuple[list[list], object]:
    """Собрать отчётный DataFrame (84 cols, предсортирован) и сериализовать.

    Чистая офлайн-функция. Возвращает (rows, df) чтобы main() мог передать df
    в format_sheet без повторного пересчёта.

    Returns:
        (rows, df) — rows: Sheets-safe list[list] (header + 1300 data rows);
                     df: the source DataFrame for apply_formatting.
    """
    df = build_report_df()
    return df_to_rows(df), df


def build_season_rows(prodazhi_path: pathlib.Path = PRODAZHI_PATH) -> list[list]:
    """Собрать 12 строк глобальных сезонных индексов для листа «Сезонность».

    Чистая офлайн-функция (читает prodazhi.parquet, без сети).

    Returns:
        list[list] — заголовок + 12 строк: [«Месяц», «Индекс», «Кол-во лет»].
        Строки в порядке 1..12 (январь → декабрь).
    """
    pro = pd.read_parquet(prodazhi_path)
    season_map = compute_global_seasonal_index(pro)

    # «Кол-во лет» — сколько различных лет данных для каждого кал. месяца.
    # jul–sep = 2 years (2024/2025 only); rest = 3 years (see 04-RESEARCH.md).
    from src.report_metrics import month_sort_key
    ym_pairs: set[tuple[int, int]] = set()
    for label in pro["month"].unique():
        ym_pairs.add(month_sort_key(label))
    year_counts: dict[int, int] = {}
    for (year, cal_month) in ym_pairs:
        year_counts[cal_month] = year_counts.get(cal_month, 0) + 1

    header = ["Месяц", "Индекс", "Кол-во лет"]
    rows: list[list] = [header]
    for m in range(1, 13):
        month_name = _MONTH_NAMES_BY_NUM.get(m, str(m))
        idx = round(float(season_map.get(m, 0.0)), 4)
        n_years = year_counts.get(m, 0)
        rows.append([month_name, idx, n_years])
    return rows


def main() -> int:
    """Живой прогон: записать лист «Отчёт» + заливку + лист «Сезонность».

    Порядок операций:
      1. build_rows() → rows (84-кол, предсортирован) + df (для форматирования).
      2. write_report(ss, «Отчёт», rows) — идемпотентно clear+update.
      3. format_sheet(ws, df) — один ws.batch_format() вызов (цвет DSI/pct/green).
      4. build_season_rows() → season_rows; write_report(ss, «Сезонность», season_rows).

    Возвращает int — число строк листа «Отчёт» (контракт для бота «обновлено N строк»).

    Касается сети — запускать вручную после human-verify gate.
    НЕ вызывается автоматически ни в pytest, ни при импорте модуля.
    """
    df = build_report_df()  # ИСХОДНЫЙ df (прогноз К заказу до корректировок)

    client = get_client()
    ss = client.open_by_key(SHEET_ID)

    # 0. Прочитать листы-входы пользователя (только чтение).
    excluded = parse_exclude(_safe_values(ss, EXCLUDE_TITLE))
    already = parse_already_ordered(_safe_values(ss, ALREADY_TITLE))
    dealer_vals = _safe_values(ss, DEALER_TITLE)
    wants = parse_dealer_wants(dealer_vals)
    factory = parse_factory_avail(_safe_values(ss, FACTORY_TITLE))
    print(f"Входы: исключить={len(excluded)} уже заказано={len(already)} "
          f"хотелки={len(wants)} лимит завода={len(factory)}")

    # 1. «Ближайший заказ» — из ИСХОДНОГО прогноза (до вычета «уже заказано»).
    order_rows = build_order_rows(df, excluded, already, wants)

    # 2. Отчёт: скорректировать «К заказу» (исключить -> 0; − уже заказано),
    #    затем перенести исключённые товары в самый низ листа.
    df_report = apply_report_order_adjustment(df, excluded, already)
    df_report = move_excluded_to_bottom(df_report, excluded)
    rows = df_to_rows(df_report)
    n = write_report(ss, WORKSHEET_TITLE, rows)
    print(f"Записано строк: {n} в лист «{WORKSHEET_TITLE}»")

    # 3. Цветовая заливка (один ws.batch_format()).
    ws = ss.worksheet(WORKSHEET_TITLE)
    format_sheet(ws, df_report)
    print("Цветовая заливка применена (DSI / %продаж / зелёный товар)")

    # 4. «Ближайший заказ» (артикул, себест, кол-во, сумма, ИТОГО).
    no = write_report(ss, ORDER_TITLE, order_rows)
    print(f"Записано строк: {no} в лист «{ORDER_TITLE}» (включая ИТОГО)")

    # 5. Блок покрытия хотелок лимитом завода -> дописать в «надо дилерам» (колонки F:H).
    if dealer_vals:
        block = build_coverage_block(dealer_vals, factory)
        ss.worksheet(DEALER_TITLE).update(values=block, range_name="F1")
        print(f"Колонки покрытия (доступно/покроется/не закроется) -> «{DEALER_TITLE}»")

    # 6. «Сезонность» (12 глобальных индексов).
    season_rows = build_season_rows()
    ns = write_report(ss, SEASON_TITLE, season_rows)
    print(f"Записано строк: {ns} в лист «{SEASON_TITLE}»")

    return n


if __name__ == "__main__":
    main()
