"""test_bot_scheduler.py — Wave 0 stub for BOT-04 (Plan 04).

Tests cover the weekly ping scheduler:
  - A scheduled job is registered at 06:00 UTC (= 09:00 MSK, Monday).

xfail until Plan 04 implements bot/scheduler.py with APScheduler (or aiogram
scheduler) registration and the actual ping job sending the reminder text.
"""
import pytest


@pytest.mark.xfail(
    reason="impl in Plan 04: job зарегистрирован hour=6 UTC = 09:00 MSK",
    strict=False,
)
def test_ping_time_utc(bot_config):
    """Weekly ping job is registered at Monday 06:00 UTC (09:00 MSK).

    Plan 04 will:
      - Import bot.scheduler and call setup_scheduler(config=bot_config).
      - Inspect registered jobs (APScheduler / aiogram-scheduler).
      - Assert exactly one job exists targeting the ping handler.
      - Assert job trigger: day_of_week='mon', hour=6, minute=0 (UTC).
      - Assert job sends text reminder to bot_config.allowed_user_id.
    """
    pytest.xfail("not implemented until Plan 04")
