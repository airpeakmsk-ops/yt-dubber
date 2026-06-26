"""compute_cost — себестоимость USD per приход + qty-weighted average per EAN (COST-01/02/03).

Reads the Phase 1 master.parquet (INPUT ONLY — no CBR API call, no import of cbr_rates:
the rate was already frozen in Phase 1 and lives as `rate_usd`/`rate_source` inside every
партия). Enriches each партия with a per-unit `cost_usd` and adds a per-EAN qty-weighted
average `cost_usd_wavg`, then writes a NEW artifact master_cost.parquet — Phase 1's
master.parquet is left untouched (reversible).

Formula (LOCKED, verified with user):
    cost_usd = price_rub / rate_usd / 1.038 / 1.16
`price_rub` is a PER-UNIT ruble price — divide directly, never touch qty in the per-unit calc.

Weighted average (COST-02) weights by qty (UNITS), NOT by the number of партии:
    cost_usd_wavg = Σ(cost_usd_i × qty_i) / Σ(qty_i)

Coefficients live in ONE place (COEF_LOGISTICS / COEF_MARKUP) — never inlined elsewhere.

Outputs (via main()):
  data/interim/master_cost.parquet
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd

# Allow `python src/compute_cost.py` to run standalone (project root on path).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# --- LOCKED coefficients (single source of truth — never inline 1.038 / 1.16 elsewhere) ---
COEF_LOGISTICS = 1.038  # LOCKED, verified with user
COEF_MARKUP = 1.16      # LOCKED, verified with user

INTERIM = pathlib.Path("data/interim")
MASTER_PATH = INTERIM / "master.parquet"
OUT_PATH = INTERIM / "master_cost.parquet"


def cost_usd_per_unit(price_rub: float, rate_usd: float) -> float:
    """Per-unit USD cost: price_rub / rate_usd / 1.038 / 1.16 (COST-01, locked formula).

    price_rub is a PER-UNIT ruble price — divide directly, never multiply/divide by qty.
    """
    return price_rub / rate_usd / COEF_LOGISTICS / COEF_MARKUP


def weighted_avg_cost(partii: list[dict]) -> float:
    """Per-EAN qty-weighted average cost (COST-02).

    Σ(cost_usd_i × qty_i) / Σ(qty_i); weight = qty (units), NOT len(partii).
    den > 0 guaranteed — no qty==0 anywhere in the data.
    """
    num = sum(cost_usd_per_unit(p["price_rub"], p["rate_usd"]) * p["qty"] for p in partii)
    den = sum(p["qty"] for p in partii)
    return num / den


def enrich(master_path: pathlib.Path = MASTER_PATH, out_path: pathlib.Path = OUT_PATH) -> pd.DataFrame:
    """Read master.parquet, add per-партия cost_usd + per-EAN cost_usd_wavg, write a NEW file.

    INPUT ONLY on master.parquet (no CBR call, no cbr_rates import). Each партия keeps its
    rate_usd / rate_source / invoice_date / source_file (COST-03 — never collapsed); only a
    per-unit cost_usd is appended. master.parquet is not mutated — output is a new artifact.
    """
    master = pd.read_parquet(master_path)

    enriched_partii: list[list[dict]] = []
    wavg: list[float] = []
    for partii in master["partii"]:
        new_partii: list[dict] = []
        for p in partii:
            row = dict(p)  # preserve all metadata (rate_usd, rate_source, invoice_date, source_file)
            row["cost_usd"] = round(cost_usd_per_unit(p["price_rub"], p["rate_usd"]), 6)
            new_partii.append(row)
        enriched_partii.append(new_partii)
        wavg.append(round(weighted_avg_cost(partii), 6))

    out = master.copy()
    out["partii"] = enriched_partii
    out["cost_usd_wavg"] = wavg

    INTERIM.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False, engine="pyarrow")
    return out


def main() -> None:
    out = enrich()
    print(
        f"master_cost.parquet: rows={len(out)} "
        f"partii_enriched={sum(len(p) for p in out['partii'])}"
    )


if __name__ == "__main__":
    main()
