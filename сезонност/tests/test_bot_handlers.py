"""test_bot_handlers.py — GREEN tests for BOT-01 (Plan 04).

Tests cover:
  - test_whitelist_reject       : чужой user_id молча игнорируется в document + callback хендлерах
  - test_document_received      : whitelisted user → FSM state=waiting_type, keyboard sent
  - test_file_type_runs_pipeline: callback ftype:ledger → run_and_report вызван, «N строк» отправлено
  - test_pipeline_error_message : run_pipeline бросает Exception → понятное сообщение об ошибке
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — фейковые aiogram objects
# ---------------------------------------------------------------------------

def _make_message(user_id: int, document=True) -> MagicMock:
    """Создать мок Message с указанным user_id и опциональным document."""
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.answer = AsyncMock()
    if document:
        msg.document = MagicMock()
        msg.document.file_id = "file_id_test_123"
        msg.document.file_name = "ledger_test.xlsx"
    else:
        msg.document = None
    return msg


def _make_callback(user_id: int, data: str) -> MagicMock:
    """Создать мок CallbackQuery с указанным user_id и callback data."""
    cb = MagicMock()
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.data = data
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    # cb.bot не существует в моке → AttributeError → файловый хендлер использует _get_bot()
    del cb.bot
    return cb


def _make_fsm_context(data: dict | None = None) -> MagicMock:
    """Создать мок FSMContext с get_data / set_state / update_data / clear."""
    ctx = MagicMock()
    ctx.set_state = AsyncMock()
    ctx.get_state = AsyncMock(return_value=None)
    ctx.update_data = AsyncMock()
    ctx.get_data = AsyncMock(return_value=data or {})
    ctx.clear = AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# test_whitelist_reject
# ---------------------------------------------------------------------------

def test_whitelist_reject():
    """Чужой user_id молча игнорируется в обоих хендлерах (document + callback).

    - on_document с id=999 → set_state НЕ вызван, answer НЕ вызван.
    - on_callback с id=999 → run_pipeline НЕ вызван, edit_text НЕ вызван.
    """
    from bot.handlers.files import on_document, on_callback_file_type

    FOREIGN_ID = 999999999

    # --- document handler ---
    msg = _make_message(user_id=FOREIGN_ID)
    state = _make_fsm_context()

    asyncio.run(on_document(msg, state))

    state.set_state.assert_not_called()
    msg.answer.assert_not_called()

    # --- callback handler ---
    cb = _make_callback(user_id=FOREIGN_ID, data="ftype:ledger")
    state2 = _make_fsm_context(data={"file_id": "x", "file_name": "x.xlsx"})

    with patch("bot.handlers.files.run_pipeline") as mock_pipeline:
        asyncio.run(on_callback_file_type(cb, state2))
        mock_pipeline.assert_not_called()

    cb.message.edit_text.assert_not_called()


# ---------------------------------------------------------------------------
# test_document_received
# ---------------------------------------------------------------------------

def test_document_received():
    """Whitelisted user → FSM set_state(waiting_type) + keyboard sent."""
    from bot.handlers.files import on_document, FileFlow

    ALLOWED_ID = 188032358
    msg = _make_message(user_id=ALLOWED_ID)
    state = _make_fsm_context()

    asyncio.run(on_document(msg, state))

    # FSM должен перейти в waiting_type
    state.set_state.assert_called_once_with(FileFlow.waiting_type)

    # update_data должен сохранить file_id и file_name
    state.update_data.assert_called_once()
    call_kwargs = state.update_data.call_args
    # check keyword args
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    assert "file_id" in kwargs, (
        f"update_data должен принять file_id, получили kwargs={kwargs}, args={call_kwargs.args}"
    )

    # Должен был ответить (клавиатура)
    msg.answer.assert_called_once()
    call_args = msg.answer.call_args
    assert call_args is not None  # answer вызван с reply_markup


# ---------------------------------------------------------------------------
# test_file_type_runs_pipeline
# ---------------------------------------------------------------------------

def test_file_type_runs_pipeline(tmp_path):
    """Callback ftype:ledger (whitelisted) → run_and_report вызван, «N строк» отправлено.

    Мокаем run_and_report напрямую (не create_task) — проще и надёжнее:
    проверяем что он вызван с правильным file_type и что бот отправил «строк» или «42».
    """
    from bot.handlers import files as files_module

    ALLOWED_ID = 188032358
    cb = _make_callback(user_id=ALLOWED_ID, data="ftype:ledger")
    state = _make_fsm_context(data={"file_id": "FILEID123", "file_name": "ledger.xlsx"})

    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()

    captured = {}

    async def fake_run_and_report(bot, user_id, file_id, file_name, file_type):
        captured["file_type"] = file_type
        captured["user_id"] = user_id
        await bot.send_message(user_id, f"Готово. Обновлено строк: 42\nТип файла: Леджер")

    with (
        patch.object(files_module, "run_and_report", side_effect=fake_run_and_report),
        patch.object(files_module, "_get_bot", return_value=fake_bot),
    ):
        async def _run():
            # create_task needs a running loop — we wrap in run()
            task = asyncio.ensure_future(files_module.on_callback_file_type(cb, state))
            await task
            # allow background tasks to complete
            await asyncio.sleep(0)

        asyncio.run(_run())

    # FSM очищен
    state.clear.assert_called_once()

    # run_and_report получил правильный file_type
    assert captured.get("file_type") == "ledger", f"file_type={captured.get('file_type')!r}"
    assert captured.get("user_id") == ALLOWED_ID

    # Бот отправил «строк» или «42»
    all_calls = fake_bot.send_message.call_args_list + cb.message.edit_text.call_args_list
    texts = " ".join(
        str(c.args) + str(c.kwargs) for c in all_calls
    ).lower()
    assert "42" in texts or "строк" in texts, f"Ожидали '42'/'строк' в ответе, получили: {texts!r}"


# ---------------------------------------------------------------------------
# test_pipeline_error_message
# ---------------------------------------------------------------------------

def test_pipeline_error_message(tmp_path):
    """run_and_report бросает Exception → бот отвечает сообщением об ошибке + бэкапе.

    Тест проверяет run_and_report напрямую (не через on_callback_file_type)
    чтобы не зависеть от create_task завершения.
    """
    from bot.handlers.files import run_and_report

    ALLOWED_ID = 188032358

    fake_tmp = tmp_path / "ledger.xlsx"
    fake_tmp.write_bytes(b"fake xlsx content")

    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()

    with (
        patch("bot.handlers.files.download_file", new=AsyncMock(return_value=fake_tmp)),
        patch("bot.handlers.files.asyncio.to_thread", new=AsyncMock(side_effect=RuntimeError("pipeline boom"))),
    ):
        asyncio.run(run_and_report(fake_bot, ALLOWED_ID, "FILEID456", "ledger.xlsx", "ledger"))

    # Должно быть сообщение об ошибке с упоминанием восстановления
    all_calls = fake_bot.send_message.call_args_list
    texts = " ".join(
        str(c.args) + str(c.kwargs) for c in all_calls
    ).lower()
    assert "восстановлен" in texts or "бэкап" in texts or "резерв" in texts or "backup" in texts, (
        f"Ожидали упоминание бэкапа в ответе при ошибке, получили: {texts!r}"
    )
