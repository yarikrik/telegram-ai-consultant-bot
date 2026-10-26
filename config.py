"""Налаштування бота з файлу .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()}


@dataclass(frozen=True)
class Config:
    bot_token: str
    gemini_api_key: str
    manager_chat_id: int | None
    admin_ids: set[int] = field(default_factory=set)
    shop_name: str = "VoltShop"
    gemini_model: str = "gemini-3.6-flash"
    embedding_model: str = "gemini-embedding-001"
    fallback_models: tuple[str, ...] = ("gemini-flash-latest", "gemini-3.1-flash-lite")
    history_limit: int = 5
    top_k: int = 4
    knowledge_dir: Path = BASE_DIR / "knowledge"
    data_dir: Path = BASE_DIR / "data"
    log_dir: Path = BASE_DIR / "logs"


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not token:
        raise SystemExit("❌ BOT_TOKEN не задано у файлі .env")
    if not key:
        raise SystemExit("❌ GEMINI_API_KEY не задано у файлі .env")
    chat = os.getenv("MANAGER_CHAT_ID", "").strip()
    return Config(
        bot_token=token,
        gemini_api_key=key,
        manager_chat_id=int(chat) if chat.lstrip("-").isdigit() else None,
        admin_ids=_ids(os.getenv("ADMIN_IDS", "")),
        shop_name=os.getenv("SHOP_NAME", "VoltShop").strip() or "VoltShop",
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "gemini-embedding-001").strip(),
        fallback_models=tuple(m.strip() for m in os.getenv(
            "GEMINI_FALLBACK_MODELS", "gemini-flash-latest,gemini-3.1-flash-lite").split(",") if m.strip()),
        history_limit=int(os.getenv("HISTORY_LIMIT", "5")),
        top_k=int(os.getenv("TOP_K", "4")),
    )
