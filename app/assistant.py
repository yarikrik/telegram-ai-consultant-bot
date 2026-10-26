"""Логіка AI-консультанта: пошук у базі знань → промпт → відповідь Gemini.

Модуль не залежить від Telegram, тому його легко тестувати окремо.
"""
from __future__ import annotations

import html
import logging
import re
import time
from dataclasses import dataclass

from .db import Database
from .rag.knowledge import Found, KnowledgeBase

log = logging.getLogger("metrics")

NO_ANSWER = "[[NO_ANSWER]]"

# Фрази, за якими клієнт явно просить живу людину (укр / рус / англ)
HUMAN_PATTERNS = re.compile(
    r"\b(менеджер\w*|оператор\w*|живу?\s*людин\w*|з\s+людиною|"
    r"живо\w*\s+(людин|человек)\w*|с\s+человеком|человек\w*\s+позов\w*|"
    r"human|operator|manager|real\s+person|live\s+agent|support\s+agent)\b",
    re.IGNORECASE,
)
ASK_VERBS = re.compile(
    r"(покли|зв.яж|з.єдна|переда|хочу|можна|можно|позов|соедин|свяж|дайте|need|want|talk|speak|connect|call)",
    re.IGNORECASE,
)


def wants_human(text: str) -> bool:
    """Клієнт просить менеджера: слово «менеджер/оператор/людина» + дієслово-прохання,
    або коротке повідомлення з одного такого слова («Менеджер!»)."""
    if not HUMAN_PATTERNS.search(text):
        return False
    short = len(text.split()) <= 3
    return short or bool(ASK_VERBS.search(text))


def build_system_prompt(shop: str, found: list[Found]) -> str:
    context = "\n\n---\n\n".join(f"[{i}] {f.text}" for i, f in enumerate(found, 1)) or "(нічого не знайдено)"
    return f"""Ти — ввічливий онлайн-консультант інтернет-магазину {shop}.

ПРАВИЛА:
1. Відповідай ТІЛЬКИ на основі фрагментів бази знань нижче. Не вигадуй цін, характеристик, термінів чи умов.
2. Відповідай мовою останнього повідомлення клієнта (українська, російська або англійська).
3. Пиши коротко й по суті: 1–6 речень або короткий список. Можна виділяти важливе **жирним**.
4. Якщо у фрагментах немає відповіді на питання, або питання не стосується магазину,
   відповідай РІВНО одним рядком: {NO_ANSWER}
5. Не згадуй слова «фрагменти», «база знань», «контекст» — говори як живий консультант.
6. Якщо клієнт хоче оформити замовлення, підкажи, як це зробити, згідно з базою знань.

ФРАГМЕНТИ БАЗИ ЗНАНЬ:
{context}"""


def to_telegram_html(text: str) -> str:
    """Безпечно перетворює відповідь моделі в HTML для Telegram (лише **жирний**)."""
    safe = html.escape(text)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe, flags=re.S)
    safe = re.sub(r"^\s*[\*\-]\s+", "• ", safe, flags=re.M)
    return safe


@dataclass
class Answer:
    text: str | None          # None — відповіді немає, треба запропонувати менеджера
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    sources: tuple[str, ...] = ()


class Assistant:
    def __init__(self, kb: KnowledgeBase, llm, db: Database, shop: str, history_limit: int = 5, top_k: int = 4):
        self.kb = kb
        self.llm = llm
        self.db = db
        self.shop = shop
        self.history_limit = history_limit
        self.top_k = top_k

    async def answer(self, user_id: int, question: str) -> Answer:
        started = time.perf_counter()
        history = await self.db.history(user_id, self.history_limit)
        # для пошуку додаємо попереднє питання клієнта: «а скільки коштує?» після «навушники»
        prev_user = next((t for r, t in reversed(history) if r == "user"), "")
        query = f"{prev_user}\n{question}" if prev_user and len(question) < 60 else question
        try:
            found = await self.kb.search(query, self.top_k)
            reply = await self.llm.generate(build_system_prompt(self.shop, found), history, question)
        except Exception:
            ms = int((time.perf_counter() - started) * 1000)
            log.exception("user=%s outcome=error latency_ms=%s", user_id, ms)
            await self.db.log_question(user_id, "error", latency_ms=ms)
            raise
        ms = int((time.perf_counter() - started) * 1000)
        text = reply.text.strip()
        no_answer = not text or NO_ANSWER in text or not found
        outcome = "no_answer" if no_answer else "answered"
        await self.db.log_question(user_id, outcome, reply.tokens_in, reply.tokens_out, ms)
        log.info("user=%s outcome=%s tokens_in=%s tokens_out=%s latency_ms=%s",
                 user_id, outcome, reply.tokens_in, reply.tokens_out, ms)

        await self.db.add_message(user_id, "user", question)
        if no_answer:
            return Answer(None, reply.tokens_in, reply.tokens_out, ms)
        await self.db.add_message(user_id, "assistant", text)
        return Answer(text, reply.tokens_in, reply.tokens_out, ms, tuple({f.source for f in found}))
