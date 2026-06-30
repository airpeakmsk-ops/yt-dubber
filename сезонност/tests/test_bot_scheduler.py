"""test_bot_scheduler.py — GREEN tests for BOT-04 (Plan 04).

Tests cover:
  - test_ping_time_utc    : setup_scheduler регистрирует job с CronTrigger mon 06:00 UTC
  - test_ping_targets_user: weekly_ping вызывает bot.send_message именно allowed_user_id
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# test_ping_time_utc
# ---------------------------------------------------------------------------

def test_ping_time_utc():
    """setup_scheduler регистрирует job: day_of_week=mon, hour=6, minute=0, timezone=UTC.

    Используем _start=False чтобы не требовать event loop при inspect (APScheduler 3.10.x
    вызывает asyncio.get_event_loop() в start() — в Python 3.14 нет auto-loop).
    """
    from bot.scheduler import setup_scheduler

    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    user_id = 188032358

    # _start=False — регистрируем job, но не запускаем планировщик (нет event loop в тесте)
    scheduler = setup_scheduler(fake_bot, user_id, _start=False)

    jobs = scheduler.get_jobs()
    assert len(jobs) >= 1, "Ожидался хотя бы один job в планировщике"

    job = jobs[0]
    trigger = job.trigger

    # Проверяем поля CronTrigger
    # APScheduler 3.x хранит fields в trigger.fields (список объектов с name+expressions)
    fields = {f.name: f for f in trigger.fields}

    # day_of_week = mon (0 или 'mon')
    dow_expr = str(fields["day_of_week"])
    assert "mon" in dow_expr or dow_expr.strip() == "0", (
        f"day_of_week должен быть 'mon'/0, получили: {dow_expr!r}"
    )

    # hour = 6
    hour_expr = str(fields["hour"])
    assert "6" in hour_expr, f"hour должен быть 6, получили: {hour_expr!r}"

    # minute = 0
    minute_expr = str(fields["minute"])
    assert "0" in minute_expr, f"minute должен быть 0, получили: {minute_expr!r}"

    # timezone = UTC
    tz = str(trigger.timezone)
    assert "utc" in tz.lower() or "UTC" in tz, (
        f"timezone должен быть UTC, получили: {tz!r}"
    )


# ---------------------------------------------------------------------------
# test_ping_targets_user
# ---------------------------------------------------------------------------

def test_ping_targets_user():
    """weekly_ping(bot, user_id) вызывает bot.send_message(user_id, ...) с текстом пинга."""
    from bot.scheduler import weekly_ping

    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    user_id = 188032358

    asyncio.run(weekly_ping(fake_bot, user_id))

    fake_bot.send_message.assert_called_once()
    call_args = fake_bot.send_message.call_args

    # Первый позиционный аргумент должен быть user_id
    if call_args.args:
        assert call_args.args[0] == user_id, (
            f"send_message должен быть вызван с user_id={user_id}, получили {call_args.args[0]}"
        )
    else:
        chat_id = call_args.kwargs.get("chat_id") or call_args.kwargs.get("user_id")
        assert chat_id == user_id, (
            f"send_message должен быть вызван с user_id={user_id}, kwargs={call_args.kwargs}"
        )

    # Сообщение содержит содержательный текст (не пустое)
    if call_args.args and len(call_args.args) >= 2:
        text = call_args.args[1]
    else:
        text = call_args.kwargs.get("text", "")
    assert len(str(text)) > 10, f"Текст пинга слишком короткий: {text!r}"
