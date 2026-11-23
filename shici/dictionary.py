"""内置词典（只读）：英语 ECDICT + Tatoeba 例句，日语 JLPT 词表 + JMdict 释义。"""
from __future__ import annotations

import json
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

    # ---- 例句里长按查词 ----
    I_TO_U = dict(zip("いきぎしちにびみり", "うくぐすつぬぶむる"))

    def peek(self, lang: str, text: str, index: int) -> tuple[list[dict], list[int]]:
        """长按例句里的一个词：返回可能的词条（最多 3 个，最像的在前）。

        英语：先按原样查（makes 本身也是词条），再查原形（makes → make）。
        日语：句子里没有空格，从按住的位置往两边找词典里最长的词；动词、形容词变了形的，试着还原（食べ → 食べる、行き → 行く）。
        """
        con = self._db.get(lang)
        if not con or not text:
            return [], []
        index = max(0, min(index, len(text) - 1))
        words: list[str] = []
        span: list[int] = []
        with self._lock:
            has = lambda w: con.execute("SELECT 1 FROM entries WHERE word=?", (w,)).fetchone() is not None  # noqa: E731
            if lang == "en":
                m = None
                for m in re.finditer(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", text):
                    if m.start() <= index < m.end():
                        break
                else:
                    m = None
                if not m:
                    return [], []
                w = m.group(0)
                span = [m.start(), m.end()]
                for cand in (w, w.lower(), w.split("'")[0], w.split("'")[0].lower()):
                    row = con.execute("SELECT word FROM entries WHERE word=? COLLATE NOCASE ORDER BY rank LIMIT 1", (cand,)).fetchone()
                    if row:
                        words.append(row[0])
                        break
                for (lem,) in con.execute("SELECT DISTINCT lemma FROM forms WHERE form=? LIMIT 3", (w.lower().split("'")[0],)):
                    if lem not in words and has(lem):
                        words.append(lem)
            else:
                found: list[tuple] = []  # (覆盖的字数, 是否靠猜词形, 起点离按住位置的距离, 词)
                for start in range(index, max(-1, index - 8), -1):
                    for end in range(min(len(text), start + 10), index, -1):
                        s = text[start:end]
                        if not s.strip() or re.fullmatch(r"[\W\d]+", s) or re.fullmatch(r"[\u3040-\u309f]", s):
                            continue  # 单个平假名多半是助词，不单独查
                        rest = text[end:]
                        verbish = rest.startswith(("ま", "た", "て", "ない", "なかっ", "そう", "に行", "ながら"))
                        cands: list[tuple[str, bool]] = []
                        last = s[-1]
                        if verbish and last in self.I_TO_U:
                            cands.append((s[:-1] + self.I_TO_U[last], False))  # 行き(ます) → 行く
                        if rest.startswith(("て", "た", "で", "だ")):  # て形、た形：歩い(て) → 歩く、待っ(て) → 待つ、読ん(で) → 読む
                            cands += [(s[:-1] + e, False) for e in {"い": "くぐ", "っ": "うつる", "ん": "むぶぬ"}.get(last, "")]
                        cands.append((s, False))
                        if re.search(r"[\u3040-\u309f]$", s):
                            if not s.endswith(("が", "を", "に", "は", "で", "と", "の", "へ", "も")):
                                cands += [(s + "る", True), (s + "い", True)]
                                if last in self.I_TO_U:
                                    cands.append((s[:-1] + self.I_TO_U[last], True))
                                if s.endswith(("かっ", "く", "けれ")):
                                    cands.append((re.sub(r"(かっ|く|けれ)$", "い", s), True))
                        elif verbish or rest.startswith(("し", "する", "さ")):
                            cands += [(s + "る", True), (s + "する", True)]
                        for c, guess in cands:
                            if has(c):
                                found.append((end - start, guess, index - start, c, start, end))
                                break
                for _, _, _, w, a, b in sorted(found, key=lambda x: (-x[0], x[1], x[2])):
                    if not span:
                        span = [a, b]
                    if w not in words:
                        words.append(w)
        out = []
        for w in words[:3]:
            e = self.lookup(lang, w)
            if e:
                out.append(e)
        return out, span

    # ---- 词根、近义词 / 反义词（只有英语） ----
    def _has(self, table: str) -> bool:
        con = self._db.get("en")
        if not con:
            return False
        key = "__t_" + table
        if key not in self._cols:
            self._cols[key] = bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())
        return self._cols[key]

    def _base(self, con, word: str, table: str):
        """先按原词查，查不到再按原形（went → go）查"""
        w = word.strip().lower()
        row = con.execute(f"SELECT * FROM {table} WHERE word=?", (w,)).fetchone()
        if not row:
            lemma = con.execute("SELECT lemma FROM forms WHERE form=? LIMIT 1", (w,)).fetchone()
            if lemma:
                row = con.execute(f"SELECT * FROM {table} WHERE word=?", (lemma[0].lower(),)).fetchone()
        return row

    def short_gloss(self, word: str) -> str:
        """很短的释义（一两个词），给同根词、近义词后面注一下"""
        e = self.lookup("en", word)
        if not e:
            return ""
        line = next((l for l in e["translation"].split("\n") if l.strip() and not DOMAIN_LINE.match(l)), "")
        line = re.sub(r"^\s*(?:[a-z]{1,5}\.\s*(?:[/&]\s*[a-z]{1,5}\.\s*)*)", "", line)
        first = re.split(r"[,，;；]", line)[0].strip()
        return first[:10]

    def morph(self, word: str) -> dict | None:
        """词根拆分：{parts: [{t, k, m}], family: [{w, g}]}；k = p 前缀 / r 词根 / s 后缀 / w 英语单词"""
        con = self._db.get("en")
        if not con or not self._has("morph"):
            return None
        with self._lock:
            row = self._base(con, word, "morph")
            if not row:
                return None
            parts = [{"t": t, "k": k, "m": m} for t, k, m in json.loads(row["parts"])]
            fam = []
            root = con.execute("SELECT root FROM morph_root WHERE word=? LIMIT 1", (row["word"],)).fetchone()
            if root:
                fam = [r[0] for r in con.execute(
                    "SELECT word FROM morph_root WHERE root=? AND word<>? ORDER BY score LIMIT 6", (root[0], row["word"]))]
        for p in parts:
            if p["k"] == "w":
                p["m"] = self.short_gloss(p["t"])
        return {"word": row["word"], "parts": parts, "family": [{"w": w, "g": self.short_gloss(w)} for w in fam]}

    def related(self, word: str) -> dict | None:
        """近义词 / 反义词：{syn: [{w, g}], ant: [{w, g}]}"""
        con = self._db.get("en")
        if not con or not self._has("related"):
            return None
        with self._lock:
            row = self._base(con, word, "related")
        if not row:
            return None
        pack = lambda ws: [{"w": w, "g": self.short_gloss(w)} for w in json.loads(ws)]
        return {"syn": pack(row["syn"]), "ant": pack(row["ant"])}

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

    def revision(self) -> str:
        """词典数据的版本：修正过词书归属（比如 1.1.2 修正日语读音）时会变，程序据此给已加入的词书补上新词。"""
        out = []
        with self._lock:
            for lang, con in sorted(self._db.items()):
                try:
                    r = con.execute("SELECT v FROM meta WHERE k='rev'").fetchone()
                except sqlite3.Error:
                    r = None
                out.append(f"{lang}:{r[0] if r else ''}")
        return ",".join(out)

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
