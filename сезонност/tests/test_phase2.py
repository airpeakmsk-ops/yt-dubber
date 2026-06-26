"""Phase 2 test suite — себестоимость USD (COST-01/02/03 + integration build).

Mirrors the Phase 1 conventions (tests/conftest.py, tests/test_phase1.py):
  - a module-level skipif guard for the integration tests, gated on
    data/interim/master.parquet (the Phase 1 artifact this phase reads), and
  - pytest.approx(..., abs=1e-6) for all float comparisons (never == on floats).

Oracle numbers come straight from the plan's verified_examples (real values pulled
from master.parquet) — they are NOT invented here.
"""
import pathlib

import pytest

# Phase 2 reads the Phase 1 master artifact; skip the integration tests until it exists.
_MASTER = pathlib.Path("data/interim/master.parquet")
_skip_no_master = pytest.mark.skipif(
    not _MASTER.exists(),
    reason="master.parquet not built — run Phase 1 first",
)


def test_cost_formula_manual():
    """COST-01: per-unit cost_usd = price_rub / rate_usd / 1.038 / 1.16 (locked formula)."""
    from src.compute_cost import cost_usd_per_unit

    assert cost_usd_per_unit(2.93, 103.79) == pytest.approx(0.023445, abs=1e-6)
    assert cost_usd_per_unit(2.77, 79.71) == pytest.approx(0.028861, abs=1e-6)
    assert cost_usd_per_unit(5.90, 96.00) == pytest.approx(0.051042, abs=1e-6)


def test_weighted_avg_by_qty():
    """COST-02: weighted average weighted by qty (units), NOT by count of партии."""
    from src.compute_cost import weighted_avg_cost

    partii = [
        {"price_rub": 2.93, "rate_usd": 103.79, "qty": 30},
        {"price_rub": 2.77, "rate_usd": 79.71, "qty": 60},
    ]
    assert weighted_avg_cost(partii) == pytest.approx(0.027056, abs=1e-6)

    # weight is qty, NOT count of партии — must differ from the naive mean of per-партия costs
    naive = (0.023445 + 0.028861) / 2  # 0.026153
    assert weighted_avg_cost(partii) != pytest.approx(naive, abs=1e-4)


@_skip_no_master
def test_rate_metadata_retained():
    """COST-03: each партия keeps rate_usd + rate_source; cost_usd added, not collapsed."""
    from src.compute_cost import enrich

    out = enrich()
    sample = out.iloc[0]["partii"][0]
    assert "rate_usd" in sample and isinstance(sample["rate_usd"], (int, float))
    assert sample["rate_source"] in ("filename", "cbr_api")
    assert "cost_usd" in sample  # per-партия cost added, metadata preserved


@_skip_no_master
def test_build_master_cost():
    """Integration: enrich() builds 1300 EAN with positive cost on every партия + per-EAN wavg."""
    from src.compute_cost import OUT_PATH, enrich

    out = enrich()
    assert len(out) == 1300
    # every партия got a positive cost_usd
    assert all(p["cost_usd"] > 0 for row in out["partii"] for p in row)
    # per-EAN weighted average present and positive
    assert (out["cost_usd_wavg"] > 0).all()
    # Phase 1 artifact untouched: master_cost.parquet is a DIFFERENT file
    assert OUT_PATH.name == "master_cost.parquet"
