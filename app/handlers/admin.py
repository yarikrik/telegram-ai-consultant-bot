"""Команди адміністратора: статистика, оновлення бази знань, ID чату."""
from __future__ import annotations

import time
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from config import Config

from ..db import Database
from ..rag.knowledge import KnowledgeBase

ALLOWED = {".md", ".txt"}
MAX_FILE = 2 * 1024 * 1024


def _fmt_stats(s: dict) -> str:
    q = s["questions"]
    share = f" ({s['answered'] * 100 // q}%)" if q else ""
    wait = f"{s['avg_wait_s'] // 60} хв {s['avg_wait_s'] % 60} с" if s["avg_wait_s"] is not None else "—"
    lat = f"{s['avg_latency_ms'] / 1000:.1f} с" if s["avg_latency_ms"] is not None else "—"
    return (f"❓ Питань до AI: <b>{q}</b>\n"
            f"✅ AI відповів сам: <b>{s['answered']}</b>{share}\n"
            f"🤷 Не знайшов відповіді: <b>{s['no_answer']}</b>\n"
            f"👤 Передано менеджеру: <b>{s['handoffs']}</b> (чекають зараз: {s['waiting_now']})\n"
            f"⏱ Середній час до відповіді менеджера: {wait}\n"
            f"⚡ Середній час відповіді AI: {lat}\n"
            f"🔢 Токени: {s['tokens_in']} вхід / {s['tokens_out']} вихід\n"
            f"🆕 Нових клієнтів: {s['new_users']}")


def get_router(admin_ids: set[int]) -> Router:
    router = Router(name="admin")

    @router.message(Command("id"))
    async def cmd_id(message: Message):
        thread = f"\nТема: <code>{message.message_thread_id}</code>" if message.message_thread_id else ""
        await message.reply(f"Чат: <code>{message.chat.id}</code>{thread}\nВаш ID: <code>{message.from_user.id}</code>")

    admin = Router(name="admin_only")
    admin.message.filter(F.from_user.id.in_(admin_ids), F.chat.type == "private")
    router.include_router(admin)

    @admin.message(Command("stats"))
    async def cmd_stats(message: Message, db: Database):
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        today = await db.stats(midnight)
        week = await db.stats(time.time() - 7 * 86400)
        total = await db.stats(0)
        await message.answer(f"📊 <b>Сьогодні</b>\n{_fmt_stats(today)}\n\n"
                             f"📅 <b>7 днів</b>\n{_fmt_stats(week)}\n\n"
                             f"🗂 <b>Весь час</b>\n{_fmt_stats(total)}")

    @admin.message(Command("kb"))
    async def cmd_kb(message: Message, kb: KnowledgeBase, cfg: Config):
        files = sorted(p.name for p in cfg.knowledge_dir.glob("*") if p.suffix.lower() in ALLOWED)
        lst = "\n".join(f"• {f}" for f in files) or "порожньо"
        await message.answer(f"📚 <b>База знань</b>\nФайли:\n{lst}\n\nФрагментів в індексі: {kb.count()}\n\n"
                             "Щоб оновити — надішліть мені .md або .txt файл.\n"
                             "Файл з такою самою назвою буде замінено.\n/reindex — перебудувати індекс")

    @admin.message(Command("reindex"))
    async def cmd_reindex(message: Message, kb: KnowledgeBase):
        msg = await message.answer("⏳ Перебудовую індекс…")
        try:
            n = await kb.rebuild()
        except Exception as e:
            await msg.edit_text(f"❌ Помилка: {e}")
            return
        await msg.edit_text(f"✅ Готово: {n} фрагментів у базі знань.")

    @admin.message(F.document)
    async def on_document(message: Message, bot: Bot, kb: KnowledgeBase, cfg: Config):
        doc = message.document
        name = doc.file_name or "knowledge.md"
        if not any(name.lower().endswith(ext) for ext in ALLOWED):
            await message.answer("Надішліть файл .md або .txt з текстом бази знань.")
            return
        if doc.file_size and doc.file_size > MAX_FILE:
            await message.answer("Файл завеликий (максимум 2 МБ).")
            return
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "._- ").strip() or "knowledge.md"
        target = cfg.knowledge_dir / safe
        backup = target.read_bytes() if target.exists() else None
        await bot.download(doc, destination=target)
        msg = await message.answer(f"⏳ Отримав «{safe}», оновлюю базу знань…")
        try:
            n = await kb.rebuild()
        except Exception as e:
            if backup is not None:  # повертаємо стару версію файлу
                target.write_bytes(backup)
            else:
                target.unlink(missing_ok=True)
            await msg.edit_text(f"❌ Не вдалося оновити: {e}\nСтара база знань працює як раніше.")
            return
        await msg.edit_text(f"✅ База знань оновлена: {n} фрагментів. Бот уже відповідає за новими даними.")

    return router
