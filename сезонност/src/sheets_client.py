"""sheets_client — тонкий безопасный слой авторизации и идемпотентной записи в Google Sheets.

Единственный модуль Phase 3, который касается сети. Все правила безопасности и
идемпотентности сосредоточены здесь, чтобы остальной код оставался офлайн и тестируемым.

SECURITY (BLOCKING):
  - Ключ сервис-аккаунта НИКОГДА не хранится в репозитории и не хардкодится в коде.
  - Путь к JSON-ключу читается из переменной окружения GOOGLE_APPLICATION_CREDENTIALS,
    с fallback на существующий абсолютный путь sibling-проекта (вне репо сезонност).
  - .gitignore блокирует любой *.json/.env, случайно скопированный в проект.

ИДЕМПОТЕНТНОСТЬ (LOCKED):
  - write_report делает ws.clear() затем ОДИН ws.update(rows) — лист НЕ пересоздаётся
    (sheetId сохраняется для Phase 4). Повторный прогон не дублирует данные.
  - gspread 6.1.4: сигнатура update(values, ...) — values первым позиционным.

TEST-SAFETY:
  - Юнит-тест мокает gspread полностью; реальный write в прод-Sheet выполняется
    один раз вручную после предоставления Editor-доступа, НЕ в pytest.
"""
from __future__ import annotations

import os
import pathlib
import sys

import gspread
from google.oauth2.service_account import Credentials

# Allow `python src/sheets_client.py` to run standalone (project root on path).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Те же scopes, что и в проверенном sales-bot (тот же сервис-аккаунт + Sheet).
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Fallback-путь к ключу — существующий sibling-проект ВНЕ репо сезонност.
# Ключ сюда НЕ копируется; это лишь местоположение уже существующего файла.
_DEFAULT_CREDS_PATH = "C:/Users/abirv/Desktop/CLODYA/market_scout/google_credentials.json"


def _resolve_creds_path() -> str:
    """Вернуть путь к JSON-ключу: env GOOGLE_APPLICATION_CREDENTIALS, иначе дефолт.

    НИКОГДА не читает ключ из репо сезонност и не хардкодит его содержимое —
    только путь к файлу, лежащему вне версионного контроля.
    """
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or _DEFAULT_CREDS_PATH
    if not os.path.exists(path):
        raise RuntimeError(
            "Не найден JSON-ключ сервис-аккаунта. Укажите путь в переменной окружения "
            "GOOGLE_APPLICATION_CREDENTIALS, например:\n"
            '  set GOOGLE_APPLICATION_CREDENTIALS=C:/path/to/key.json\n'
            f"(проверенный путь по умолчанию: {_DEFAULT_CREDS_PATH} — отсутствует)."
        )
    return path


def get_client(creds_path: str | None = None) -> gspread.Client:
    """Авторизовать gspread-клиент по сервис-аккаунту (creds из env/fallback-пути)."""
    creds = Credentials.from_service_account_file(
        creds_path or _resolve_creds_path(), scopes=SCOPES
    )
    return gspread.authorize(creds)


def write_report(spreadsheet, title: str, rows: list[list]) -> int:
    """Идемпотентно записать rows в лист `title`: clear() затем ОДИН update().

    Лист не пересоздаётся (sheetId стабилен для Phase 4). Если листа нет — создаётся
    один раз с запасом по размеру. Возвращает число строк ДАННЫХ (без заголовка).
    """
    try:
        ws = spreadsheet.worksheet(title)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title=title, rows=len(rows) + 10, cols=len(rows[0]) + 5
        )
    # ОДИН batch-write всех строк (≈100k ячеек, 1 API call, в квоте).
    ws.update(rows, value_input_option="USER_ENTERED")
    return len(rows) - 1  # строки данных, минус заголовок
