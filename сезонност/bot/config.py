"""bot/config.py — конфигурация Telegram-бота складского аналитика.

Читает секреты из переменных окружения (через python-dotenv).
Импорт модуля НЕ падает при отсутствии env — load_config() бросает понятную
ошибку только при вызове. Нужно для pytest-коллекции без .env.

Секреты:
  BOT_TOKEN   : env-ключ «skladetbot_BOT_TOKEN» (значение в .env CLODYA и на VPS)
  CREDS_PATH  : env-ключ «GOOGLE_APPLICATION_CREDENTIALS» (путь к service-account JSON)

Whitelist:
  ALLOWED_USER_ID = 188032358 (Telegram ID владельца, из clodeer/digest_chat_id.txt)
  Переопределяется через env «ALLOWED_USER_ID» для тестов.
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

# python-dotenv — загрузить .env если присутствует; не бросать ошибку если нет.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv опционален при тестировании


@dataclass
class Config:
    """Конфигурация бота.

    Поля:
        bot_token        : Telegram Bot API token (skladetbot).
        allowed_user_id  : Единственный whitelisted Telegram user ID (188032358).
        project_root     : Корень проекта сезонност/ (кросс-платформенный Path).
        creds_path       : Путь к Google service-account JSON (из env на VPS).
    """

    bot_token: str
    allowed_user_id: int
    project_root: pathlib.Path
    creds_path: str


def load_config() -> Config:
    """Считать конфиг из окружения и вернуть Config.

    Raises:
        RuntimeError: если BOT_TOKEN не задан в окружении.
    """
    bot_token = os.environ.get("skladetbot_BOT_TOKEN", "")
    if not bot_token:
        raise RuntimeError(
            "BOT_TOKEN не задан: установите переменную окружения "
            "'skladetbot_BOT_TOKEN' (или добавьте в .env)."
        )

    allowed_user_id = int(os.environ.get("ALLOWED_USER_ID", "188032358"))

    # Корень проекта — родитель пакета bot/ (кросс-платформенно: работает на
    # Windows (разработка) и Linux VPS одновременно).
    project_root = pathlib.Path(__file__).resolve().parent.parent

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

    return Config(
        bot_token=bot_token,
        allowed_user_id=allowed_user_id,
        project_root=project_root,
        creds_path=creds_path,
    )
