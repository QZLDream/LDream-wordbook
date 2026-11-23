"""给没有例句的词补上例句（1.1.4）。

    python tools/own_examples.py [shici/data]

1. 日语：同一个读音、写法不同的词（明い ↔ 明るい、其れでは ↔ それでは、さ来年 ↔ 再来年）共用例句。
2. 还是没有的，用本项目自己写的例句：tools/extra_examples_en.tsv、tools/extra_examples_ja.tsv（词 \\t 例句 \\t 中文译文）。
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from refine_examples import related  # noqa: E402

HERE = Path(__file__).parent
KANJI = re.compile(r"[一-鿿]")
KANA = re.compile(r"[぀-ヿー・]+")


def siblings_ja(db: sqlite3.Connection) -> int:
    ent = {w: (p or w, zh or "") for w, p, zh in db.execute("SELECT word, phonetic, translation_zh FROM entries")}
    has = {w for (w,) in db.execute("SELECT DISTINCT word FROM examples")}
    by_read: dict[str, list[str]] = {}
    for w, (p, _) in ent.items():
        if w in has:
            by_read.setdefault(p, []).append(w)
    n = 0
    for w, (p, zh) in ent.items():
        if w in has:
            continue
        ks = set(KANJI.findall(w))
        for c in by_read.get(p, []):
            kc = set(KANJI.findall(c))
            same = (ks and ks & kc) or (KANA.fullmatch(c) and c == p) or (KANA.fullmatch(w) and w == p and kc)
            if same and (not zh or not ent[c][1] or related(zh, ent[c][1])):
                db.executemany("INSERT INTO examples(word, sid) VALUES(?,?)",
                               [(w, sid) for (sid,) in db.execute("SELECT sid FROM examples WHERE word=? ORDER BY rowid", (c,))])
                n += 1
                break
    return n


def own(db: sqlite3.Connection, path: Path, lang: str) -> int:
    if not path.exists():
        return 0
    has = {w for (w,) in db.execute("SELECT DISTINCT word FROM examples")}
    words = {w for (w,) in db.execute("SELECT word FROM entries")}
    sid = min(0, db.execute("SELECT MIN(sid) FROM sentences").fetchone()[0] or 0) - 1
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) != 3 or p[0] not in words or p[0] in has:
            continue
        if lang == "en":
            db.execute("INSERT INTO sentences(sid, en, zh, mt) VALUES(?,?,?,0)", (sid, p[1], p[2]))
        else:
            db.execute("INSERT INTO sentences(sid, en, zh, mt) VALUES(?,?,?,0)", (sid, p[1], p[2]))
        db.execute("INSERT INTO examples(word, sid) VALUES(?,?)", (p[0], sid))
        sid -= 1
        n += 1
    return n


def main() -> None:
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "shici" / "data"
    ja = sqlite3.connect(data / "dict_ja.db")
    print(f"日语：同音异写共用例句 {siblings_ja(ja)} 个词，自编例句 {own(ja, HERE / 'extra_examples_ja.tsv', 'ja')} 个词")
    ja.commit()
    en = sqlite3.connect(data / "dict_en.db")
    print(f"英语：自编例句 {own(en, HERE / 'extra_examples_en.tsv', 'en')} 个词")
    en.commit()
    for db, name in ((ja, "dict_ja"), (en, "dict_en")):
        if name == "dict_ja":
            left = db.execute("SELECT COUNT(*) FROM entries e WHERE NOT EXISTS (SELECT 1 FROM examples x WHERE x.word=e.word)").fetchone()[0]
        else:
            left = db.execute("SELECT COUNT(DISTINCT w.word) FROM book_words w WHERE NOT EXISTS (SELECT 1 FROM examples x WHERE x.word=w.word)").fetchone()[0]
        print(f"  {name} 仍然没有例句的词：{left}")


if __name__ == "__main__":
    main()
