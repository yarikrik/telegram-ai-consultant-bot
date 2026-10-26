"""SQLite: користувачі, історія діалогів, передачі менеджеру, статистика.

Використовується стандартний sqlite3; блокуючі виклики виконуються в окремому
потоці через asyncio.to_thread, щоб не гальмувати бота.
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    lang        TEXT,
    mode        TEXT NOT NULL DEFAULT 'ai',      -- 'ai' | 'manager'
    thread_id   INTEGER,                          -- тема в групі менеджерів
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    role        TEXT NOT NULL,                    -- 'user' | 'assistant' | 'manager'
    text        TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_messages_user ON messages(user_id, id);
CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    outcome     TEXT NOT NULL,                    -- 'answered' | 'no_answer' | 'error'
    tokens_in   INTEGER DEFAULT 0,
    tokens_out  INTEGER DEFAULT 0,
    latency_ms  INTEGER DEFAULT 0,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS handoffs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    reason          TEXT,
    created_at      REAL NOT NULL,
    first_reply_at  REAL,
    closed_at       REAL
);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._lock = threading.Lock()

    def _run(self, sql: str, params: tuple = (), fetch: str | None = None):
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return cur.lastrowid

    async def q(self, sql: str, params: tuple = (), fetch: str | None = None):
        return await asyncio.to_thread(self._run, sql, params, fetch)

    # ---------------------------------------------------------------- користувачі
    async def upsert_user(self, user_id: int, username: str | None, full_name: str, lang: str | None):
        await self.q(
            "INSERT INTO users(user_id, username, full_name, lang, created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name, "
            "lang=COALESCE(excluded.lang, users.lang)",
            (user_id, username, full_name, lang, time.time()))

    async def get_user(self, user_id: int):
        return await self.q("SELECT * FROM users WHERE user_id=?", (user_id,), "one")

    async def user_by_thread(self, thread_id: int):
        return await self.q("SELECT * FROM users WHERE thread_id=?", (thread_id,), "one")

    async def set_mode(self, user_id: int, mode: str, thread_id: int | None = None):
        if thread_id is None:
            await self.q("UPDATE users SET mode=? WHERE user_id=?", (mode, user_id))
        else:
            await self.q("UPDATE users SET mode=?, thread_id=? WHERE user_id=?", (mode, thread_id, user_id))

    # ---------------------------------------------------------------- історія
    async def add_message(self, user_id: int, role: str, text: str):
        await self.q("INSERT INTO messages(user_id, role, text, created_at) VALUES(?,?,?,?)",
                     (user_id, role, text, time.time()))

    async def history(self, user_id: int, limit: int) -> list[tuple[str, str]]:
        """Останні `limit` повідомлень клієнта й бота (без менеджера), від старих до нових."""
        rows = await self.q(
            "SELECT role, text FROM messages WHERE user_id=? AND role IN ('user','assistant') "
            "ORDER BY id DESC LIMIT ?", (user_id, limit), "all")
        return [(r["role"], r["text"]) for r in reversed(rows)]

    async def transcript(self, user_id: int, limit: int = 10) -> list[tuple[str, str]]:
        rows = await self.q("SELECT role, text FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
                            (user_id, limit), "all")
        return [(r["role"], r["text"]) for r in reversed(rows)]

    async def clear_history(self, user_id: int):
        await self.q("DELETE FROM messages WHERE user_id=?", (user_id,))

    # ---------------------------------------------------------------- статистика
    async def log_question(self, user_id: int, outcome: str, tokens_in: int = 0, tokens_out: int = 0,
                           latency_ms: int = 0):
        await self.q("INSERT INTO questions(user_id, outcome, tokens_in, tokens_out, latency_ms, created_at) "
                     "VALUES(?,?,?,?,?,?)", (user_id, outcome, tokens_in, tokens_out, latency_ms, time.time()))

    async def open_handoff(self, user_id: int, reason: str) -> int:
        return await self.q("INSERT INTO handoffs(user_id, reason, created_at) VALUES(?,?,?)",
                            (user_id, reason, time.time()))

    async def waiting_first_reply(self, user_id: int) -> bool:
        row = await self.q("SELECT first_reply_at FROM handoffs WHERE user_id=? AND closed_at IS NULL "
                           "ORDER BY id DESC LIMIT 1", (user_id,), "one")
        return row is not None and row["first_reply_at"] is None

    async def mark_first_reply(self, user_id: int):
        await self.q("UPDATE handoffs SET first_reply_at=? WHERE id=(SELECT MAX(id) FROM handoffs "
                     "WHERE user_id=?) AND first_reply_at IS NULL AND closed_at IS NULL",
                     (time.time(), user_id))

    async def close_handoff(self, user_id: int):
        await self.q("UPDATE handoffs SET closed_at=? WHERE user_id=? AND closed_at IS NULL",
                     (time.time(), user_id))

    async def stats(self, since: float = 0) -> dict:
        q = await self.q(
            "SELECT COUNT(*) total, "
            "SUM(outcome='answered') answered, SUM(outcome='no_answer') no_answer, SUM(outcome='error') errors, "
            "COALESCE(SUM(tokens_in),0) tin, COALESCE(SUM(tokens_out),0) tout, AVG(latency_ms) lat "
            "FROM questions WHERE created_at>=?", (since,), "one")
        h = await self.q(
            "SELECT COUNT(*) total, AVG(first_reply_at-created_at) wait, SUM(first_reply_at IS NULL "
            "AND closed_at IS NULL) waiting FROM handoffs WHERE created_at>=?", (since,), "one")
        users = await self.q("SELECT COUNT(*) n FROM users WHERE created_at>=?", (since,), "one")
        return {
            "questions": q["total"] or 0,
            "answered": q["answered"] or 0,
            "no_answer": q["no_answer"] or 0,
            "errors": q["errors"] or 0,
            "tokens_in": q["tin"],
            "tokens_out": q["tout"],
            "avg_latency_ms": round(q["lat"]) if q["lat"] is not None else None,
            "handoffs": h["total"] or 0,
            "avg_wait_s": round(h["wait"]) if h["wait"] is not None else None,
            "waiting_now": h["waiting"] or 0,
            "new_users": users["n"] or 0,
        }
