"""bot/main.py — точка входа Telegram-бота складской аналитики.

Запуск:
    python -m bot.main

Собирает:
  - Bot (токен из load_config())
  - Dispatcher (MemoryStorage — FSM в памяти, бот одиночный)
  - Router из bot.handlers.files (document handler + callback)
  - AsyncIOScheduler из bot.scheduler (еженедельный пинг пн 06:00 UTC)
  - Logging → stdout (journald подхватит на VPS)

load_dotenv() вызывается в начале main() — подхватывает .env на VPS
(EnvironmentFile в systemd unit или .env рядом с проектом).
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]


async def main() -> None:
    """Инициализировать бота и запустить polling."""
    # Загрузить .env если есть (VPS: EnvironmentFile=/opt/bot/.env в unit-файле тоже работает)
    if load_dotenv is not None:
        load_dotenv()

    # Настроить логирование → stdout (journald на VPS, консоль при разработке)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Конфигурация (бросит RuntimeError если BOT_TOKEN не задан)
    from bot.config import load_config
    cfg = load_config()

    logger.info("Запуск бота, allowed_user_id=%d", cfg.allowed_user_id)

    # aiogram 3.x: Bot + Dispatcher
    bot = Bot(token=cfg.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Подключить роутер (document handler + FSM callbacks)
    from bot.handlers import files
    dp.include_router(files.router)

    # Запустить планировщик (еженедельный пинг пн 06:00 UTC)
    from bot.scheduler import setup_scheduler
    scheduler = setup_scheduler(bot, cfg.allowed_user_id)

    try:
        logger.info("Начинаю polling...")
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
