"""从 kaikki.org 的英文维基词典数据里，取出本项目词典里英语单词的词源和近义词 / 反义词。

用法：python tools/enwikt_extract.py kaikki.org-dictionary-English.jsonl.gz shici/data/dict_en.db 输出.jsonl
数据：维基词典（CC BY-SA 4.0），经 wiktextract / kaikki.org 提取。
"""
import gzip, json, sqlite3, sys

AFFIX = {"af", "affix", "prefix", "pre", "suffix", "suf", "confix", "con", "compound", "com", "surf", "blend", "doublet"}


def rel(items):
    out = []
    for s in items or []:
        w = s.get("word")
        if w and w.replace("-", "").isalpha() and " " not in w:
            out.append(w)
    return out


def main(src, db, dst):
    words = {r[0].lower() for r in sqlite3.connect(db).execute("SELECT word FROM entries")}
    n = k = 0
    with gzip.open(src, "rt", encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as out:
        for line in f:
            n += 1
            if '"lang_code": "en"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            w = e.get("word", "")
            if e.get("lang_code") != "en" or w.lower() not in words:
                continue
            # 每个词带上它出自第几个义项（-1 = 整个词条通用）：越靠前的义项越常用
            syn = [[x, -1] for x in rel(e.get("synonyms"))]
            ant = [[x, -1] for x in rel(e.get("antonyms"))]
            for i, s in enumerate(e.get("senses", []) or []):
                syn += [[x, i] for x in rel(s.get("synonyms"))]
                ant += [[x, i] for x in rel(s.get("antonyms"))]
            tpl = [{"name": t.get("name"), "args": t.get("args", {})} for t in e.get("etymology_templates", []) or []
                   if t.get("name") in AFFIX or t.get("name") in ("der", "inh", "bor", "m", "l", "uder", "lbor", "learned borrowing")]
            out.write(json.dumps({"word": w, "pos": e.get("pos"), "etym": (e.get("etymology_text") or "")[:1500],
                                  "tpl": tpl[:30], "syn": syn[:60], "ant": ant[:30]}, ensure_ascii=False) + "\n")
            k += 1
    print("lines", n, "kept", k)


if __name__ == "__main__":
    main(*sys.argv[1:4])
