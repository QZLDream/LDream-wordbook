"""构建程序内置的词典数据（shici/data/dict_en.db 与 dict_ja.db）。

普通用户不需要运行这个脚本，仓库里已经带了构建好的数据库。
只有想更新词典数据时才需要：

    pip install opencc-python-reimplemented pyopenjtalk
    python tools/build_dict.py --src <下载目录>

<下载目录> 里需要有以下文件（脚本不会自动下载）：

    ecdict.csv                 https://github.com/skywind3000/ECDICT            (MIT)
    eng_sentences.tsv.bz2      https://downloads.tatoeba.org/exports/per_language/eng/   (CC BY 2.0 FR)
    cmn_sentences.tsv.bz2      https://downloads.tatoeba.org/exports/per_language/cmn/
    eng-cmn_links.tsv.bz2      https://downloads.tatoeba.org/exports/per_language/eng/
    jpn_sentences.tsv.bz2      https://downloads.tatoeba.org/exports/per_language/jpn/   （日语例句）
    jpn-cmn_links.tsv.bz2      同上
    jpn-eng_links.tsv.bz2      同上
    nltk/corpora/wordnet/      WordNet 3.0 数据文件（可选；用来给没有例句的生僻词补用法示例）
    JLPT_vocab_ALL.csv         https://github.com/Bluskyo/JLPT_Vocabulary (数据来自 tanos.co.uk, CC BY)
    JMdict_e.gz                http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz     (CC BY-SA 4.0)
"""
from __future__ import annotations

import argparse
import bz2
import csv
import gzip
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "shici" / "data"

EN_BOOKS = [
    # id, 标题, 副标题, ECDICT 标签
    ("cet4", "四级", "CET-4", "cet4"),
    ("cet6", "六级", "CET-6", "cet6"),
    ("ky", "考研", "POSTGRADUATE", "ky"),
    ("toefl", "托福", "TOEFL", "toefl"),
    ("ielts", "雅思", "IELTS", "ielts"),
    ("gre", "GRE", "GRE", "gre"),
    ("gk", "高考", "GAOKAO", "gk"),
    ("zk", "中考", "ZHONGKAO", "zk"),
]

PHONETIC_FIX = str.maketrans({"ә": "ə", "'": "ˈ", ",": "ˌ", ":": "ː", "g": "ɡ"})


def to_int(s: str) -> int:
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def clean_translation(s: str) -> str:
    lines = [ln.strip() for ln in s.replace("\\n", "\n").split("\n")]
    lines = [ln for ln in lines if ln]
    # “[网络]” 一行通常是机器抓取的杂项，已有正式释义时去掉
    formal = [ln for ln in lines if not ln.startswith("[网络]")]
    return "\n".join(formal or lines)


# ---------------------------------------------------------------- 英语 ----
def build_en(src: Path) -> None:
    out = OUT / "dict_en.db"
    out.unlink(missing_ok=True)
    db = sqlite3.connect(out)
    db.executescript(
        """
        CREATE TABLE entries(
            word TEXT PRIMARY KEY, phonetic TEXT, translation TEXT,
            tags TEXT, rank INTEGER, exchange TEXT);
        CREATE INDEX idx_entries_nocase ON entries(word COLLATE NOCASE);
        CREATE TABLE forms(form TEXT, lemma TEXT);
        CREATE TABLE sentences(sid INTEGER PRIMARY KEY, en TEXT, zh TEXT);
        CREATE TABLE examples(word TEXT, sid INTEGER);
        CREATE TABLE books(id TEXT PRIMARY KEY, title TEXT, subtitle TEXT, count INTEGER, sort INTEGER);
        CREATE TABLE book_words(book TEXT, word TEXT, rank INTEGER, PRIMARY KEY(book, word)) WITHOUT ROWID;
        CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
        """
    )
    word_ok = re.compile(r"^[A-Za-z][A-Za-z\-'. ]*$")
    entries: dict[str, tuple] = {}
    forms: dict[str, set[str]] = defaultdict(set)
    with open(src / "ecdict.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            w = r["word"].strip()
            tags = r["tag"].strip()
            frq, bnc = to_int(r["frq"]), to_int(r["bnc"])
            keep = tags or frq or bnc or to_int(r["collins"]) or r["oxford"].strip()
            if not keep or not word_ok.match(w) or len(w) > 40:
                continue
            tr = clean_translation(r["translation"])
            if not tr:
                continue
            rank = frq or bnc or 999999
            entries[w] = (w, r["phonetic"].strip().translate(PHONETIC_FIX), tr, tags, rank, r["exchange"].strip())
    for w, e in entries.items():
        for part in e[5].split("/"):
            if ":" not in part:
                continue
            kind, val = part.split(":", 1)
            if kind == "0":  # 本词是 val 的变形
                forms[w.lower()].add(val)
            elif kind != "1" and val:  # val 是本词的变形
                forms[val.lower()].add(w)
    db.executemany("INSERT INTO entries VALUES(?,?,?,?,?,?)", entries.values())
    db.executemany(
        "INSERT INTO forms VALUES(?,?)",
        [(f, lemma) for f, ls in forms.items() for lemma in ls if lemma in entries and f != lemma.lower()],
    )
    db.execute("CREATE INDEX idx_forms ON forms(form)")

    for sort, (bid, title, sub, tag) in enumerate(EN_BOOKS):
        words = sorted((e for e in entries.values() if tag in e[3].split()), key=lambda e: (e[4], e[0].lower()))
        db.executemany("INSERT INTO book_words VALUES(?,?,?)", [(bid, e[0], i) for i, e in enumerate(words)])
        db.execute("INSERT INTO books VALUES(?,?,?,?,?)", (bid, title, sub, len(words), sort))
        print(f"  词书 {bid}: {len(words)} 词")

    build_examples(src, db, entries, forms)
    db.execute("INSERT INTO meta VALUES('source','ECDICT (MIT) + Tatoeba (CC BY 2.0 FR)')")
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(f"dict_en.db: {len(entries)} 词条, {out.stat().st_size / 1e6:.1f} MB")


def build_examples(src: Path, db: sqlite3.Connection, entries: dict, forms: dict) -> None:
    try:
        from opencc import OpenCC
        t2s = OpenCC("t2s").convert
    except ImportError:  # 没装 OpenCC 就保留原文
        print("  (未安装 opencc，例句中的繁体字不会转换)")
        t2s = lambda s: s  # noqa: E731

    def read(name):
        with bz2.open(src / name, "rt", encoding="utf-8") as f:
            for line in f:
                yield line.rstrip("\n").split("\t")

    cmn = {int(r[0]): r[2] for r in read("cmn_sentences.tsv.bz2") if len(r) >= 3}
    link: dict[int, int] = {}
    for r in read("eng-cmn_links.tsv.bz2"):
        e, c = int(r[0]), int(r[1])
        if c in cmn and (e not in link or len(cmn[c]) < len(cmn[link[e]])):
            link[e] = c
    lower = {w.lower(): w for w in entries}
    token = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")
    cands: dict[str, list[tuple[int, int]]] = defaultdict(list)
    sents: dict[int, tuple[str, str]] = {}
    for r in read("eng_sentences.tsv.bz2"):
        sid = int(r[0])
        if sid not in link or len(r) < 3:
            continue
        en = r[2].strip()
        zh = t2s(cmn[link[sid]].strip())
        if not (18 <= len(en) <= 110) or len(zh) > 60 or len(zh) < 3:
            continue
        sents[sid] = (en, zh)
        seen = set()
        for tk in token.findall(en):
            t = tk.lower()
            heads = set()
            if t in lower:
                heads.add(lower[t])
            heads.update(forms.get(t, ()))
            for h in heads:
                if h in entries and h not in seen:
                    seen.add(h)
                    cands[h].append((abs(len(en) - 52), sid))
    used: set[int] = set()
    rows = []
    count: dict[str, int] = defaultdict(int)
    for w, cs in cands.items():
        cs.sort()
        for _, sid in cs[:3]:
            rows.append((w, sid))
            used.add(sid)
            count[w] += 1
    paired = len(cands)

    # 第二轮：有中文译文的句子不够 3 条的词，用 Tatoeba 里只有英文的句子补上（界面上不显示译文）
    import heapq
    ok_sentence = re.compile(r"^[A-Z][A-Za-z0-9 ,;:'\"\-()]{22,98}[.?!]$")
    extra: dict[str, list[tuple[float, int, str]]] = defaultdict(list)
    for r in read("eng_sentences.tsv.bz2"):
        sid = int(r[0])
        if sid in sents or len(r) < 3:
            continue
        en = r[2].strip()
        if not ok_sentence.match(en):
            continue
        seen = set()
        for tk in token.findall(en):
            t = tk.lower()
            heads = set(forms.get(t, ()))
            if t in lower:
                heads.add(lower[t])
            for h in heads:
                if h in seen or h not in entries or count[h] >= 3:
                    continue
                seen.add(h)
                heap, item = extra[h], (-abs(len(en) - 55), sid, en)
                if len(heap) < 3 - count[h]:
                    heapq.heappush(heap, item)
                elif item > heap[0]:
                    heapq.heapreplace(heap, item)
    for w, heap in extra.items():
        for _, sid, en in sorted(heap, reverse=True):
            sents[sid] = (en, "")
            rows.append((w, sid))
            used.add(sid)
            count[w] += 1
    mono = sum(1 for w in extra if w not in cands)

    # 带连字符、句点或空格的词条（T-shirt、Mr.、account for…）按字母切词匹配不到，单独整词查找
    special = {w: re.compile(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", re.I)
               for w, e in entries.items() if e[3] and count[w] == 0 and re.search(r"[^A-Za-z]", w)}
    if special:
        keys = [(w, re.split(r"[^a-z]", w.lower())[0][:4] or w.lower()[:2]) for w in special]
        loose = re.compile(r"^[A-Z][A-Za-z0-9 ,;:'\"\-().]{22,98}[.?!]$")
        for r in read("eng_sentences.tsv.bz2"):
            if len(r) < 3 or not loose.match(r[2]):
                continue
            en, low = r[2].strip(), r[2].lower()
            for w, k in keys:
                if count[w] < 2 and k in low and special[w].search(en):
                    sid = int(r[0])
                    sents.setdefault(sid, (en, ""))
                    rows.append((w, sid))
                    used.add(sid)
                    count[w] += 1

    # 第三轮：还是一条都没有的词，用 WordNet 词条里的用法示例（多是短语）
    wn_rows = wordnet_examples(src, {w for w in entries if count[w] == 0}, forms, lower)
    next_id = -1
    for w, phrases in wn_rows.items():
        for ph in phrases[:2]:
            sents[next_id] = (ph, "")
            rows.append((w, next_id))
            used.add(next_id)
            count[w] += 1
            next_id -= 1

    # 第四轮：考试词汇里仍然没有例句的生僻词，用本项目自己编写的例句（带中文译文）
    own = 0
    extra_file = Path(__file__).with_name("extra_examples_en.tsv")
    if extra_file.exists():
        for line in extra_file.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) != 3 or parts[0] not in entries or count[parts[0]]:
                continue
            sents[next_id] = (parts[1], parts[2])
            rows.append((parts[0], next_id))
            used.add(next_id)
            count[parts[0]] += 1
            next_id -= 1
            own += 1

    db.executemany("INSERT INTO sentences VALUES(?,?,?)", [(s, *sents[s]) for s in used])
    db.executemany("INSERT INTO examples VALUES(?,?)", rows)
    db.execute("CREATE INDEX idx_examples ON examples(word)")
    tagged = [w for w, e in entries.items() if e[3]]
    print(f"  例句: {len(used)} 句; 有中文译文的词 {paired}，只有英文例句的词 {mono}，WordNet 补充 {len(wn_rows)}，自编 {own}")
    print(f"  考试词汇有例句的比例: {sum(1 for w in tagged if count[w]) / len(tagged):.0%}")
    for bid, _, _, tag in EN_BOOKS:
        ws = [w for w, e in entries.items() if tag in e[3].split()]
        print(f"    {bid}: 有例句 {sum(1 for w in ws if count[w]) / len(ws):.0%}，其中带中文译文 {sum(1 for w in ws if w in cands) / len(ws):.0%}")


def wordnet_examples(src: Path, need: set[str], forms: dict, lower: dict) -> dict[str, list[str]]:
    """从 WordNet 3.0 的 data.* 文件里取用法示例。src/nltk/corpora/wordnet 不存在就跳过。"""
    base = src / "nltk" / "corpora" / "wordnet"
    out: dict[str, list[str]] = defaultdict(list)
    if not base.exists() or not need:
        return out
    token = re.compile(r"[A-Za-z]+")
    for pos in ("noun", "verb", "adj", "adv"):
        for line in open(base / f"data.{pos}", encoding="utf-8"):
            if line.startswith("  ") or "|" not in line:
                continue
            head, gloss = line.split("|", 1)
            parts = head.split()
            n = int(parts[3], 16)
            lemmas = {parts[4 + 2 * i].split("(")[0].replace("_", " ").lower() for i in range(n)}
            for ex in re.findall(r'"([^"]{12,90})"', gloss):
                toks = {t.lower() for t in token.findall(ex)}
                for t in toks:
                    for h in ({lower[t]} if t in lower else set()) | set(forms.get(t, ())):
                        if h in need and h.lower() in lemmas and ex not in out[h] and len(out[h]) < 2:
                            out[h].append(ex[0].upper() + ex[1:])
    return out


# ---------------------------------------------------------------- 日语 ----
POS_SHORT = [
    ("pronoun", "pron."), ("adjectiv", "adj."), ("adverb", "adv."), ("noun", "n."),
    ("verb", "v."), ("particle", "part."), ("conjunction", "conj."), ("interjection", "int."),
    ("expression", "exp."), ("suffix", "suf."), ("prefix", "pref."), ("counter", "ctr."), ("numeric", "num."),
    ("auxiliary", "aux."), ("copula", "cop."),
]


def short_pos(pos_list: list[str]) -> str:
    out = []
    for p in pos_list:
        pl = p.lower()
        for key, short in POS_SHORT:
            if key in pl:
                if short not in out:
                    out.append(short)
                break
    return "/".join(out[:2])


def build_ja(src: Path) -> None:
    out = OUT / "dict_ja.db"
    out.unlink(missing_ok=True)
    by_keb: dict[str, list] = defaultdict(list)
    by_reb: dict[str, list] = defaultdict(list)
    with gzip.open(src / "JMdict_e.gz", "rb") as f:
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag != "entry":
                continue
            kebs = [k.findtext("keb") for k in el.findall("k_ele")]
            rebs = [r.findtext("reb") for r in el.findall("r_ele")]
            pri = [p.text for p in el.iter("ke_pri")] + [p.text for p in el.iter("re_pri")]
            nf = min((int(p[2:]) for p in pri if p and p.startswith("nf")), default=99)
            common = any(p in ("news1", "ichi1", "spec1", "gai1") for p in pri)
            uk = any("usually written using kana" in (m.text or "") for m in el.iter("misc"))
            senses, last_pos = [], []
            for s in el.findall("sense"):
                pos = [p.text or "" for p in s.findall("pos")] or last_pos
                last_pos = pos
                gl = [g.text for g in s.findall("gloss") if g.text]
                if gl:
                    senses.append((short_pos(pos), "; ".join(gl[:3])))
            lines, prev = [], None
            for p, g in senses[:3]:
                lines.append(f"{p} {g}".strip() if p and p != prev else g)
                prev = p
            entry = {"rebs": rebs, "kebs": kebs, "nf": nf, "common": common, "uk": uk, "meaning": "\n".join(lines)}
            for k in kebs:
                by_keb[k].append(entry)
            for r in rebs:
                by_reb[r].append(entry)
            el.clear()

    def find(term: str, reading: str):
        t = re.sub(r"[()（）]", "", term)
        r = re.sub(r"[()（）]", "", reading)
        pools = [
            [e for e in by_keb.get(t, []) if r in e["rebs"]],
            by_keb.get(t, []),
            # 纯假名词：优先“通常用假名书写”或本来就没有汉字写法的词条
            [e for e in by_reb.get(r, []) if e["uk"] or not e["kebs"]],
            by_reb.get(r, []),
        ]
        for pool in pools:
            if pool:
                return sorted(pool, key=lambda e: (not e["common"], e["nf"]))[0]
        return None

    db = sqlite3.connect(out)
    db.executescript(
        """
        CREATE TABLE entries(word TEXT, phonetic TEXT, translation TEXT, tags TEXT, rank INTEGER,
                             PRIMARY KEY(word, phonetic));
        CREATE TABLE books(id TEXT PRIMARY KEY, title TEXT, subtitle TEXT, count INTEGER, sort INTEGER);
        CREATE TABLE book_words(book TEXT, word TEXT, rank INTEGER, PRIMARY KEY(book, word)) WITHOUT ROWID;
        CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
        """
    )
    levels: dict[str, list] = defaultdict(list)
    seen, miss, total = set(), 0, 0
    with open(src / "JLPT_vocab_ALL.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            term, reading, lv = r["Kanji"].strip(), r["Reading"].strip(), r["Level"].strip()
            term = re.sub(r"\s*[(（]=.*?[)）]", "", term).strip()
            reading = re.sub(r"\s*[(（]=.*?[)）]", "", reading).strip()
            if not term or term in seen:
                continue
            seen.add(term)
            total += 1
            reading = re.sub(r"[(（].*$", "", reading).strip()
            e = find(term, reading or term)
            if not e or not e["meaning"]:  # 原始词表里有少量残缺条目，查不到释义的直接丢弃
                miss += 1
                continue
            levels[lv].append((term, "" if reading == term else reading, e["meaning"], f"n{lv}", e["nf"]))
    for lv in sorted(levels, reverse=True):  # N5 → N1
        rows = sorted(levels[lv], key=lambda x: x[4])
        db.executemany("INSERT OR IGNORE INTO entries VALUES(?,?,?,?,?)", rows)
        db.executemany("INSERT OR IGNORE INTO book_words VALUES(?,?,?)", [(f"jlpt-n{lv}", x[0], i) for i, x in enumerate(rows)])
        db.execute("INSERT INTO books VALUES(?,?,?,?,?)", (f"jlpt-n{lv}", f"JLPT N{lv}", "日本語能力試験", len(rows), 20 - int(lv)))
        print(f"  词书 jlpt-n{lv}: {len(rows)} 词")
    build_ja_examples(src, db)
    db.execute("INSERT INTO meta VALUES('source','JLPT lists by Jonathan Waller, tanos.co.uk (CC BY) + JMdict, EDRDG (CC BY-SA 4.0) + Tatoeba (CC BY 2.0 FR)')")
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(f"dict_ja.db: {total} 词, 丢弃无释义条目 {miss} 个, {out.stat().st_size / 1e6:.1f} MB")


def build_ja_examples(src: Path, db: sqlite3.Connection) -> None:
    """给 JLPT 词汇配 Tatoeba 例句：优先用有中文译文的句子，没有就用英文译文。"""
    import pyopenjtalk

    try:
        from opencc import OpenCC
        t2s = OpenCC("t2s").convert
    except ImportError:
        t2s = lambda s: s  # noqa: E731

    def read(name):
        with bz2.open(src / name, "rt", encoding="utf-8") as f:
            for line in f:
                yield line.rstrip("\n").split("\t")

    db.executescript(
        """
        CREATE TABLE sentences(sid INTEGER PRIMARY KEY, en TEXT, zh TEXT);  -- en 列放日语原句，zh 列放译文
        CREATE TABLE examples(word TEXT, sid INTEGER);
        """
    )
    cmn = {int(r[0]): r[2] for r in read("cmn_sentences.tsv.bz2") if len(r) >= 3}
    to_cmn: dict[int, int] = {}
    for r in read("jpn-cmn_links.tsv.bz2"):
        j, c = int(r[0]), int(r[1])
        if c in cmn and (j not in to_cmn or len(cmn[c]) < len(cmn[to_cmn[j]])):
            to_cmn[j] = c
    to_eng: dict[int, int] = {}
    for r in read("jpn-eng_links.tsv.bz2"):
        to_eng.setdefault(int(r[0]), int(r[1]))
    need_eng = {e for j, e in to_eng.items() if j not in to_cmn}
    eng = {int(r[0]): r[2] for r in read("eng_sentences.tsv.bz2") if len(r) >= 3 and int(r[0]) in need_eng}

    vocab = {r[0] for r in db.execute("SELECT word FROM entries")}
    clean = {re.sub(r"[()（）～〜]", "", w): w for w in vocab}
    cands: dict[str, list[tuple[float, int]]] = defaultdict(list)
    sents: dict[int, tuple[str, str]] = {}
    n = 0
    for r in read("jpn_sentences.tsv.bz2"):
        sid, jp = int(r[0]), r[2].strip()
        if not (7 <= len(jp) <= 38):
            continue
        if sid in to_cmn:
            tr, bonus = t2s(cmn[to_cmn[sid]].strip()), 0.0
        elif sid in to_eng and to_eng[sid] in eng:
            tr, bonus = eng[to_eng[sid]].strip(), 30.0  # 英文译文的句子排在中文译文之后
        else:
            continue
        if not tr or len(tr) > 90:
            continue
        toks = pyopenjtalk.run_frontend(jp)
        surf = [t["string"] for t in toks]
        found = {t["orig"] for t in toks if t["pos"] not in ("助詞", "助動詞", "記号")}
        for k in (2, 3):  # 被切成几段的词（お姉さん、勉強する…）
            found.update("".join(surf[i:i + k]) for i in range(len(surf) - k + 1))
        hits = {clean[f] for f in found if f in clean}
        if not hits:
            continue
        sents[sid] = (jp, tr)
        for w in hits:
            cands[w].append((abs(len(jp) - 18) + bonus, sid))
        n += 1
        if n % 20000 == 0:
            print(f"  日语例句 {n}…", flush=True)
    used, rows = set(), []
    for w, cs in cands.items():
        cs.sort()
        for _, sid in cs[:3]:
            rows.append((w, sid))
            used.add(sid)
    db.executemany("INSERT INTO sentences VALUES(?,?,?)", [(s, *sents[s]) for s in used])
    db.executemany("INSERT INTO examples VALUES(?,?)", rows)
    db.execute("CREATE INDEX idx_examples ON examples(word)")
    zh = sum(1 for s in used if s in to_cmn)
    print(f"  日语例句: {len(used)} 句（中文译文 {zh}，英文译文 {len(used) - zh}），覆盖 {len(cands)}/{len(vocab)} 词 = {len(cands) / len(vocab):.0%}")
    for lv in "54321":
        ws = [r[0] for r in db.execute("SELECT word FROM entries WHERE tags=?", ("n" + lv,))]
        print(f"    N{lv}: {sum(1 for w in ws if w in cands) / max(1, len(ws)):.0%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, type=Path)
    ap.add_argument("--only", choices=["en", "ja"])
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.only != "ja":
        build_en(a.src)
    if a.only != "en":
        build_ja(a.src)
    sys.exit(0)
