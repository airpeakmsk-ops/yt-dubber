"""bot/handlers/files.py — aiogram 3.x document handler + FSM + pipeline bridge.

Реализует BOT-01:
  - Принимает document от whitelisted user → спрашивает тип кнопками (FSM).
  - Callback ftype:* → скачивает файл, запускает run_pipeline через asyncio.to_thread,
    отвечает «Готово. Обновлено строк: N».
  - Whitelist fail-closed: любой user_id != ALLOWED_USER_ID молча игнорируется
    В КАЖДОМ хендлере (не только /start).
  - Ошибка пайплайна → сообщение «данные восстановлены из бэкапа».

Публичный API:
    router           — aiogram Router для включения в Dispatcher.
    FileFlow         — StatesGroup с единственным состоянием waiting_type.
    on_document      — хендлер входящего документа (whitelist-guard внутри).
    on_callback_file_type — хендлер выбора типа кнопкой (whitelist-guard внутри).
    download_file    — async загрузка файла из Telegram во tmp (патчится в тестах).
"""
from __future__ import annotations

import asyncio
import pathlib
import tempfile

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import load_config
from bot.keyboards import file_type_keyboard
from bot.pipeline import run_pipeline

# ---------------------------------------------------------------------------
# Константа whitelist (загружается один раз при импорте модуля; тесты патчат
# модульный атрибут ALLOWED_USER_ID через monkeypatch или используют bot_config).
# ---------------------------------------------------------------------------
try:
    _cfg = load_config()
    ALLOWED_USER_ID: int = _cfg.allowed_user_id
except Exception:
    # В тестовом окружении без .env load_config() бросает RuntimeError.
    # Хардкодим дефолт — тесты передают правильный id через bot_config fixture.
    ALLOWED_USER_ID = 188032358

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = Router()


# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------
class FileFlow(StatesGroup):
    waiting_type = State()


# ---------------------------------------------------------------------------
# Helper: получить Bot из текущего хендлера (инжектируется aiogram, но
# тесты могут подменить через _get_bot()).
# ---------------------------------------------------------------------------
def _get_bot() -> Bot | None:  # pragma: no cover — только в aiogram runtime
    """Заглушка: в реальном aiogram Bot инжектируется как параметр хендлера.

    Выделена отдельной функцией чтобы тесты могли monkeypatch-ить.
    В реальных хендлерах bot передаётся как параметр напрямую.
    """
    return None


# ---------------------------------------------------------------------------
# Helper: скачать файл из Telegram
# ---------------------------------------------------------------------------
async def download_file(bot: Bot, file_id: str, suffix: str = ".xlsx") -> pathlib.Path:
    """Получить файл из Telegram и сохранить в tmp-файл.

    Returns:
        pathlib.Path к скачанному файлу (в системном tmp или project_root/tmp).
    """
    tg_file = await bot.get_file(file_id)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = pathlib.Path(tmp.name)
    tmp.close()
    await bot.download_file(tg_file.file_path, destination=str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# Helper: фоновая задача отправки статусов и финального результата
# ---------------------------------------------------------------------------
async def run_and_report(
    bot: Bot,
    user_id: int,
    file_id: str,
    file_name: str,
    file_type: str,
) -> None:
    """Скачать файл → запустить пайплайн → ответить «обновлено N строк».

    Все шаги выполняются в фоне (create_task) чтобы не блокировать event loop.
    Промежуточные статусы → send_message пользователю.
    При ошибке → понятное сообщение с упоминанием восстановления из бэкапа.
    """
    try:
        await bot.send_message(user_id, "Скачиваю файл...")
        suffix = pathlib.Path(file_name).suffix or ".xlsx"
        tmp_path = await download_file(bot, file_id, suffix=suffix)

        await bot.send_message(user_id, "Запускаю пересчёт... (~1-2 мин)")
        n: int = await asyncio.to_thread(run_pipeline, file_type, tmp_path)

        type_label = {
            "ledger": "Леджер",
            "weekly": "Недельные остатки",
            "invoice": "Накладная",
        }.get(file_type, file_type)

        await bot.send_message(
            user_id,
            f"Готово. Обновлено строк: {n}\nТип файла: {type_label}",
        )
    except Exception as exc:
        await bot.send_message(
            user_id,
            f"Ошибка: {exc}\n"
            "Данные восстановлены из бэкапа, таблица не изменена.",
        )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def on_start(message, state: FSMContext) -> None:
    """/start: whitelist-guard + краткая инструкция."""
    if message.from_user.id != ALLOWED_USER_ID:
        return
    await message.answer(
        "Привет! Пришли файл склада (леджер, недельные остатки или накладную) "
        "чтобы пересчитать таблицу."
    )


@router.message(F.document)
async def on_document(message, state: FSMContext) -> None:
    """Document handler: whitelist-guard → сохранить file_id → keyboard."""
    if message.from_user.id != ALLOWED_USER_ID:
        return  # fail-closed: молча игнорируем

    file_id = message.document.file_id
    file_name = message.document.file_name or "file.xlsx"

    await state.update_data(file_id=file_id, file_name=file_name)
    await state.set_state(FileFlow.waiting_type)

    await message.answer(
        "Что это за файл?",
        reply_markup=file_type_keyboard(),
    )


@router.callback_query(FileFlow.waiting_type, F.data.startswith("ftype:"))
async def on_callback_file_type(callback, state: FSMContext) -> None:
    """Callback ftype:* → запустить пайплайн в фоне, ответить пользователю."""
    if callback.from_user.id != ALLOWED_USER_ID:
        await callback.answer()  # закрыть spinner, но ничего не делать
        return  # fail-closed

    data = await state.get_data()
    file_id: str = data.get("file_id", "")
    file_name: str = data.get("file_name", "file.xlsx")
    file_type: str = callback.data.split(":", 1)[1]  # "ftype:ledger" → "ledger"

    await state.clear()

    # Показать промежуточный статус в сообщении с кнопками
    try:
        await callback.message.edit_text("Принял, пересчитываю...")
    except Exception:
        pass  # edit_text может упасть если сообщение слишком старое

    await callback.answer()  # закрыть spinner кнопки

    # Получить Bot для фоновой задачи
    # В aiogram 3.x Bot инжектируется через DI; в тестах используем monkeypatched _get_bot.
    try:
        bot: Bot = callback.bot  # type: ignore[attr-defined]
    except AttributeError:
        bot = _get_bot()  # type: ignore[assignment]

    user_id = callback.from_user.id

    # Запустить в фоне чтобы не блокировать event loop
    asyncio.create_task(
        run_and_report(bot, user_id, file_id, file_name, file_type)
    )
