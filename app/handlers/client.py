"""Діалог із клієнтом в особистому чаті з ботом."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender

from config import Config

from .. import keyboards as kb
from ..assistant import Assistant, to_telegram_html, wants_human
from ..db import Database
from ..handoff import start_handoff
from ..texts import HELP_BUTTONS, MANAGER_BUTTONS, lang_of, t

router = Router(name="client")
router.message.filter(F.chat.type == "private")
log = logging.getLogger(__name__)


async def _user(db: Database, message_or_call) -> tuple[int, str]:
    u = message_or_call.from_user
    lang = lang_of(u.language_code)
    await db.upsert_user(u.id, u.username, u.full_name, lang)
    return u.id, lang


async def _handoff(bot: Bot, db: Database, cfg: Config, chat_id: int, user_id: int, lang: str, reason: str):
    result = await start_handoff(bot, db, cfg.manager_chat_id, user_id, reason)
    key = {"ok": "handoff_ok", "already": "handoff_already"}.get(result, "handoff_off")
    await bot.send_message(chat_id, t(lang, key))


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, cfg: Config):
    _, lang = await _user(db, message)
    name = message.from_user.first_name or "друже"
    await message.answer(t(lang, "start", name=name, shop=cfg.shop_name), reply_markup=kb.main_menu(lang))


@router.message(Command("help"))
@router.message(F.text.in_(HELP_BUTTONS))
async def cmd_help(message: Message, db: Database, cfg: Config):
    _, lang = await _user(db, message)
    await message.answer(t(lang, "help", shop=cfg.shop_name))


@router.message(Command("reset"))
async def cmd_reset(message: Message, db: Database):
    user_id, lang = await _user(db, message)
    await db.clear_history(user_id)
    await message.answer(t(lang, "reset"))


@router.message(F.text.in_(MANAGER_BUTTONS))
async def btn_manager(message: Message, bot: Bot, db: Database, cfg: Config):
    user_id, lang = await _user(db, message)
    await db.add_message(user_id, "user", message.text)
    await _handoff(bot, db, cfg, message.chat.id, user_id, lang, "натиснув кнопку «Менеджер»")


@router.callback_query(F.data == "handoff")
async def cb_handoff(call: CallbackQuery, bot: Bot, db: Database, cfg: Config):
    user_id, lang = await _user(db, call)
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)
    await _handoff(bot, db, cfg, call.message.chat.id, user_id, lang, "бот не знайшов відповідь")


@router.message()
async def on_message(message: Message, bot: Bot, db: Database, cfg: Config, assistant: Assistant):
    user_id, lang = await _user(db, message)
    user = await db.get_user(user_id)

    # Розмову веде менеджер: пересилаємо все (текст, фото, файли) в його тему
    if user["mode"] == "manager" and cfg.manager_chat_id:
        await bot.copy_message(cfg.manager_chat_id, message.chat.id, message.message_id,
                               message_thread_id=user["thread_id"])
        if message.text or message.caption:
            await db.add_message(user_id, "user", message.text or message.caption)
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        await message.answer(t(lang, "no_answer"), reply_markup=kb.call_manager(lang))
        return

    if wants_human(text):
        await db.add_message(user_id, "user", text)
        await _handoff(bot, db, cfg, message.chat.id, user_id, lang, "клієнт попросив менеджера")
        return

    try:
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            answer = await assistant.answer(user_id, text)
    except Exception:
        log.exception("Помилка AI-відповіді для %s", user_id)
        await message.answer(t(lang, "error"), reply_markup=kb.call_manager(lang))
        return

    if answer.text is None:
        await message.answer(t(lang, "no_answer"), reply_markup=kb.call_manager(lang))
    else:
        await message.answer(to_telegram_html(answer.text))
