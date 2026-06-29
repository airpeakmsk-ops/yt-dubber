"""Phase 4 — Availability-based metrics, bucket functions, and order-plan tests.

Covers VISUAL-01 (dsi_bucket), VISUAL-02 (green_item), VISUAL-04 (pct_bucket),
ORDER-01/02 (pct_sales, compute_order_qty), SEASON-02 (is_dead, is_stale),
VISUAL-03 (presort_by_dsi), and the oracle availability velocity/DSI
(EAN 4525807270297, months_in_stock=18).

Oracle (verified 2026-06-27):
  EAN 4525807270297: qty_sold_total=87, qty_stock=3, months_in_stock=18
  velocity = 87/18 = 4.833...
  DSI = 3 / (4.833.../30) = 18.6 days  -> red bucket (<30)
  Old Phase 3 DSI would be: 3 / (87/33/30) = 34.5 days -> yellow. Contract change matters.

Order oracle (locked CONTEXT C):
  pct_sales = 87/90 = 0.9667 (>= 0.60 -> eligible)
  avg_season_idx(Jul+Aug) = (1.211 + 0.328) / 2 = 0.7695
  K_zakaz = max(0, round(4.833*2*0.7695 - 3, 1)) = max(0, round(4.44, 1)) = 4.4
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from src.report_metrics import dsi_days, sht_per_month

# New Phase 4 bucket/flag functions — absent until Task 2 adds them.
# importorskip-style guard: skip entire module at collection if functions missing.
try:
    from src.report_metrics import dsi_bucket, green_item, pct_bucket
except ImportError:
    pytest.skip(
        "dsi_bucket/green_item/pct_bucket not yet in report_metrics (Task 2 RED)",
        allow_module_level=True,
    )

# order_plan functions — added in Task 1 (04-03).
try:
    from src.order_plan import (
        SELL_THROUGH_COL,
        compute_order_qty,
        is_dead,
        is_priority_eligible,
        is_stale,
        pct_sales,
        presort_by_dsi,
        sell_through_last_batch,
    )
    _ORDER_PLAN_AVAILABLE = True
except ImportError:
    _ORDER_PLAN_AVAILABLE = False

_skip_order = pytest.mark.skipif(
    not _ORDER_PLAN_AVAILABLE,
    reason="src.order_plan not yet implemented (Task 1/2 RED)",
)

ORACLE_EAN = 4525807270297
ORACLE_QTY_SOLD = 87
ORACLE_QTY_STOCK = 3
ORACLE_MONTHS = 18
ORACLE_VELOCITY = ORACLE_QTY_SOLD / ORACLE_MONTHS  # 4.8333...
ORACLE_DSI = round(ORACLE_QTY_STOCK / (ORACLE_VELOCITY / 30), 1)  # 18.6


# --- dsi_bucket ---------------------------------------------------------------
def test_dsi_bucket():
    """dsi_bucket: <30->0(red), 30-60->1(yellow), 60-90->2(green), >90->3(blue), ''/nan->4."""
    assert dsi_bucket(15) == 0,   "DSI 15 should be red (bucket 0)"
    assert dsi_bucket(29.9) == 0, "DSI 29.9 should be red (bucket 0)"
    assert dsi_bucket(30) == 1,   "DSI 30 should be yellow (bucket 1)"
    assert dsi_bucket(45) == 1,   "DSI 45 should be yellow (bucket 1)"
    assert dsi_bucket(60) == 2,   "DSI 60 should be green (bucket 2)"
    assert dsi_bucket(75) == 2,   "DSI 75 should be green (bucket 2)"
    assert dsi_bucket(90) == 3,   "DSI 90 should be blue (bucket 3)"
    assert dsi_bucket(120) == 3,  "DSI 120 should be blue (bucket 3)"
    assert dsi_bucket("") == 4,   "Empty string DSI should be bucket 4 (no stock)"
    assert dsi_bucket(float("nan")) == 4, "NaN DSI should be bucket 4"


# --- oracle availability velocity/DSI ----------------------------------------
def test_dsi_oracle_availability():
    """sht_per_month(87, 18) ≈ 4.833; dsi_days(3, 4.833) ≈ 18.6; bucket == red (0)."""
    velocity = sht_per_month(ORACLE_QTY_SOLD, ORACLE_MONTHS)
    assert velocity == pytest.approx(ORACLE_VELOCITY, abs=1e-6), (
        f"Expected velocity {ORACLE_VELOCITY:.4f}, got {velocity:.4f}"
    )
    dsi = dsi_days(ORACLE_QTY_STOCK, velocity)
    assert dsi == pytest.approx(ORACLE_DSI, abs=0.05), (
        f"Expected DSI {ORACLE_DSI}, got {dsi}"
    )
    # Must fall in red bucket (< 30 days)
    assert dsi_bucket(dsi) == 0, f"Oracle DSI {dsi} should be red (bucket 0), got {dsi_bucket(dsi)}"


# --- green_item ---------------------------------------------------------------
def test_green_item_flag():
    """green_item: velocity > 20 -> True; velocity <= 20 or '' -> False."""
    assert green_item(25) is True,   "velocity 25 > 20 should be green"
    assert green_item(20.1) is True, "velocity 20.1 > 20 should be green"
    assert green_item(20) is False,  "velocity exactly 20 should NOT be green (> 20, not >=)"
    assert green_item(0) is False,   "velocity 0 should not be green"
    assert green_item("") is False,  "empty string should not be green"


# --- pct_bucket ---------------------------------------------------------------
def test_pct_sales_bucket():
    """pct_bucket: 5-level scale; <0.20->0, 0.20-0.40->1, 0.40-0.60->2, 0.60-0.80->3, 0.80-1.0->4; ''->None."""
    assert pct_bucket(0.10) == 0, "10% should be bucket 0 (red)"
    assert pct_bucket(0.19) == 0, "19% should be bucket 0"
    assert pct_bucket(0.20) == 1, "20% should be bucket 1 (orange)"
    assert pct_bucket(0.30) == 1, "30% should be bucket 1"
    assert pct_bucket(0.40) == 2, "40% should be bucket 2 (yellow)"
    assert pct_bucket(0.50) == 2, "50% should be bucket 2"
    assert pct_bucket(0.60) == 3, "60% should be bucket 3 (blue)"
    assert pct_bucket(0.70) == 3, "70% should be bucket 3"
    assert pct_bucket(0.80) == 4, "80% should be bucket 4 (green)"
    assert pct_bucket(0.90) == 4, "90% should be bucket 4"
    assert pct_bucket("") is None,             "empty string should return None"
    assert pct_bucket(float("nan")) is None,   "NaN should return None"


# =============================================================================
# ORDER-01 / ORDER-02 — pct_sales + compute_order_qty (04-03 Task 1)
# =============================================================================

ORACLE_QTY_PRIKHOD = 90   # oracle EAN: 90 units received total
ORACLE_PCT_SALES = 87 / 90  # 0.9667 >= 0.60 -> eligible
ORACLE_AVG_IDX = (1.211 + 0.328) / 2  # avg(Jul=1.211, Aug=0.328) = 0.7695


@_skip_order
def test_pct_sales_calculation():
    """pct_sales(87, 90) ≈ 0.9667; pct_sales(x, 0) = '' (guard); pct_sales(x, nan) = ''."""
    result = pct_sales(87, 90)
    assert result == pytest.approx(87 / 90, abs=1e-6), f"Expected 0.9667, got {result}"

    # qty_prikhod == 0 -> sentinel ""
    assert pct_sales(10, 0) == "", "qty_prikhod=0 should return ''"

    # qty_prikhod NaN -> sentinel ""
    assert pct_sales(10, float("nan")) == "", "qty_prikhod=NaN should return ''"


@_skip_order
def test_order_eligibility():
    """compute_order_qty returns '' when pct_sales < 0.60 or pct=''."""
    # Below threshold
    assert compute_order_qty(5.0, 3, 0.59, 0.77) == "", (
        "pct_sales 0.59 < 0.60 should return ''"
    )
    # Exactly at boundary — 0.599... rounds differently; check 0.5999 < 0.60
    assert compute_order_qty(5.0, 3, 0.5999, 0.77) == "", (
        "pct_sales 0.5999 < 0.60 should return ''"
    )
    # Sentinel "" pct
    assert compute_order_qty(5.0, 3, "", 0.77) == "", (
        "pct='' sentinel should return ''"
    )


@_skip_order
def test_order_formula_oracle():
    """Oracle EAN 4525807270297: K_zakaz = max(0, round(4.833*2*0.7695 - 3, 1)) = 4.4."""
    result = compute_order_qty(
        velocity=ORACLE_VELOCITY,
        qty_stock=ORACLE_QTY_STOCK,
        pct=ORACLE_PCT_SALES,
        avg_season_idx=ORACLE_AVG_IDX,
    )
    assert result == pytest.approx(4.4, abs=0.1), (
        f"Oracle K_zakaz expected ~4.4, got {result}"
    )
    # Exactly at 60% threshold — should be eligible
    result_border = compute_order_qty(5.0, 0, 0.60, 1.0)
    assert result_border != "", "pct_sales exactly 0.60 should be eligible"


@_skip_order
def test_order_negative_stock():
    """qty_stock < 0 is treated as 0 in the formula (CONTEXT C, LOCKED detail)."""
    # With stock=0: raw = velocity*2*idx - 0 = 10*2*1.0 = 20.0
    result_zero = compute_order_qty(10.0, 0, 0.80, 1.0)
    # With stock=-5: must give same result as stock=0
    result_neg = compute_order_qty(10.0, -5, 0.80, 1.0)
    assert result_neg == result_zero, (
        f"Negative qty_stock should be treated as 0: got {result_neg} vs {result_zero}"
    )
    assert result_neg == pytest.approx(20.0, abs=0.05), (
        f"Expected 20.0 when stock treated as 0, got {result_neg}"
    )


# =============================================================================
# SEASON-02 — is_dead / is_stale flags (04-03 Task 2)
# =============================================================================

@_skip_order
def test_dead_stock_flag():
    """is_dead: stock>0 AND recent_12mo_sales==0 -> True; else False."""
    assert is_dead(5, 0) is True,  "stock=5, recent=0 -> dead"
    assert is_dead(0, 0) is False, "stock=0, recent=0 -> not dead (no stock to worry about)"
    assert is_dead(5, 3) is False, "stock=5, recent=3 -> not dead (has recent sales)"
    assert is_dead(float("nan"), 0) is False, "NaN stock -> not dead"
    assert is_dead(-1, 0) is False, "Negative stock -> not dead (no positive stock)"


@_skip_order
def test_stale_flag():
    """is_stale: recent>0 AND (DSI>90 OR age>180) -> True; recent==0 -> False (that's dead)."""
    # Stale by DSI > 90
    assert is_stale(120, 50, 3) is True,  "DSI=120>90, recent=3 -> stale"
    # Stale by age > 180
    assert is_stale(40, 200, 3) is True,  "age=200>180, recent=3 -> stale"
    # Both conditions true
    assert is_stale(120, 200, 3) is True, "DSI=120 AND age=200, recent=3 -> stale"
    # recent == 0 -> NOT stale (dead, not stale — mutually exclusive)
    assert is_stale(120, 200, 0) is False, "recent=0 -> not stale (dead category)"
    # Neither condition
    assert is_stale(40, 50, 3) is False,  "DSI=40, age=50, recent=3 -> not stale"
    # DSI sentinel "" with age < 180 -> not stale
    assert is_stale("", 50, 3) is False,  "DSI='', age=50, recent=3 -> not stale"


# =============================================================================
# VISUAL-03 — presort_by_dsi (04-03 Task 2)
# =============================================================================

@_skip_order
def test_presort_order():
    """presort_by_dsi: red bucket (DSI<30) first, secondary DSI ascending, '' last."""
    df = pd.DataFrame({
        "DSI, дней": [120, 15, "", 45],
        "name": ["blue", "red", "no_stock", "yellow"],
    })
    sorted_df = presort_by_dsi(df)
    names = sorted_df["name"].tolist()

    # First row must be the red item (DSI=15, bucket 0)
    assert names[0] == "red", f"Expected 'red' first (DSI=15), got {names[0]}"
    # Last row must be the sentinel '' item
    assert names[-1] == "no_stock", f"Expected 'no_stock' last (''), got {names[-1]}"
    # yellow (DSI=45, bucket 1) before blue (DSI=120, bucket 3)
    assert names.index("yellow") < names.index("blue"), (
        "yellow (bucket 1) should come before blue (bucket 3)"
    )
    # Index reset to 0..N-1
    assert list(sorted_df.index) == list(range(len(df))), "Index should be reset after sort"


@_skip_order
def test_presort_secondary_dsi_asc():
    """Within the same bucket, lower DSI comes first (secondary key ascending)."""
    df = pd.DataFrame({
        "DSI, дней": [25, 10, 20],  # all red (< 30)
        "name": ["r25", "r10", "r20"],
    })
    sorted_df = presort_by_dsi(df)
    names = sorted_df["name"].tolist()
    assert names == ["r10", "r20", "r25"], (
        f"Within red bucket, DSI should be ascending: got {names}"
    )


# ---------------------------------------------------------------------------
# Priority sell-through gate (70%, user 2026-06-29)
# ---------------------------------------------------------------------------

@_skip_order
def test_sell_through_last_batch():
    """Доля распродажи = (last_qty − остаток) / last_qty, кламп [0,1]."""
    assert sell_through_last_batch(100, 70) == pytest.approx(0.30)   # 30 из 100 ушло
    assert sell_through_last_batch(200, 50) == pytest.approx(0.75)   # 150 из 200 ушло
    assert sell_through_last_batch(100, 0) == pytest.approx(1.0)     # распродан -> 1.0
    assert sell_through_last_batch(100, -1) == pytest.approx(1.0)    # отриц. остаток -> 0 -> 1.0
    assert sell_through_last_batch(100, 150) == pytest.approx(0.0)   # остаток > партии -> кламп 0
    assert sell_through_last_batch(0, 5) == ""                       # нет данных о последней закупке
    assert sell_through_last_batch(None, 5) == ""


@_skip_order
def test_is_priority_eligible():
    """>= 70% распродажи последней партии = eligible (попадает в приоритет)."""
    assert is_priority_eligible(0.70) is True
    assert is_priority_eligible(0.95) is True
    assert is_priority_eligible(0.69) is False
    assert is_priority_eligible(0.0) is False
    assert is_priority_eligible("") is False        # нет данных -> не приоритет


@_skip_order
def test_presort_demotes_low_sellthrough():
    """Товар, распродавший < 70% последней партии, уходит ВНИЗ даже при малом DSI (красный)."""
    df = pd.DataFrame({
        "DSI, дней": [5, 100, 8],                       # urgent(red), blue, urgent(red)
        SELL_THROUGH_COL: [0.10, 0.90, 0.95],           # 1й — низкая распродажа
        "name": ["red_low_sellthru", "blue_ok", "red_ok"],
    })
    sorted_df = presort_by_dsi(df)
    names = sorted_df["name"].tolist()
    # eligible сначала (red_ok=8, blue_ok=100), потом демотированный red_low_sellthru
    assert names[0] == "red_ok", f"eligible red должен быть первым: {names}"
    assert names[-1] == "red_low_sellthru", (
        f"низкая распродажа последней партии -> вниз, даже при DSI=5: {names}"
    )
