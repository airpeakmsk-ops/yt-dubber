"""test_bot_handlers.py — Wave 0 stubs for BOT-01 (Plan 04).

Tests cover the Telegram message handler layer:
  - Incoming document from whitelisted user triggers pipeline + replies «N строк».
  - Non-whitelisted user is silently ignored (no reply).

All tests are xfail until Plan 04 implements bot/handlers.py with the actual
aiogram router, mock Bot, and pipeline orchestration.
"""
import pytest


@pytest.mark.xfail(reason="impl in Plan 04: mock Bot+pipeline, ответ N строк", strict=False)
def test_document_received(bot_config):
    """Whitelisted user sends a document → bot processes it and replies with N rows.

    Plan 04 will:
      - Mock aiogram Bot + Message with document from allowed_user_id.
      - Mock report_to_sheets.main() to return 1300.
      - Assert bot replied «обновлено 1300 строк» (or similar).
    """
    pytest.xfail("not implemented until Plan 04")


@pytest.mark.xfail(reason="impl in Plan 04: чужой user_id молча игнорируется", strict=False)
def test_whitelist_reject(bot_config):
    """Non-whitelisted user sends a document → bot silently ignores (no reply sent).

    Plan 04 will:
      - Mock aiogram Bot + Message with document from a foreign user_id (e.g. 999999999).
      - Assert that bot.send_message / answer was NOT called.
    """
    pytest.xfail("not implemented until Plan 04")
