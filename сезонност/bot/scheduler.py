"""bot/scheduler.py — еженедельный пинг-планировщик (BOT-04).

setup_scheduler(bot, user_id) -> AsyncIOScheduler:
  Регистрирует еженедельный job «weekly_ping» на понедельник 06:00 UTC (= 09:00 МСК).
  Запускает планировщик и возвращает его (для shutdown в тестах).

weekly_ping(bot, user_id):
  Async coroutine — отправляет текстовое напоминание единственному пользователю.
  НЕ является авто-перезапуском пайплайна (BOT-04 CONTEXT LOCKED: только текст-пинг).

Зависимости:
  APScheduler 3.10.4 (apscheduler>=3.10 — установлен на VPS и локально).
  asyncio event loop должен быть запущен (вызывается из bot/main.py).
"""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


async def weekly_ping(bot, user_id: int) -> None:
    """Отправить текстовое напоминание о присылке леджера.

    Вызывается планировщиком каждый понедельник 06:00 UTC (= 09:00 МСК).
    Только текст — НЕ авто-запускает пайплайн (BOT-04 CONTEXT LOCKED).

    Args:
        bot      : aiogram.Bot instance (инжектируется APScheduler через args=[bot, user_id]).
        user_id  : Telegram ID получателя (единственный whitelisted пользователь, 188032358).
    """
    await bot.send_message(
        user_id,
        "Пора прислать свежий леджер для пересчёта таблицы.",
    )


def setup_scheduler(bot, user_id: int, *, _start: bool = True) -> AsyncIOScheduler:
    """Создать, настроить и (опционально) запустить AsyncIOScheduler с еженедельным пингом.

    Args:
        bot     : aiogram.Bot instance.
        user_id : Telegram ID пользователя для пинга.
        _start  : Запускать ли планировщик сразу (False в тестах — нет event loop).

    Returns:
        AsyncIOScheduler с зарегистрированным job (запущенный если _start=True).

    Job trigger: CronTrigger(day_of_week="mon", hour=6, minute=0, timezone="UTC")
    Это 09:00 МСК (UTC+3) — рабочее начало понедельника.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        weekly_ping,
        CronTrigger(day_of_week="mon", hour=6, minute=0, timezone="UTC"),
        args=[bot, user_id],
        id="weekly_ping",
        name="Weekly ledger reminder",
        replace_existing=True,
    )
    if _start:
        scheduler.start()
    return scheduler
