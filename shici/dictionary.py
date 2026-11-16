"""内置词典（只读）：英语 ECDICT + Tatoeba 例句，日语 JLPT 词表 + JMdict 释义。"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

from .paths import resource_dir


# 专业领域标记，如「[计] 专有权」「[医] …」
DOMAIN_LINE = re.compile(r"^\s*(?:[a-z]{1,5}\.\s*(?:[/&]\s*[a-z]{1,5}\.\s*)*)?\[[^\]]{1,4}\]")


class Dictionary:
    def __init__(self, data_dir: Path | None = None):
        d = data_dir or resource_dir() / "data"
        self._lock = threading.RLock()
        self._db: dict[str, sqlite3.Connection] = {}
        # 释义语言：英语词 zh（英中）/ ja（日英）；日语词 zh（中日）/ en（英日）
        self.gloss = {"en": "zh", "ja": "zh"}
        self.show_domain = False  # 是否显示「[计]」「[医]」这类专业领域释义
        self._cols: dict[str, set[str]] = {}
        for lang in ("en", "ja"):
            path = d / f"dict_{lang}.db"
            if path.exists():
                # 不用 file: URI，避免路径里有 # ? 或中文用户名时出问题；用 query_only 保证只读
                con = sqlite3.connect(path, check_same_thread=False)
                con.execute("PRAGMA query_only=ON")
                con.row_factory = sqlite3.Row
                self._db[lang] = con
                self._cols[lang] = {t: {r[1] for r in con.execute(f"PRAGMA table_info({t})")} for t in ("entries", "sentences")}

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
        out = {k: row[k] for k in ("word", "phonetic", "translation", "tags", "rank")}
        out["translation"], out["auto"] = self._gloss(lang, row)
        return out

    def _gloss(self, lang: str, row) -> tuple[str, bool]:
        """按设置挑释义语言，没有就退回默认的那份；auto=True 表示释义是程序自动匹配的（非人工词典）"""
        text, auto = row["translation"] or "", False
        want = self.gloss.get(lang, "zh")
        cols = self._cols.get(lang, {}).get("entries", set())
        if lang == "en" and want == "ja" and "translation_ja" in cols and row["translation_ja"]:
            text = row["translation_ja"]
        elif lang == "ja" and want == "zh" and "translation_zh" in cols and row["translation_zh"]:
            text, auto = row["translation_zh"], row["zh_src"] in ("pivot", "ecdict")
        if not self.show_domain and lang == "en":
            lines = text.split("\n")
            keep = [l for l in lines if not DOMAIN_LINE.match(l)]
            text = "\n".join(keep) if keep else text
        return text, auto

    def examples(self, lang: str, term: str, limit: int = 3) -> list[dict]:
        """例句；zh 字段放按设置选的译文（英语词：中文或日语；日语词：中文或英文），mt=True 表示是机器翻译"""
        con = self._db.get(lang)
        if not con:
            return []
        cols = self._cols.get(lang, {}).get("sentences", set())
        extra = ", ".join(c for c in ("mt", "ja", "tr_en") if c in cols)
        with self._lock:
            rows = con.execute(
                f"SELECT s.sid, s.en, s.zh{', ' + extra if extra else ''} FROM examples e JOIN sentences s USING(sid) "
                "WHERE e.word=? ORDER BY e.rowid LIMIT ?",
                (term, limit),
            ).fetchall()
        out = []
        for r in rows:
            keys = r.keys()
            tr, mt = r["zh"], bool("mt" in keys and r["mt"])
            want = self.gloss.get(lang, "zh")
            if lang == "en" and want == "ja" and "ja" in keys and r["ja"]:
                tr, mt = r["ja"], False
            elif lang == "ja" and want == "en" and "tr_en" in keys and r["tr_en"]:
                tr, mt = r["tr_en"], False
            out.append({"en": r["en"], "zh": tr or "", "mt": mt and bool(tr), "sid": r["sid"]})
        return out

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
