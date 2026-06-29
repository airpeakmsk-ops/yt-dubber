"""bot/keyboards.py — inline-клавиатуры Telegram-бота.

Используется для выбора типа присланного файла склада.
Три типа (по решению CONTEXT.md, раздел C):
  - Леджер (приходы + продажи + остатки) → полный пересчёт пайплайна
  - Недельные остатки → пересборка скорости/отчёта
  - Накладная (цены/себестоимость) → пересчёт себестоимости + отчёт

callback_data формат: «ftype:<тип>»
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def file_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа загружаемого файла.

    Три кнопки в столбик (одна кнопка на строку):
      «Леджер (приходы+продажи)»     → callback_data="ftype:ledger"
      «Недельные остатки»             → callback_data="ftype:weekly"
      «Накладная (себестоимость)»     → callback_data="ftype:invoice"

    Returns:
        InlineKeyboardMarkup — готовая клавиатура для передачи в reply_markup.
    """
    buttons = [
        [InlineKeyboardButton(
            text="Леджер (приходы+продажи)",
            callback_data="ftype:ledger",
        )],
        [InlineKeyboardButton(
            text="Недельные остатки",
            callback_data="ftype:weekly",
        )],
        [InlineKeyboardButton(
            text="Накладная (себестоимость)",
            callback_data="ftype:invoice",
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
