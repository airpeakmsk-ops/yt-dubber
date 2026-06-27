"""Phase 4 — Weekly stock parser tests (RED until Task 2 creates the module).

Verifies:
  - parse_weekly_stock covers 1300/1300 master EAN (100% coverage).
  - Oracle EAN 4525807270297 has months_in_stock == 18.
  - Sample EAN 9999999999999 is absent from the result.

Data oracle verified 2026-06-27 against live остатки по неделям.xlsx.
"""
from __future__ import annotations

import pytest

ORACLE_EAN = 4525807270297
SAMPLE_EAN = 9999999999999
EXPECTED_MASTER_COUNT = 1300
ORACLE_MONTHS = 18


def test_weekly_coverage(weekly_months_map, master_cost_path):
    """parse_weekly_stock must cover all 1300 master EAN (intersection == 1300)."""
    import pandas as pd

    master = pd.read_parquet(master_cost_path)
    master_eans = set(master["ean"].astype(int))

    result_eans = set(weekly_months_map.keys())

    # Sample EAN must not appear
    assert SAMPLE_EAN not in result_eans, "Sample EAN 9999999999999 must be excluded"

    # Intersection with master spine must cover 100% (1300/1300)
    intersection = master_eans & result_eans
    assert len(intersection) == EXPECTED_MASTER_COUNT, (
        f"Expected {EXPECTED_MASTER_COUNT} EAN covered, got {len(intersection)}. "
        f"Missing from weekly: {len(master_eans - result_eans)}"
    )


def test_oracle_months(weekly_months_map):
    """Oracle EAN 4525807270297 must have exactly 18 months with stock > 0."""
    assert ORACLE_EAN in weekly_months_map, (
        f"Oracle EAN {ORACLE_EAN} not found in weekly_months_map"
    )
    months_set = weekly_months_map[ORACLE_EAN]
    assert len(months_set) == ORACLE_MONTHS, (
        f"Oracle EAN {ORACLE_EAN}: expected {ORACLE_MONTHS} months in stock, "
        f"got {len(months_set)}. Months: {sorted(months_set)}"
    )
