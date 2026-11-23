"""重新挑选例句（1.1.3）：去掉敏感内容，换成更日常、更实用的句子。

    python tools/refine_examples.py <源数据目录> [shici/data] [ctranslate2 英译中模型目录]

以前的例句只按“句子长度接近 52 个字母”挑，Tatoeba 里大量奇怪的句子被选了进来：
政治（台湾、泽连斯基……）、暴力和色情，Sami / Layla 的犯罪故事、阿尔及利亚 / 卡拜尔的政论，还有满是生僻词的句子。

现在给每个候选句打分再挑：
- 敏感内容：政治、色情、自残、歧视直接排除；暴力、宗教、毒品等扣很多分（除非这个词本身就是这方面的词，比如 murder）。
- 实用：7~14 个词最好；句子里其他词越常用越好；少出现人名（Tom、Mary 稍扣分，Sami、Layla 扣很多）。
- 释义对得上：中文译文里出现这个词的中文释义，说明用的是常见意思、翻译也靠谱，加分。
- 有人工中文译文的优先；没有的用机器翻译补（标“机翻”）。
- 同一个词的几条例句不要太像。
日语词典同样处理。
"""
from __future__ import annotations

import bz2
import heapq
import math
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_bilingual import gloss_terms  # noqa: E402

# ---------------------------------------------------------------- 敏感词
# 政治：一律排除（目标词本身是这类词也不放宽，宁可没有例句）
POL_EN = r"""taiwan\w*|tibet\w*|xinjiang|uyghur\w*|uighur\w*|tiananmen|dalai|falun|hong\s+kong|
communis[tm]\w*|ccp|mao(?:ist)?|xi\s+jinping|jinping|putin|zelensk\w*|trump|trumpen\w*|biden|obama|hitler|nazi\w*|stalin\w*|kim\s+jong\w*|
ukrain\w*|palestin\w*|gaza|isis|hamas|taliban|qaeda|terroris\w*|kabyl\w*|berber\w*|tamazight|amazigh|
separatis\w*|genocide|holocaust|jihad\w*|islamis\w*|regime|dictator\w*|algeria\w*"""
# 色情、自残、脏话、歧视：排除（目标词本身是这类词时只扣分，比如 breast、naked）
HARD_EN = r"""sex|sexy|sexual\w*|naked|nude|nudity|porn\w*|rape\w*|raping|
rapist\w*|penis\w*|vagina\w*|breasts?|boobs?|orgasm\w*|condoms?|prostitut\w*|whores?|sluts?|erotic\w*|masturbat\w*|
suicid\w*|kill\s+(?:my|him|her|them|your|our)sel(?:f|ves)|hang(?:ed)?\s+(?:him|her|my|them)sel(?:f|ves)|self-harm|
nigg\w*|fag\w*|retard\w*|cunt\w*|fuck\w*|shit\w*|bitch\w*|bastard\w*|dick|cock|pussy|asshole\w*|slave\w*|racis\w*"""
# 扣分多（暴力、犯罪、宗教、毒品、政治）
SOFT_EN = r"""kill\w*|murder\w*|stab\w*|shoot\w*|shot|shotgun|guns?|pistol\w*|rifle\w*|bomb\w*|explosi\w*|blood\w*|bleed\w*|
corpse\w*|dead\s+body|torture\w*|war|wars|warfare|weapons?|soldiers?|army|armies|military|invade\w*|invasion\w*|
funeral\w*|coffin\w*|crime\w*|criminal\w*|prison\w*|jail\w*|arrest\w*|steal\w*|stole\w*|robb\w*|thie\w*|
god|gods|jesus|christ\w*|allah|muslim\w*|islam\w*|bible\w*|quran|koran|satan\w*|devil\w*|hell|drugs|cocaine|heroin|
marijuana|weed|vodka|whisk(?:e)?y|politic\w*|election\w*|democra\w*|parliament\w*|senat\w*|protest\w*|revolution\w*|
independence|colonial\w*|empire\w*|soviet\w*|algeria\w*|africa\w*|nationalis\w*|russia\w*|israel\w*"""
# 扣分少（死亡、警察、喝酒、负面情绪……日常也会说，但不算好例句）
MILD_EN = r"""die|died|dies|dying|death\w*|dead|grave|police\w*|drunk\w*|beer|wine|cigarett\w*|smok\w*|divorc\w*|cheat\w*|
affair|hate\w*|stupid\w*|idiot\w*|ugly|fat|government\w*|president\w*|minister\w*|congress\w*|church\w*|pray\w*|religio\w*"""
NAMES_MILD = {"Tom", "Mary", "John", "Ken", "Bob", "Jack", "Jim", "Mike", "Lucy", "Alice", "Emily", "Kate", "Jane", "Bill", "Tony"}
NAMES_BAD = {"Sami", "Layla", "Fadil", "Dania", "Salima", "Rami", "Farid", "Mennad", "Baya", "Yanni", "Skura", "Ziri", "Rima",
             "Nuja", "Taninna", "Yidir", "Ziri's", "Mohamed", "Muhammad", "Salas", "Sonia", "Tanya"}
HARD_ZH = r"炮友|性生活|性关系|上床|色情|妓|嫖|裸体|裸照|阴茎|阴道|乳房|胸部|避孕套|台湾|台獨|台独|西藏|藏独|新疆|维吾尔|天安门|法轮|共产党|共产主义|习近平|毛泽东|六四|达赖|疆独|港独|泽连斯基|泽伦斯基|普京|特朗普|希特勒|纳粹|乌克兰|以色列|巴勒斯坦|卡拜尔|柏柏尔|自杀|强奸|做爱|色情|性交"
HARD_JA = r"台湾|チベット|新疆|ウイグル|天安門|法輪|共産党|共産主義|習近平|毛沢東|プーチン|ゼレンスキー|トランプ|ヒトラー|ナチ|ウクライナ|イスラエル|パレスチナ|自殺|強姦|レイプ|セックス|売春|ポルノ|裸"
SOFT_JA = r"殺|死|戦争|爆弾|銃|血|刑務所|警察|逮捕|泥棒|盗|酔|酒|タバコ|煙草|神|教会|宗教|祈|離婚|浮気|嫌い|馬鹿|バカ|政府|大統領|政治|選挙|首相|軍"
NAMES_JA = r"トム|メアリー|メアリ|ジョン|ケン|ボブ|ジャック|サミ|ライラ|マユコ|ナンシー|ビル|ジム"

pol_en = re.compile(r"\b(?:" + re.sub(r"\s+", "", POL_EN) + r")\b", re.I)
hard_en = re.compile(r"\b(?:" + re.sub(r"\s+", "", HARD_EN) + r")\b", re.I)
soft_en = re.compile(r"\b(?:" + re.sub(r"\s+", "", SOFT_EN) + r")\b", re.I)
mild_en = re.compile(r"\b(?:" + re.sub(r"\s+", "", MILD_EN) + r")\b", re.I)
hard_zh = re.compile(HARD_ZH)
hard_ja, soft_ja, names_ja = re.compile(HARD_JA), re.compile(SOFT_JA), re.compile(NAMES_JA)
TOKEN = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")
LATIN = re.compile(r"[A-Za-z]{2,}")


def read(src: Path, name: str):
    with bz2.open(src / name, "rt", encoding="utf-8") as f:
        for line in f:
            yield line.rstrip("\n").split("\t")


def t2s_fn():
    try:
        from opencc import OpenCC
        return OpenCC("t2s").convert
    except ImportError:
        return lambda s: s


STOP_CJK = set("的使地得了者性人物之于於不化子一有无被把可能上下大小中")


def related(a: str, b: str) -> bool:
    """两个词的中文释义有没有相通的地方（共有两个相邻汉字，或共有一个不是虚字的汉字）。"""
    ta, tb = "".join(gloss_terms(a)), "".join(gloss_terms(b))
    if any(ta[i:i + 2] in tb for i in range(len(ta) - 1)):
        return True
    return bool((set(ta) - STOP_CJK) & (set(tb) - STOP_CJK))


def sense_bonus(zh: str, terms: list[str]) -> float:
    if not zh or not terms:
        return 0.0
    if any(len(t) >= 2 and t in zh for t in terms):
        return 1.5
    if any((len(t) == 1 and t in zh) or any(t[i:i + 2] in zh for i in range(len(t) - 1)) for t in terms):
        return 0.8
    return -0.4


def matches_en(en: str) -> tuple[list[str], list[str], list[str]]:
    return ([m.group(0).lower() for m in hard_en.finditer(en)], [m.group(0).lower() for m in soft_en.finditer(en)],
            [m.group(0).lower() for m in mild_en.finditer(en)])


def flags_en(en: str, target_family: set[str], found=None) -> tuple[bool, float]:
    """(要不要排除, 扣分)。target_family 里的词（目标词和它的变形）不算。"""
    hard, soft, mild = found or matches_en(en)
    if pol_en.search(en):
        return True, 0.0
    pen = 0.0
    for t in hard:
        if t not in target_family:
            return True, 0.0
        pen += 3.0
    pen += sum(2.2 for t in soft if t not in target_family) + sum(1.0 for t in mild if t not in target_family)
    return False, pen


def mt_translate(rows: list[tuple[str, str]], cache: Path, model: Path) -> dict[str, str]:
    """rows: (key, 英文)。结果追加到缓存文件（和 tools/mt_sentences.py 同一格式），返回 {key: 中文}。"""
    done: dict[str, str] = {}
    if cache.exists():
        for line in open(cache, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) == 3:
                done[p[0]] = p[2]
    todo = [r for r in rows if r[0] not in done]
    if todo:
        import ctranslate2
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-zh")
        tr = ctranslate2.Translator(str(model), device="cpu", inter_threads=1, intra_threads=2)
        t0 = time.time()
        with open(cache, "a", encoding="utf-8") as f:
            for i in range(0, len(todo), 64):
                chunk = todo[i:i + 64]
                out = tr.translate_batch([tok.convert_ids_to_tokens(tok.encode(en)) for _, en in chunk], beam_size=4, max_batch_size=64)
                for (k, en), o in zip(chunk, out):
                    zh = tok.decode(tok.convert_tokens_to_ids(o.hypotheses[0]), skip_special_tokens=True).replace("\t", " ").replace("\n", " ")
                    f.write(f"{k}\t{en}\t{zh}\n")
                    done[k] = zh
                if i % 3200 == 0:
                    print(f"    机翻 {i}/{len(todo)} …{time.time() - t0:.0f}s", flush=True)
    return {k: done[k] for k, _ in rows if k in done}


# ---------------------------------------------------------------- 英语
def refine_en(src: Path, data: Path, model: Path) -> None:
    t0 = time.time()
    db = sqlite3.connect(data / "dict_en.db")
    t2s = t2s_fn()
    entries = {w: (t, r or 60000) for w, t, r in db.execute("SELECT word, translation, rank FROM entries")}
    lower = {w.lower(): w for w in entries}
    lemma: dict[str, set[str]] = defaultdict(set)
    for form, lem in db.execute("SELECT form, lemma FROM forms"):
        f = form.lower()
        # 变形本身也是一个更常用的词时，不算作这个词的变形：number 是 numb 的比较级，但句子里的 number 几乎都是“数字”；
        # 同理 better/butter 之类。saw 比 see 少见，所以 saw 仍然算 see 的过去式
        own = lower.get(f)
        if own and own != lem and entries[own][1] < entries.get(lem, ("", 60000))[1] and not related(entries[own][0], entries.get(lem, ("", 0))[0]):
            continue  # 再看释义：dissatisfied（不满意的）和 dissatisfy（使不满）意思相通，仍算变形；number 和 numb 不相干
        lemma[f].add(lem)
    family: dict[str, set[str]] = defaultdict(set)  # 词 → 它的各种变形（小写）
    for form, lems in lemma.items():
        for lem in lems:
            family[lem].add(form)
    for w in entries:
        family[w].add(w.lower())
    terms = {w: gloss_terms(t) for w, (t, _) in entries.items()}
    old = defaultdict(list)
    for w, sid in db.execute("SELECT word, sid FROM examples ORDER BY rowid"):
        old[w].append(sid)
    old_sent = {r[0]: r[1:] for r in db.execute("SELECT sid, en, zh, mt, ja FROM sentences")}
    need = set(old) | {w for w, in db.execute("SELECT word FROM entries WHERE tags!='' AND tags IS NOT NULL")}

    cmn = {int(r[0]): r[2] for r in read(src, "cmn_sentences.tsv.bz2") if len(r) >= 3}
    to_cmn: dict[int, int] = {}
    for r in read(src, "eng-cmn_links.tsv.bz2"):
        e, c = int(r[0]), int(r[1])
        if c in cmn and (e not in to_cmn or len(cmn[c]) < len(cmn[to_cmn[e]])):
            to_cmn[e] = c
    mtc: dict[int, str] = {}
    cache = src / "mt" / "en_zh.tsv"
    for line in open(cache, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) == 3 and p[0].startswith("en:"):
            mtc[int(p[0][3:])] = p[2].strip()
    has_ja: set[int] = set()
    for r in read(src, "jpn-eng_links.tsv.bz2"):
        has_ja.add(int(r[1]))
    print(f"  读完词典和 Tatoeba 链接 {time.time() - t0:.0f}s", flush=True)

    ok_shape = re.compile(r"^[A-Z\"'][^\t]{14,108}[.?!\"']$")
    heaps: dict[str, list] = defaultdict(list)
    texts: dict[int, tuple[str, str, int]] = {}  # sid → (英文, 中文, 0 人工 / 1 机翻 / 2 待机翻)
    K = 8
    n = 0
    for r in read(src, "eng_sentences.tsv.bz2"):
        if len(r) < 3:
            continue
        sid, en = int(r[0]), r[2].strip()
        if not ok_shape.match(en) or pol_en.search(en):
            continue
        toks = TOKEN.findall(en)
        nw = len(toks)
        if nw < 4 or nw > 20:
            continue
        if sid in to_cmn:
            zh, kind = t2s(cmn[to_cmn[sid]].strip()), 0
            if not zh or len(zh) > 70 or hard_zh.search(zh):
                continue
        elif sid in mtc:
            zh, kind = mtc[sid], 1
            if hard_zh.search(zh):
                continue
        else:
            zh, kind = "", 2
        # 和目标词无关的部分先算好
        base = 0.0
        base -= 0 if 7 <= nw <= 14 else (0.35 * (7 - nw) if nw < 7 else 0.25 * (nw - 14))
        caps = [t for i, t in enumerate(toks) if i and t[0].isupper() and t != "I" and t.lower() not in lower]
        base -= 0.6 * len(caps)
        base -= sum(1.0 for t in toks if t in NAMES_MILD) + sum(4.0 for t in toks if t in NAMES_BAD)
        if '"' in en or ";" in en:
            base -= 0.5
        if re.search(r"\d", en):
            base -= 0.3
        if re.search(r"\b(I|you|we|my|your|our|let's)\b", en, re.I):
            base += 0.3  # 日常对话、说自己的事
        if kind == 0:
            base += 1.8
            ratio = len(zh) / max(1, nw)
            if ratio < 0.8 or ratio > 3.6:
                base -= 0.5
        if zh and LATIN.search(zh):
            base -= 0.8  # 译文里留着没翻的英文名字
        if sid in has_ja:
            base += 0.3
        ranks = []
        heads_all: dict[str, str] = {}
        for tk in toks:
            t = tk.lower()
            hs = set(lemma.get(t, ()))
            if t in lower:
                hs.add(lower[t])
            hs = {h for h in hs if h in entries}
            for h in hs:
                heads_all.setdefault(h, t)
            ranks.append((min((entries[h][1] for h in hs), default=60000), t))
        ranks.sort(reverse=True)
        found = matches_en(en)
        hit = False
        for h in heads_all:
            if h not in need:
                continue
            fam = family[h]
            excl, pen = flags_en(en, fam, found)
            if excl:
                continue
            rare = [rk for rk, t in ranks if t not in fam][:2]
            score = base - pen - sum(max(0.0, math.log10(max(rk, 1)) - 3.3) for rk in rare) + sense_bonus(zh, terms.get(h, []))
            item = (score, -sid, sid)
            hp = heaps[h]
            if len(hp) < K:
                heapq.heappush(hp, item)
                hit = True
            elif item > hp[0]:
                heapq.heapreplace(hp, item)
                hit = True
        if hit:
            texts[sid] = (en, zh, kind)
        n += 1
        if n % 300000 == 0:
            print(f"    英文句子 {n} …{time.time() - t0:.0f}s", flush=True)

    # 每个词挑 3 条：分数高的优先，几条之间不要太像
    def sig(en: str) -> set[str]:
        return {t.lower() for t in TOKEN.findall(en)}

    chosen: dict[str, list[int]] = {}
    for w, hp in heaps.items():
        picks: list[int] = []
        for score, _, sid in sorted(hp, reverse=True):
            if score < -4.5 and picks:
                break
            s = sig(texts[sid][0])
            if any(len(s & sig(texts[p][0])) / max(1, len(s | sig(texts[p][0]))) > 0.5 for p in picks):
                continue
            picks.append(sid)
            if len(picks) == 3:
                break
        chosen[w] = picks
    # 待机翻的句子
    todo = sorted({sid for ps in chosen.values() for sid in ps if texts[sid][2] == 2})
    print(f"  需要机翻 {len(todo)} 句", flush=True)
    got = mt_translate([(f"en:{sid}", texts[sid][0]) for sid in todo], cache, model)
    for sid in todo:
        en, _, _ = texts[sid]
        texts[sid] = (en, got.get(f"en:{sid}", "").strip(), 1)
    for w in chosen:  # 机翻出来带敏感词的（比如把俚语翻成了不雅的说法）也不要
        chosen[w] = [sid for sid in chosen[w] if not hard_zh.search(texts[sid][1])]
    # 日语译文
    want = {sid for ps in chosen.values() for sid in ps}
    e2j: dict[int, int] = {}
    for r in read(src, "jpn-eng_links.tsv.bz2"):
        j, e = int(r[0]), int(r[1])
        if e in want:
            e2j.setdefault(e, j)
    jset = set(e2j.values())
    jpn = {int(r[0]): r[2].strip() for r in read(src, "jpn_sentences.tsv.bz2") if len(r) >= 3 and int(r[0]) in jset}

    # 写回：新挑的不够 3 条时，用原来那些（WordNet 短语、自编例句等）补，敏感的去掉
    sent_rows: dict[int, tuple] = {}
    ex_rows: list[tuple[str, int]] = []
    kept_old = 0
    for w in need:
        picks = list(chosen.get(w, []))
        for sid in picks:
            en, zh, kind = texts[sid]
            sent_rows[sid] = (sid, en, zh, 1 if kind else 0, jpn.get(e2j.get(sid, -1)))
        for sid in old.get(w, []):
            if len(picks) >= 3:
                break
            if sid in picks or sid not in old_sent:
                continue
            en, zh, mt, ja = old_sent[sid]
            if flags_en(en, family[w])[0] or hard_zh.search(zh or ""):
                continue
            def has(t: str) -> bool:
                t, lw = t.lower(), w.lower()
                return t == lw or w in lemma.get(t, ()) or (t.startswith(lw) and t[len(lw):] in ("s", "es", "ed", "d", "ing", "ly"))
            if sid > 0 and re.fullmatch(r"[A-Za-z]+", w) and not any(has(t) for t in TOKEN.findall(en)):
                continue  # 旧例句里其实没有这个词（比如 numb 配了 number 的句子）
            picks.append(sid)
            sent_rows[sid] = (sid, en, zh, mt, ja)
            kept_old += 1
        ex_rows += [(w, sid) for sid in picks]
    db.execute("DELETE FROM examples")
    db.execute("DELETE FROM sentences")
    db.executemany("INSERT INTO sentences(sid, en, zh, mt, ja) VALUES(?,?,?,?,?)", list(sent_rows.values()))
    db.executemany("INSERT INTO examples(word, sid) VALUES(?,?)", ex_rows)
    db.commit()
    db.execute("VACUUM")
    human = sum(1 for r in sent_rows.values() if not r[3] and r[2])
    print(f"  英语例句：{len(sent_rows)} 句（人工中文译文 {human}），{len(ex_rows)} 条词-例句，沿用旧例句 {kept_old}；用时 {time.time() - t0:.0f}s")
    db.close()


# ---------------------------------------------------------------- 日语
def refine_ja(src: Path, data: Path, model: Path) -> None:
    import pyopenjtalk
    t0 = time.time()
    db = sqlite3.connect(data / "dict_ja.db")
    t2s = t2s_fn()
    vocab = {w: (zh or "") for w, zh in db.execute("SELECT word, translation_zh FROM entries")}
    clean = {re.sub(r"[()（）～〜]", "", w): w for w in vocab}
    terms = {w: gloss_terms(zh) for w, zh in vocab.items()}
    # 只有一个词读这个音时，句子里写成假名也算（中々 ↔ なかなか、寧ろ ↔ むしろ）
    by_read: dict[str, list[str]] = defaultdict(list)
    for w, p in db.execute("SELECT word, phonetic FROM entries"):
        if p and len(p) >= 3:
            by_read[p].append(w)
    for p, ws in by_read.items():
        if len(ws) == 1 and p not in clean:
            clean[p] = ws[0]
    old = defaultdict(list)
    for w, sid in db.execute("SELECT word, sid FROM examples ORDER BY rowid"):
        old[w].append(sid)
    old_sent = {r[0]: r[1:] for r in db.execute("SELECT sid, en, zh, tr_en, mt FROM sentences")}

    cmn = {int(r[0]): r[2] for r in read(src, "cmn_sentences.tsv.bz2") if len(r) >= 3}
    to_cmn: dict[int, int] = {}
    for r in read(src, "jpn-cmn_links.tsv.bz2"):
        j, c = int(r[0]), int(r[1])
        if c in cmn and (j not in to_cmn or len(cmn[c]) < len(cmn[to_cmn[j]])):
            to_cmn[j] = c
    to_eng: dict[int, int] = {}
    for r in read(src, "jpn-eng_links.tsv.bz2"):
        to_eng.setdefault(int(r[0]), int(r[1]))
    need_eng = set(to_eng.values())
    eng = {int(r[0]): r[2].strip() for r in read(src, "eng_sentences.tsv.bz2") if len(r) >= 3 and int(r[0]) in need_eng}
    mtc: dict[str, str] = {}
    cache = src / "mt" / "ja_en_zh.tsv"
    if cache.exists():
        for line in open(cache, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) == 3:
                mtc[p[0]] = p[2].strip()
    print(f"  读完日语词典和 Tatoeba 链接 {time.time() - t0:.0f}s", flush=True)

    heaps: dict[str, list] = defaultdict(list)
    texts: dict[int, tuple[str, str, str, int]] = {}  # sid → (日语, 中文, 英文, 0 人工中文 / 1 机翻中文 / 2 待机翻)
    n = 0
    for r in read(src, "jpn_sentences.tsv.bz2"):
        if len(r) < 3:
            continue
        sid, jp = int(r[0]), r[2].strip()
        if not (7 <= len(jp) <= 34) or hard_ja.search(jp):
            continue
        en = eng.get(to_eng.get(sid, -1), "")
        if sid in to_cmn:
            zh, kind = t2s(cmn[to_cmn[sid]].strip()), 0
            if not zh or len(zh) > 60 or hard_zh.search(zh):
                continue
        elif en:
            if hard_en.search(en):
                continue
            k = f"ja:{sid}"
            zh, kind = (mtc[k], 1) if k in mtc else ("", 2)
        else:
            continue
        base = 0.0
        L = len(jp)
        base -= 0 if 9 <= L <= 22 else (0.25 * (9 - L) if L < 9 else 0.18 * (L - 22))
        base -= 1.2 * len(names_ja.findall(jp))
        base -= 2.2 * len(soft_ja.findall(jp))
        if re.search(r"[A-Za-z0-9０-９]", jp):
            base -= 0.5
        if kind == 0:
            base += 1.2
        if zh and LATIN.search(zh):
            base -= 0.8
        if re.search(r"私|あなた|僕|君|ます|ください|でしょう", jp):
            base += 0.3
        toks = pyopenjtalk.run_frontend(jp)
        surf = [t["string"] for t in toks]
        found = {t["orig"] for t in toks if t["pos"] not in ("助詞", "助動詞", "記号")}
        found.update(t["string"] for t in toks if t["pos"] not in ("記号",))  # 写法本身（終わり、ください）
        for k in (2, 3):
            found.update("".join(surf[i:i + k]) for i in range(len(surf) - k + 1))
        hits = {clean[f] for f in found if f in clean}
        hit = False
        for w in hits:
            pen = 0.0
            for m in soft_ja.finditer(jp):  # 目标词本身带“死”“酒”之类的字，不扣
                if m.group(0) in w:
                    pen -= 2.2
            score = base - pen + sense_bonus(zh, terms.get(w, []))
            item = (score, -sid, sid)
            hp = heaps[w]
            if len(hp) < 8:
                heapq.heappush(hp, item)
                hit = True
            elif item > hp[0]:
                heapq.heapreplace(hp, item)
                hit = True
        if hit:
            texts[sid] = (jp, zh, en, kind)
        n += 1
        if n % 50000 == 0:
            print(f"    日语句子 {n} …{time.time() - t0:.0f}s", flush=True)

    chosen: dict[str, list[int]] = {}
    for w, hp in heaps.items():
        picks: list[int] = []
        for score, _, sid in sorted(hp, reverse=True):
            if score < -4.5 and picks:
                break
            a = set(texts[sid][0])
            if any(len(a & set(texts[p][0])) / max(1, len(a | set(texts[p][0]))) > 0.6 for p in picks):
                continue
            picks.append(sid)
            if len(picks) == 3:
                break
        chosen[w] = picks
    todo = sorted({sid for ps in chosen.values() for sid in ps if texts[sid][3] == 2})
    print(f"  日语例句需要机翻 {len(todo)} 句（从英文译文翻成中文）", flush=True)
    got = mt_translate([(f"ja:{sid}", texts[sid][2]) for sid in todo], cache, model)
    for sid in todo:
        jp, _, en, _ = texts[sid]
        texts[sid] = (jp, got.get(f"ja:{sid}", "").strip(), en, 1)

    sent_rows: dict[int, tuple] = {}
    ex_rows: list[tuple[str, int]] = []
    for w in vocab:
        picks = list(chosen.get(w, []))
        for sid in picks:
            jp, zh, en, kind = texts[sid]
            sent_rows[sid] = (sid, jp, zh, en or None, 1 if kind else 0)
        for sid in old.get(w, []):
            if len(picks) >= 3:
                break
            if sid in picks or sid not in old_sent:
                continue
            jp, zh, tr_en, mt = old_sent[sid]
            if hard_ja.search(jp) or hard_zh.search(zh or ""):
                continue
            picks.append(sid)
            sent_rows[sid] = (sid, jp, zh, tr_en, mt)
        ex_rows += [(w, sid) for sid in picks]
    db.execute("DELETE FROM examples")
    db.execute("DELETE FROM sentences")
    db.executemany("INSERT INTO sentences(sid, en, zh, tr_en, mt) VALUES(?,?,?,?,?)", list(sent_rows.values()))
    db.executemany("INSERT INTO examples(word, sid) VALUES(?,?)", ex_rows)
    db.commit()
    db.execute("VACUUM")
    human = sum(1 for r in sent_rows.values() if not r[4])
    print(f"  日语例句：{len(sent_rows)} 句（人工中文译文 {human}），覆盖 {len({w for w, _ in ex_rows})}/{len(vocab)} 词；用时 {time.time() - t0:.0f}s")
    db.close()


if __name__ == "__main__":
    src = Path(sys.argv[1])
    data = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "shici" / "data"
    model = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("en-zh-ct2")
    which = sys.argv[4] if len(sys.argv) > 4 else "en,ja"
    if "en" in which:
        refine_en(src, data, model)
    if "ja" in which:
        refine_ja(src, data, model)
