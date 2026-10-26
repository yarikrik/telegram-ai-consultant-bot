"""Група менеджерів: кожен клієнт — окрема тема, відповіді йдуть клієнту від імені бота."""
from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import Config

from ..db import Database
from ..handoff import close_handoff
from ..texts import t

log = logging.getLogger(__name__)


def get_router(manager_chat_id: int | None) -> Router:
    router = Router(name="manager")
    if manager_chat_id is None:
        return router
    router.message.filter(F.chat.id == manager_chat_id)
    router.callback_query.filter(F.message.chat.id == manager_chat_id)

    async def _finish(bot: Bot, db: Database, cfg: Config, user_id: int) -> bool:
        if not await close_handoff(bot, db, cfg.manager_chat_id, user_id):
            return False
        user = await db.get_user(user_id)
        await bot.send_message(user_id, t(user["lang"], "back_to_ai"))
        return True

    @router.callback_query(F.data.startswith("close:"))
    async def cb_close(call: CallbackQuery, bot: Bot, db: Database, cfg: Config):
        user_id = int(call.data.split(":", 1)[1])
        ok = await _finish(bot, db, cfg, user_id)
        await call.answer("Повернуто боту 🤖" if ok else "Розмову вже завершено")
        if ok:
            await call.message.reply(f"✅ Розмову завершив {call.from_user.full_name}. Клієнт знову з ботом.")

    @router.message(Command("close"))
    async def cmd_close(message: Message, bot: Bot, db: Database, cfg: Config):
        if not message.message_thread_id:
            return
        user = await db.user_by_thread(message.message_thread_id)
        if user and await _finish(bot, db, cfg, user["user_id"]):
            await message.reply("✅ Клієнт знову з ботом.")

    @router.message(F.message_thread_id)
    async def from_manager(message: Message, bot: Bot, db: Database):
        if message.from_user.is_bot or (message.text or "").startswith("/"):
            return
        if message.forum_topic_created or message.forum_topic_reopened or message.forum_topic_closed:
            return
        user = await db.user_by_thread(message.message_thread_id)
        if user is None:
            return
        if user["mode"] != "manager":
            await message.reply("ℹ️ Клієнт зараз спілкується з ботом. Повідомлення не надіслано.")
            return
        if await db.waiting_first_reply(user["user_id"]):
            name = html.escape(message.from_user.first_name or "")
            await bot.send_message(user["user_id"], f"{t(user['lang'], 'manager_label')} {name} на зв'язку:"
                                   if user["lang"] == "uk" else f"{t(user['lang'], 'manager_label')} {name}:")
        await bot.copy_message(user["user_id"], message.chat.id, message.message_id)
        await db.add_message(user["user_id"], "manager", message.text or message.caption or "[медіа]")
        await db.mark_first_reply(user["user_id"])

    return router
