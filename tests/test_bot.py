"""Тести логіки бота. Запуск: python -m pytest  (або python -m unittest discover tests)."""
import tempfile
import time
import unittest
from pathlib import Path

from app.assistant import NO_ANSWER, Assistant, build_system_prompt, to_telegram_html, wants_human
from app.db import Database
from app.rag.chunker import chunk_markdown, load_chunks
from app.rag.knowledge import Found, KnowledgeBase
from tests.fakes import FakeChroma, FakeEmbedder, FakeLLM

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "knowledge"


class ChunkerTests(unittest.TestCase):
    def test_headings_become_section_path(self):
        md = "# Магазин\nВступ\n## Доставка\n### Нова Пошта\nДо 2 днів."
        chunks = chunk_markdown(md, "x.md")
        self.assertEqual([c.section for c in chunks], ["Магазин", "Магазин › Доставка › Нова Пошта"])
        self.assertTrue(chunks[1].text.startswith("Магазин › Доставка › Нова Пошта\n"))

    def test_long_section_is_split_with_limit(self):
        body = "\n\n".join(f"Абзац номер {i}. " + "слово " * 40 for i in range(20))
        chunks = chunk_markdown(f"# Довгий\n{body}", "x.md", max_chars=500, overlap=80)
        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(len(c.text) <= 500 + len("Довгий\n") for c in chunks))

    def test_ids_are_unique_and_stable(self):
        a = load_chunks(KB_DIR)
        b = load_chunks(KB_DIR)
        self.assertEqual([c.id for c in a], [c.id for c in b])
        self.assertEqual(len({c.id for c in a}), len(a))

    def test_demo_knowledge_base_loads(self):
        chunks = load_chunks(KB_DIR)
        self.assertGreater(len(chunks), 15)
        self.assertTrue(any("Volt Buds Pro" in c.text for c in chunks))


class HumanIntentTests(unittest.TestCase):
    def test_explicit_requests(self):
        for text in ["Покличте менеджера", "хочу поговорити з людиною", "Менеджер!", "оператор",
                     "соедините с оператором", "можно живого человека?", "I want to talk to a manager",
                     "connect me with a real person"]:
            self.assertTrue(wants_human(text), text)

    def test_regular_questions(self):
        for text in ["Скільки коштує доставка?", "Які навушники з шумозаглушенням?",
                     "менеджер мені вчора дзвонив щодо замовлення, а коли відправка?",
                     "Do you ship abroad?"]:
            self.assertFalse(wants_human(text), text)


class FormattingTests(unittest.TestCase):
    def test_html_is_escaped_and_bold_converted(self):
        out = to_telegram_html("Ціна **2499 грн** <script>\n* пункт")
        self.assertIn("<b>2499 грн</b>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("• пункт", out)

    def test_prompt_contains_rules_and_context(self):
        p = build_system_prompt("VoltShop", [Found("Доставка 1–2 дні", "kb.md", 0.1)])
        self.assertIn("VoltShop", p)
        self.assertIn(NO_ANSWER, p)
        self.assertIn("[1] Доставка 1–2 дні", p)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")

    async def asyncTearDown(self):
        self.db.conn.close()
        self.tmp.cleanup()

    async def test_history_order_and_limit(self):
        await self.db.upsert_user(1, "u", "User", "uk")
        for i in range(8):
            await self.db.add_message(1, "user" if i % 2 == 0 else "assistant", f"m{i}")
        await self.db.add_message(1, "manager", "від менеджера")
        hist = await self.db.history(1, 5)
        self.assertEqual([t for _, t in hist], ["m3", "m4", "m5", "m6", "m7"])  # без менеджера

    async def test_mode_thread_and_stats(self):
        await self.db.upsert_user(7, None, "Anna", "ru")
        await self.db.set_mode(7, "manager", 555)
        self.assertEqual((await self.db.user_by_thread(555))["user_id"], 7)
        await self.db.log_question(7, "answered", 100, 20, 900)
        await self.db.log_question(7, "no_answer", 80, 5, 700)
        await self.db.open_handoff(7, "test")
        await self.db.mark_first_reply(7)
        s = await self.db.stats(0)
        self.assertEqual((s["questions"], s["answered"], s["no_answer"], s["handoffs"]), (2, 1, 1, 1))
        self.assertEqual(s["avg_latency_ms"], 800)
        self.assertEqual(s["waiting_now"], 0)
        future = await self.db.stats(time.time() + 60)
        self.assertEqual(future["questions"], 0)

    async def test_upsert_keeps_language(self):
        await self.db.upsert_user(3, "a", "A", "en")
        await self.db.upsert_user(3, "a", "A B", None)
        u = await self.db.get_user(3)
        self.assertEqual((u["lang"], u["full_name"], u["mode"]), ("en", "A B", "ai"))


class RagTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")
        self.kb = KnowledgeBase(FakeEmbedder(), KB_DIR, Path(self.tmp.name), store=FakeChroma())
        await self.db.upsert_user(1, "u", "User", "uk")

    async def asyncTearDown(self):
        self.db.conn.close()
        self.tmp.cleanup()

    async def test_rebuild_and_search(self):
        n = await self.kb.rebuild()
        self.assertEqual(self.kb.count(), n)
        found = await self.kb.search("Укрпошта доставка термін вартість", 3)
        self.assertEqual(len(found), 3)
        self.assertTrue(any("Укрпошт" in f.text for f in found))
        # повторна перебудова не дублює фрагменти
        await self.kb.rebuild()
        self.assertEqual(self.kb.count(), n)

    async def test_assistant_answers_and_saves_history(self):
        await self.kb.rebuild()
        llm = FakeLLM("Доставка Новою Поштою займає **1–2 дні**.")
        bot = Assistant(self.kb, llm, self.db, "VoltShop", history_limit=5, top_k=4)
        ans = await bot.answer(1, "Скільки йде доставка?")
        self.assertEqual(ans.text, "Доставка Новою Поштою займає **1–2 дні**.")
        self.assertIn("ФРАГМЕНТИ БАЗИ ЗНАНЬ", llm.last["system"])
        self.assertEqual(await self.db.history(1, 5),
                         [("user", "Скільки йде доставка?"), ("assistant", ans.text)])
        # друге питання отримує попередню розмову як історію
        await bot.answer(1, "А Укрпоштою?")
        self.assertEqual(len(llm.last["history"]), 2)
        self.assertEqual((await self.db.stats(0))["answered"], 2)

    async def test_no_answer_marker(self):
        await self.kb.rebuild()
        bot = Assistant(self.kb, FakeLLM(NO_ANSWER), self.db, "VoltShop")
        ans = await bot.answer(1, "Яка погода в Парижі?")
        self.assertIsNone(ans.text)
        s = await self.db.stats(0)
        self.assertEqual((s["no_answer"], s["answered"]), (1, 0))

    async def test_empty_index_means_no_answer(self):
        bot = Assistant(self.kb, FakeLLM("щось"), self.db, "VoltShop")
        self.assertIsNone((await bot.answer(1, "Привіт")).text)

    async def test_llm_error_is_logged(self):
        await self.kb.rebuild()

        class Broken(FakeLLM):
            async def generate(self, *a):
                raise RuntimeError("quota")

        bot = Assistant(self.kb, Broken(), self.db, "VoltShop")
        with self.assertRaises(RuntimeError):
            await bot.answer(1, "Ціна навушників?")
        self.assertEqual((await self.db.stats(0))["errors"], 1)


if __name__ == "__main__":
    unittest.main()
