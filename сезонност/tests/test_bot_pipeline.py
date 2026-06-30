"""test_bot_pipeline.py — Wave 0 stubs for BOT-02/03 (Plan 03).

Tests cover the pipeline orchestration layer — which steps run for each file type:
  - Леджер  → parse_ledger → build_master → compute_cost → report_to_sheets
  - Недельные остатки → только report_to_sheets (скорость по наличию)
  - Накладная → build_master → compute_cost → report_to_sheets

All tests are xfail until Plan 03 implements bot/pipeline.py with the step map
and subprocess/import orchestration.
"""
import pytest


@pytest.mark.xfail(
    reason="impl in Plan 03: ledger → parse_ledger→build_master→compute_cost→report",
    strict=False,
)
def test_ledger_steps(bot_config, tmp_path):
    """Леджер pipeline: все 4 шага вызываются в правильном порядке.

    Plan 03 will:
      - Mock parse_ledger.main, build_master.main, compute_cost.main,
        report_to_sheets.main (return 1300).
      - Call bot.pipeline.run_pipeline(ftype='ledger', file_path=..., config=...).
      - Assert all 4 mocks called exactly once, in order.
      - Assert return value is 1300 (N строк «Отчёт»).
    """
    pytest.xfail("not implemented until Plan 03")


@pytest.mark.xfail(
    reason="impl in Plan 03: weekly → только report",
    strict=False,
)
def test_weekly_steps(bot_config, tmp_path):
    """Недельные остатки pipeline: только report_to_sheets (пересборка отчёта).

    Plan 03 will:
      - Mock report_to_sheets.main only.
      - Call bot.pipeline.run_pipeline(ftype='weekly', ...).
      - Assert parse_ledger / build_master / compute_cost NOT called.
      - Assert report_to_sheets.main called once, return value forwarded.
    """
    pytest.xfail("not implemented until Plan 03")


@pytest.mark.xfail(
    reason="impl in Plan 03: invoice → build_master→compute_cost→report",
    strict=False,
)
def test_invoice_steps(bot_config, tmp_path):
    """Накладная pipeline: build_master → compute_cost → report_to_sheets.

    Plan 03 will:
      - Mock build_master.main, compute_cost.main, report_to_sheets.main.
      - Call bot.pipeline.run_pipeline(ftype='invoice', ...).
      - Assert parse_ledger NOT called (накладная не меняет леджер).
      - Assert build_master → compute_cost → report called in order.
    """
    pytest.xfail("not implemented until Plan 03")
