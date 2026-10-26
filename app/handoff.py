"""Передача розмови живому менеджеру через теми (topics) у групі менеджерів."""
from __future__ import annotations

import html
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from . import keyboards as kb
from .db import Database

log = logging.getLogger(__name__)

ROLE_LABEL = {"user": "👤 Клієнт", "assistant": "🤖 Бот", "manager": "🧑‍💼 Менеджер"}


def _topic_name(full_name: str, user_id: int) -> str:
    return f"{full_name[:100]} · {user_id}"


async def _ensure_topic(bot: Bot, chat_id: int, user) -> int:
    """Повертає тему клієнта в групі менеджерів; створює нову, якщо її немає або її видалили."""
    if user["thread_id"]:
        try:
            await bot.reopen_forum_topic(chat_id, user["thread_id"])
        except TelegramBadRequest as e:
            if "TOPIC_NOT_MODIFIED" not in str(e):  # тема вже відкрита — це нормально
                log.info("Тема %s недоступна (%s), створюю нову", user["thread_id"], e)
                topic = await bot.create_forum_topic(chat_id, _topic_name(user["full_name"], user["user_id"]))
                return topic.message_thread_id
        return user["thread_id"]
    topic = await bot.create_forum_topic(chat_id, _topic_name(user["full_name"], user["user_id"]))
    return topic.message_thread_id


async def start_handoff(bot: Bot, db: Database, manager_chat_id: int | None, user_id: int, reason: str) -> str:
    """Підключає менеджера. Повертає 'ok', 'already' або 'off'."""
    user = await db.get_user(user_id)
    if user is None or manager_chat_id is None:
        return "off"
    if user["mode"] == "manager":
        return "already"
    try:
        thread_id = await _ensure_topic(bot, manager_chat_id, user)
    except TelegramBadRequest as e:
        log.error("Не вдалося створити тему в групі менеджерів: %s", e)
        return "off"

    lines = [
        "🆕 <b>Новий запит на менеджера</b>",
        f"Клієнт: {html.escape(user['full_name'])}"
        + (f" (@{html.escape(user['username'])})" if user["username"] else ""),
        f"ID: <code>{user_id}</code> · мова: {user['lang'] or '—'}",
        f"Причина: {html.escape(reason)}",
        "",
        "<b>Остання розмова:</b>",
    ]
    for role, text in await db.transcript(user_id, 10):
        short = text if len(text) <= 300 else text[:300] + "…"
        lines.append(f"{ROLE_LABEL.get(role, role)}: {html.escape(short)}")
    lines += ["", "✍️ Відповідайте прямо в цій темі — клієнт отримає повідомлення від бота."]
    await bot.send_message(manager_chat_id, "\n".join(lines)[:4000], message_thread_id=thread_id,
                           reply_markup=kb.manager_card(user_id))
    await db.set_mode(user_id, "manager", thread_id)
    await db.open_handoff(user_id, reason)
    log.info("Handoff: user=%s thread=%s reason=%s", user_id, thread_id, reason)
    return "ok"


async def close_handoff(bot: Bot, db: Database, manager_chat_id: int, user_id: int) -> bool:
    user = await db.get_user(user_id)
    if user is None or user["mode"] != "manager":
        return False
    await db.set_mode(user_id, "ai")
    await db.close_handoff(user_id)
    try:
        await bot.close_forum_topic(manager_chat_id, user["thread_id"])
    except TelegramBadRequest:
        pass
    return True
