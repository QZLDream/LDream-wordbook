"""把界面用到的字体裁剪成小体积的 woff2（shici/web/fonts/）。

普通用户不需要运行。改了界面文字、想让新出现的汉字也用上衬线标题字体时再运行：

    pip install fonttools brotli
    python tools/build_fonts.py --src <字体目录>

<字体目录> 里放 Google Fonts 仓库 (github.com/google/fonts, 均为 SIL OFL 1.1) 里的四个可变字体：
    NotoSerifSC[wght].ttf   NotoSerifJP[wght].ttf   Inter[opsz,wght].ttf   JetBrainsMono[wght].ttf
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "shici" / "web"
OUT = WEB / "fonts"

LATIN = set(range(0x20, 0x7F)) | set(range(0xA0, 0x180)) | set(range(0x2010, 0x2040)) | {0x2190, 0x2191, 0x2192, 0x2193, 0x2212, 0x00D7, 0xFF0B}
IPA = set(range(0x250, 0x370)) | {0x3B8, 0x3B2, 0x1D4A}
CJK_PUNCT = set(range(0x3000, 0x3040)) | set(range(0xFF00, 0xFFF0))
KANA = set(range(0x3040, 0x3100))


def ui_chars() -> set[int]:
    """界面源码里出现过的所有汉字。"""
    chars: set[int] = set()
    for p in list(WEB.rglob("*.html")) + list(WEB.rglob("*.js")) + list(WEB.rglob("*.css")):
        chars |= {ord(c) for c in p.read_text(encoding="utf-8") if "一" <= c <= "鿿"}
    return chars


def jlpt_chars() -> set[int]:
    db = sqlite3.connect(ROOT / "shici" / "data" / "dict_ja.db")
    text = "".join(r[0] for r in db.execute("SELECT word FROM entries"))
    return {ord(c) for c in text if "㐀" <= c <= "鿿"}


def make(src: Path, out: str, unicodes: set[int], limits: dict, features=("kern", "mark", "mkmk", "ccmp", "locl")) -> None:
    font = TTFont(src)
    opts = subset.Options()
    opts.layout_features = list(features)
    opts.name_IDs = [1, 2, 3, 4, 6, 13, 14]
    opts.notdef_outline = True
    opts.hinting = False
    opts.drop_tables += ["vhea", "vmtx", "VVAR", "VORG", "STAT", "meta"]  # 横排用不到竖排度量
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=sorted(unicodes))
    sub.subset(font)  # 先裁剪字符再固定字重范围，速度快很多
    font = instancer.instantiateVariableFont(font, limits)
    font.flavor = "woff2"
    font.save(OUT / out)
    have = set(font.getBestCmap())
    print(f"{out}: {(OUT / out).stat().st_size / 1024:.0f} KB, {len(have)} 字符, 缺 {len(unicodes - have)} 个")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, type=Path)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    find = lambda pat: next(p for p in a.src.iterdir() if re.search(pat, p.name))  # noqa: E731
    make(find(r"NotoSerifSC.*\.ttf$"), "serif.woff2", LATIN | CJK_PUNCT | ui_chars(), {"wght": (500, 900)})
    make(find(r"NotoSerifJP.*\.ttf$"), "serif-jp.woff2", KANA | CJK_PUNCT | jlpt_chars(), {"wght": 700})
    make(find(r"Inter.*\.ttf$"), "sans.woff2", LATIN | IPA, {"opsz": 14, "wght": (300, 800)})
    make(find(r"JetBrainsMono.*\.ttf$"), "mono.woff2", LATIN, {"wght": (400, 700)})
