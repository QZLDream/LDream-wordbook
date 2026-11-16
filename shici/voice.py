"""单词发音的来源：内置语音包、在线发音（带本地缓存）。系统语音在 desktop.py 里。

内置语音包是两个 SQLite 文件（data/audio_en.db、audio_ja.db），每个词一条 MP3，
用开源语音合成提前生成好，所以不联网、不装语音包也能发音。
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
import urllib.request
from pathlib import Path
from urllib.parse import quote

from .paths import resource_dir

ONLINE_TIMEOUT = 4.0


def _looks_like_mp3(data: bytes) -> bool:
    return len(data) > 400 and (data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0))


class VoiceBank:
    def __init__(self, cache_dir: Path, data_dir: Path | None = None):
        self.cache = Path(cache_dir)
        self._lock = threading.Lock()
        self._packs: dict[str, sqlite3.Connection] = {}
        d = data_dir or resource_dir() / "data"
        for lang in ("en", "ja"):
            path = d / f"audio_{lang}.db"
            if path.exists():
                con = sqlite3.connect(path, check_same_thread=False)
                con.execute("PRAGMA query_only=ON")
                self._packs[lang] = con

    def pack_langs(self) -> list[str]:
        return sorted(self._packs)

    # ---- 内置语音包 ----
    def pack(self, lang: str, text: str) -> bytes | None:
        con = self._packs.get(lang)
        if not con:
            return None
        with self._lock:
            row = con.execute("SELECT data FROM audio WHERE word=?", (text,)).fetchone()
            if not row and lang == "en" and text != text.lower():
                row = con.execute("SELECT data FROM audio WHERE word=?", (text.lower(),)).fetchone()
        return bytes(row[0]) if row else None

    # ---- 在线发音 ----
    @staticmethod
    def online_url(lang: str, text: str, accent: str) -> str:
        url = "https://dict.youdao.com/dictvoice?audio=" + quote(text)
        return url + ("&le=jap" if lang == "ja" else ("&type=1" if accent == "uk" else "&type=2"))

    def _fetch(self, url: str) -> bytes | None:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=ONLINE_TIMEOUT) as r:
            data = r.read(2_000_000)
        return data if _looks_like_mp3(data) else None

    def online(self, lang: str, text: str, accent: str) -> bytes | None:
        """先看本地缓存，没有再联网取一次并缓存。断网或取不到时返回 None。"""
        tag = "ja" if lang == "ja" else f"en-{accent}"
        path = self.cache / "online" / tag / (hashlib.sha1(text.encode("utf-8")).hexdigest()[:20] + ".mp3")
        if path.exists():
            return path.read_bytes()
        try:
            data = self._fetch(self.online_url(lang, text, accent))
        except Exception:
            return None
        if data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return data

    # ---- 例句发音 ----
    # 例句太多（英语一万多句、日语六千多句），全部提前合成会让程序大一两百 MB，所以不内置：
    # 第一次播放时联网取一次并永久缓存，复习时还会在后台提前下载接下来几张卡片的例句。
    def _sentence_path(self, lang: str, text: str, accent: str) -> Path:
        tag = "ja" if lang == "ja" else f"en-{accent}"
        return self.cache / "sentences" / tag / (hashlib.sha1(text.encode("utf-8")).hexdigest()[:24] + ".mp3")

    def sentence_cached(self, lang: str, text: str, accent: str) -> bytes | None:
        path = self._sentence_path(lang, text, accent)
        return path.read_bytes() if path.exists() else None

    def sentence(self, lang: str, text: str, accent: str) -> bytes | None:
        """例句发音：本地缓存 → 有道词典的整句朗读 → 谷歌翻译的朗读。都取不到返回 None。"""
        data = self.sentence_cached(lang, text, accent)
        if data:
            return data
        gl = "ja" if lang == "ja" else ("en-GB" if accent == "uk" else "en-US")
        for url in (self.online_url(lang, text, accent),
                    "https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=" + gl + "&q=" + quote(text[:200])):
            try:
                data = self._fetch(url)
            except Exception:
                data = None
            if data:
                path = self._sentence_path(lang, text, accent)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return data
        return None

    def prefetch(self, jobs: list[tuple[str, str, str]]) -> None:
        """在后台把例句发音下载好：jobs = [(lang, text, accent), …]。只开一个后台线程，按顺序慢慢下。"""
        with self._lock:
            if not hasattr(self, "_queue"):
                import queue
                self._queue: "queue.Queue" = queue.Queue()
                self._queued: set = set()
                threading.Thread(target=self._prefetch_loop, name="shici-prefetch", daemon=True).start()
            for job in jobs:
                if job not in self._queued and not self._sentence_path(*job).exists():
                    self._queued.add(job)
                    self._queue.put(job)

    def _prefetch_loop(self) -> None:
        fails = 0
        while True:
            job = self._queue.get()
            ok = self.sentence(*job) is not None
            fails = 0 if ok else fails + 1
            if fails >= 3:  # 连着三次取不到，多半是断网了：清空队列，等下次再说
                with self._lock:
                    while not self._queue.empty():
                        self._queue.get_nowait()
                    self._queued.clear()
                fails = 0

    # ---- 给桌面播放器用：把音频落成文件 ----
    def as_file(self, kind: str, lang: str, text: str, data: bytes) -> Path:
        path = self.cache / "play" / f"{kind}-{lang}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:20]}.mp3"
        if not path.exists() or path.stat().st_size != len(data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return path
