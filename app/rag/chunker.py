"""Розбиття бази знань на фрагменти (чанки) для векторного пошуку.

Markdown-файл ділиться за заголовками на розділи, а довгі розділи — на шматки
до `max_chars` символів із перекриттям `overlap`. До кожного чанка додається
шлях заголовків («Доставка › Нова Пошта»), щоб модель розуміла контекст.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str
    section: str


def _sections(markdown: str) -> list[tuple[str, str]]:
    """Повертає список (шлях заголовків, текст розділу)."""
    path: list[str] = []
    result: list[tuple[str, list[str]]] = []
    current: list[str] = []

    def flush():
        body = "\n".join(current).strip()
        if body:
            result.append((" › ".join(path), body))

    for line in markdown.splitlines():
        m = HEADING.match(line)
        if m:
            flush()
            current = []
            level = len(m.group(1))
            path[:] = path[: level - 1] + [m.group(2)]
        else:
            current.append(line)
    flush()
    return [(p, b) for p, b in result]


def _split(text: str, max_chars: int, overlap: int) -> list[str]:
    """Ділить текст на шматки за абзацами, а дуже довгі абзаци — за реченнями."""
    if len(text) <= max_chars:
        return [text]
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            units.append(para)
        else:
            units.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip())

    chunks: list[str] = []
    cur = ""
    for u in units:
        candidate = f"{cur}\n\n{u}".strip() if cur else u
        if len(candidate) <= max_chars:
            cur = candidate
            continue
        if cur:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            # починаємо наступний шматок з кінця попереднього (з межі слова)
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            cur = f"{tail}\n\n{u}".strip() if tail else u
        else:
            cur = u
        while len(cur) > max_chars:  # одне «речення» довше за ліміт
            chunks.append(cur[:max_chars])
            cur = cur[max_chars - overlap:]
    if cur:
        chunks.append(cur)
    return chunks


def chunk_markdown(markdown: str, source: str, max_chars: int = 900, overlap: int = 120) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section, body in _sections(markdown):
        for i, part in enumerate(_split(body, max_chars, overlap)):
            text = f"{section}\n{part}" if section else part
            digest = hashlib.sha1(f"{source}|{section}|{i}|{part}".encode()).hexdigest()[:16]
            chunks.append(Chunk(id=digest, text=text, source=source, section=section))
    return chunks


def load_chunks(folder: Path, max_chars: int = 900, overlap: int = 120) -> list[Chunk]:
    """Читає всі .md і .txt файли з папки бази знань."""
    chunks: list[Chunk] = []
    for path in sorted(folder.glob("*")):
        if path.suffix.lower() in {".md", ".txt"} and path.is_file():
            chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.name, max_chars, overlap))
    return chunks
