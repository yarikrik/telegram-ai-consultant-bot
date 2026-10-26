"""Підробки (fakes/mocks) для тестів: без мережі, без Gemini і без ChromaDB."""
from __future__ import annotations

import math
import re


def _vec(text: str, dim: int = 64) -> list[float]:
    """Детермінований «ембединг»: мішок слів, захешований у вектор."""
    v = [0.0] * dim
    for w in re.findall(r"\w+", text.lower()):
        v[hash(w) % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    async def embed(self, texts, for_query=False):
        self.calls += 1
        return [_vec(t) for t in texts]


class FakeCollection:
    def __init__(self):
        self.rows = []

    def count(self):
        return len(self.rows)

    def add(self, ids, documents, embeddings, metadatas):
        self.rows.extend(zip(ids, documents, embeddings, metadatas))

    def query(self, query_embeddings, n_results):
        q = query_embeddings[0]
        scored = sorted(((1 - sum(a * b for a, b in zip(q, e)), d, m) for _, d, e, m in self.rows))[:n_results]
        return {"documents": [[d for _, d, _ in scored]], "metadatas": [[m for _, _, m in scored]],
                "distances": [[s for s, _, _ in scored]]}


class FakeChroma:
    def __init__(self):
        self.cols = {}

    def get_or_create_collection(self, name, metadata=None, embedding_function=None):
        return self.cols.setdefault(name, FakeCollection())

    def delete_collection(self, name):
        if name not in self.cols:
            raise ValueError("no collection")
        del self.cols[name]


class FakeLLM:
    """Повертає заготовлену відповідь і запам'ятовує, що йому передали."""

    def __init__(self, reply="Доставка Новою Поштою займає 1–2 дні."):
        self.reply = reply
        self.last = None

    async def generate(self, system, history, question):
        self.last = {"system": system, "history": list(history), "question": question}
        from types import SimpleNamespace
        return SimpleNamespace(text=self.reply, tokens_in=120, tokens_out=30)
