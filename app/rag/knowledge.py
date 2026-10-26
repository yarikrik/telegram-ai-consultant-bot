"""База знань: індексація в ChromaDB і пошук релевантних фрагментів."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .chunker import Chunk, load_chunks

log = logging.getLogger(__name__)
COLLECTION = "knowledge"


class Embedder(Protocol):
    async def embed(self, texts: list[str], for_query: bool = False) -> list[list[float]]: ...


@dataclass
class Found:
    text: str
    source: str
    distance: float


class KnowledgeBase:
    """Обгортка над локальною ChromaDB (дані лежать у папці data/chroma)."""

    def __init__(self, embedder: Embedder, knowledge_dir: Path, db_dir: Path, store=None):
        self.embedder = embedder
        self.knowledge_dir = knowledge_dir
        if store is None:  # імпорт тут, щоб тести могли підставити свій store
            import chromadb
            store = chromadb.PersistentClient(path=str(db_dir / "chroma"))
        self.client = store

    def _collection(self):
        # embedding_function=None: вектори рахуємо самі через Gemini
        return self.client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None)

    def count(self) -> int:
        return self._collection().count()

    async def rebuild(self) -> int:
        """Повністю перебудовує індекс з файлів у knowledge/. Повертає кількість чанків."""
        chunks: list[Chunk] = load_chunks(self.knowledge_dir)
        if not chunks:
            raise ValueError("У папці knowledge/ немає .md або .txt файлів")
        vectors = await self.embedder.embed([c.text for c in chunks])
        try:
            self.client.delete_collection(COLLECTION)
        except Exception:  # колекції ще немає
            pass
        col = self._collection()
        col.add(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=vectors,
            metadatas=[{"source": c.source, "section": c.section} for c in chunks],
        )
        log.info("Індекс перебудовано: %d чанків з %s", len(chunks), self.knowledge_dir)
        return len(chunks)

    async def search(self, query: str, top_k: int = 4) -> list[Found]:
        col = self._collection()
        if col.count() == 0:
            return []
        [vector] = await self.embedder.embed([query], for_query=True)
        res = col.query(query_embeddings=[vector], n_results=min(top_k, col.count()))
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        return [Found(text=d, source=(m or {}).get("source", ""), distance=float(x))
                for d, m, x in zip(docs, metas, dists)]
