"""生成内置语音包（shici/data/audio_en.db 与 audio_ja.db）。

普通用户不需要运行，仓库里已经带了生成好的语音包。想换声音或补充词汇时再运行：

    pip install piper-tts pyopenjtalk lameenc numpy
    python tools/build_audio.py --voices <目录> [--only en|ja] [--limit N]

<目录> 里需要有：
    en_US-ljspeech-medium.onnx 和 .onnx.json   Piper 英语语音，来自 huggingface.co/rhasspy/piper-voices
                                                （LJ Speech 数据集，公有领域）
    mei_normal.htsvoice                         Open JTalk 日语语音 “Mei”，来自 MMDAgent 示例包
                                                （名古屋工业大学，CC BY 3.0）

每个词合成一条 MP3（单声道 32 kbps），存进 SQLite：audio(word PRIMARY KEY, data BLOB)。
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "shici" / "data"


def trim(a: np.ndarray, sr: int, head: float = 0.03, tail: float = 0.09) -> np.ndarray:
    """去掉首尾静音，留一点余量，并做淡入淡出、统一响度。"""
    a = a.astype(np.float32)
    peak = float(np.max(np.abs(a))) if len(a) else 0.0
    if peak < 1e-4:
        return a[:0]
    loud = np.where(np.abs(a) > peak * 0.02)[0]
    s, e = max(0, loud[0] - int(head * sr)), min(len(a), loud[-1] + int(tail * sr))
    a = a[s:e] / peak * 0.89
    f = min(int(0.008 * sr), len(a) // 2)
    if f:
        a[:f] *= np.linspace(0, 1, f)
        a[-f:] *= np.linspace(1, 0, f)
    return a


def to_mp3(a: np.ndarray, sr: int) -> bytes:
    import lameenc

    enc = lameenc.Encoder()
    enc.set_bit_rate(32)
    enc.set_in_sample_rate(sr)
    enc.set_channels(1)
    enc.set_quality(2)
    enc.silence()
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes()
    return bytes(enc.encode(pcm)) + bytes(enc.flush())


def open_pack(lang: str, source: str) -> sqlite3.Connection:
    db = sqlite3.connect(DATA / f"audio_{lang}.db")
    db.execute("PRAGMA page_size=32768")  # 每条音频约 3 KB，用大页面能省下三分之一的文件体积
    db.executescript("CREATE TABLE IF NOT EXISTS audio(word TEXT PRIMARY KEY, data BLOB NOT NULL);"
                     "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);")
    db.execute("REPLACE INTO meta VALUES('source', ?)", (source,))
    return db


def progress(i: int, n: int, t0: float, lang: str) -> None:
    if i % 500 == 0 or i == n:
        print(f"[{lang}] {i}/{n}  {time.time() - t0:.0f}s", flush=True)


def build_en(voices: Path, limit: int | None) -> None:
    from piper import PiperVoice

    voice = PiperVoice.load(str(voices / "en_US-ljspeech-medium.onnx"))
    words = [r[0] for r in sqlite3.connect(DATA / "dict_en.db").execute("SELECT DISTINCT word FROM book_words ORDER BY word")]
    db = open_pack("en", "Piper en_US-ljspeech-medium (LJ Speech, public domain)")
    have = {r[0] for r in db.execute("SELECT word FROM audio")}
    todo = [w for w in words if w not in have][:limit]
    t0 = time.time()
    for i, w in enumerate(todo, 1):
        chunks = list(voice.synthesize(w + "."))  # 句号让语调自然收尾
        a = trim(np.concatenate([c.audio_float_array for c in chunks]), chunks[0].sample_rate)
        if len(a):
            db.execute("REPLACE INTO audio VALUES(?,?)", (w, to_mp3(a, chunks[0].sample_rate)))
        if i % 200 == 0:
            db.commit()
        progress(i, len(todo), t0, "en")
    db.commit()
    db.execute("PRAGMA page_size=1024")  # 每条只有 3 KB 左右，小页面能少浪费一半空间
    db.execute("VACUUM")
    db.close()


def kata(s: str) -> str:
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def same_reading(guess: str, reading: str) -> bool:
    """Open JTalk 猜的读音和词表读音是否一致（忽略长音的两种写法）。"""
    def norm(s: str) -> str:
        s = kata(s)
        s = re.sub(r"(?<=[オコソトノホモヨロゴゾドボポョ])ウ", "ー", s)
        s = re.sub(r"(?<=[エケセテネヘメレゲゼデベペ])イ", "ー", s)
        for row, v in (("アカサタナハマヤラワガザダバパャ", "ア"), ("イキシチニヒミリギジヂビピ", "イ"), ("ウクスツヌフムユルグズヅブプュ", "ウ"),
                       ("エケセテネヘメレゲゼデベペ", "エ"), ("オコソトノホモヨロゴゾドボポョ", "オ")):
            s = re.sub(f"(?<=[{row}]){v}", "ー", s)
        return s.replace("ヲ", "オ").replace("ヅ", "ズ").replace("ヂ", "ジ")
    return norm(guess) == norm(reading)


def build_ja(voices: Path, limit: int | None) -> None:
    import pyopenjtalk
    from pyopenjtalk import HTSEngine

    engine = HTSEngine(str(voices / "mei_normal.htsvoice").encode("utf-8"))
    rows = sqlite3.connect(DATA / "dict_ja.db").execute("SELECT word, phonetic FROM entries ORDER BY word").fetchall()
    db = open_pack("ja", "Open JTalk + HTS voice Mei (Nagoya Institute of Technology, CC BY 3.0)")
    have = {r[0] for r in db.execute("SELECT word FROM audio")}
    todo = [r for r in rows if r[0] not in have][:limit]
    t0, by_kana = time.time(), 0
    for i, (word, reading) in enumerate(todo, 1):
        text = re.sub(r"[()（）～〜]", "", word)
        # 汉字写法能带出正确的声调；但如果 Open JTalk 读成了别的读音，就改用词表里的假名
        if reading and not same_reading(pyopenjtalk.g2p(text, kana=True), reading):
            text, by_kana = reading, by_kana + 1
        wav = engine.synthesize(pyopenjtalk.make_label(pyopenjtalk.run_frontend(text)))
        a = np.asarray(wav, dtype=np.float32) / 32768.0
        a = trim(a[::2], 24000)  # 48 kHz → 24 kHz（语音能量集中在低频，直接抽取即可）
        if len(a):
            db.execute("REPLACE INTO audio VALUES(?,?)", (word, to_mp3(a, 24000)))
        if i % 200 == 0:
            db.commit()
        progress(i, len(todo), t0, "ja")
    db.commit()
    db.execute("PRAGMA page_size=1024")  # 每条只有 3 KB 左右，小页面能少浪费一半空间
    db.execute("VACUUM")
    db.close()
    print(f"[ja] 其中 {by_kana} 个词按假名读音合成")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voices", required=True, type=Path)
    ap.add_argument("--only", choices=["en", "ja"])
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.only != "ja":
        build_en(a.voices, a.limit)
    if a.only != "en":
        build_ja(a.voices, a.limit)
    for lang in ("en", "ja"):
        p = DATA / f"audio_{lang}.db"
        if p.exists():
            n = sqlite3.connect(p).execute("SELECT COUNT(*) FROM audio").fetchone()[0]
            print(f"{p.name}: {n} 条, {p.stat().st_size / 1e6:.1f} MB")
    sys.exit(0)
