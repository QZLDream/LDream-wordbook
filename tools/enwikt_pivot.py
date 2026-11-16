# 用法: curl -sSL https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl | python enwikt_pivot.py
# 从英文维基词典的英语词条翻译表里，取出同一义项下同时有日语和普通话译词的组，写到 ja_cmn_pivot.jsonl
import sys, json
out = open("ja_cmn_pivot.jsonl", "w", encoding="utf-8")
n = k = 0
def add(groups, t, default_sense=""):
    code = t.get("code") or t.get("lang_code")
    lang = t.get("lang", "")
    if code == "zh" or "Mandarin" in lang or "Chinese" in lang:
        if any(x in lang for x in ("Cantonese", "Hokkien", "Wu", "Hakka", "Min")): return
        code = "cmn"
    if code not in ("ja", "cmn") or not t.get("word"): return
    g = groups.setdefault(t.get("sense") or default_sense, {"ja": [], "cmn": []})
    g[code].append(t["word"])
for line in sys.stdin:
    n += 1
    if '"ja"' not in line:
        continue
    try:
        e = json.loads(line)
    except ValueError:
        continue
    groups = {}
    for t in e.get("translations", []) or []:
        add(groups, t)
    for s in e.get("senses", []) or []:
        for t in s.get("translations", []) or []:
            add(groups, t, (s.get("glosses") or [""])[0])
    for sense, g in groups.items():
        if g["ja"] and g["cmn"]:
            out.write(json.dumps({"en": e.get("word"), "pos": e.get("pos"), "sense": sense, "ja": g["ja"], "cmn": g["cmn"]}, ensure_ascii=False) + "\n")
            k += 1
print("lines", n, "groups", k, file=sys.stderr)
