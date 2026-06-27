"""build_report — assemble the single Phase 3 report DataFrame (OFFLINE, pure pandas).

Joins the Phase 2 spine (master_cost.parquet — all 1300 EAN, nothing lost) with the
long-format monthly sales (prodazhi.parquet). Produces, per товар:
  - base columns A..J (cost, приходы, остаток, продано, возраст, скорость, DSI)
  - «Накопит. приходы» / «Накопит. продажи» (REPORT-03 summary)
  - 33 monthly sales columns, chronological via month_sort_key (REPORT-02)
  - 33 «Кум. …» monthly cumulative sales columns (REPORT-03 manual-checkable)

NO network, NO gspread — Sheets writing lives in Plan 02. df_to_rows() converts the
DataFrame to a JSON-safe list[list] (dates → ISO str, NaN/NaT → "", numpy → py scalar)
so the eventual Sheets writer never sees a non-serializable cell (REPORT serializable).
"""
from __future__ import annotations

import math
import pathlib
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd

# Allow `python src/build_report.py` and pytest to import siblings cleanly.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.report_metrics import (  # noqa: E402
    N_MONTHS_DEFAULT,
    cumulative,
    dsi_days,
    month_sort_key,
    sht_per_month,
    stock_age_days,
)

INTERIM = pathlib.Path("data/interim")
MASTER_COST_PATH = INTERIM / "master_cost.parquet"
PRODAZHI_PATH = INTERIM / "prodazhi.parquet"

CUM_PREFIX = "Кум. "

# Base columns A..J (exact order, locked in column_layout).
BASE_COLS = [
    "EAN",
    "Наименование",
    "Себестоимость USD",
    "Кол-во приходов итого",
    "Число партий",
    "Остаток",
    "Продано всего",
    "Возраст остатка, дней",
    "Скорость, шт/мес",
    "DSI, дней",
]
CUM_SUMMARY_COLS = ["Накопит. приходы", "Накопит. продажи"]


def build_report_df(
    master_cost_path: pathlib.Path = MASTER_COST_PATH,
    prodazhi_path: pathlib.Path = PRODAZHI_PATH,
    n_months: int = N_MONTHS_DEFAULT,
) -> pd.DataFrame:
    """Build the report DataFrame: 1300 rows (all EAN spine) × ~78 columns.

    n_months (default 33) is the velocity / DSI base period (locked).
    """
    master = pd.read_parquet(master_cost_path)
    pro = pd.read_parquet(prodazhi_path)

    spine = master["ean"].tolist()  # stable order = master order (REPORT-01: nothing lost)

    # --- monthly pivot, chronologically ordered (Pitfall 1: never trust parquet order) ---
    month_order = sorted(pro["month"].unique(), key=month_sort_key)
    pivot = (
        pro.pivot_table(index="ean", columns="month", values="qty", aggfunc="sum")
        .reindex(columns=month_order)
        .reindex(index=spine)          # left-join onto spine; EAN w/o sales -> all-NaN row
        .fillna(0.0)
    )
    pivot.columns = list(month_order)  # drop the columns-name ("month")

    # --- monthly cumulative sales row (REPORT-03 manual-checkable on 2 oracle EAN) ---
    cum_pivot = cumulative(pivot)
    cum_pivot.columns = [CUM_PREFIX + m for m in month_order]

    # --- base columns A..J, computed per EAN in spine order ---
    base = pd.DataFrame(index=spine)
    base["EAN"] = master["ean"].values
    base["Наименование"] = master["name"].values
    base["Себестоимость USD"] = master["cost_usd_wavg"].values
    base["Кол-во приходов итого"] = master["qty_prikhod"].values
    base["Число партий"] = master["n_partii"].values
    base["Остаток"] = master["qty_stock"].values
    base["Продано всего"] = master["qty_sold_total"].values
    # Keep native python int (object dtype) — pandas would upcast a list to np.int64,
    # which violates the "no numpy" serializability contract (REPORT serializable).
    base["Возраст остатка, дней"] = pd.Series(
        [stock_age_days(p) for p in master["partii"]], index=spine, dtype=object
    )

    velocity = [sht_per_month(q, n_months) for q in master["qty_sold_total"]]
    base["Скорость, шт/мес"] = velocity
    base["DSI, дней"] = [
        dsi_days(stock, v) for stock, v in zip(master["qty_stock"], velocity)
    ]

    # --- cumulative summary columns ---
    base["Накопит. приходы"] = master["qty_prikhod"].values
    base["Накопит. продажи"] = master["qty_sold_total"].values

    # --- final assembly: base + summary + monthly + cum-monthly (locked column order) ---
    df = pd.concat([base, pivot, cum_pivot], axis=1)
    final_cols = BASE_COLS + CUM_SUMMARY_COLS + list(month_order) + list(cum_pivot.columns)
    df = df[final_cols].reset_index(drop=True)
    return df


def _to_cell(v):
    """Convert one DataFrame cell to a JSON / Sheets-safe scalar (Pitfall 4).

    date/datetime -> ISO str; NaN/NaT/None -> ""; numpy int/float -> py int/float;
    the DSI "" sentinel passes through unchanged.
    """
    if v is None:
        return ""
    if isinstance(v, (datetime,)):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    # NaT
    if v is pd.NaT:
        return ""
    # numpy scalars -> python scalars
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float):
        return "" if math.isnan(v) else v
    return v


def df_to_rows(df: pd.DataFrame) -> list[list]:
    """Serialize the report DataFrame to list[list]: header row + one row per товар.

    Guarantees no cell is a date/NaN/NaT/numpy type (safe for gspread in Plan 02).
    """
    rows: list[list] = [df.columns.tolist()]
    for record in df.itertuples(index=False, name=None):
        rows.append([_to_cell(v) for v in record])
    return rows


def main() -> None:
    df = build_report_df()
    print(f"report shape: {df.shape}")
    for ean in (4525807270297, 4525807270280):
        row = df[df["EAN"] == ean]
        if not row.empty:
            r = row.iloc[0]
            print(
                f"  EAN {ean}: продано={r['Продано всего']} остаток={r['Остаток']} "
                f"скорость={r['Скорость, шт/мес']:.3f} DSI={r['DSI, дней']} "
                f"возраст={r['Возраст остатка, дней']} накоп.прод={r['Накопит. продажи']}"
            )


if __name__ == "__main__":
    main()
