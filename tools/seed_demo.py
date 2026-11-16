"""生成一份演示用的学习记录（模拟最近 50 天的学习），用来截图或试用界面。

    python tools/seed_demo.py --data ./demo-data
    python -m shici --data ./demo-data
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shici.core import Core  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--days", type=int, default=50)
    a = ap.parse_args()
    rnd = random.Random(7)
    now = time.time()
    t = [now]
    core = Core(a.data, clock=lambda: t[0])
    core.call("book_enable", {"id": "toefl"})
    core.call("book_enable", {"id": "jlpt-n5"})
    for w, note in [("ubiquitous", "ubi（哪里）+ quit → 哪里都不离开 → 无处不在"), ("serendipity", ""), ("ephemeral", "")]:
        core.call("add_word", {"term": w, "note": note})
    core.call("settings_set", {"new_per_day": 15})
    for back in range(a.days, 0, -1):
        if back > 9 and rnd.random() < 0.22:   # 偶尔休息一天；最近 9 天连续
            continue
        t[0] = now - back * 86400 + rnd.uniform(-2, 2) * 3600
        n, guard = core.call("next"), 0
        while n["card"] and guard < 400:
            guard += 1
            t[0] += rnd.uniform(4, 11)
            hard = n["card"]["lang"] == "ja" or len(n["card"]["term"]) > 9
            rating = rnd.choices([1, 2, 3, 4], weights=[16, 14, 64, 6] if hard else [8, 10, 72, 10])[0]
            n = core.call("answer", {"id": n["card"]["id"], "rating": rating, "elapsed_ms": int(rnd.uniform(2500, 9000))})
    t[0] = now
    print(core.call("home")["counts"], core.call("stats")["streak"])
    core.close()


if __name__ == "__main__":
    main()
