"""Phase 4 — Seasonal index tests (RED placeholder until Plan 02 creates src/seasonality.py).

Collection does NOT fail before Plan 02 — pytest.importorskip handles the missing module.
All tests here are marked xfail/skip until Plan 02 delivers the implementation.

Verified oracle values (from live prodazhi.parquet, 2026-06-27):
  April (4): 1.516, March (3): 1.060, September (9): 1.623, October (10): 1.439
  January (1): 0.349  (expected low — TIMON line added mostly Jan 2025, few 2024 data)
  Summer avg (July+August): (1.211 + 0.328) / 2 = 0.770 -> used for order plan horizon
"""
from __future__ import annotations

import pytest

# Skip this entire module gracefully until Plan 02 creates src.seasonality.
# importorskip returns the module or raises Skipped at collection — no ImportError crash.
seasonality = pytest.importorskip(
    "src.seasonality",
    reason="src.seasonality not yet implemented (TODO: Plan 02)",
)


@pytest.mark.xfail(reason="TODO: Plan 02 — compute_global_seasonal_index not yet implemented", strict=False)
def test_global_index_peaks(season_map):
    """SEASON-01: Spring (Mar–May) and Autumn (Sep–Oct) peaks must be > 1; Jan < 1.

    Known deviation: November index is ~0.78 (< 1) due to sparse Nov 2023 data.
    Criterion verified for March, April, May and September, October only.
    """
    # Spring peaks
    assert season_map[3] > 1.0, f"March index should be > 1, got {season_map[3]:.3f}"
    assert season_map[4] > 1.0, f"April index should be > 1, got {season_map[4]:.3f}"
    assert season_map[5] > 1.0, f"May index should be > 1, got {season_map[5]:.3f}"
    # Autumn peaks
    assert season_map[9] > 1.0, f"September index should be > 1, got {season_map[9]:.3f}"
    assert season_map[10] > 1.0, f"October index should be > 1, got {season_map[10]:.3f}"
    # Low season
    assert season_map[1] < 1.0, f"January index should be < 1, got {season_map[1]:.3f}"
    # 12 months present
    assert set(season_map.keys()) == set(range(1, 13)), "Must have indices for all 12 calendar months"


@pytest.mark.xfail(reason="TODO: Plan 02 — seasonal index average not yet verifiable", strict=False)
def test_global_index_average_near_one(season_map):
    """Sum of 12 seasonal indices should be approximately 12 (average ≈ 1.0)."""
    total = sum(season_map.values())
    assert abs(total - 12.0) < 0.5, f"Sum of 12 indices should be ~12, got {total:.3f}"
