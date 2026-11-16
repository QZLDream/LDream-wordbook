"""内置词典（只读）：英语 ECDICT + Tatoeba 例句，日语 JLPT 词表 + JMdict 释义。"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .paths import resource_dir


class Dictionary:
    def __init__(self, data_dir: Path | None = None):
        d = data_dir or resource_dir() / "data"
        self._lock = threading.RLock()
        self._db: dict[str, sqlite3.Connection] = {}
        for lang in ("en", "ja"):
            path = d / f"dict_{lang}.db"
            if path.exists():
                # 不用 file: URI，避免路径里有 # ? 或中文用户名时出问题；用 query_only 保证只读
                con = sqlite3.connect(path, check_same_thread=False)
                con.execute("PRAGMA query_only=ON")
                con.row_factory = sqlite3.Row
                self._db[lang] = con

    # ---- 查词 ----
    def lookup(self, lang: str, term: str) -> dict | None:
        """返回 {word, phonetic, translation, tags, rank}；英语会尝试忽略大小写和还原词形。"""
        con = self._db.get(lang)
        term = (term or "").strip()
        if not con or not term:
            return None
        with self._lock:
            row = con.execute("SELECT * FROM entries WHERE word=?", (term,)).fetchone()
            if not row and lang == "en":
                row = con.execute(
                    "SELECT * FROM entries WHERE word=? COLLATE NOCASE ORDER BY rank LIMIT 1", (term,)
                ).fetchone()
                if not row:
                    lemma = con.execute("SELECT lemma FROM forms WHERE form=? LIMIT 1", (term.lower(),)).fetchone()
                    if lemma:
                        row = con.execute("SELECT * FROM entries WHERE word=?", (lemma[0],)).fetchone()
        if not row:
            return None
        return {k: row[k] for k in ("word", "phonetic", "translation", "tags", "rank")}

    def examples(self, lang: str, term: str, limit: int = 3) -> list[dict]:
        con = self._db.get(lang)
        if not con:
            return []
        with self._lock:
            rows = con.execute(
                "SELECT s.sid, s.en, s.zh FROM examples e JOIN sentences s USING(sid) WHERE e.word=? LIMIT ?",
                (term, limit),
            ).fetchall()
        return [{"en": r["en"], "zh": r["zh"], "sid": r["sid"]} for r in rows]

    def suggest(self, lang: str, prefix: str, limit: int = 8) -> list[dict]:
        con = self._db.get(lang)
        prefix = (prefix or "").strip()
        if not con or not prefix:
            return []
        like = prefix.replace("%", "").replace("_", "") + "%"
        collate = "COLLATE NOCASE" if lang == "en" else ""
        with self._lock:
            rows = con.execute(
                f"SELECT word, phonetic, translation FROM entries WHERE word LIKE ? {collate} ORDER BY rank LIMIT ?",
                (like, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- 词书 ----
    def books(self) -> list[dict]:
        out = []
        with self._lock:
            for lang, con in self._db.items():
                for r in con.execute("SELECT * FROM books ORDER BY sort"):
                    out.append({"id": r["id"], "title": r["title"], "subtitle": r["subtitle"],
                                "count": r["count"], "lang": lang})
        return out

    def book(self, book_id: str) -> dict | None:
        return next((b for b in self.books() if b["id"] == book_id), None)

    def book_words(self, book_id: str) -> tuple[str, list[tuple[str, int]]]:
        with self._lock:
            for lang, con in self._db.items():
                # 英语用全局词频做排名，这样同时学几本词书时也是常用词在前
                sql = ("SELECT b.word, e.rank FROM book_words b JOIN entries e ON e.word=b.word WHERE b.book=? ORDER BY b.rank"
                       if lang == "en" else "SELECT word, rank FROM book_words WHERE book=? ORDER BY rank")
                rows = con.execute(sql, (book_id,)).fetchall()
                if rows:
                    return lang, [(r["word"], r["rank"]) for r in rows]
        return "en", []
