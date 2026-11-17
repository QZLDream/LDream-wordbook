"""给英语词典加上「词根拆分」和「近义词 / 反义词」。

用法：python tools/build_related.py <data_src> [shici/data]
需要：
  data_src/enwikt/en_extract.jsonl   tools/enwikt_extract.py 从维基词典（CC BY-SA 4.0）取出的词源、近义词、反义词
  data_src/nltk/corpora/wordnet.zip   WordNet 3.0（普林斯顿大学，WordNet 许可证）
  tools/roots_data.py                 本项目自己整理的词根、前缀、后缀表

词根拆分的原则是“宁缺毋滥”：单词里出现了某个词根的拼写还不够，维基词典的词源里还得确实出现这个词根的拉丁语 / 希腊语词干，
前面剩下的部分必须是认识的前缀，后面剩下的部分必须是认识的后缀，三样都对得上才收。

写入 dict_en.db：
  morph(word, parts)          parts = JSON [[片段, 类型, 中文意思], ...]，类型 p 前缀 / r 词根 / s 后缀 / w 英语单词（意思运行时查词典）
  morph_root(root, word, score)  同根词：root 是词根的第一个写法，score 越小越常用
  related(word, syn, ant)     JSON 单词列表，已按常用程度排好
"""
import json
import re
import sqlite3
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import roots_data  # noqa: E402

# 词源里这些语言的词才拿来核对词根（拉丁语及其后代、希腊语）
LA = {"la", "la-lat", "la-med", "la-new", "la-ecc", "la-vul", "la-cla", "la-ren", "LL.", "ML.", "NL.", "VL.", "itc-pro",
      "fro", "frm", "fr", "xno", "pro", "it", "es", "pt", "ca", "roa-opt", "roa-oit", "ofr"}
GRC = {"grc", "grc-koi", "grc-att", "grc-ion", "gkm", "el", "grc-dor"}
TREE_LANG = re.compile(r"^(Latin|Late Latin|Medieval Latin|New Latin|Vulgar Latin|Ecclesiastical Latin|Old French|Middle French|French|"
                       r"Anglo-Norman|Old Occitan|Italian|Spanish|Ancient Greek|Koine Greek|Byzantine Greek|Greek) (.+)$")


def norm(s: str) -> str:
    s = s.replace("æ", "ae").replace("œ", "oe").replace("Æ", "ae").replace("Œ", "oe")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return s


def greek_latin(s: str) -> str:
    """希腊字母转拉丁字母（维基词典的希腊语词条常带转写，但词源树里是希腊字母）"""
    table = {"α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "e", "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m",
             "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "u", "φ": "ph", "χ": "kh", "ψ": "ps", "ω": "o"}
    s = norm(s)
    out = "".join(table.get(c, c) for c in s)
    # γγ / γκ 读 ng
    return out.replace("gg", "ng").replace("gk", "nk")


def evidence(recs: list[dict]) -> dict[str, list[str]]:
    """从词源里取出拉丁系 / 希腊语的词（规范化成小写无变音的拉丁字母），用来核对词根"""
    la, grc = [], []
    for r in recs:
        for line in r.get("etym", "").split("\n"):
            m = TREE_LANG.match(line.strip())
            if m:
                words = re.findall(r"[^\s*()“”\"‘’,.;:]+", m.group(2))
                (grc if "Greek" in m.group(1) else la).extend(greek_latin(w) for w in words)
        for t in r.get("tpl", []):
            a = t.get("args", {})
            lang = a.get("2") if t["name"] in ("der", "inh", "bor", "uder", "lbor", "learned borrowing") else a.get("1")
            vals = [v for k, v in a.items() if k.isdigit() and int(k) >= (3 if t["name"] in ("der", "inh", "bor", "uder", "lbor", "learned borrowing") else 2)]
            vals += [a.get("tr", ""), a.get("ts", "")]
            for v in vals:
                v = re.sub(r"<[^>]*>", "", v or "")
                if not v:
                    continue
                if lang in GRC:
                    grc.append(greek_latin(v))
                elif lang in LA:
                    la.append(norm(v))
    return {"la": la, "grc": grc}


def has_stem(stems: list[str], words: list[str], heads: frozenset | None = None) -> bool:
    """词源里有没有这个词根的词干。给了 heads（前缀写法）时更严格：词干要在词首，或者紧跟在一个前缀后面，
    避免 provincia 里的 vinc、desplacer 里的 plac 这种碰巧拼写相同的情况"""
    for w in words:
        for s in stems:
            if not s:
                continue
            i = w.find(s)
            while i >= 0:
                if heads is None or i == 0 or w[:i] in heads or any(w[:i] == a + b for a in heads for b in heads if len(a) >= 2):
                    return True
                i = w.find(s, i + 1)
    return False


class Splitter:
    def __init__(self, vocab=frozenset()):
        self.vocab = vocab
        self.roots = roots_data.roots()
        self.prefixes = roots_data.prefixes()
        self.suffixes = roots_data.suffixes()
        # 词根的每个写法 → 词根；长的写法优先
        self.forms = sorted(((f, r) for r in self.roots for f in r["forms"]), key=lambda x: -len(x[0]))
        self.suf_forms = sorted(self.suffixes, key=len, reverse=True)
        # 拉丁语 / 希腊语里前缀的写法（核对词干位置用），比英语多几个古写法
        self.heads = frozenset({f for p in self.prefixes for f, _ in p["forms"]} | {"prae", "trans", "tra", "ex", "e", "ad", "com", "con", "co", "dis", "di", "re", "red", "sub", "sus", "ob", "in", "im", "per", "pro", "de"})

    def parse_prefix(self, p: str, nxt: str, lang: str):
        """p 能不能拆成 1~2 个前缀；返回 [(写法, 意思)] 或 None"""
        if not p:
            return []
        for pre in self.prefixes:
            if pre["lang"] not in (lang, "en") and not (lang == "la" and pre["lang"] == "la"):
                continue
            for form, allowed in pre["forms"]:
                if not p.startswith(form):
                    continue
                rest = p[len(form):]
                follow = rest[:1] or nxt
                if allowed and follow not in allowed:
                    continue
                if not rest:
                    return [(form, pre["meaning"])]
                if len(rest) >= 2:
                    more = self.parse_prefix(rest, nxt, lang)
                    if more and len(more) == 1:
                        return [(form, pre["meaning"])] + more
        return None

    def parse_suffix(self, q: str, depth=0):
        """q 能不能拆成 0~3 个后缀（开头可以有一个连接元音）；返回 [(写法, 意思)] 或 None"""
        if not q:
            return []
        if depth > 3:
            return None
        for s in self.suf_forms:
            if q.startswith(s):
                rest = self.parse_suffix(q[len(s):], depth + 1)
                if rest is not None:
                    return [(s, self.suffixes[s])] + rest
        # 词尾的不发音 e、词根和后缀之间的连接元音、拉丁词干留下的尾巴：并到词根上显示（类型 g）
        if depth == 0 and q[0] in "aeiou":
            if len(q) == 1:
                return [(q, "")]
            rest = self.parse_suffix(q[1:], depth + 1)
            if rest is not None:
                return [(q[0], "")] + rest
        if depth == 0 and q in ("t", "s", "d", "x"):
            return [(q, "")]
        return None

    def split(self, word: str, ev: dict) -> list | None:
        w = word.lower()
        if len(w) < 5 or not w.isalpha():
            return None
        best = None
        for form, root in self.forms:
            if len(form) < 3 and form != w[: len(form)]:
                continue
            start = 0
            while True:
                pos = w.find(form, start)
                if pos < 0:
                    break
                start = pos + 1
                if not has_stem(root["stems"], ev[root["lang"]], self.heads):
                    break
                pre = self.parse_prefix(w[:pos], form[0], root["lang"])
                if pre is None:
                    continue
                # 英语本族前缀（un- / mis- / over-……）只能加在现成的英语单词前面：unsocial 可以，unanimity 不行
                en_pre = [x for x in pre if any(x[0] == f for pp in self.prefixes if pp["lang"] == "en" for f, _ in pp["forms"])]
                if en_pre and pre[0] in en_pre and w[len(pre[0][0]):] not in self.vocab:
                    continue
                q = w[pos + len(form):]
                suf = self.parse_suffix(q)
                second = []
                if suf is None:  # 两个词根连在一起：bio + log + y、manu + script
                    for form2, root2 in self.forms:
                        for glue in ("", "o", "i"):
                            if q.startswith(glue + form2) and len(form2) >= 3 and has_stem(root2["stems"], ev[root2["lang"]]):
                                rest = self.parse_suffix(q[len(glue + form2):])
                                if rest is not None:
                                    second = ([(glue, "", "")] if glue else []) + [(form2, "r", root2["meaning"])]
                                    suf = rest
                                    break
                        if second:
                            break
                if suf is None:
                    continue
                if not pre and not suf and not second:
                    continue  # 整个词就是词根本身，拆了没意义
                cand = [(p, "p", m) for p, m in pre] + [(form, "r", root["meaning"])] + second + [(x, "s" if m else "", m) for x, m in suf]
                # 连接元音、不发音的 e 并到前一个片段上
                merged = []
                for t, k, m in cand:
                    if not k and merged:
                        merged[-1] = (merged[-1][0] + t, merged[-1][1], merged[-1][2])
                    elif k:
                        merged.append((t, k, m))
                cand = merged
                if len(cand) < 2:
                    continue
                score = (len(form) + (len(second[-1][0]) if second else 0), -len(suf))
                if best is None or score > best[0]:
                    best = (score, cand, root)
        if not best:
            return None
        parts, root = best[1], best[2]
        # 拼回去要和原词一致（防止写法表出错）
        if "".join(p[0] for p in parts) != w:
            return None
        return [list(p) for p in parts], root["forms"][0]


def english_split(word: str, recs: list[dict], vocab: set, sp: Splitter):
    """维基词典的英语构词模板：un- + happy、care + -less、black + board"""
    w = word.lower()
    # 只看第一个词源（最常用的那个意思）：flower 的第二个词源是 flow + -er（“流动的东西”），不能拿来解释“花”
    first = recs[0].get("etym", "") if recs else ""
    for r in recs:
        if r.get("etym", "") != first:
            continue
        for t in r.get("tpl", []):
            if t["name"] not in ("af", "affix", "prefix", "pre", "suffix", "suf", "compound", "com", "surf", "confix", "con"):
                continue
            a = t.get("args", {})
            if a.get("1") != "en":
                continue
            raw = [re.sub(r"<[^>]*>", "", a[k]).strip() for k in sorted((k for k in a if k.isdigit() and int(k) >= 2), key=int)]
            raw = [x for x in raw if x]
            if t["name"] in ("prefix", "pre") and raw:
                raw[0] = raw[0].rstrip("-") + "-"
            if t["name"] in ("suffix", "suf") and len(raw) >= 2:
                raw[-1] = "-" + raw[-1].lstrip("-")
            if len(raw) < 2:
                continue
            parts, ok = [], True
            for x in raw:
                xl = x.lower()
                if xl.endswith("-") and len(xl) > 1:
                    m = next((p["meaning"] for p in sp.prefixes for f, _ in p["forms"] if f == xl[:-1]), None)
                    if not m:
                        ok = False
                        break
                    parts.append([xl[:-1], "p", m])
                elif xl.startswith("-") and len(xl) > 1:
                    m = sp.suffixes.get(xl[1:])
                    if not m:
                        ok = False
                        break
                    parts.append([xl[1:], "s", m])
                elif xl.isalpha() and xl in vocab and xl != w:
                    parts.append([xl, "w", ""])
                else:
                    ok = False
                    break
            if ok and len(parts) >= 2 and any(p[1] == "w" for p in parts):
                return parts
    return None


def load_wordnet(src: Path):
    import nltk
    nltk.data.path.insert(0, str(src / "nltk"))
    from nltk.corpus import wordnet as wn
    wn.ensure_loaded()
    return wn


def build(src: Path, data: Path):
    db = sqlite3.connect(data / "dict_en.db")
    entries = {r[0].lower(): (r[1] or 999999, r[2] or "") for r in db.execute("SELECT word, rank, translation FROM entries")}
    vocab = {w for w, (_, tr) in entries.items() if tr.strip() and w.isalpha()}
    book = {r[0].lower() for r in db.execute("SELECT DISTINCT word FROM book_words")}
    lemma = {r[0].lower(): r[1].lower() for r in db.execute("SELECT form, lemma FROM forms")}

    def score(w):  # 越小越常用：考试词表里的优先，再按词频
        return (0 if w in book else 1, entries.get(w, (999999,))[0])

    recs = defaultdict(list)
    with open(src / "enwikt" / "en_extract.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            recs[r["word"].lower()].append(r)

    # ---------------- 词根 ----------------
    sp = Splitter(vocab)
    morph, fam = {}, []
    # 人名、地名不拆（Florida 不是“花”）；还有几个拼写碰巧像、词源也绕到同一个拉丁词干上的
    names = re.compile(r"(人名|男子名|女子名|地名|姓氏|国名|州名|城市)")
    skip = {"severe", "severity", "severely", "celery", "summer", "nutria", "murmur", "candy", "canteen", "grater", "vegan",
            "bison", "salvia", "salver", "impact", "compact", "compaction", "embellish", "leviathan", "cuban", "cubism",
            "province", "provincial", "pedant", "monica", "liberia", "persona", "person", "personal", "personality",
            "impersonal", "personally", "personnel", "personify", "personification", "portion", "proportion",
            "proportional", "proportionate", "apportion", "disproportionate"}
    targets = sorted(w for w in vocab if w in recs and w not in skip and not names.search(entries[w][1][:40]))
    for w in targets:
        ev = evidence(recs[w])
        got = sp.split(w, ev)
        if got:
            parts, root = got
            morph[w] = parts
            fam.append((root, w, score(w)[0] * 1_000_000 + score(w)[1]))
            continue
        parts = english_split(w, recs[w], vocab, sp)
        if parts:
            morph[w] = parts
    print(f"  词根拆分：{len(morph)} 个词（其中考试词表 {sum(1 for w in morph if w in book)} / {len(book)}）；"
          f"拉丁 / 希腊词根 {len(fam)} 个词")

    # ---------------- 近义词 / 反义词 ----------------
    wn = load_wordnet(src)

    def ok(x, w):
        x = x.lower()
        return x != w and x in vocab and lemma.get(x, x) != w and lemma.get(w, w) != x and len(x) > 1

    def zh_words(w):
        """中文释义里的词（两个字以上），用来看两个英语词的意思是不是真的相近"""
        tr = re.sub(r"\[[^\]]*\]|[a-z]+\.", " ", entries.get(w, (0, ""))[1])
        out = set()
        for seg in re.split(r"[,，;；、\s/()（）]+", tr):
            seg = seg.strip("的地得着了")
            if len(seg) >= 2:
                out.add(seg)
        return out

    def weight(idx):  # 维基词典里出自第几个义项：整个词条通用和前两个义项最可信
        return 2 if idx < 2 else 1 if idx < 4 else 0

    related = {}
    for w in sorted(vocab & (book | set(recs))):
        syn, ant = defaultdict(int), defaultdict(int)
        for r in recs.get(w, []):
            for x, idx in r.get("syn", []):
                if ok(x, w):
                    syn[x.lower()] += weight(idx)
            for x, idx in r.get("ant", []):
                if ok(x, w):
                    ant[x.lower()] += weight(idx) or 1
        by_pos = defaultdict(int)
        for s in wn.synsets(w):
            by_pos[s.pos()] += 1
            first = by_pos[s.pos()] <= 2  # 每个词性最常用的两个义项
            for lem in s.lemmas():
                x = lem.name()
                if first and "_" not in x and ok(x, w):
                    syn[x.lower()] += 1
                if lem.name().lower() == w:
                    for a in lem.antonyms():
                        if "_" not in a.name() and ok(a.name(), w):
                            ant[a.name().lower()] += 2
        mine = zh_words(w)
        for x in list(syn):
            if mine & zh_words(x):  # 中文释义里有同一个词：意思确实相近
                syn[x] += 2
        for x in list(syn):
            # 只有一处来源、中文意思也对不上的不要；太生僻的词（不在考试词表、词频也低）对背单词没帮助，也不要
            if x in ant or syn[x] < 2 or (x not in book and entries[x][0] > 15000):
                del syn[x]
        for x in list(ant):
            if x not in book and entries[x][0] > 15000:
                del ant[x]
        pick = lambda d, n: [x for x, _ in sorted(d.items(), key=lambda kv: (-kv[1], score(kv[0])))][:n]
        s_, a_ = pick(syn, 6), pick({x: v for x, v in ant.items() if v >= 1}, 4)
        if s_ or a_:
            related[w] = (s_, a_)
    print(f"  近义 / 反义：{len(related)} 个词（考试词表 {sum(1 for w in related if w in book)} / {len(book)}）；"
          f"有反义词的 {sum(1 for v in related.values() if v[1])}")

    db.executescript("""
        DROP TABLE IF EXISTS morph; DROP TABLE IF EXISTS morph_root; DROP TABLE IF EXISTS related;
        CREATE TABLE morph(word TEXT PRIMARY KEY, parts TEXT NOT NULL);
        CREATE TABLE morph_root(root TEXT NOT NULL, word TEXT NOT NULL, score INTEGER NOT NULL);
        CREATE INDEX idx_morph_root ON morph_root(root, score);
        CREATE TABLE related(word TEXT PRIMARY KEY, syn TEXT NOT NULL, ant TEXT NOT NULL);
    """)
    db.executemany("INSERT INTO morph VALUES (?, ?)", [(w, json.dumps(p, ensure_ascii=False)) for w, p in morph.items()])
    db.executemany("INSERT INTO morph_root VALUES (?, ?, ?)", fam)
    db.executemany("INSERT INTO related VALUES (?, ?, ?)", [(w, json.dumps(s), json.dumps(a)) for w, (s, a) in related.items()])
    src_meta = db.execute("SELECT v FROM meta WHERE k = 'source'").fetchone()
    if src_meta and "Wiktionary" not in src_meta[0]:
        db.execute("UPDATE meta SET v = ? WHERE k = 'source'", (src_meta[0] + " + Wiktionary (CC BY-SA 4.0) + WordNet 3.0 词根 / 近义词 / 反义词",))
    db.commit()
    db.execute("VACUUM")
    db.close()


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "shici/data"))
