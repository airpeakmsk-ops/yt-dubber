"""parse_prodazhi — monthly sales by EAN (DATA-02).

The продажи workbook (`все продажи с 2023 по 26июня2026.xlsx`, sheet TDSheet) is a
1С Покупатель→Номенклатура grouping. Each product occupies TWO rows: a name-row
(col[0] str) then an EAN-row (col[0] float) with identical values. We take only the
EAN-row, route it through normalize_ean (drops samples 9999..., '-1' test SKUs and
footer/non-EAN noise), and emit one record per (EAN, month) with non-zero qty/revenue.

Layout (verified 2026-06-26):
  rows 0-6 meta; row 7 = month labels ('Октябрь 2023 г.' at col 1, step 4);
  rows 8/9 subheaders; data rows 10..2719 (two-row pattern); row 2720 = 'Итог'.
  col 133 = the all-time 'Итог' column — excluded from the month map.
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd
import python_calamine as pc

# Allow `python src/parse_prodazhi.py` to run standalone (project root on path).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.normalize import normalize_ean

SHEET = "TDSheet"
DATA_START = 10
DATA_END = 2720  # exclusive — row 2720 is the 'Итог' footer
MONTH_COL_START = 1
MONTH_COL_STOP = 133  # col 133 = all-time Итог, not a month
MONTH_STEP = 4

OUTPUT_PATH = pathlib.Path("data/interim/prodazhi.parquet")


def build_month_map(rows) -> list[dict]:
    """Build the list of months from row 7 (labels at col 1, 5, 9, ... step 4).

    Returns up to 33 dicts {label, col_qty, col_rev, col_profit, col_margin}.
    The all-time 'Итог' column (col 133) is outside the iterated range and any
    stray 'Итог'/blank label is skipped, so only real months remain.
    """
    header = rows[7]
    months: list[dict] = []
    for col in range(MONTH_COL_START, MONTH_COL_STOP, MONTH_STEP):
        label = header[col] if col < len(header) else None
        if not label or label == "Итог":
            continue
        months.append(
            {
                "label": label,
                "col_qty": col,
                "col_rev": col + 1,
                "col_profit": col + 2,
                "col_margin": col + 3,
            }
        )
    return months


def _num(value) -> float:
    """Coerce a cell to a float, treating blanks/None/non-numeric as 0.0."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def parse_prodazhi(path) -> pd.DataFrame:
    """Parse the продажи workbook into a per-EAN, per-month sales DataFrame.

    Columns: ean, month, qty, revenue_rub, profit_rub, margin_pct.
    Only EAN-rows are taken (normalize_ean is not None); a record is emitted only
    when qty or revenue is non-zero, keeping the frame compact (documented choice).
    """
    ws = pc.CalamineWorkbook.from_path(str(path)).get_sheet_by_name(SHEET)
    rows = list(ws.iter_rows())
    months = build_month_map(rows)

    records: list[dict] = []
    for row in rows[DATA_START:DATA_END]:
        ean = normalize_ean(row[0])
        if ean is None:
            continue  # name-row / sample / test-SKU / footer
        for m in months:
            qty = _num(row[m["col_qty"]])
            revenue = _num(row[m["col_rev"]])
            if qty == 0 and revenue == 0:
                continue  # keep frame compact — no all-zero month rows
            records.append(
                {
                    "ean": ean,
                    "month": m["label"],
                    "qty": qty,
                    "revenue_rub": revenue,
                    "profit_rub": _num(row[m["col_profit"]]),
                    "margin_pct": _num(row[m["col_margin"]]),
                }
            )

    df = pd.DataFrame(
        records,
        columns=["ean", "month", "qty", "revenue_rub", "profit_rub", "margin_pct"],
    )
    df["ean"] = df["ean"].astype("int64")
    return df


def main() -> None:
    path = pathlib.Path("все продажи с 2023 по 26июня2026.xlsx")
    df = parse_prodazhi(path)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    print(
        f"prodazhi.parquet: rows={len(df)} "
        f"eans={df['ean'].nunique()} months={df['month'].nunique()}"
    )


if __name__ == "__main__":
    main()
