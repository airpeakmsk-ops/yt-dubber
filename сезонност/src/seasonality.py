"""seasonality — compute seasonal indices from historical sales data.

Seasonal index formula (LOCKED, Phase 04-CONTEXT.md § B):
  index[cal_month] = avg_sales_of_that_cal_month_across_years / overall_monthly_avg
  12 indices average ≈ 1.0 (normalised).

Incomplete years: average over AVAILABLE years per calendar month
  (Jul–Sep have 2 years of data, others have 3).

Source: data/interim/prodazhi.parquet (long format: ean × month × qty).
Month parsing: report_metrics.month_sort_key / RU_MONTHS (single source of truth).

Per-model index (TIMON справочник):
  model_aliases.json (76 canonical models) + timon_normalize.match_models().
  ⛔ NO ad-hoc regex normalisation — use match_models() only.
  match_models() RETURNS A LIST — take [0] or None if empty.
  Threshold: ≥ 30 total sales AND ≥ 6 calendar months with sales → own index.
  Otherwise: global fallback.
  Unrecognised items (hooks/rods/clasps → match_models returns []) → global.

Output contract for order_plan (04-03):
  compute_global_seasonal_index returns dict[int 1..12, float]
  (same shape as model-level indices and season_index_for_ean result).

avg_next2_index(season_map, months=(7, 8)) → float
  helper for ORDER-02 formula: average index for July + August 2026.
  RUN_DATE 2026-06-27 → next 2 months are 7, 8.
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd

# sys.path bootstrap — allow `python src/seasonality.py`, pytest, and -m invocation.
_SRC_DIR = pathlib.Path(__file__).resolve().parent
_PROJECT_ROOT = _SRC_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Add TIMON shared normaliser to path (for match_models).
_TIMON_SHARED = pathlib.Path("C:/Users/abirv/.claude/shared/timon")
if str(_TIMON_SHARED) not in sys.path:
    sys.path.insert(0, str(_TIMON_SHARED))

from src.report_metrics import RU_MONTHS, month_sort_key  # noqa: E402

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _parse_cal_month(label: str) -> tuple[int, int]:
    """Parse «Октябрь 2023 г.» → (2023, 10) using the canonical RU_MONTHS dict."""
    return month_sort_key(label)


def compute_global_seasonal_index(prodazhi_df: pd.DataFrame) -> dict[int, float]:
    """Compute 12 normalised seasonal indices from long-format sales history.

    Algorithm (Pattern 3, RESEARCH.md):
      1. Parse month label → (year, cal_month_num).
      2. groupby(year, cal_month_num)['qty'].sum()  — total sales per (year, month).
      3. groupby(cal_month_num).mean()              — avg across available years.
      4. Divide each by the grand average of those 12 values → index ≈ 1.0 each.

    Fills missing calendar months with 0.0 (guard for data gaps, not expected on
    real data — all 12 months present in prodazhi.parquet).

    Args:
        prodazhi_df: DataFrame with columns 'month' (str «Месяц YYYY г.»), 'qty' (float).

    Returns:
        dict[int, float] — {1: idx_jan, 2: idx_feb, ..., 12: idx_dec}, avg ≈ 1.0.
    """
    df = prodazhi_df.copy()

    # Parse month label into (year, cal_month_num) components.
    df["_ym"] = df["month"].map(_parse_cal_month)
    df["_year"] = df["_ym"].map(lambda x: x[0])
    df["_cal_month"] = df["_ym"].map(lambda x: x[1])

    # Step 1: sum qty per (year, calendar month).
    ym_totals = df.groupby(["_year", "_cal_month"])["qty"].sum()

    # Step 2: average across available years for each calendar month.
    avg_per_month: pd.Series = ym_totals.groupby(level="_cal_month").mean()

    # Step 3: normalise so the 12 indices average ≈ 1.0.
    global_avg = avg_per_month.mean()

    result: dict[int, float] = {}
    for m in range(1, 13):
        if m in avg_per_month.index:
            result[m] = avg_per_month[m] / global_avg
        else:
            result[m] = 0.0  # data gap guard (not expected in practice)

    return result


def avg_next2_index(
    season_map: dict[int, float],
    months: tuple[int, int] = (7, 8),
) -> float:
    """Average seasonal index for the next 2 calendar months (ORDER-02 multiplier).

    Default: months=(7, 8) = July + August 2026, because RUN_DATE = 2026-06-27.

    Args:
        season_map: dict[cal_month 1..12, float] from compute_global_seasonal_index.
        months: tuple of 2 integer calendar month numbers.

    Returns:
        float — mean index used in «К заказу = velocity*2*avg_idx − stock».
    """
    return sum(season_map[m] for m in months) / len(months)


# ---------------------------------------------------------------------------
# Per-model seasonal index (TIMON справочник)
# ---------------------------------------------------------------------------

def extract_model(name: str) -> str | None:
    """Extract the canonical TIMON model name from a 1С item name string.

    Uses match_models() from timon_normalize (TIMON справочник, 76 models).
    ⛔ DO NOT reimplement regex normalisation here — match_models is the authority.

    Returns:
        str (canonical model) if recognised, None otherwise (hooks/rods/clasps → None).
    """
    try:
        from timon_normalize import match_models
    except ImportError:
        return None

    models = match_models(name)
    return models[0] if models else None


def compute_model_seasonal_index(
    prodazhi_df: pd.DataFrame,
    master_df: pd.DataFrame,
    min_qty: int = 30,
    min_months: int = 6,
) -> dict[str, dict[int, float]]:
    """Compute per-model seasonal indices for models with sufficient sales history.

    Threshold (Claude's Discretion, RESEARCH.md):
      Model qualifies for its own index if:
        - total sales (qty sum across all its EANs) >= min_qty (default 30)
        - AND number of distinct calendar months with any sales >= min_months (default 6)
      Below threshold → use global fallback (caller's responsibility via season_index_for_ean).

    Algorithm per qualifying model:
      Same as compute_global_seasonal_index but scoped to EANs of that model.

    Args:
        prodazhi_df: long-format sales DataFrame (ean, month, qty).
        master_df: DataFrame with columns 'ean' and 'name' (1С item names for match_models).
        min_qty: minimum total sales units for model to get own index.
        min_months: minimum distinct months with sales for model to get own index.

    Returns:
        dict[str model_name, dict[int 1..12, float]] — only for qualifying models.
        Empty dict if no model meets the threshold.
    """
    # Build EAN → canonical model mapping.
    ean_to_model: dict[int, str] = {}
    for _, row in master_df.iterrows():
        model = extract_model(str(row.get("name", "")))
        if model is not None:
            ean_to_model[int(row["ean"])] = model

    if not ean_to_model:
        return {}

    # Attach model column to prodazhi.
    df = prodazhi_df.copy()
    df["_model"] = df["ean"].map(ean_to_model)
    df_model = df.dropna(subset=["_model"])

    if df_model.empty:
        return {}

    # Parse month into year + cal_month components.
    df_model = df_model.copy()
    df_model["_ym"] = df_model["month"].map(_parse_cal_month)
    df_model["_year"] = df_model["_ym"].map(lambda x: x[0])
    df_model["_cal_month"] = df_model["_ym"].map(lambda x: x[1])

    result: dict[str, dict[int, float]] = {}

    for model, grp in df_model.groupby("_model"):
        total_qty = grp["qty"].sum()
        n_months_with_sales = grp["_cal_month"].nunique()

        # Threshold check — both conditions must pass.
        if total_qty < min_qty or n_months_with_sales < min_months:
            continue  # below threshold → global fallback

        # Compute index for this model using the same algorithm as global.
        ym_totals = grp.groupby(["_year", "_cal_month"])["qty"].sum()
        avg_per_month = ym_totals.groupby(level="_cal_month").mean()
        global_avg = avg_per_month.mean()

        if global_avg == 0:
            continue  # degenerate case, skip

        model_idx: dict[int, float] = {}
        for m in range(1, 13):
            if m in avg_per_month.index:
                model_idx[m] = avg_per_month[m] / global_avg
            else:
                model_idx[m] = 0.0  # month with no sales for this model

        result[model] = model_idx

    return result


def season_index_for_ean(
    ean: int,
    name: str,
    model_index_map: dict[str, dict[int, float]],
    global_index: dict[int, float],
) -> dict[int, float]:
    """Return the appropriate seasonal index dict for a given EAN.

    Logic:
      1. Extract canonical model from item name via match_models.
      2. If model recognised AND has an entry in model_index_map → return that.
      3. Otherwise (unrecognised item or model below threshold) → return global_index.

    Args:
        ean: integer EAN (unused in lookup, kept for interface symmetry / logging).
        name: 1С item name string (fed to extract_model → match_models).
        model_index_map: result of compute_model_seasonal_index.
        global_index: result of compute_global_seasonal_index (fallback).

    Returns:
        dict[int 1..12, float] — either model-specific or global index.
    """
    model = extract_model(name)
    if model is not None and model in model_index_map:
        return model_index_map[model]
    return global_index
