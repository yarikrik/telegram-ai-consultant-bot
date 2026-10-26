"""Окремий скрипт: перебудувати векторний індекс бази знань без запуску бота.

    python ingest.py            — проіндексувати всі файли з knowledge/
    python ingest.py "запит"    — після індексації показати, що знаходить пошук
"""
import asyncio
import sys

from app.rag.gemini import GeminiClient
from app.rag.knowledge import KnowledgeBase
from config import load_config


async def main():
    cfg = load_config()
    llm = GeminiClient(cfg.gemini_api_key, cfg.gemini_model, cfg.embedding_model, list(cfg.fallback_models))
    kb = KnowledgeBase(llm, cfg.knowledge_dir, cfg.data_dir)
    n = await kb.rebuild()
    print(f"✅ Проіндексовано фрагментів: {n}")
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"\n🔎 Пошук: {query}\n")
        for f in await kb.search(query, cfg.top_k):
            print(f"[{f.distance:.3f}] {f.source}: {f.text[:150].replace(chr(10), ' ')}…")


if __name__ == "__main__":
    asyncio.run(main())
