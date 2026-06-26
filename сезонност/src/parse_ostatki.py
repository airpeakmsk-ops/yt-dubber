"""parse_ostatki — free stock by EAN (DATA-03).

The остатки workbook (`остатки все 260626.xlsx`, sheet TDSheet) is an already-aggregated
'Анализ доступности': two columns (Номенклатура, Свободный остаток), NO per-warehouse
split. Each product occupies a name-row (col[0] str) then an EAN-row (col[0] float) then a
blank row; the free-stock value (col[1]) is the per-product Итог. We take only EAN-rows via
normalize_ean (drops samples 9999..., test SKUs, footer), carrying the most recent name-row
label so each product keeps its name.

Layout (verified 2026-06-26):
  rows 0-5 meta; row 6 header ('Номенклатура','Свободный остаток'); row 7 subheader;
  row 8 blank; data rows 9..2924 (name/EAN/blank pattern); row 2925 = 'Итог' (51893 total).
  ~959 unique EAN expected after exclusions.
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd
import python_calamine as pc

# Allow `python src/parse_ostatki.py` to run standalone (project root on path).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.normalize import normalize_ean

SHEET = "TDSheet"
DATA_START = 9  # first data row; rows 0-8 are meta/header/blank

OUTPUT_PATH = pathlib.Path("data/interim/ostatki.parquet")


def _stock(value) -> int:
    """Coerce a free-stock cell to an int (whole) or 0 for blank/non-numeric."""
    if value is None or value == "":
        return 0
    try:
        f = float(value)
    except (ValueError, TypeError):
        return 0
    return int(f) if f == int(f) else f  # keep fractional only if not whole


def parse_ostatki(path) -> pd.DataFrame:
    """Parse the остатки workbook into a per-EAN free-stock DataFrame.

    Columns: ean, name, qty_stock. Only EAN-rows are taken (normalize_ean not None);
    the most recent preceding name-row string is carried as `name`. The footer 'Итог'
    row and free-sample / test-SKU rows are excluded by normalize_ean.
    """
    ws = pc.CalamineWorkbook.from_path(str(path)).get_sheet_by_name(SHEET)
    rows = list(ws.iter_rows())

    records: list[dict] = []
    last_name: str | None = None
    for row in rows[DATA_START:]:
        cell0 = row[0] if len(row) else None
        ean = normalize_ean(cell0)
        if ean is None:
            # Track the most recent non-empty name-row label for the next EAN-row.
            if isinstance(cell0, str) and cell0.strip() and cell0.strip() != "Итог":
                last_name = cell0.strip()
            continue
        qty_stock = _stock(row[1] if len(row) > 1 else 0)
        records.append({"ean": ean, "name": last_name, "qty_stock": qty_stock})

    df = pd.DataFrame(records, columns=["ean", "name", "qty_stock"])
    df["ean"] = df["ean"].astype("int64")
    # Force a numeric dtype: _stock can yield int or float per-row, which would
    # otherwise leave the column as object. pd.to_numeric picks int64 when all
    # values are whole, float64 if any are fractional. No downcast — a small
    # int16 would be fragile if stock magnitudes grow. NOTE: qty_stock CAN be
    # negative (4 EANs here) — 1С free stock goes negative when reserved exceeds
    # physical on-hand; this is meaningful (urgent-reorder signal), keep as-is.
    df["qty_stock"] = pd.to_numeric(df["qty_stock"])
    return df


def main() -> None:
    path = pathlib.Path("остатки все 260626.xlsx")
    df = parse_ostatki(path)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    print(
        f"ostatki.parquet: eans={df['ean'].nunique()} "
        f"sum_stock={int(df['qty_stock'].sum())}"
    )


if __name__ == "__main__":
    main()
