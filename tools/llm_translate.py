"""用本地小模型重新翻译“机翻”例句（1.1.6）。

    python tools/llm_translate.py <模型目录> <缓存文件> [shici/data] [all|apply]

模型目录里放 ctranslate2 int8 转换好的 qwen15-ct2（Qwen2.5-1.5B-Instruct；试过 0.5B，常把提示抄回来、漏译）：
    ct2-transformers-converter --model Qwen/Qwen2.5-1.5B-Instruct --output_dir qwen15-ct2 --quantization int8
两核 CPU 上大约每秒 2~3 句。

以前没有人工中文译文的例句用 opus-mt 翻译，质量差，常把句子里的生词翻错（learn by rote → “由腐烂”）。
现在用 Qwen2.5-1.5B-Instruct（ctranslate2 int8，CPU 上就能跑），并在提示里告诉它这个句子是哪个词的例句、
这个词在词典里的意思，译文就会用对词义。日语例句直接从日语翻成中文（以前是先看英文译文再机翻）。
默认只翻词书里的词用到的、像是翻错了的机翻例句（译文里找不到这个词的中文释义），按词书常用程度先后翻；
加 all 全部重翻；apply 只把缓存里已经翻好的写回词典。结果追加到缓存文件，中断后可以接着跑。
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
from pathlib import Path

SYSTEM = "你是专业译者，把句子译成自然、准确、简洁的简体中文。只输出译文，不要解释。"
CJK = re.compile(r"[一-鿿]")


def short_gloss(translation: str) -> str:
    """词典释义的前两行（带词性），每行最多 30 个字"""
    out = []
    for line in (translation or "").split("\n"):
        line = re.sub(r"\[[^\]]*\]|（[^）]*）|\([^)]*\)", "", line).strip()
        if CJK.search(line) and not line.startswith("["):
            out.append(line[:30])
        if len(out) == 2:
            break
    return "；".join(out)


ORDER = ["zk", "gk", "cet4", "jlpt-n5", "jlpt-n4", "cet6", "ky", "jlpt-n3", "toefl", "ielts", "jlpt-n2", "gre", "jlpt-n1"]


def suspicious(zh: str, gloss: str) -> bool:
    """旧机翻像是翻错了：译文里找不到这个词的任何一个中文释义，或者夹着没翻的英文"""
    from build_bilingual import gloss_terms
    terms = gloss_terms(gloss or "")
    ok = any(t in (zh or "") for t in terms if len(t) >= 1)
    return not zh or not ok or bool(re.search(r"[A-Za-z]{3,}", zh))


def jobs(data: Path, everything: bool) -> list[tuple[str, int, str, str, str]]:
    """(语言, sid, 原句, 目标词, 词义)，按词书的常用程度排好（中考、高考、四级、N5…先翻）。
    每个句子只翻一次；默认只翻词书里的词用到的、像是翻错了的机翻句子，everything=True 时全部重翻。"""
    sys.path.insert(0, str(Path(__file__).parent))
    out, seen = [], set()
    plan: list[tuple[int, str, int, str, str, str]] = []
    for lang in ("en", "ja"):
        db = sqlite3.connect(data / f"dict_{lang}.db")
        col = "translation_zh" if lang == "ja" else "translation"
        prio: dict[str, int] = {}
        for book, word in db.execute("SELECT book, word FROM book_words"):
            k = ORDER.index(book) if book in ORDER else len(ORDER)
            prio[word] = min(prio.get(word, 99), k)
        for word, sid, text, zh, gl in db.execute(
                f"SELECT e.word, s.sid, s.en, s.zh, n.{col} FROM examples e JOIN sentences s ON s.sid=e.sid "
                "JOIN entries n ON n.word=e.word WHERE s.mt=1 ORDER BY e.rowid"):
            if word not in prio and not everything:
                continue
            if not everything and not suspicious(zh, gl):
                continue
            plan.append((prio.get(word, 99), lang, sid, text, word, short_gloss(gl or "")))
        db.close()
    plan.sort(key=lambda x: x[0])
    for _, lang, sid, text, word, gloss in plan:
        if (lang, sid) not in seen:
            seen.add((lang, sid))
            out.append((lang, sid, text, word, gloss))
    return out


KANA = re.compile(r"[\u3040-\u30ff]")


def clean(out: str, src: str, lang: str) -> str:
    """模型偶尔会把原文、提示抄回来，或者没翻完：这些不要（保留原来的机翻）。"""
    out = out.strip().split("\n")[0].strip()
    out = re.sub(r"^(译文|翻译|中文|简体中文)[：:]\s*", "", out).strip().strip("“”\"'")
    if not out or not CJK.search(out) or "提示" in out or "日本语" in out or "日文" in out or "英文" in out:
        return ""
    if lang == "ja" and len(KANA.findall(out)) > 1:
        return ""
    if lang == "en" and len(re.findall(r"[A-Za-z]{3,}", out)) > 2:
        return ""
    if len(out) > 3 * len(src) + 10:
        return ""
    return out


def main() -> None:
    import ctranslate2
    from transformers import AutoTokenizer
    model, cache = Path(sys.argv[1]), Path(sys.argv[2])
    data = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parent.parent / "shici" / "data"
    everything = len(sys.argv) > 4 and sys.argv[4] == "all"  # 第 4 个参数：all 全部重翻 / apply 只把缓存写回词典
    done: dict[str, str] = {}
    if cache.exists():
        for line in open(cache, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) == 2:
                done[p[0]] = p[1]
    apply_only = len(sys.argv) > 4 and sys.argv[4] == "apply"
    if not apply_only:
        tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
        gen = ctranslate2.Generator(str(model / "qwen15-ct2"), device="cpu", intra_threads=2)
        # 系统提示每句都一样：作为 static_prompt 只算一次
        full = tok.apply_chat_template([{"role": "system", "content": SYSTEM}, {"role": "user", "content": "@@@"}],
                                       add_generation_prompt=True, tokenize=False)
        pre, post = full.split("@@@")
        static = tok.convert_ids_to_tokens(tok.encode(pre))

        def body(text: str, word: str, gloss: str, lang: str) -> list[str]:
            # 告诉模型这是哪个词的例句、词典里有哪些意思，让它按句意挑（只给一个意思时会被带偏：maul 的第一个意思是“大槌”）
            hint = f"\n（“{word}”的词典释义：{gloss}。按句意选用合适的意思。）" if gloss else ""
            return tok.convert_ids_to_tokens(tok.encode(("日文：" if lang == "ja" else "") + text + hint + post))

        todo = [j for j in jobs(data, everything) if f"{j[0]}:{j[1]}" not in done]
        print(f"要翻译 {len(todo)} 句（英语 {sum(j[0] == 'en' for j in todo)}，日语 {sum(j[0] == 'ja' for j in todo)}）", flush=True)
        t0 = time.time()
        with open(cache, "a", encoding="utf-8") as f:
            for i in range(0, len(todo), 24):
                chunk = todo[i:i + 24]
                res = gen.generate_batch([body(t, w, g, lang) for lang, _, t, w, g in chunk], static_prompt=static,
                                         max_length=96, sampling_topk=1, include_prompt_in_result=False, max_batch_size=24)
                for (lang, sid, text, _, _), r in zip(chunk, res):
                    zh = clean(tok.decode(r.sequences_ids[0], skip_special_tokens=True), text, lang)
                    if zh:
                        done[f"{lang}:{sid}"] = zh
                        f.write(f"{lang}:{sid}\t{zh}\n")
                f.flush()
                n = i + len(chunk)
                if n % 960 < 24:
                    rate = n / max(1, time.time() - t0)
                    print(f"  {n}/{len(todo)}  {rate:.1f} 句/秒  还要约 {(len(todo) - n) / max(rate, .01) / 60:.0f} 分钟", flush=True)
    # 写回词典（还是标“机翻”）
    for lang in ("en", "ja"):
        db = sqlite3.connect(data / f"dict_{lang}.db")
        rows = [(zh, int(k.split(":")[1])) for k, zh in done.items() if k.startswith(lang + ":")]
        db.executemany("UPDATE sentences SET zh=? WHERE sid=? AND mt=1", rows)
        db.commit()
        db.close()
        print(f"{lang}: 写回 {len(rows)} 句", flush=True)

if __name__ == "__main__":
    main()
