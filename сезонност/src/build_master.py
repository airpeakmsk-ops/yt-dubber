"""build_master — единый EAN-ключ: join приходы + продажи + остатки (MATCH-01, MATCH-02).

приходы are the spine (unique EAN set, ~1300). продажи and остатки left-join onto the
spine on the exact int EAN key (all three sources already routed col[0] through the 01-01
normalize_ean contract, so the join is int==int — NO fuzzy, NO str(), which was the
RESEARCH pitfall of '.0' tails breaking the key).

master_df = one row per spine EAN with:
  - name              : first приход name for that EAN
  - qty_prikhod       : total received quantity across all партии
  - n_partii          : number of приход партии (rows) for that EAN
  - partii            : list of per-партия dicts (price_rub, qty, rate_usd, rate_source,
                        invoice_date, source_file) — kept intact so Phase 2 can compute the
                        weighted-average себестоимость; never collapsed away
  - qty_stock         : left-joined free stock (NaN if the EAN has no остаток row)
  - has_sales         : True if the EAN has any monthly-sales rows in prodazhi.parquet
                        (full monthly detail stays in prodazhi.parquet — master keeps the
                        link, not all 33 columns; Phase 3/4 read prodazhi.parquet directly)
  - qty_sold_total    : total units sold across all months (0.0 if no sales)

Sale / stock EANs with NO приход are NOT silently dropped — they are collected into the
unmatched report with a reason ('sale_without_prikhod' / 'stock_without_prikhod') so the
gap is auditable (MATCH-02).

Outputs (via main()):
  data/interim/master.parquet
  data/interim/unmatched_report.json
"""
from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd

# Allow `python src/build_master.py` to run standalone (project root on path).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

INTERIM = pathlib.Path("data/interim")
PRIKHODY_PATH = INTERIM / "prikhody.parquet"
PRODAZHI_PATH = INTERIM / "prodazhi.parquet"
OSTATKI_PATH = INTERIM / "ostatki.parquet"
MASTER_PATH = INTERIM / "master.parquet"
UNMATCHED_PATH = INTERIM / "unmatched_report.json"


def _aggregate_prikhody(pri: pd.DataFrame) -> pd.DataFrame:
    """Collapse приход rows to one row per EAN, retaining per-партия detail.

    Per-партия price/qty/rate is preserved in a `partii` list so Phase 2 can compute the
    weighted-average себестоимость; we do NOT collapse away the per-партия price.
    """
    partia_cols = [
        "price_rub",
        "qty",
        "rate_usd",
        "rate_source",
        "invoice_date",
        "source_file",
    ]

    rows: list[dict] = []
    for ean, grp in pri.groupby("ean", sort=False):
        partii = grp[partia_cols].to_dict("records")
        rows.append(
            {
                "ean": int(ean),
                "name": grp["name"].iloc[0],
                "qty_prikhod": float(grp["qty"].sum()),
                "n_partii": int(len(grp)),
                "partii": partii,
            }
        )
    return pd.DataFrame(rows)


def build_master() -> tuple[pd.DataFrame, dict]:
    """Join the three interim parquets into one EAN-keyed master + coverage report.

    Returns (master_df, report_dict). report_dict carries coverage_pct_sales,
    coverage_pct_stock, the in-spine counts and the unmatched EAN lists with reasons.
    """
    pri = pd.read_parquet(PRIKHODY_PATH)
    pro = pd.read_parquet(PRODAZHI_PATH)
    ost = pd.read_parquet(OSTATKI_PATH)

    spine = set(pri["ean"].unique())
    sale_eans = set(pro["ean"].unique())
    stock_eans = set(ost["ean"].unique())

    n_sales_in_spine = len(sale_eans & spine)
    n_stock_in_spine = len(stock_eans & spine)
    coverage_pct_sales = round(100.0 * n_sales_in_spine / len(sale_eans), 2)
    coverage_pct_stock = round(100.0 * n_stock_in_spine / len(stock_eans), 2)

    # --- master frame: приходы spine + left-joined остатки + sales link ---------
    master = _aggregate_prikhody(pri)

    # Left-join free stock (qty_stock NaN where an EAN has no остаток row).
    stock = ost[["ean", "qty_stock"]].drop_duplicates("ean")
    master = master.merge(stock, on="ean", how="left")

    # Sales link: a boolean flag + total units sold; monthly detail stays in
    # prodazhi.parquet (master keeps the link, not all 33 monthly columns).
    sales_agg = (
        pro.groupby("ean", as_index=False)["qty"].sum().rename(columns={"qty": "qty_sold_total"})
    )
    master = master.merge(sales_agg, on="ean", how="left")
    master["has_sales"] = master["ean"].isin(sale_eans)
    master["qty_sold_total"] = master["qty_sold_total"].fillna(0.0)

    # --- unmatched: sale/stock EANs with no приход (auditable, not dropped) ------
    sales_without_prikhod = [
        {"ean": int(e), "reason": "sale_without_prikhod"} for e in sorted(sale_eans - spine)
    ]
    stock_without_prikhod = [
        {"ean": int(e), "reason": "stock_without_prikhod"} for e in sorted(stock_eans - spine)
    ]

    report = {
        "n_spine_eans": len(spine),
        "n_sales_eans": len(sale_eans),
        "n_stock_eans": len(stock_eans),
        "n_sales_in_spine": n_sales_in_spine,
        "n_stock_in_spine": n_stock_in_spine,
        "coverage_pct_sales": coverage_pct_sales,
        "coverage_pct_stock": coverage_pct_stock,
        "sales_without_prikhod": sales_without_prikhod,
        "stock_without_prikhod": stock_without_prikhod,
    }
    return master, report


def main() -> None:
    master, report = build_master()
    INTERIM.mkdir(parents=True, exist_ok=True)

    master.to_parquet(MASTER_PATH, index=False)
    with open(UNMATCHED_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(
        "master.parquet: "
        f"spine_eans={report['n_spine_eans']} rows={len(master)} | "
        f"sales_cov={report['coverage_pct_sales']}% "
        f"({report['n_sales_in_spine']}/{report['n_sales_eans']}) | "
        f"stock_cov={report['coverage_pct_stock']}% "
        f"({report['n_stock_in_spine']}/{report['n_stock_eans']}) | "
        f"unmatched sales={len(report['sales_without_prikhod'])} "
        f"stock={len(report['stock_without_prikhod'])}"
    )


if __name__ == "__main__":
    main()
