"""Точка входу: запуск AI-консультанта."""
from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.assistant import Assistant
from app.db import Database
from app.handlers import admin, client, manager
from app.rag.gemini import GeminiClient
from app.rag.knowledge import KnowledgeBase
from config import load_config


def setup_logging(log_dir):
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    file = RotatingFileHandler(log_dir / "bot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[console, file])
    # метрики кожного запиту (токени, затримка) — в окремий файл для аналізу
    metrics = RotatingFileHandler(log_dir / "metrics.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    metrics.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging.getLogger("metrics").addHandler(metrics)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def main():
    cfg = load_config()
    setup_logging(cfg.log_dir)
    log = logging.getLogger("main")

    db = Database(cfg.data_dir / "bot.db")
    llm = GeminiClient(cfg.gemini_api_key, cfg.gemini_model, cfg.embedding_model, list(cfg.fallback_models))
    kb = KnowledgeBase(llm, cfg.knowledge_dir, cfg.data_dir)
    if kb.count() == 0:
        log.info("Індекс порожній — будую з папки knowledge/ …")
        n = await kb.rebuild()
        log.info("Готово: %d фрагментів", n)
    assistant = Assistant(kb, llm, db, cfg.shop_name, cfg.history_limit, cfg.top_k)

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(db=db, kb=kb, assistant=assistant, cfg=cfg)
    dp.include_routers(admin.get_router(cfg.admin_ids), manager.get_router(cfg.manager_chat_id), client.router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Почати"),
        BotCommand(command="help", description="Що вміє бот"),
        BotCommand(command="reset", description="Очистити історію розмови"),
    ])
    if cfg.manager_chat_id is None:
        log.warning("MANAGER_CHAT_ID не задано — передача менеджеру вимкнена")
    me = await bot.get_me()
    log.info("Бот @%s запущено. Модель: %s", me.username, cfg.gemini_model)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code not in (None, 0):
            raise
