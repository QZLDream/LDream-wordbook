"""在 build_dict.py 生成的词典上补充多语释义和例句译文。

    python tools/build_bilingual.py <源数据目录> [shici/data]

需要的源数据（放在源数据目录下）:
    ejdict/*.txt                 https://github.com/kujirahand/EJDict   英和辞典 (Public Domain)
    wikt/ja_*.jsonl              https://kaikki.org/zhwiktionary/  中文维基词典里的日语词条 (CC BY-SA 4.0)
    enwikt/ja_cmn_pivot.jsonl    英文维基词典英语词条的翻译表里，同一义项的日语/普通话译词 (CC BY-SA 4.0)
                                 （由 kaikki.org 的英语词典用 enwikt_pivot.py 提取）
    jpn_sentences.tsv.bz2 / jpn-eng_links.tsv.bz2 / eng_sentences.tsv.bz2   Tatoeba (CC BY 2.0 FR)
    mt/en_zh.tsv                 没有人工中文译文的英文例句的机器翻译（opus-mt-en-zh, mt_sentences.py 生成）

加进去的东西:
    dict_en.entries.translation_ja   日语释义（英日）
    dict_en.sentences.mt             zh 列是机器翻译时为 1
    dict_en.sentences.ja             Tatoeba 里的日语译文
    dict_en.examples                 每个词的例句重新排序：人工中文 > 机翻且译对了这个词 > 其余
    dict_ja.entries.translation_zh   中文释义（中日）；zh_src 记录来源 wikt / pivot / ecdict
    dict_ja.sentences.tr_en          Tatoeba 里的英文译文；zh 列原来放英文的，改成机翻中文并标 mt=1
"""
from __future__ import annotations

import bz2
import json
import pickle
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wikt_ja_zh  # noqa: E402

CJK = re.compile(r"[㐀-鿿]")


def read_tsv_bz2(path: Path):
    with bz2.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield line.rstrip("\n").split("\t")


def add_col(db, table, col, typ):
    cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


# ---------------------------------------------------------------- 英日释义
def ejdict_clean(meaning: str) -> str:
    senses = []
    for s in meaning.split(" / "):
        s = s.replace("『", "").replace("』", "")
        s = re.sub(r"《[^》]*\+[^》]*》", "", s)        # 《+『for』+『名』》这类语法说明
        s = re.sub(r"〈[CU]〉", "", s)
        s = re.sub(r"\s+", " ", s).strip(" ,;")
        if s and s not in senses:
            senses.append(s)
    senses = senses[:6]
    lines = ["；".join(senses[i:i + 3]) for i in range(0, len(senses), 3)]
    return "\n".join(lines)


def build_en_ja(src: Path, db: sqlite3.Connection) -> None:
    ej: dict[str, str] = {}
    for f in sorted((src / "ejdict").glob("*.txt")):
        for line in open(f, encoding="utf-8"):
            if "\t" not in line:
                continue
            w, m = line.rstrip("\n").split("\t", 1)
            if m.startswith("="):  # 「'em =them」这种只是指向别的词
                continue
            for x in w.split(","):
                ej.setdefault(x.strip(), m)
    add_col(db, "entries", "translation_ja", "TEXT")
    n = 0
    rows = db.execute("SELECT word FROM entries").fetchall()
    for (w,) in rows:
        m = ej.get(w) or ej.get(w.lower()) or ej.get(w.replace("-", " "))
        if m:
            db.execute("UPDATE entries SET translation_ja=? WHERE word=?", (ejdict_clean(m), w))
            n += 1
    print(f"  英日释义: {n} / {len(rows)}")


# ---------------------------------------------------------------- 英语例句：机翻中文、日语译文、排序
def gloss_terms(translation: str) -> list[str]:
    terms = []
    for line in (translation or "").split("\n"):
        line = re.sub(r"^\s*([a-z]{1,5}\.\s*(?:[/&]\s*[a-z]{1,5}\.)*)", "", line)
        line = re.sub(r"\[[^\]]*\]|\([^)]*\)|（[^）]*）", "", line)
        for t in re.split(r"[,，;；、\s]+", line):
            t = "".join(CJK.findall(t))
            if t:
                terms.append(t)
    return terms


def mt_consistent(zh: str, terms: list[str]) -> bool:
    """机翻里有没有出现这个词的某个中文释义（取释义里的任意两个相邻汉字，单字释义就看单字）"""
    for t in terms:
        if len(t) == 1:
            if t in zh:
                return True
        elif any(t[i:i + 2] in zh for i in range(len(t) - 1)):
            return True
    return False


def build_en_sentences(src: Path, db: sqlite3.Connection) -> None:
    add_col(db, "sentences", "mt", "INTEGER DEFAULT 0")
    add_col(db, "sentences", "ja", "TEXT")
    mt = {}
    for line in open(src / "mt" / "en_zh.tsv", encoding="utf-8"):
        k, _, zh = line.rstrip("\n").split("\t")
        mt[int(k.split(":", 1)[1])] = zh.strip()
    filled = 0
    for sid, zh in db.execute("SELECT sid, zh FROM sentences").fetchall():
        if not zh and sid in mt and mt[sid]:
            db.execute("UPDATE sentences SET zh=?, mt=1 WHERE sid=?", (mt[sid], sid))
            filled += 1
    print(f"  英文例句机翻中文: {filled}")

    # Tatoeba 日语译文
    need = {r[0] for r in db.execute("SELECT sid FROM sentences WHERE sid>0")}
    eng2jpn: dict[int, int] = {}
    for r in read_tsv_bz2(src / "jpn-eng_links.tsv.bz2"):
        j, e = int(r[0]), int(r[1])
        if e in need:
            eng2jpn.setdefault(e, j)
    want = set(eng2jpn.values())
    jpn = {int(r[0]): r[2].strip() for r in read_tsv_bz2(src / "jpn_sentences.tsv.bz2") if len(r) >= 3 and int(r[0]) in want}
    n = 0
    for e, j in eng2jpn.items():
        if j in jpn:
            db.execute("UPDATE sentences SET ja=? WHERE sid=?", (jpn[j], e))
            n += 1
    print(f"  英文例句日语译文: {n}")

    # 例句排序
    trans = {w: gloss_terms(t) for w, t in db.execute("SELECT word, translation FROM entries")}
    lemma = dict(db.execute("SELECT form, lemma FROM forms"))
    sent = {sid: (zh, m) for sid, zh, m in db.execute("SELECT sid, zh, mt FROM sentences")}
    rows = db.execute("SELECT rowid, word, sid FROM examples ORDER BY rowid").fetchall()
    by_word: dict[str, list[int]] = defaultdict(list)
    for _, w, sid in rows:
        by_word[w].append(sid)
    bad = 0

    def rank(w, sid):
        nonlocal bad
        zh, m = sent.get(sid, ("", 0))
        if zh and not m:
            return 0
        if zh and mt_consistent(zh, trans.get(w) or trans.get(lemma.get(w, ""), [])):
            return 1
        bad += 1
        return 2 if zh else 3

    db.execute("CREATE TABLE examples_new(word TEXT, sid INTEGER)")
    dropped = 0
    for w, sids in by_word.items():
        ranked = sorted(sids, key=lambda s: rank(w, s))
        if any(sent.get(s, ("", 0))[0] for s in ranked):  # 有带译文的例句时，没译文的就不要了
            keep = [s for s in ranked if sent.get(s, ("", 0))[0]]
            dropped += len(ranked) - len(keep)
            ranked = keep
        for sid in ranked:
            db.execute("INSERT INTO examples_new VALUES(?,?)", (w, sid))
    db.execute("DROP TABLE examples")
    db.execute("ALTER TABLE examples_new RENAME TO examples")
    db.execute("CREATE INDEX idx_examples ON examples(word)")
    print(f"  例句重新排序：机翻没译对这个词的 {bad} 句排到后面；去掉没有译文的 {dropped} 句")


# ---------------------------------------------------------------- 日语：中文释义
def build_ja_zh(src: Path, db: sqlite3.Connection, ecdict_db: sqlite3.Connection, t2s, only: set | None = None) -> None:
    cache = src / "wikt" / "parsed.pkl"
    if cache.exists():
        by_word, alias = pickle.load(open(cache, "rb"))
    else:
        by_word, alias = wikt_ja_zh.load(sorted((src / "wikt").glob("ja_*.jsonl")), t2s)
        pickle.dump((by_word, alias), open(cache, "wb"))

    # 维基词典英语词条翻译表：同一义项下的日语词 -> 普通话译词
    zh_vocab = set()
    for (t,) in ecdict_db.execute("SELECT translation FROM entries WHERE rank < 60000"):
        zh_vocab.update(gloss_terms(t))
    pivot: dict[str, Counter] = defaultdict(Counter)
    for line in open(src / "enwikt" / "ja_cmn_pivot.jsonl", encoding="utf-8"):
        g = json.loads(line)
        cmn = []
        for w in g["cmn"]:
            w = t2s((w.split("/")[-1] if "/" in w else w).strip())
            if re.fullmatch(r"[一-鿿]{1,6}", w) and w in zh_vocab and w not in cmn:  # 只留普通话里常见的写法（去掉方言词）
                cmn.append(w)
        for j in g["ja"]:
            j = re.sub(r"[（(].*?[)）]", "", j).strip()
            pivot[j].update(cmn)

    # ECDICT：把 JMdict 的英文释义逐个查英汉词典
    ec = {w.lower(): t for w, t in ecdict_db.execute("SELECT word, translation FROM entries WHERE rank < 80000")}

    def ec_first(gloss: str) -> str:
        g = re.sub(r"\([^)]*\)", "", gloss).strip().lower()
        g = re.sub(r"^(to|a|an|the) ", "", g)
        t = ec.get(g)
        if not t:
            return ""
        terms = gloss_terms(t.split("\n")[0])
        return terms[0] if terms else ""

    add_col(db, "entries", "translation_zh", "TEXT")
    add_col(db, "entries", "zh_src", "TEXT")
    stat = Counter()
    for word, reading, en in db.execute("SELECT word, phonetic, translation FROM entries").fetchall():
        if only is not None and word not in only:
            continue
        zh, srcname = wikt_ja_zh.definition(word, reading, by_word, alias, strict=only is not None), "wikt"
        if not zh:
            top = [w for w, n in pivot.get(word, Counter()).most_common(4)]
            if top:
                first = (en or "").split("\n")[0]
                m = re.match(r"^((?:[a-z]{1,5}\.)(?:\s*[/&]\s*[a-z]{1,5}\.)*)\s", first)
                zh, srcname = ((m.group(1) + " ") if m else "") + "；".join(top), "pivot"
        if not zh:
            lines = []
            for line in (en or "").split("\n")[:3]:
                m = re.match(r"^((?:[a-z]{1,5}\.)(?:\s*[/&]\s*[a-z]{1,5}\.)*)\s+(.*)$", line)
                pos, body = (m.group(1) + " ", m.group(2)) if m else ("", line)
                got = []
                for g in body.split(";")[:3]:
                    z = ec_first(g)
                    if z and z not in got:
                        got.append(z)
                if got:
                    lines.append(pos + "；".join(got))
            if lines:
                zh, srcname = "\n".join(lines), "ecdict"
        if zh:
            zh = zh.replace("adj-na", "adj.")
            db.execute("UPDATE entries SET translation_zh=?, zh_src=? WHERE word=? AND phonetic=?", (zh, srcname, word, reading))
            stat[srcname] += 1
        else:
            stat["none"] += 1
    print("  日语中文释义:", dict(stat))


# ---------------------------------------------------------------- 日语例句：英文译文、机翻中文
def build_ja_sentences(src: Path, db: sqlite3.Connection) -> None:
    add_col(db, "sentences", "tr_en", "TEXT")
    add_col(db, "sentences", "mt", "INTEGER DEFAULT 0")
    sids = {r[0] for r in db.execute("SELECT sid FROM sentences")}
    to_eng: dict[int, int] = {}
    for r in read_tsv_bz2(src / "jpn-eng_links.tsv.bz2"):
        j = int(r[0])
        if j in sids:
            to_eng.setdefault(j, int(r[1]))
    want = set(to_eng.values())
    eng = {int(r[0]): r[2].strip() for r in read_tsv_bz2(src / "eng_sentences.tsv.bz2") if len(r) >= 3 and int(r[0]) in want}
    mt = {}
    p = src / "mt" / "ja_en_zh.tsv"
    if p.exists():
        for line in open(p, encoding="utf-8"):
            k, _, zh = line.rstrip("\n").split("\t")
            mt[int(k.split(":", 1)[1])] = zh.strip()
    moved = 0
    for sid, zh in db.execute("SELECT sid, zh FROM sentences").fetchall():
        tr_en = eng.get(to_eng.get(sid, -1))
        if zh and not CJK.search(zh):  # 原来没有中文译文，放的是英文
            tr_en = tr_en or zh
            new = mt.get(sid, "")
            db.execute("UPDATE sentences SET tr_en=?, zh=?, mt=? WHERE sid=?", (tr_en, new, 1 if new else 0, sid))
            moved += 1
        elif tr_en:
            db.execute("UPDATE sentences SET tr_en=? WHERE sid=?", (tr_en, sid))
    print(f"  日语例句：{moved} 句原来只有英文译文，改为机翻中文")


def main() -> None:
    src = Path(sys.argv[1])
    data = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "shici" / "data"
    try:
        from opencc import OpenCC
        t2s = OpenCC("t2s").convert
    except ImportError:
        t2s = lambda s: s  # noqa: E731
    en = sqlite3.connect(data / "dict_en.db")
    ja = sqlite3.connect(data / "dict_ja.db")
    print("dict_en.db")
    build_en_ja(src, en)
    build_en_sentences(src, en)
    en.execute("INSERT OR REPLACE INTO meta VALUES('source', ?)",
               ("ECDICT (MIT) + Tatoeba (CC BY 2.0 FR) + EJDict-hand (Public Domain) + opus-mt-en-zh 机器翻译",))
    en.commit()
    print("dict_ja.db")
    build_ja_zh(src, ja, en, t2s)
    build_ja_sentences(src, ja)
    ja.execute("INSERT OR REPLACE INTO meta VALUES('source', ?)",
               ("JLPT lists by Jonathan Waller, tanos.co.uk (CC BY) + JMdict, EDRDG (CC BY-SA 4.0) + Wiktionary (CC BY-SA 4.0) + Tatoeba (CC BY 2.0 FR)",))
    ja.commit()
    for db in (en, ja):
        db.execute("VACUUM")
        db.close()


if __name__ == "__main__":
    main()
