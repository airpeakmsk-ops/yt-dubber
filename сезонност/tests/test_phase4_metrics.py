"""Phase 4 — Availability-based metrics and bucket function tests (RED until Task 2).

Covers VISUAL-01 (dsi_bucket), VISUAL-02 (green_item), VISUAL-04 (pct_bucket),
and the oracle availability velocity/DSI (EAN 4525807270297, months_in_stock=18).

Oracle (verified 2026-06-27):
  EAN 4525807270297: qty_sold_total=87, qty_stock=3, months_in_stock=18
  velocity = 87/18 = 4.833...
  DSI = 3 / (4.833.../30) = 18.6 days  -> red bucket (<30)
  Old Phase 3 DSI would be: 3 / (87/33/30) = 34.5 days -> yellow. Contract change matters.
"""
from __future__ import annotations

import math

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
