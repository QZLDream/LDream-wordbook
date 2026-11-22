"""从中文维基词典（kaikki.org 提取的 zhwiktionary 日语词条, CC BY-SA 4.0）整理日语词的中文释义。"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

POS = {
    "名詞": "n.", "名词": "n.", "專有名詞": "n.", "专有名词": "n.", "動詞": "v.", "动词": "v.",
    "形容詞": "adj.", "形容词": "adj.", "形容動詞": "adj-na", "形容动词": "adj-na", "副詞": "adv.", "副词": "adv.",
    "感嘆詞": "int.", "感叹词": "int.", "代詞": "pron.", "代词": "pron.", "代名詞": "pron.", "量詞": "ctr.", "量词": "ctr.",
    "數詞": "num.", "数词": "num.", "連詞": "conj.", "连词": "conj.", "接續詞": "conj.", "助詞": "prt.", "助词": "prt.",
    "後綴": "suf.", "后缀": "suf.", "前綴": "pref.", "前缀": "pref.", "連體詞": "adj.", "连体词": "adj.",
    "短語": "exp.", "短语": "exp.", "惯用语": "exp.", "慣用語": "exp.", "成語": "exp.", "成语": "exp.", "諺語": "exp.", "谚语": "exp.",
}
SKIP = {"漢字", "汉字", "soft-redirect", "羅馬化", "罗马化", "罗马字", "羅馬字", "音節", "音节", "character", "符號", "符号"}
# 词典式词条里的词性缩写（「名·自サ」「副」「自五」等）
ABBR = re.compile(r"^((?:名|代|副|形動|形|連体|接続|感|助動|助|接頭|接尾|自|他|サ|五|上一|下一|カ|変|·|・|/|、|\s)+)\s*")


def abbr_pos(a: str) -> str:
    if re.search(r"自|他", a): return "v."
    if "形動" in a: return "adj-na"
    if a.startswith("形"): return "adj."
    if a.startswith("副"): return "adv."
    if a.startswith("名") or a.startswith("代"): return "n."
    if a.startswith("感"): return "int."
    return ""


def clean(gloss: str, word: str) -> tuple[str, str]:
    """返回 (词性, 释义)。去掉词头、例句、括号里的读音说明。"""
    pos = ""
    lines = [l.strip() for l in gloss.split("\n") if l.strip()]
    if lines and "【" in lines[0] and len(lines) > 1:  # 「主に【おもに】」这种词典式词条：第二行才是释义
        lines = lines[1:]
    if not lines:
        return "", ""
    s = lines[0]
    m = ABBR.match(s)
    if m and len(m.group(1).strip()) <= 8 and len(s) > len(m.group(0)):
        pos = abbr_pos(m.group(1).strip())
        s = s[len(m.group(0)):]
    s = re.sub(r"[（(][^（）()]*?[ぁ-ゟ゠-ヿ][^（）()]*?[）)]", "", s)  # 去掉含假名的括注
    s = re.sub(r"^\(?\d+[.)、．]\s*", "", s)
    s = s.strip(" 。.;；").replace("；", "，")
    if not s or re.search(r"[ぁ-ゟ゠-ヿ]{3,}", s):  # 剩下的还是日语句子：不要
        return "", ""
    return pos, s


def load(paths: list[Path], t2s) -> tuple[dict, dict]:
    """返回 (按词: [(读音集合, 词性, [释义...])], 异体/假名写法 -> 正体词)"""
    by_word: dict[str, list] = defaultdict(list)
    alias: dict[str, str] = {}
    for p in paths:
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            title = e.get("pos_title") or e.get("pos") or ""
            if title in SKIP:
                continue
            word = e["word"]
            readings = set()
            for f in e.get("forms", []):
                if f.get("ruby"):
                    readings.add("".join(r[1] if len(r) > 1 else r[0] for r in f["ruby"]))
                form = f.get("form") or ""
                if form and form != word and not {"romanization", "canonical"} & set(f.get("tags", [])) and re.fullmatch(r"[぀-ヿ一-鿿々〆ー]+", form):
                    alias.setdefault(form, word)
                    if re.fullmatch(r"[぀-ゟー]+", form):
                        readings.add(form)
            senses = []
            for s in e.get("senses", []):
                gl = s.get("glosses") or []
                if not gl:
                    continue
                pos, txt = clean(gl[-1] if len(gl) > 1 else gl[0], word)
                if txt:
                    senses.append((pos or POS.get(title, ""), t2s(txt)))
            if senses:
                by_word[word].append((readings, senses, title in ("專有名詞", "专有名词")))
    return by_word, alias


META = re.compile(r"(截断|缩略|简略|简称|缩写|略称|旧字体|异体|另一种写法|罕用写法|其他写法|假名写法|的形式$|^见|^参见|的敬语|的谦让语)")


def reading_ok(word: str, reading: str, rset: set) -> bool:
    """读音对不对得上。维基词典有时只给汉字部分的读音（走る → はし），要去掉送假名再比。"""
    if not reading:
        return False
    if reading in rset:
        return True
    tail = re.search(r"[\u3040-\u309f]+$", word)
    if tail and reading.endswith(tail.group(0)):
        stem = reading[: -len(tail.group(0))]
        return stem in rset or any(reading.startswith(x) and len(x) >= len(stem) for x in rset)
    return False


def definition(word: str, reading: str, by_word: dict, alias: dict, strict: bool = False) -> str:
    """strict：没标读音的词条也不用（同形异音词修正读音时用，免得拿到另一个读音的释义）。"""
    cands = by_word.get(word) or by_word.get(alias.get(word, ""), [])
    if not cands and reading:
        cands = by_word.get(reading) or by_word.get(alias.get(reading, ""), [])
    if not cands:
        return ""
    # 只用读音对得上的词条（同形异音词很多，对不上宁可不用，改用机翻 JMdict）；
    # 假名词（本身就是读音）直接用；专有名词（人名地名）不用
    kana_word = bool(re.fullmatch(r"[\u3040-\u30ffー]+", word))
    use = [c for c in cands if not c[2] and (kana_word or (not c[0] and not strict) or reading_ok(word, reading, c[0]))]
    if not use:
        return ""
    # 「××的截断形式」「××的异体写法」这类说明性义项：有别的释义时就不要
    real = [(p, t) for _, senses, _ in use for p, t in senses if not META.search(t)]
    allsenses = real or [(p, t) for _, senses, _ in use for p, t in senses]
    same_ok = not re.search(r"[\u3040-\u30ff]", word)  # 「猫」释义就是「猫」：汉字词照样给出
    groups: dict[str, list[str]] = {}
    for pos, txt in allsenses:
            lst = groups.setdefault(pos, [])
            if txt not in lst and (txt != word or same_ok) and len(lst) < 3:
                lst.append(txt)
    lines = []
    for pos, lst in groups.items():
        if lst:
            lines.append((pos + " " if pos else "") + "；".join(lst))
    if not lines:  # 只有和词形相同的释义（如「心身」）：也照样给出
        for _, senses, _ in use:
            for pos, txt in senses:
                return (pos + " " if pos else "") + txt
    return "\n".join(lines[:3])
