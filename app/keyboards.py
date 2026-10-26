"""Клавіатури бота."""
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .texts import t


def main_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_manager")), KeyboardButton(text=t(lang, "btn_help"))]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="✍️",
    )


def call_manager(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_call"), callback_data="handoff")
    return kb.as_markup()


def manager_card(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🤖 Повернути боту", callback_data=f"close:{user_id}")
    return kb.as_markup()
