"""Робота з Gemini API: ембединги для пошуку та генерація відповідей."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

log = logging.getLogger(__name__)

EMBED_BATCH = 50  # скільки текстів відправляти в одному запиті на ембединги
RETRYABLE = {429, 500, 503, 504}  # перевантаження / ліміт — можна спробувати іншу модель


@dataclass
class LLMReply:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class GeminiClient:
    def __init__(self, api_key: str, model: str, embedding_model: str, fallback_models: list[str] | None = None):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.embedding_model = embedding_model
        self.fallback_models = fallback_models or []

    async def embed(self, texts: list[str], for_query: bool = False) -> list[list[float]]:
        """Перетворює тексти на вектори. Для бази знань і для запиту — різні task_type."""
        task = "RETRIEVAL_QUERY" if for_query else "RETRIEVAL_DOCUMENT"
        vectors: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            resp = await self.client.aio.models.embed_content(
                model=self.embedding_model,
                contents=batch,
                config=types.EmbedContentConfig(task_type=task),
            )
            vectors.extend(list(e.values) for e in resp.embeddings)
        return vectors

    async def generate(self, system: str, history: list[tuple[str, str]], question: str) -> LLMReply:
        """history — список (role, text), де role = 'user' або 'assistant'.

        Якщо модель перевантажена (503) або вичерпано ліміт (429), пробуємо запасні моделі.
        """
        contents = [
            types.Content(role="model" if role == "assistant" else "user", parts=[types.Part(text=text)])
            for role, text in history
        ]
        contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
        config = types.GenerateContentConfig(system_instruction=system, temperature=0.3)
        models = [self.model] + [m for m in self.fallback_models if m != self.model]
        for i, model in enumerate(models):
            try:
                resp = await self.client.aio.models.generate_content(model=model, contents=contents, config=config)
                break
            except genai_errors.APIError as e:
                if e.code not in RETRYABLE or i == len(models) - 1:
                    raise
                log.warning("Модель %s недоступна (%s), пробую %s", model, e.code, models[i + 1])
        usage = resp.usage_metadata
        return LLMReply(
            text=(resp.text or "").strip(),
            tokens_in=(usage.prompt_token_count or 0) if usage else 0,
            tokens_out=(usage.candidates_token_count or 0) if usage else 0,
        )
