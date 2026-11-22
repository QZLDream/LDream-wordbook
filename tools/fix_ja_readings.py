"""修正日语词典里同形异音词的读音（1.1.2）。

    python tools/fix_ja_readings.py <源数据目录> [shici/data]

JLPT 词表里同一个写法可能有好几条（今日：N5 きょう、N3 こんにち），以前的 build_dict.py 取了先出现的那条（N1 在最前），
于是「今日」显示 こんにち、「上手」显示 うわて、「塩」显示 えん，还被放进了 N1 词书。
这个脚本按 build_dict.jlpt_levels 的新规则（取最简单的级别）就地修正 dict_ja.db：读音、英文释义、中文释义、
JLPT 词书归属，并重新合成这些词的内置语音（audio_ja.db）。不用从头重建整个词典。
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_audio  # noqa: E402
import build_bilingual  # noqa: E402
import build_dict  # noqa: E402


def main() -> None:
    src = Path(sys.argv[1])
    data = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "shici" / "data"
    t0 = time.time()
    find = build_dict.load_jmdict(src)
    levels = build_dict.jlpt_levels(src, find)
    print(f"读完 JMdict 和 JLPT 词表：{time.time() - t0:.0f} 秒")
    db = sqlite3.connect(data / "dict_ja.db")
    cur = {w: (p, t) for w, p, t in db.execute("SELECT word, phonetic, tags FROM entries")}
    changed: list[tuple] = []
    for lv, rows in levels.items():
        for term, reading, meaning, tags, nf in rows:
            if term not in cur:
                db.execute("INSERT INTO entries(word, phonetic, translation, tags, rank) VALUES(?,?,?,?,?)", (term, reading, meaning, tags, nf))
                changed.append((term, None, reading))
            elif cur[term] != (reading, tags):
                if cur[term][0] != reading:
                    changed.append((term, cur[term][0], reading))
                db.execute("UPDATE entries SET phonetic=?, translation=?, tags=?, rank=? WHERE word=?", (reading, meaning, tags, nf, term))
    keep = {t for rows in levels.values() for t, *_ in rows}
    # JLPT 词书整个重排：每级按常用度排序（和 build_dict 一样）
    db.execute("DELETE FROM book_words WHERE book LIKE 'jlpt-n%'")
    for lv, rows in levels.items():
        rows = sorted(rows, key=lambda x: x[4])
        db.executemany("INSERT OR IGNORE INTO book_words VALUES(?,?,?)", [(f"jlpt-n{lv}", x[0], i) for i, x in enumerate(rows)])
        db.execute("UPDATE books SET count=? WHERE id=?", (len(rows), f"jlpt-n{lv}"))
    print(f"读音改了 {len(changed)} 个词；词书：" + "，".join(f"N{lv} {len(r)}" for lv, r in sorted(levels.items(), reverse=True)))
    for term, old, new in changed[:12]:
        print(f"  {term}: {old} → {new}")
    db.execute("REPLACE INTO meta VALUES('rev', '2026.11.22')")  # 程序看到版本变了，会把已加入计划的词书补上新归进来的词
    db.commit()
    # 中文释义：按新读音重新匹配
    try:
        from opencc import OpenCC
        t2s = OpenCC("t2s").convert
    except ImportError:
        t2s = lambda s: s  # noqa: E731
    en = sqlite3.connect(data / "dict_en.db")
    build_bilingual.build_ja_zh(src, db, en, t2s, only={t for t, _, _ in changed})
    # 自动匹配出来明显不对的几个，手工改
    fix = {"値": "n. 价格；价值；数值", "汚れる": "v. 变脏，弄脏；被玷污", "玉": "n. 球；珠子；玉石",
           "所々": "n./adv. 处处，到处，各处"}
    for w, zh in fix.items():
        db.execute("UPDATE entries SET translation_zh=?, zh_src='manual' WHERE word=?", (zh, w))
    db.commit()
    db.close()
    # 内置语音：重新合成读音变了的词
    import numpy as np
    import pyopenjtalk
    from pyopenjtalk import HTSEngine
    voice = Path(pyopenjtalk.__file__).parent / "htsvoice" / "mei_normal.htsvoice"
    engine = HTSEngine(str(voice).encode("utf-8"))
    pack = sqlite3.connect(data / "audio_ja.db")
    for term, _, reading in changed:
        text = re.sub(r"[()（）～〜]", "", term)
        if reading and not build_audio.same_reading(pyopenjtalk.g2p(text, kana=True), reading):
            text = reading
        wav = engine.synthesize(pyopenjtalk.make_label(pyopenjtalk.run_frontend(text)))
        a = build_audio.trim((np.asarray(wav, dtype=np.float32) / 32768.0)[::2], 24000)
        if len(a):
            pack.execute("REPLACE INTO audio VALUES(?,?)", (term, build_audio.to_mp3(a, 24000)))
    pack.commit()
    pack.execute("VACUUM")
    pack.close()
    print(f"重新合成了 {len(changed)} 个词的内置语音。共用时 {time.time() - t0:.0f} 秒；不在词表里的旧条目保留 {len(set(cur) - keep)} 个")


if __name__ == "__main__":
    main()
