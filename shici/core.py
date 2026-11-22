"""程序核心：用户数据库、每日队列、复习调度、词库管理、统计。

界面通过 Core.call("方法名", 参数字典) 调用这里所有以 api_ 开头的方法，
返回值都是可以直接转成 JSON 的字典。
"""
from __future__ import annotations

import base64
import csv
import json
import lzma
import random
import re
import sqlite3
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from . import APP_NAME, __version__
from .dictionary import Dictionary
from .importer import detect_lang, parse_file
from .paths import user_data_dir
from .scheduler import LEARNING, NEW, RELEARNING, REVIEW, Card, Srs, State, utc
from .voice import VoiceBank
from .fonts import FontStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
    id INTEGER PRIMARY KEY,
    lang TEXT NOT NULL,              -- en / ja
    term TEXT NOT NULL,
    reading TEXT,                    -- 音标或假名；NULL 表示用内置词典的
    definition TEXT,                 -- 释义；NULL 表示用内置词典的
    note TEXT NOT NULL DEFAULT '',   -- 自己写的助记
    examples TEXT NOT NULL DEFAULT '[]',  -- 自己加的例句 [{en, zh}]
    prio INTEGER NOT NULL DEFAULT 1, -- 0 = 自己添加或导入的词（优先学），1 = 词书里的词
    rank INTEGER NOT NULL DEFAULT 0, -- 词频排名，越小越常用
    shuffle INTEGER NOT NULL DEFAULT 0,
    added_at INTEGER NOT NULL,
    suspended INTEGER NOT NULL DEFAULT 0,
    UNIQUE(lang, term)
);
CREATE TABLE IF NOT EXISTS item_sources(
    item_id INTEGER NOT NULL, source TEXT NOT NULL,   -- book:toefl / list:名称 / manual
    PRIMARY KEY(item_id, source)
);
CREATE INDEX IF NOT EXISTS idx_sources ON item_sources(source);
CREATE TABLE IF NOT EXISTS cards(
    item_id INTEGER PRIMARY KEY,
    state INTEGER NOT NULL,          -- 1 学习中 / 2 复习中 / 3 重新学习
    due INTEGER NOT NULL,            -- 下次复习时间（Unix 秒）
    stability REAL, difficulty REAL,
    data TEXT NOT NULL,              -- py-fsrs Card 的 JSON
    reps INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0,
    first_review INTEGER, last_review INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(state, due);
CREATE TABLE IF NOT EXISTS logs(
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL, ts INTEGER NOT NULL, rating INTEGER NOT NULL,
    mode TEXT NOT NULL DEFAULT 'recall',   -- recall 回忆 / spell 拼写
    elapsed_ms INTEGER NOT NULL DEFAULT 0,
    state_before INTEGER NOT NULL DEFAULT 0, was_new INTEGER NOT NULL DEFAULT 0,
    prev TEXT                               -- 复习前的卡片状态，用于撤销
);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts);
CREATE INDEX IF NOT EXISTS idx_logs_item ON logs(item_id);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT NOT NULL);
-- 局域网同步用的“事件”：删掉的词、移出计划的词书 / 词表、撤销掉的复习、清空进度。
-- 两台设备合并进度时靠它知道哪些东西是被故意删掉的，免得又从对方那里同步回来。
CREATE TABLE IF NOT EXISTS sync_events(
    kind TEXT NOT NULL,   -- item 词条 / source 词书或词表 / undo 撤销的复习 / reset 清空进度
    key TEXT NOT NULL,    -- item: 语言\t单词；source: book:toefl 这类；undo: 语言\t单词\t复习时间；reset: 空
    val INTEGER NOT NULL, -- source: 1 加入 / 0 移出；其他: 0
    ts INTEGER NOT NULL,
    PRIMARY KEY(kind, key)
);
"""

DEFAULTS = {
    "new_per_day": 20,      # 每天新词数
    "review_per_day": 200,  # 每天复习上限，0 = 不限
    "retention": 0.90,      # 期望记忆保持率
    "order": "freq",        # 新词顺序：freq 常用优先 / random 随机 / alpha 字母序
    "autoplay": True,       # 出现单词时自动朗读
    "autoplay_example": False,  # 显示答案时自动朗读第一条例句（单词读完之后）
    "voice_rate": 1.0,      # 语速：0.6~1.3 倍，内置 / 在线 / 例句 / 系统语音都按这个速度读（不变调）
    "voice": "builtin",     # builtin 内置语音包（离线）/ online 在线真人发音 / system 系统语音
    "online_fallback": True,  # 内置语音包里没有的词（自己加的生词）联网取发音并缓存
    "accent": "us",         # 在线发音口音 us / uk
    "show_examples": True,
    "theme": "light",       # light / dark / auto
    "palette": "silver",    # 配色：silver 简约白（默认）/ vermilion 朱橙
    "motion": "full",       # full / reduced
    "font_title": "",       # 标题和单词的字体："" 跟随配色 / builtin:serif / builtin:sans / system:<字体名> / user:<id>
    "font_body": "",        # 正文字体，取值同上
    "haptic": False,        # 震动反馈（安卓版，默认关闭）
    "sfx": True,            # 按键音效（默认打开，木质）
    "sfx_set": "wood",      # wood 木质 / felt 毛毡 / stone 石子 / keys 键盘 / glass 玻璃
    "sfx_volume": 60,
    "day_start": 4,         # 一天从凌晨几点开始算
    "gloss_en": "zh",       # 英语词的释义：zh 英中 / ja 日英
    "gloss_ja": "zh",       # 日语词的释义：zh 中日 / en 英日
    "show_domain": False,
    "show_roots": False,    # 英语单词显示词根拆分和同根词
    "show_related": False,  # 英语单词显示近义词、反义词   # 显示「[计]」「[医]」这类专业领域释义
    "update_check": True,   # 启动时联网检查有没有新版本（只访问 GitHub 的发布页接口）
    "render": "auto",       # 画面渲染方式（Windows 桌面版）：auto 自动（N 卡 / A 卡用 OpenGL）/ d3d11 / opengl
    "gpu": "auto",          # 渲染用哪张显卡（Windows 双显卡）：auto 系统决定 / high 高性能 / low 省电
    "lan_sync": False,      # 局域网同步：同一个 Wi-Fi 下的手机和电脑自动合并进度
    "sync_code": "",        # 同步码：两台设备填一样的才会互相同步
}
RELEASES_API = "https://api.github.com/repos/QZLDream/LDream-wordbook/releases/latest"
LINKS = {
    "github": "https://github.com/QZLDream/LDream-wordbook",
    "releases": "https://github.com/QZLDream/LDream-wordbook/releases/latest",
    "bilibili": "https://space.bilibili.com/397075230",
    "netdisk": "https://pan.baidu.com/s/1FHgXzc63Vxhqn1hGDLpuLQ?pwd=2922",
    "netdisk_code": "2922",
}
MATURE_DAYS = 21  # 稳定度超过 21 天算“已掌握”
KEY_PREFIX = "XMCS1."  # 进度密钥的开头：小梦词书，第 1 版格式
FILE_MAGIC = b"XMDB1\n"  # 进度文件（.xmdb）的开头，后面紧跟和密钥同样的压缩数据
STUDY_KEYS = ("new_per_day", "review_per_day", "retention", "order", "day_start")  # 随密钥带走的学习设置


class ApiError(Exception):
    pass


class Core:
    def __init__(self, data_dir: Path | str | None = None, dictionary: Dictionary | None = None, clock=time.time):
        self.dir = Path(data_dir) if data_dir else user_data_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.lock = threading.RLock()
        self.dict = dictionary or Dictionary()
        self.db = sqlite3.connect(self.dir / "user.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.settings = dict(DEFAULTS)
        for r in self.db.execute("SELECT k, v FROM settings"):
            if r["k"] in DEFAULTS:
                self.settings[r["k"]] = json.loads(r["v"])
        if self.settings["render"] not in ("auto", "d3d11", "opengl"):  # 0.5.3 的「软件渲染」已去掉
            self.settings["render"] = "auto"
        self.srs = Srs(self.settings["retention"])
        self._apply_gloss()
        self._refresh_books()
        self._undo: list[int] = []
        self.voice = VoiceBank(self.dir / "audio-cache")
        self.fonts = FontStore(self.dir)
        self.system_fonts: list[str] = []  # 桌面外壳启动时填入系统里装的字体
        self.speaker = None  # 桌面外壳注入：speaker(text, lang, 音频文件路径或空串) 负责出声
        self.clipboard = None  # 桌面外壳注入：clipboard(text) 写入系统剪贴板
        self.voice_langs: set[str] | None = None  # 系统语音支持的语言；None = 还不知道
        self.opener = None   # 桌面外壳注入：opener(path) 在文件管理器里打开
        self.restarter = None      # 桌面外壳注入：restarter() 重启程序（换渲染方式后用）
        self.android = False       # 安卓版外壳设置
        self.file_saver = None     # 安卓版注入：file_saver(路径) 把导出的文件存到手机的“下载”文件夹，返回给人看的位置
        self.render_trial = False  # 桌面外壳设置：这次是不是刚换了渲染方式、等用户确认画面正常
        self.render_confirm = None # 桌面外壳注入：用户确认新的渲染方式没问题
        self.display_ok = None     # 桌面外壳注入：界面已经正常画出来（参数：网页用的显卡名）
        self.look_changed = None   # 桌面外壳注入：主题 / 明暗变了（参数：是否暗色, 是否简约白），用来同步窗口底色
        self.display_reverted = False  # 上次的画面设置没能正常打开，这次已自动换回默认
        self.url_opener = None  # 桌面外壳注入：url_opener(url) 用系统浏览器打开网页
        self.device_name = ""   # 局域网同步时给对方看的设备名；空 = 用电脑名
        from .lansync import LanSync
        self.sync = LanSync(self)

    # ------------------------------------------------------------ 调度入口
    def call(self, name: str, params: dict | None = None):
        fn = getattr(self, "api_" + name, None)
        if not fn:
            raise ApiError(f"未知接口: {name}")
        if name in ("speak", "sync_status"):  # 朗读可能要联网取音频、同步状态随时要看：不占用数据库锁，免得卡住别的操作
            return fn(params or {})
        with self.lock:
            try:
                return fn(params or {})
            except Exception:
                self.db.rollback()
                raise

    def _refresh_books(self) -> None:
        """词典更新后（词书里加了词、词换了词书），把已加入计划的词书补齐。只在词典版本变了时做一次。"""
        rev = self.dict.revision()
        row = self.db.execute("SELECT v FROM settings WHERE k='_dict_rev'").fetchone()
        if row and json.loads(row["v"]) == rev:
            return
        for (src,) in self.db.execute("SELECT DISTINCT source FROM item_sources WHERE source LIKE 'book:%'").fetchall():
            if self.dict.book(src[5:]):
                lang, words = self.dict.book_words(src[5:])
                self._insert_items(lang, [{"term": w, "rank": r} for w, r in words], src, prio=1)
        self.db.execute("REPLACE INTO settings(k, v) VALUES('_dict_rev', ?)", (json.dumps(rev),))
        self.db.commit()

    # ------------------------------------------------------------ 同步事件
    def _event(self, kind: str, key: str, val: int = 0, ts: int | None = None) -> None:
        self.db.execute("REPLACE INTO sync_events(kind, key, val, ts) VALUES(?,?,?,?)",
                        (kind, key, val, int(self.clock()) if ts is None else ts))

    # ------------------------------------------------------------ 时间
    def _day_start(self, ts: float | None = None) -> float:
        h = int(self.settings["day_start"])
        d = datetime.fromtimestamp(self.clock() if ts is None else ts) - timedelta(hours=h)
        return (datetime(d.year, d.month, d.day) + timedelta(hours=h)).timestamp()

    def _day(self, ts: float) -> date:
        return (datetime.fromtimestamp(ts) - timedelta(hours=int(self.settings["day_start"]))).date()

    # ------------------------------------------------------------ 词条
    def _resolve(self, it: sqlite3.Row, full: bool = False) -> dict:
        """把用户词条和内置词典合并成界面要显示的内容。"""
        entry = None
        if it["reading"] is None or it["definition"] is None or full:
            entry = self.dict.lookup(it["lang"], it["term"])
            if entry and entry["word"].lower() != it["term"].lower():
                entry = dict(entry, phonetic="")  # 查到的是原形，音标不通用
        out = {
            "id": it["id"], "lang": it["lang"], "term": it["term"],
            "reading": it["reading"] if it["reading"] is not None else (entry or {}).get("phonetic", ""),
            "definition": it["definition"] if it["definition"] is not None else (entry or {}).get("translation", ""),
            "auto_def": it["definition"] is None and bool((entry or {}).get("auto")),
            "note": it["note"], "suspended": bool(it["suspended"]),
        }
        if full:
            mine = json.loads(it["examples"] or "[]")
            out["my_examples"] = mine
            out["examples"] = mine + self.dict.examples(it["lang"], (entry or {}).get("word", it["term"]))
            out["custom_definition"] = it["definition"] is not None
            out["sources"] = self._source_titles(it["id"])
            if it["lang"] == "en":
                base = (entry or {}).get("word", it["term"])
                if self.settings.get("show_roots"):
                    out["roots"] = self.dict.morph(base)
                if self.settings.get("show_related"):
                    out["related"] = self.dict.related(base)
        return out

    def _source_titles(self, item_id: int) -> list[str]:
        titles = []
        books = {b["id"]: b["title"] for b in self.dict.books()}
        for r in self.db.execute("SELECT source FROM item_sources WHERE item_id=? ORDER BY source", (item_id,)):
            kind, _, name = r["source"].partition(":")
            titles.append(books.get(name, name) if kind == "book" else (name if kind == "list" else "自己添加"))
        return titles

    @staticmethod
    def _status(card: sqlite3.Row | None, suspended: bool) -> str:
        if suspended:
            return "suspended"
        if card is None or card["state"] is None:
            return "new"
        if card["state"] != REVIEW:
            return "learning"
        return "mature" if (card["stability"] or 0) >= MATURE_DAYS else "young"

    def _card_payload(self, it: sqlite3.Row, card: sqlite3.Row | None, now: float) -> dict:
        out = self._resolve(it, full=True)
        out.update({
            "is_new": card is None,
            "state": card["state"] if card else NEW,
            "reps": card["reps"] if card else 0,
            "lapses": card["lapses"] if card else 0,
            "intervals": self.srs.preview(card["data"] if card else None, now),
        })
        return out

    def _insert_items(self, lang: str, rows: list[dict], source: str, prio: int) -> tuple[int, int]:
        """rows: [{term, reading?, definition?, rank?}]，返回 (新增数, 已存在数)。"""
        now = int(self.clock())
        before = self.db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        self.db.executemany(
            "INSERT OR IGNORE INTO items(lang, term, reading, definition, prio, rank, shuffle, added_at) VALUES(?,?,?,?,?,?,?,?)",
            [(lang, r["term"], r.get("reading") or None, r.get("definition") or None, prio,
              int(r.get("rank") or 0), random.getrandbits(30), now) for r in rows],
        )
        added = self.db.execute("SELECT COUNT(*) FROM items").fetchone()[0] - before
        self.db.executemany(
            "INSERT OR IGNORE INTO item_sources(item_id, source) SELECT id, ? FROM items WHERE lang=? AND term=?",
            [(source, lang, r["term"]) for r in rows],
        )
        if prio == 0:  # 自己加的词即使原来在词书里，也提到前面学
            self.db.executemany("UPDATE items SET prio=0 WHERE lang=? AND term=?", [(lang, r["term"]) for r in rows])
        return added, len(rows) - added

    # ------------------------------------------------------------ 队列
    def _counts(self, now: float) -> dict:
        start, end = self._day_start(now), self._day_start(now) + 86400
        q = lambda sql, *a: self.db.execute(sql, a).fetchone()[0]  # noqa: E731
        alive = "JOIN items i ON i.id=c.item_id AND i.suspended=0"
        learning = q(f"SELECT COUNT(*) FROM cards c {alive} WHERE c.state IN (?,?) AND c.due<?", LEARNING, RELEARNING, end)
        review_due = q(f"SELECT COUNT(*) FROM cards c {alive} WHERE c.state=? AND c.due<?", REVIEW, end)
        new_done = q("SELECT COUNT(*) FROM logs WHERE was_new=1 AND ts>=?", start)
        review_done = q("SELECT COUNT(*) FROM logs WHERE state_before=? AND ts>=?", REVIEW, start)
        unseen = q("SELECT COUNT(*) FROM items i LEFT JOIN cards c ON c.item_id=i.id WHERE c.item_id IS NULL AND i.suspended=0")
        cap = int(self.settings["review_per_day"])
        review = review_due if cap <= 0 else min(review_due, max(0, cap - review_done))
        new = min(unseen, max(0, int(self.settings["new_per_day"]) - new_done))
        done = q("SELECT COUNT(*) FROM logs WHERE ts>=?", start)
        return {"new": new, "learning": learning, "review": review, "done": done,
                "total": new + learning + review, "unseen": unseen}

    def _pick(self, now: float, last: int | None = None) -> tuple[sqlite3.Row, sqlite3.Row | None] | None:
        end = self._day_start(now) + 86400
        counts = self._counts(now)
        join = "FROM cards c JOIN items i ON i.id=c.item_id AND i.suspended=0"
        pair = lambda c: (self.db.execute("SELECT * FROM items WHERE id=?", (c["item_id"],)).fetchone(), c)  # noqa: E731
        # 1. 到时间的学习中卡片
        c = self.db.execute(f"SELECT c.* {join} WHERE c.state IN (?,?) AND c.due<=? ORDER BY c.due LIMIT 1",
                            (LEARNING, RELEARNING, now)).fetchone()
        if c:
            return pair(c)
        # 2. 今天到期的复习
        if counts["review"] > 0:
            c = self.db.execute(f"SELECT c.* {join} WHERE c.state=? AND c.due<? ORDER BY c.due LIMIT 1", (REVIEW, end)).fetchone()
            if c:
                return pair(c)
        # 3. 新词
        if counts["new"] > 0:
            order = {"random": "i.shuffle", "alpha": "i.term COLLATE NOCASE"}.get(self.settings["order"], "i.rank")
            it = self.db.execute(
                "SELECT i.* FROM items i LEFT JOIN cards c ON c.item_id=i.id "
                f"WHERE c.item_id IS NULL AND i.suspended=0 ORDER BY i.prio, {order}, i.id LIMIT 1").fetchone()
            if it:
                return it, None
        # 4. 还没到时间的学习中卡片（提前学完，不让人干等）
        rows = self.db.execute(f"SELECT c.* {join} WHERE c.state IN (?,?) AND c.due<? ORDER BY c.due LIMIT 2",
                               (LEARNING, RELEARNING, end)).fetchall()
        if rows:
            c = rows[1] if len(rows) > 1 and rows[0]["item_id"] == last else rows[0]
            return pair(c)
        return None

    def api_next(self, p: dict) -> dict:
        now = self.clock()
        picked = self._pick(now, p.get("last"))
        card = self._card_payload(picked[0], picked[1], now) if picked else None
        self._prefetch_examples([card])
        return {"card": card, "counts": self._counts(now), "can_undo": bool(self._undo)}

    def api_answer(self, p: dict) -> dict:
        item_id, rating = int(p["id"]), int(p["rating"])
        if rating not in (1, 2, 3, 4):
            raise ApiError("评分必须是 1~4")
        if not self.db.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone():
            raise ApiError("词条不存在")
        now = self.clock()
        row = self.db.execute("SELECT * FROM cards WHERE item_id=?", (item_id,)).fetchone()
        state_before = row["state"] if row else NEW
        card = self.srs.review(row["data"] if row else None, rating, now)
        lapses = (row["lapses"] if row else 0) + (1 if rating == 1 and state_before == REVIEW else 0)
        self.db.execute(
            "REPLACE INTO cards(item_id, state, due, stability, difficulty, data, reps, lapses, first_review, last_review) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (item_id, int(card.state), int(card.due.timestamp()), card.stability, card.difficulty, card.to_json(),
             (row["reps"] if row else 0) + 1, lapses, row["first_review"] if row else int(now), int(now)),
        )
        cur = self.db.execute(
            "INSERT INTO logs(item_id, ts, rating, mode, elapsed_ms, state_before, was_new, prev) VALUES(?,?,?,?,?,?,?,?)",
            (item_id, int(now), rating, p.get("mode") or "recall", min(int(p.get("elapsed_ms") or 0), 120000),
             state_before, 0 if row else 1, json.dumps(dict(row)) if row else None),
        )
        self.db.commit()
        self._undo = (self._undo + [cur.lastrowid])[-50:]
        return self.api_next({"last": item_id})

    def api_undo(self, p: dict) -> dict:
        if not self._undo:
            return {"undone": False}
        log = self.db.execute("SELECT * FROM logs WHERE id=?", (self._undo.pop(),)).fetchone()
        if not log:
            return {"undone": False}
        it0 = self.db.execute("SELECT lang, term FROM items WHERE id=?", (log["item_id"],)).fetchone()
        if it0:
            self._event("undo", f"{it0['lang']}\t{it0['term']}\t{log['ts']}")
        if log["prev"]:
            prev = json.loads(log["prev"])
            cols = ",".join(prev)
            self.db.execute(f"REPLACE INTO cards({cols}) VALUES({','.join('?' * len(prev))})", list(prev.values()))
        else:
            self.db.execute("DELETE FROM cards WHERE item_id=?", (log["item_id"],))
        self.db.execute("DELETE FROM logs WHERE id=?", (log["id"],))
        self.db.commit()
        now = self.clock()
        it = self.db.execute("SELECT * FROM items WHERE id=?", (log["item_id"],)).fetchone()
        card = self.db.execute("SELECT * FROM cards WHERE item_id=?", (log["item_id"],)).fetchone()
        return {"undone": True, "card": self._card_payload(it, card, now), "counts": self._counts(now),
                "can_undo": bool(self._undo)}

    def api_practice(self, p: dict) -> dict:
        """自由拼写练习：从学过的词里随机抽，不影响复习安排。"""
        n = max(1, min(100, int(p.get("n") or 20)))
        now = self.clock()
        rows = self.db.execute(
            "SELECT i.* FROM items i JOIN cards c ON c.item_id=i.id WHERE i.suspended=0 ORDER BY random() LIMIT ?", (n,)).fetchall()
        return {"cards": [self._card_payload(it, None, now) | {"is_new": False} for it in rows]}

    # ------------------------------------------------------------ 首页
    def api_home(self, p: dict) -> dict:
        now = self.clock()
        s = self._stats_core(now)
        nxt = self.db.execute(
            "SELECT MIN(c.due) FROM cards c JOIN items i ON i.id=c.item_id AND i.suspended=0").fetchone()[0]
        # 打开首页时，在后台把今天要复习的词的例句发音先下好（最多 60 个词），复习时就不用等
        due = self.db.execute("SELECT i.lang, i.term, i.examples FROM cards c JOIN items i ON i.id=c.item_id AND i.suspended=0 "
                              "WHERE c.due < ? ORDER BY c.due LIMIT 60", (self._day_start(now) + 86400,)).fetchall()
        self._prefetch_examples([{"lang": r["lang"], "examples": json.loads(r["examples"] or "[]") + self.dict.examples(r["lang"], r["term"])}
                                 for r in due])
        return {"counts": self._counts(now), "streak": s["streak"], "today": s["today"], "states": s["states"],
                "retention": s["retention"], "forecast": s["forecast"][:7], "next_due": nxt, "now": int(now),
                "has_items": self.db.execute("SELECT 1 FROM items LIMIT 1").fetchone() is not None}

    # ------------------------------------------------------------ 词书与词表
    def api_books(self, p: dict) -> dict:
        stat = {}
        for r in self.db.execute(
            "SELECT s.source, COUNT(*) n, SUM(c.item_id IS NOT NULL) learned, "
            "SUM(c.state=? AND c.stability>=?) mature "
            "FROM item_sources s JOIN items i ON i.id=s.item_id LEFT JOIN cards c ON c.item_id=s.item_id GROUP BY s.source",
                (REVIEW, MATURE_DAYS)):
            stat[r["source"]] = {"in_plan": r["n"], "learned": r["learned"] or 0, "mature": r["mature"] or 0}
        books = []
        for b in self.dict.books():
            st = stat.get("book:" + b["id"])
            books.append(dict(b, enabled=st is not None, **(st or {"in_plan": 0, "learned": 0, "mature": 0})))
        lists = [dict(id=k, title=k.split(":", 1)[1] if ":" in k else "自己添加的词", **v)
                 for k, v in sorted(stat.items()) if not k.startswith("book:")]
        return {"books": books, "lists": lists}

    def api_book_enable(self, p: dict) -> dict:
        b = self.dict.book(p.get("id", ""))
        if not b:
            raise ApiError("没有这本词书")
        lang, words = self.dict.book_words(b["id"])
        added, existed = self._insert_items(lang, [{"term": w, "rank": r} for w, r in words], "book:" + b["id"], prio=1)
        self._event("source", "book:" + b["id"], 1)
        self.db.commit()
        return {"added": added, "existed": existed}

    def api_source_remove(self, p: dict) -> dict:
        """把一本词书或一个词表移出学习计划：没学过的词删除，学过的保留。"""
        src = p.get("id", "")
        if ":" not in src and src != "manual":
            src = "book:" + src
        self._event("source", src, 0)
        return self._remove_source(src)

    def _remove_source(self, src: str) -> dict:
        ids = [r[0] for r in self.db.execute("SELECT item_id FROM item_sources WHERE source=?", (src,))]
        self.db.execute("DELETE FROM item_sources WHERE source=?", (src,))
        removed = self.db.execute(
            "DELETE FROM items WHERE id IN (SELECT i.id FROM items i LEFT JOIN cards c ON c.item_id=i.id "
            "LEFT JOIN item_sources s ON s.item_id=i.id WHERE c.item_id IS NULL AND s.item_id IS NULL)").rowcount
        self.db.commit()
        return {"removed": removed, "kept": len(ids) - removed}

    def _items_where(self, p: dict) -> tuple[str, list]:
        """词库列表的筛选条件。filter 可以是一个状态，也可以是几个状态的列表（满足任意一个即可）。"""
        where, args = ["1=1"], []
        q = (p.get("q") or "").strip()
        if q:
            where.append("i.term LIKE ?")
            args.append(f"%{q}%")
        conds = {
            "new": "c.item_id IS NULL AND i.suspended=0",
            "learning": f"c.state IN ({LEARNING},{RELEARNING}) AND i.suspended=0",
            "young": f"c.state={REVIEW} AND c.stability<{MATURE_DAYS} AND i.suspended=0",
            "mature": f"c.state={REVIEW} AND c.stability>={MATURE_DAYS} AND i.suspended=0",
            "suspended": "i.suspended=1",
            "learned": "c.item_id IS NOT NULL",
        }
        f = p.get("filter") or "all"
        picked = [conds[k] for k in ([f] if isinstance(f, str) else f) if k in conds]
        if picked:
            where.append("(" + " OR ".join(f"({c})" for c in picked) + ")")
        src = p.get("source")
        if src:
            where.append("i.id IN (SELECT item_id FROM item_sources WHERE source=?)")
            args.append(src)
        return f"FROM items i LEFT JOIN cards c ON c.item_id=i.id WHERE {' AND '.join(where)}", args

    def api_items(self, p: dict) -> dict:
        base, args = self._items_where(p)
        total = self.db.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
        order = {"due": "c.due IS NULL, c.due, i.term COLLATE NOCASE", "added": "i.added_at DESC, i.id DESC",
                 "hard": "c.difficulty IS NULL, c.difficulty DESC"}.get(p.get("sort"), "i.term COLLATE NOCASE")
        limit, offset = max(1, min(200, int(p.get("limit") or 60))), max(0, int(p.get("offset") or 0))
        rows = self.db.execute(
            f"SELECT i.*, c.state, c.due, c.stability, c.last_review, c.reps, c.lapses {base} ORDER BY {order} LIMIT ? OFFSET ?",
            args + [limit, offset]).fetchall()
        now = self.clock()
        items = []
        for r in rows:
            d = self._resolve(r)
            d["definition"] = d["definition"].split("\n")[0][:80]
            d.update(status=self._status(r if r["state"] is not None else None, bool(r["suspended"])), due=r["due"],
                     stability=r["stability"], reps=r["reps"] or 0,
                     recall=round(self.srs.recall(r["stability"], (now - r["last_review"]) / 86400), 3)
                     if r["state"] == REVIEW else None)
            items.append(d)
        return {"items": items, "total": total}

    def api_item_ids(self, p: dict) -> dict:
        """符合当前筛选条件的全部词条编号（多选里的“全选”用）。"""
        base, args = self._items_where(p)
        return {"ids": [r[0] for r in self.db.execute(f"SELECT i.id {base} LIMIT 50000", args)]}

    def api_items_bulk(self, p: dict) -> dict:
        """对一批词做同一个操作：prioritize 优先学 / suspend 搁置 / resume 恢复 / reset 重新学 / delete 删除。"""
        ids = [int(i) for i in (p.get("ids") or [])][:50000]
        action = p.get("action")
        sql = {
            "prioritize": ["UPDATE items SET prio=0, suspended=0 WHERE id IN ({m})"],
            "suspend": ["UPDATE items SET suspended=1 WHERE id IN ({m})"],
            "resume": ["UPDATE items SET suspended=0 WHERE id IN ({m})"],
            "reset": ["DELETE FROM cards WHERE item_id IN ({m})"],
            "delete": ["DELETE FROM cards WHERE item_id IN ({m})", "DELETE FROM logs WHERE item_id IN ({m})",
                       "DELETE FROM item_sources WHERE item_id IN ({m})", "DELETE FROM items WHERE id IN ({m})"],
        }.get(action)
        if not sql:
            raise ApiError("不认识的操作")
        for i in range(0, len(ids), 500):  # SQLite 一条语句的参数个数有限，分批执行
            chunk = ids[i:i + 500]
            for stmt in sql:
                self.db.execute(stmt.format(m=",".join("?" * len(chunk))), chunk)
        self.db.commit()
        if action in ("reset", "delete"):
            self._undo.clear()
        return {"count": len(ids)}

    def api_item(self, p: dict) -> dict:
        it = self.db.execute("SELECT * FROM items WHERE id=?", (int(p["id"]),)).fetchone()
        if not it:
            raise ApiError("词条不存在")
        now = self.clock()
        card = self.db.execute("SELECT * FROM cards WHERE item_id=?", (it["id"],)).fetchone()
        out = self._resolve(it, full=True)
        out["status"] = self._status(card, bool(it["suspended"]))
        if card:
            elapsed = (now - card["last_review"]) / 86400
            span = max(7.0, (card["due"] - card["last_review"]) / 86400 * 1.8, elapsed * 1.2)
            out["card"] = {
                "state": card["state"], "due": card["due"], "last_review": card["last_review"],
                "stability": card["stability"], "difficulty": card["difficulty"], "reps": card["reps"], "lapses": card["lapses"],
                "recall": round(self.srs.recall(card["stability"], elapsed), 4), "elapsed_days": round(elapsed, 3),
                "due_days": round((card["due"] - card["last_review"]) / 86400, 3),
                "curve": self.srs.curve(card["stability"], span), "span": round(span, 2), "retention": self.srs.retention,
            }
        out["logs"] = [dict(r) for r in self.db.execute(
            "SELECT ts, rating, mode, was_new FROM logs WHERE item_id=? ORDER BY id DESC LIMIT 30", (it["id"],))]
        return out

    def api_item_update(self, p: dict) -> dict:
        item_id = int(p["id"])
        it = self.db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not it:
            raise ApiError("词条不存在")
        sets, args = [], []
        for key in ("definition", "reading"):
            if key in p:  # 传空字符串 = 恢复使用内置词典
                sets.append(f"{key}=?")
                args.append((p[key] or "").strip() or None)
        if "note" in p:
            sets.append("note=?")
            args.append((p["note"] or "").strip())
        if "examples" in p:
            ex = [{"en": (e.get("en") or "").strip(), "zh": (e.get("zh") or "").strip()} for e in p["examples"] or []]
            sets.append("examples=?")
            args.append(json.dumps([e for e in ex if e["en"]], ensure_ascii=False))
        if "suspended" in p:
            sets.append("suspended=?")
            args.append(1 if p["suspended"] else 0)
        if sets:
            self.db.execute(f"UPDATE items SET {','.join(sets)} WHERE id=?", args + [item_id])
        if p.get("reset"):
            self.db.execute("DELETE FROM cards WHERE item_id=?", (item_id,))
        self.db.commit()
        return self.api_item({"id": item_id})

    def api_item_delete(self, p: dict) -> dict:
        ids = [int(i) for i in p.get("ids") or []]
        marks = ",".join("?" * len(ids))
        for r in self.db.execute(f"SELECT lang, term FROM items WHERE id IN ({marks})", ids).fetchall():
            self._event("item", f"{r['lang']}\t{r['term']}")
        for table, col in (("cards", "item_id"), ("logs", "item_id"), ("item_sources", "item_id"), ("items", "id")):
            self.db.execute(f"DELETE FROM {table} WHERE {col} IN ({marks})", ids)
        self.db.commit()
        return {"deleted": len(ids)}

    def api_lookup(self, p: dict) -> dict:
        term = (p.get("term") or "").strip()
        lang = p.get("lang") or "auto"
        if lang == "auto":
            lang = detect_lang(term)
        entry = self.dict.lookup(lang, term)
        exists = bool(term) and self.db.execute(
            "SELECT 1 FROM items WHERE lang=? AND term=? COLLATE NOCASE", (lang, term)).fetchone() is not None
        return {"lang": lang, "entry": entry, "exists": exists,
                "examples": self.dict.examples(lang, entry["word"]) if entry else [],
                "suggest": self.dict.suggest(lang, term, 6) if len(term) >= 2 else []}

    def api_add_word(self, p: dict) -> dict:
        term = (p.get("term") or "").strip()
        if not term:
            raise ApiError("请输入单词")
        lang = p.get("lang") or "auto"
        if lang == "auto":
            lang = detect_lang(term)
        entry = self.dict.lookup(lang, term)
        if entry and entry["word"].lower() == term.lower():
            term = entry["word"]
        definition = (p.get("definition") or "").strip()
        reading = (p.get("reading") or "").strip()
        same = lambda a, b: (a or "").strip() == (b or "").strip()  # noqa: E731
        row = {"term": term,
               "definition": None if entry and same(definition, entry["translation"]) else definition,
               "reading": None if entry and same(reading, entry["phonetic"]) else reading,
               "rank": entry["rank"] if entry else 0}
        if not entry and not definition:
            raise ApiError("词典里没有这个词，请填写释义")
        added, _ = self._insert_items(lang, [row], "manual", prio=0)
        self._event("source", "manual", 1)
        self._event("item", f"{lang}\t{term}", 1)  # 删掉过又加回来：告诉其他设备这个词又要了
        if p.get("note"):
            self.db.execute("UPDATE items SET note=? WHERE lang=? AND term=?", (p["note"].strip(), lang, term))
        self.db.commit()
        it = self.db.execute("SELECT id FROM items WHERE lang=? AND term=?", (lang, term)).fetchone()
        return {"added": bool(added), "id": it["id"], "term": term}

    def api_import_preview(self, p: dict) -> dict:
        try:
            rows = parse_file(p.get("filename", ""), base64.b64decode(p.get("data") or ""))
        except ValueError as e:
            raise ApiError(str(e)) from e
        except Exception as e:  # 文件损坏等
            raise ApiError(f"读不了这个文件：{e}") from e
        force = p.get("lang") or "auto"
        out, found, missing, existing = [], 0, 0, 0
        for r in rows:
            lang = detect_lang(r["term"]) if force == "auto" else force
            entry = self.dict.lookup(lang, r["term"])
            has = self.db.execute("SELECT 1 FROM items WHERE lang=? AND term=? COLLATE NOCASE", (lang, r["term"])).fetchone()
            row = {"term": r["term"], "lang": lang, "definition": r["definition"], "reading": r["reading"],
                   "dict": (entry["translation"].split("\n")[0][:60] if entry else ""), "exists": bool(has)}
            row["ok"] = bool(r["definition"] or entry)
            found += row["ok"]
            missing += not row["ok"]
            existing += row["exists"]
            out.append(row)
        return {"rows": out, "total": len(out), "found": found, "missing": missing, "existing": existing}

    def api_import_commit(self, p: dict) -> dict:
        name = (p.get("name") or "").strip() or "导入的词表"
        by_lang: dict[str, list] = {}
        for r in p.get("rows") or []:
            term = (r.get("term") or "").strip()
            if not term:
                continue
            lang = r.get("lang") or detect_lang(term)
            entry = self.dict.lookup(lang, term)
            if entry and entry["word"].lower() == term.lower():
                term = entry["word"]
            by_lang.setdefault(lang, []).append({
                "term": term, "definition": (r.get("definition") or "").strip() or (None if entry else ""),
                "reading": (r.get("reading") or "").strip() or (None if entry else ""),
                "rank": entry["rank"] if entry else 0})
        added = existed = 0
        for lang, rows in by_lang.items():
            a, e = self._insert_items(lang, rows, "list:" + name, prio=0)
            added, existed = added + a, existed + e
        self._event("source", "list:" + name, 1)
        ts = int(self.clock())
        self.db.executemany("REPLACE INTO sync_events(kind, key, val, ts) VALUES('item', ?, 1, ?)",
                            [(f"{lang}\t{r['term']}", ts) for lang, rows in by_lang.items() for r in rows])
        self.db.commit()
        return {"added": added, "existed": existed, "name": name}

    # ------------------------------------------------------------ 统计
    def _stats_core(self, now: float) -> dict:
        start = self._day_start(now)
        today = self._day(now)
        logs = self.db.execute("SELECT ts, rating, was_new, state_before, elapsed_ms FROM logs WHERE ts>=?",
                               (start - 400 * 86400,)).fetchall()
        per_day: dict[date, dict] = {}
        for r in logs:
            d = per_day.setdefault(self._day(r["ts"]), {"new": 0, "review": 0, "ms": 0, "right": 0})
            d["new" if r["was_new"] else "review"] += 1
            d["ms"] += r["elapsed_ms"]
            d["right"] += r["rating"] > 1
        streak, d = 0, today if today in per_day else today - timedelta(days=1)
        while d in per_day:
            streak, d = streak + 1, d - timedelta(days=1)
        t = per_day.get(today, {"new": 0, "review": 0, "ms": 0, "right": 0})
        n_today = t["new"] + t["review"]
        mature_logs = [r for r in logs if r["state_before"] == REVIEW and r["ts"] >= start - 30 * 86400]
        retention = {"n": len(mature_logs),
                     "rate": round(sum(r["rating"] > 1 for r in mature_logs) / len(mature_logs), 4) if mature_logs else None}
        forecast = [0] * 30
        for r in self.db.execute("SELECT c.due FROM cards c JOIN items i ON i.id=c.item_id AND i.suspended=0"):
            idx = max(0, min(29, int((r["due"] - start) // 86400))) if r["due"] < start + 30 * 86400 else None
            if idx is not None:
                forecast[idx] += 1
        st = self.db.execute(
            "SELECT SUM(i.suspended=0 AND c.item_id IS NULL) unseen, "
            f"SUM(i.suspended=0 AND c.state IN ({LEARNING},{RELEARNING})) learning, "
            f"SUM(i.suspended=0 AND c.state={REVIEW} AND c.stability<{MATURE_DAYS}) young, "
            f"SUM(i.suspended=0 AND c.state={REVIEW} AND c.stability>={MATURE_DAYS}) mature, "
            "SUM(i.suspended=1) suspended, COUNT(*) total FROM items i LEFT JOIN cards c ON c.item_id=i.id").fetchone()
        return {
            "per_day": per_day, "streak": streak,
            "today": {"reviews": n_today, "new": t["new"], "minutes": round(t["ms"] / 60000, 1),
                      "accuracy": round(t["right"] / n_today, 3) if n_today else None},
            "retention": retention,
            "forecast": [{"date": (today + timedelta(days=i)).isoformat(), "count": c} for i, c in enumerate(forecast)],
            "states": {k: st[k] or 0 for k in ("unseen", "learning", "young", "mature", "suspended", "total")},
        }

    def api_stats(self, p: dict) -> dict:
        now = self.clock()
        s = self._stats_core(now)
        today, per_day = self._day(now), s.pop("per_day")
        day = lambda i: today - timedelta(days=i)  # noqa: E731
        zero = {"new": 0, "review": 0, "ms": 0}
        s["daily"] = [dict(date=day(i).isoformat(), new=per_day.get(day(i), zero)["new"], review=per_day.get(day(i), zero)["review"])
                      for i in range(29, -1, -1)]
        weeks = 52
        span = weeks * 7 + today.weekday()  # 对齐到周一
        s["heatmap"] = [dict(date=day(i).isoformat(), count=sum(per_day.get(day(i), zero)[k] for k in ("new", "review")))
                        for i in range(span, -1, -1)]
        offset = datetime.fromtimestamp(now).astimezone().utcoffset().total_seconds()
        tot = self.db.execute("SELECT COUNT(*) n, COALESCE(SUM(elapsed_ms),0) ms, COUNT(DISTINCT item_id) items FROM logs").fetchone()
        s["totals"] = {"reviews": tot["n"], "hours": round(tot["ms"] / 3600000, 1), "items": tot["items"],
                       "days": self.db.execute("SELECT COUNT(*) FROM (SELECT DISTINCT CAST((ts + ?) / 86400 AS INT) FROM logs)",
                                               (int(offset) - int(self.settings["day_start"]) * 3600,)).fetchone()[0]}
        stabs = sorted(r[0] for r in self.db.execute("SELECT stability FROM cards WHERE state=? AND stability IS NOT NULL", (REVIEW,)))
        median = stabs[len(stabs) // 2] if stabs else None
        s["memory"] = {"median_stability": round(median, 2) if median else None, "retention": self.srs.retention,
                       "curve": self.srs.curve(median, max(14.0, median * 3)) if median else None,
                       "example_curve": self.srs.curve(10.0, 30.0)}
        return s

    # ------------------------------------------------------------ 设置与数据
    def api_bootstrap(self, p: dict) -> dict:
        return {"app": APP_NAME, "version": __version__, "settings": self.settings, "data_dir": str(self.dir), "links": LINKS,
                "desktop": self.speaker is not None,
                "can_restart": self.restarter is not None, "android": self.android, "platform": sys.platform, "render_trial": self.render_trial, "display_reverted": self.display_reverted, "voice_packs": self.voice.pack_langs(), "user_fonts": self.fonts.list()}

    # ------------------------------------------------------------ 字体
    def api_fonts(self, p: dict) -> dict:
        return {"user": self.fonts.list(), "system": self.system_fonts}

    def api_font_import(self, p: dict) -> dict:
        try:
            entry = self.fonts.add(p.get("filename") or "", base64.b64decode(p.get("data") or ""))
        except ValueError as e:
            raise ApiError(str(e)) from e
        return {"font": entry, "user": self.fonts.list()}

    def api_font_delete(self, p: dict) -> dict:
        fid = str(p.get("id") or "")
        self.fonts.remove(fid)
        reset = {k: "" for k in ("font_title", "font_body") if self.settings[k] == "user:" + fid}
        if reset:
            self.api_settings_set(reset)
        return {"user": self.fonts.list(), "settings": self.settings}

    def api_restart(self, p: dict) -> dict:
        """重启程序（桌面版）。浏览器里打开的没法自己重启。"""
        if not self.restarter:
            return {"restarting": False}
        self.restarter()
        return {"restarting": True}

    def api_look(self, p: dict) -> dict:
        if self.look_changed:
            self.look_changed(bool(p.get("dark")), p.get("palette") == "silver")
        return {"ok": True}

    def api_display_ok(self, p: dict) -> dict:
        if self.display_ok:
            self.display_ok(str(p.get("renderer") or "")[:200])
        return {"ok": True}

    def api_render_confirm(self, p: dict) -> dict:
        self.render_trial = False
        if self.render_confirm:
            self.render_confirm()
        return {"ok": True}

    def api_settings_set(self, p: dict) -> dict:
        ranges = {"new_per_day": (0, 500), "review_per_day": (0, 5000), "day_start": (0, 12)}
        ranges["sfx_volume"] = (0, 100)
        choices = {"order": ("freq", "random", "alpha"), "voice": ("builtin", "online", "system"), "accent": ("us", "uk"),
                   "theme": ("light", "dark", "auto"), "motion": ("full", "reduced"), "palette": ("vermilion", "silver"),
                   "sfx_set": ("wood", "felt", "stone", "keys", "glass"), "gloss_en": ("zh", "ja"), "gloss_ja": ("zh", "en"),
                   "render": ("auto", "d3d11", "opengl"), "gpu": ("auto", "high", "low")}
        for k, v in p.items():
            if k not in DEFAULTS:
                continue
            if k in ranges:
                v = max(ranges[k][0], min(ranges[k][1], int(v)))
            elif k == "retention":
                v = max(0.70, min(0.97, round(float(v), 2)))
            elif k == "voice_rate":
                v = max(0.6, min(1.3, round(float(v), 2)))
            elif k in choices:
                if v not in choices[k]:
                    raise ApiError(f"{k} 的取值不对")
            elif k == "sync_code":
                v = re.sub(r"[^0-9A-Z]", "", str(v or "").upper())
                if not 6 <= len(v) <= 16:
                    raise ApiError("同步码要 6~16 位字母或数字")
            elif k in ("font_title", "font_body"):
                v = str(v or "")[:120]
                kind, _, val = v.partition(":")
                if v and not ((kind == "builtin" and val in ("serif", "sans")) or (kind == "system" and val)
                              or (kind == "user" and any(f["id"] == val for f in self.fonts.list()))):
                    raise ApiError("没有这个字体")
            else:
                v = bool(v)
            self.settings[k] = v
            self.db.execute("REPLACE INTO settings(k, v) VALUES(?,?)", (k, json.dumps(v)))
        self.db.commit()
        if "retention" in p:
            self.srs.set_retention(self.settings["retention"])
        self._apply_gloss()
        if "lan_sync" in p or "sync_code" in p:
            if self.settings["lan_sync"] and not self.settings["sync_code"]:
                self.settings["sync_code"] = self.sync.new_code()
                self.db.execute("REPLACE INTO settings(k, v) VALUES(?,?)", ("sync_code", json.dumps(self.settings["sync_code"])))
                self.db.commit()
            self.sync.apply()
        return {"settings": self.settings}

    def _apply_gloss(self) -> None:
        self.dict.gloss = {"en": self.settings["gloss_en"], "ja": self.settings["gloss_ja"]}
        self.dict.show_domain = bool(self.settings["show_domain"])

    def api_open_url(self, p: dict) -> dict:
        url = str(p.get("url") or "")
        if not re.match(r"^https://[\w.-]+(/|$)", url):
            raise ApiError("链接不对")
        if self.url_opener:
            self.url_opener(url)
            return {"opened": True}
        return {"opened": False}

    # ------------------------------------------------------------ 检查更新
    @staticmethod
    def _ver(v: str) -> tuple:
        n = [int(x) for x in re.findall(r"\d+", v or "")[:3]]
        return tuple(n + [0] * (3 - len(n)))  # 补齐三段：GitHub 上写 v1.0 也当作 1.0.0

    def api_update_check(self, p: dict) -> dict:
        """问 GitHub 最新发布的版本号。联网失败不报错，只返回 ok=False。"""
        import urllib.request
        req = urllib.request.Request(RELEASES_API, headers={"Accept": "application/vnd.github+json",
                                                            "User-Agent": f"LDream-wordbook/{__version__}"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception as e:  # 没网、被墙、GitHub 限流
            return {"ok": False, "current": __version__, "error": str(e)[:120], "links": LINKS}
        latest = (d.get("tag_name") or "").lstrip("vV")
        return {"ok": True, "current": __version__, "latest": latest,
                "newer": self._ver(latest) > self._ver(__version__),
                "url": d.get("html_url") or LINKS["releases"], "name": d.get("name") or "",
                "notes": (d.get("body") or "")[:1500], "links": LINKS}

    def api_speak(self, p: dict) -> dict:
        """朗读一个词。按设置的来源依次尝试，前一个没有就用下一个，保证尽量能出声。

        返回 handled=True 表示已经由桌面程序播放；否则界面自己播放 audio（base64 的 MP3），
        两者都没有时界面退回浏览器自带的朗读。
        web=True：界面要自己播放音频文件（用 Web Audio，带淡入淡出，不会断续爆音），即使在桌面版也把音频传回去；
        系统语音仍由桌面程序朗读。
        """
        text, lang = (p.get("text") or "").strip(), p.get("lang") or "en"
        if not text:
            return {"handled": True}
        s = self.settings
        native = self.speaker if not p.get("web") else None
        if p.get("kind") == "sentence":
            return self._speak_sentence(text, lang, native)
        order = {"online": ("online", "builtin", "system"), "system": ("system", "builtin", "online")}.get(
            s["voice"], ("builtin", "online", "system"))
        for src in order:
            data = None
            if src == "builtin":
                data = self.voice.pack(lang, text)
            elif src == "online" and (s["voice"] == "online" or s["online_fallback"]):
                data = self.voice.online(lang, self._say_as(lang, text), s["accent"])
            elif src == "system":
                if self.speaker is None:
                    return {"handled": False, "source": "browser"}
                if self.voice_langs is None or lang in self.voice_langs:
                    self.speaker(text, lang, "")
                    return {"handled": True, "source": "system"}
            if data:
                if native:
                    native(text, lang, str(self.voice.as_file(src, lang, text, data)))
                    return {"handled": True, "source": src}
                return {"handled": False, "source": src, "audio": base64.b64encode(data).decode("ascii")}
        return {"handled": True, "missing": lang}

    def _say_as(self, lang: str, text: str) -> str:
        """在线发音要发给网站的文字。日语用读音（假名）：网站拿到单个汉字时常常读错（比如「木」读成「もく」甚至读不出来），
        词书里的读音才是这个词该有的读法。"""
        if lang != "ja":
            return text
        row = self.db.execute("SELECT reading FROM items WHERE lang='ja' AND term=?", (text,)).fetchone()
        reading = row["reading"] if row and row["reading"] else (self.dict.lookup("ja", text) or {}).get("phonetic") or ""
        reading = re.split(r"[;；,，、/／]", reading)[0].strip()
        return reading if reading and re.fullmatch(r"[\u3040-\u30ffー・ ]+", reading) else text

    def _online_ok(self) -> bool:
        return self.settings["voice"] == "online" or bool(self.settings["online_fallback"])

    def _speak_sentence(self, text: str, lang: str, native=None) -> dict:
        """例句：缓存 → 联网取（允许联网时）→ 系统语音 → 浏览器朗读。选了“系统语音”时系统语音优先。"""
        s = self.settings
        accent = s["accent"]
        data = self.voice.sentence_cached(lang, text, accent)
        system_ok = self.speaker is not None and (self.voice_langs is None or lang in self.voice_langs)
        if not data and s["voice"] == "system" and system_ok:
            self.speaker(text, lang, "")
            return {"handled": True, "source": "system"}
        if not data and self._online_ok():
            data = self.voice.sentence(lang, text, accent)
        if data:
            if native:
                native(text, lang, str(self.voice.as_file("sent", lang, text, data)))
                return {"handled": True, "source": "online"}
            return {"handled": False, "source": "online", "audio": base64.b64encode(data).decode("ascii")}
        if system_ok:
            self.speaker(text, lang, "")
            return {"handled": True, "source": "system"}
        if self.speaker is None:
            return {"handled": False, "source": "browser"}
        return {"handled": True, "missing": lang, "kind": "sentence"}

    def _prefetch_examples(self, cards: list[dict]) -> None:
        """后台提前下载这些卡片要显示的例句发音（最多两句），断网时什么也不做。"""
        if not self._online_ok() or not self.settings["show_examples"]:
            return
        jobs = [(c["lang"], ex["en"], self.settings["accent"]) for c in cards if c for ex in (c.get("examples") or [])[:2] if ex.get("en")]
        if jobs:
            self.voice.prefetch(jobs)

    def api_backup(self, p: dict) -> dict:
        out = self.dir / "backups"
        out.mkdir(exist_ok=True)
        path = out / f"user-{datetime.fromtimestamp(self.clock()):%Y%m%d-%H%M%S}.db"
        dst = sqlite3.connect(path)
        self.db.backup(dst)
        dst.close()
        return {"path": self._shown(path)}

    def _shown(self, path: Path) -> str:
        """导出的文件：安卓版再复制一份到手机的“下载”文件夹（程序自己的数据文件夹用户看不到）"""
        if self.file_saver:
            try:
                return self.file_saver(str(path)) or str(path)
            except Exception:
                pass
        return str(path)

    def api_export(self, p: dict) -> dict:
        out = self.dir / "exports"
        out.mkdir(exist_ok=True)
        path = out / f"shici-{datetime.fromtimestamp(self.clock()):%Y%m%d-%H%M%S}.csv"
        names = {"new": "未学", "learning": "学习中", "young": "复习中", "mature": "已掌握", "suspended": "已搁置"}
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["单词", "读音", "释义", "助记", "状态", "下次复习", "稳定度(天)", "复习次数", "遗忘次数"])
            for r in self.db.execute("SELECT i.*, c.state, c.due, c.stability, c.reps, c.lapses FROM items i "
                                     "LEFT JOIN cards c ON c.item_id=i.id ORDER BY i.term COLLATE NOCASE"):
                d = self._resolve(r)
                w.writerow([d["term"], d["reading"], d["definition"].replace("\n", "; "), d["note"],
                            names[self._status(r if r["state"] is not None else None, bool(r["suspended"]))],
                            f"{datetime.fromtimestamp(r['due']):%Y-%m-%d}" if r["due"] else "",
                            round(r["stability"], 1) if r["stability"] else "", r["reps"] or 0, r["lapses"] or 0])
        return {"path": self._shown(path)}

    # ------------------------------------------------------------ 进度密钥
    def api_progress_export(self, p: dict) -> dict:
        """把学习进度打包成一串可以复制的文字（压缩后的 JSON），在另一台设备上粘贴即可继承。

        密钥里有：学过的词和它们的记忆状态、复习记录、自己加的词/助记/例句/释义、计划里的词书、学习设置。
        没学过的词书单词不放进去（新设备上有同样的内置词典），所以密钥长度只跟学过多少有关。
        """
        payload = self._progress_payload()
        items, logs = payload["items"], payload["logs"]
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        packed = lzma.compress(raw, preset=9)
        stats = {"words": sum(1 for it in items if it[9]), "logs": len(logs["i"])}
        if p.get("as_file"):  # 进度文件：同样的数据，不转成文字，开头加一个标记
            name = f"小梦的词书-进度-{datetime.fromtimestamp(self.clock()):%Y%m%d-%H%M}.xmdb"
            data = FILE_MAGIC + packed
            return {"filename": name, "data": base64.b64encode(data).decode("ascii"), "bytes": len(data), **stats}
        key = KEY_PREFIX + base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
        return {"key": key, "chars": len(key), **stats}

    def _progress_payload(self) -> dict:
        """进度数据（密钥、进度文件、局域网同步共用）。

        "x" 是 1.0.2 加的补充信息（词条加入时间、删除 / 撤销 / 清空这些事件），旧版本读到会忽略。
        """
        rows = self.db.execute(
            "SELECT i.*, c.state, c.due, c.stability, c.difficulty, c.data, c.reps, c.lapses, c.first_review, c.last_review "
            "FROM items i LEFT JOIN cards c ON c.item_id=i.id WHERE c.item_id IS NOT NULL OR i.prio=0 OR i.note!='' "
            "OR i.examples!='[]' OR i.definition IS NOT NULL OR i.reading IS NOT NULL OR i.suspended=1 ORDER BY i.id").fetchall()
        index = {r["id"]: n for n, r in enumerate(rows)}
        src: dict[int, list[str]] = {}
        books = set()
        for r in self.db.execute("SELECT item_id, source FROM item_sources"):
            if r["source"].startswith("book:"):
                books.add(r["source"][5:])
            elif r["item_id"] in index:
                src.setdefault(r["item_id"], []).append(r["source"])
        items = []
        for r in rows:
            card = None
            if r["state"] is not None:
                card = [r["state"], json.loads(r["data"]).get("step"), round(r["stability"] or 0, 4), round(r["difficulty"] or 0, 4),
                        r["due"], r["last_review"], r["reps"], r["lapses"], r["first_review"]]
            items.append([r["lang"], r["term"], r["reading"], r["definition"], r["note"], json.loads(r["examples"] or "[]"),
                          r["prio"], r["suspended"], src.get(r["id"], []), card])
        logs = {"i": [], "t": [], "r": [], "m": [], "e": [], "s": [], "n": []}
        last = 0
        for r in self.db.execute("SELECT item_id, ts, rating, mode, elapsed_ms, state_before, was_new FROM logs ORDER BY ts, id"):
            if r["item_id"] not in index:
                continue
            logs["i"].append(index[r["item_id"]]); logs["t"].append(r["ts"] - last); last = r["ts"]
            logs["r"].append(r["rating"]); logs["m"].append(1 if r["mode"] == "spell" else 0)
            logs["e"].append(r["elapsed_ms"] // 100); logs["s"].append(r["state_before"]); logs["n"].append(r["was_new"])
        events = [[r["kind"], r["key"], r["val"], r["ts"]] for r in self.db.execute("SELECT * FROM sync_events")]
        return {"v": 1, "app": APP_NAME, "t": int(self.clock()), "settings": {k: self.settings[k] for k in STUDY_KEYS},
                "books": sorted(books), "items": items, "logs": logs,
                "x": {"added": [r["added_at"] for r in rows], "events": events}}

    @staticmethod
    def _decode_progress(p: dict) -> dict:
        """读出进度：p["file"] 是进度文件（base64），p["key"] 是进度密钥文字。文件里装的是密钥文字也认。"""
        if p.get("file"):
            try:
                blob = base64.b64decode(p["file"])
            except Exception as e:
                raise ApiError("读不了这个文件") from e
            if blob.startswith(FILE_MAGIC):
                return Core._unpack(blob[len(FILE_MAGIC):], "进度文件不完整或已损坏，请重新导出一次")
            text = blob[:30_000_000].decode("utf-8", "ignore").strip()
            if not text.startswith(KEY_PREFIX):
                raise ApiError("这不是小梦的词书的进度文件（.xmdb）")
            p = {"key": text}
        key = "".join((p.get("key") or "").split())
        if not key.startswith(KEY_PREFIX):
            raise ApiError("这不是小梦的词书的进度密钥（应该以 XMCS1. 开头）")
        if len(key) > 20_000_000:
            raise ApiError("密钥太长了")
        body = key[len(KEY_PREFIX):]
        try:
            packed = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        except Exception as e:
            raise ApiError("密钥不完整或已损坏，请重新复制一次（要从头到尾完整复制）") from e
        return Core._unpack(packed, "密钥不完整或已损坏，请重新复制一次（要从头到尾完整复制）")

    @staticmethod
    def _unpack(packed: bytes, broken: str) -> dict:
        try:
            dec = lzma.LZMADecompressor()
            raw = dec.decompress(packed, max_length=200_000_000)
            assert dec.eof  # 没读到结尾 = 被截断了
            data = json.loads(raw.decode("utf-8"))
            assert data.get("v") == 1 and isinstance(data["items"], list) and isinstance(data["logs"]["i"], list)
        except Exception as e:
            raise ApiError(broken) from e
        return data

    def api_progress_inspect(self, p: dict) -> dict:
        d = self._decode_progress(p)
        titles = {b["id"]: b["title"] for b in self.dict.books()}
        local = self.db.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        return {"exported_at": d["t"], "words": sum(1 for it in d["items"] if it[9]), "custom": sum(1 for it in d["items"] if it[6] == 0),
                "logs": len(d["logs"]["i"]), "books": [titles.get(b, b) for b in d["books"]], "local_words": local}

    def api_progress_import(self, p: dict) -> dict:
        """导入进度文件或进度密钥并和本机进度合并：每个词以最近复习过的那一边为准，复习记录取并集。导入前自动备份。"""
        d = self._decode_progress(p)
        backup = self.api_backup({})["path"]
        res = self._merge_progress(d)
        if p.get("settings", True):
            self.api_settings_set({k: v for k, v in d.get("settings", {}).items() if k in STUDY_KEYS})
        self._undo.clear()
        return dict(res, backup=backup)

    def _merge_progress(self, d: dict) -> dict:
        """把另一台设备的进度合并进来（导入进度和局域网同步共用）。

        规则：每个词的记忆状态以最近复习过的那一边为准；复习记录取并集；
        对方删掉的词、移出计划的词书、撤销掉的复习、清空进度，按“谁后做的算谁”同步过来。
        """
        now = int(self.clock())
        x = d.get("x") or {}
        # ---- 事件：两边各取最新的那条
        mine = {(r["kind"], r["key"]): (r["val"], r["ts"]) for r in self.db.execute("SELECT * FROM sync_events")}
        fresh = []  # 对方比本机新的事件，下面逐条照做
        for kind, key, val, ts in x.get("events") or []:
            if (kind, key) not in mine or ts > mine[(kind, key)][1]:
                mine[(kind, key)] = (val, ts)
                self._event(kind, key, val, ts)
                fresh.append((kind, key, val, ts))
        reset_ts = mine.get(("reset", ""), (0, 0))[1]
        undone = {key for (kind, key) in mine if kind == "undo"}
        gone_src = {key for (kind, key), (val, _) in mine.items() if kind == "source" and val == 0}
        gone_items = {key for (kind, key), (val, _) in mine.items() if kind == "item" and val == 0}
        item_id_of = lambda key: (lambda r: r["id"] if r else None)(  # noqa: E731
            self.db.execute("SELECT id FROM items WHERE lang=? AND term=?", tuple(key.split("\t")[:2])).fetchone())
        revert: set[int] = set()  # 本机还停在“被撤销的那次复习”上的词，要换回对方的状态
        for kind, key, val, ts in fresh:
            if kind == "reset":
                self.db.execute("DELETE FROM cards WHERE last_review<=?", (ts,))
                self.db.execute("DELETE FROM logs WHERE ts<=?", (ts,))
                self._undo.clear()
            elif kind == "source" and val == 0:
                self._remove_source(key)
            elif kind == "item" and val == 0:
                iid = item_id_of(key)
                row = iid and self.db.execute("SELECT i.added_at, c.last_review FROM items i LEFT JOIN cards c ON c.item_id=i.id "
                                              "WHERE i.id=?", (iid,)).fetchone()
                if row and row["added_at"] < ts and (row["last_review"] or 0) < ts:
                    for table, col in (("cards", "item_id"), ("logs", "item_id"), ("item_sources", "item_id"), ("items", "id")):
                        self.db.execute(f"DELETE FROM {table} WHERE {col}=?", (iid,))
            elif kind == "undo":
                iid = item_id_of(key)
                if iid:
                    t = int(key.split("\t")[2])
                    self.db.execute("DELETE FROM logs WHERE item_id=? AND ts=?", (iid, t))
                    if self.db.execute("SELECT 1 FROM cards WHERE item_id=? AND last_review=?", (iid, t)).fetchone():
                        revert.add(iid)
        # ---- 词书
        for bid in d["books"]:
            if "book:" + bid not in gone_src and self.dict.book(bid):
                lang, words = self.dict.book_words(bid)
                self._insert_items(lang, [{"term": w, "rank": r} for w, r in words if f"{lang}\t{w}" not in gone_items],
                                   "book:" + bid, prio=1)
        # ---- 词条和记忆状态
        added_at = x.get("added") or []
        ids: list[int | None] = []
        added = updated = kept = 0
        for n, (lang, term, reading, definition, note, examples, prio, suspended, sources, card) in enumerate(d["items"]):
            key = f"{lang}\t{term}"
            if card and (card[5] <= reset_ts or f"{key}\t{card[5]}" in undone):
                card = None  # 对方这个状态是清空进度之前的，或者是被撤销掉的那次复习
            row = self.db.execute("SELECT * FROM items WHERE lang=? AND term=?", (lang, term)).fetchone()
            if not row:
                dead = mine.get(("item", key))
                born = max(added_at[n] if n < len(added_at) else 0, card[5] if card else 0)
                if dead and dead[0] == 0 and dead[1] >= born:  # 这个词在本机（或第三台设备上）被删掉了，而且是在对方加入 / 复习之后
                    ids.append(None)
                    continue
                entry = self.dict.lookup(lang, term)
                self.db.execute("INSERT INTO items(lang, term, prio, rank, shuffle, added_at) VALUES(?,?,?,?,?,?)",
                                (lang, term, prio, entry["rank"] if entry else 0, random.getrandbits(30),
                                 added_at[n] if n < len(added_at) and added_at[n] else now))
                row = self.db.execute("SELECT * FROM items WHERE lang=? AND term=?", (lang, term)).fetchone()
                added += 1
            item_id = row["id"]
            ids.append(item_id)
            for s in sources:
                if s not in gone_src:
                    self.db.execute("INSERT OR IGNORE INTO item_sources VALUES(?,?)", (item_id, s))
            local = self.db.execute("SELECT last_review FROM cards WHERE item_id=?", (item_id,)).fetchone()
            stuck = item_id in revert or (local is not None and f"{key}\t{local['last_review']}" in undone)
            newer = local is None or stuck or (card is not None and card[5] > local["last_review"])
            if newer:  # 对方的更新（或本机没学过）：词条内容和记忆状态都用对方的
                self.db.execute("UPDATE items SET reading=?, definition=?, note=?, examples=?, prio=MIN(prio, ?), suspended=? WHERE id=?",
                                (reading, definition, note or row["note"], json.dumps(examples or json.loads(row["examples"]), ensure_ascii=False),
                                 prio, suspended, item_id))
                if card:
                    state, step, stab, diff, due, last, reps, lapses, first = card
                    fc = Card(card_id=item_id, state=State(state), step=step, stability=stab or None, difficulty=diff or None,
                              due=utc(due), last_review=utc(last))
                    self.db.execute("REPLACE INTO cards(item_id, state, due, stability, difficulty, data, reps, lapses, first_review, last_review) "
                                    "VALUES(?,?,?,?,?,?,?,?,?,?)", (item_id, state, due, stab, diff, fc.to_json(), reps, lapses, first, last))
                    updated += 1
                elif stuck:  # 对方撤销后这个词回到了没学过
                    self.db.execute("DELETE FROM cards WHERE item_id=?", (item_id,))
                    updated += 1
            else:
                kept += 1
                if note and not row["note"]:
                    self.db.execute("UPDATE items SET note=? WHERE id=?", (note, item_id))
        for iid in revert - set(ids):  # 对方撤销的是这个词的第一次复习，对方那边它已经回到没学过（进度里没有它）
            self.db.execute("DELETE FROM cards WHERE item_id=?", (iid,))
            updated += 1
        # ---- 复习记录取并集：同一个词、同一秒、同一评分算同一条，本机已有几条就少插几条
        lg, t, logs_added = d["logs"], 0, 0
        have: dict[tuple, int] = {}
        for r in self.db.execute("SELECT item_id, ts, rating FROM logs"):
            k = (r["item_id"], r["ts"], r["rating"])
            have[k] = have.get(k, 0) + 1
        for n in range(len(lg["i"])):
            t += lg["t"][n]
            iid = ids[lg["i"][n]]
            if iid is None or t <= reset_ts:
                continue
            it = d["items"][lg["i"][n]]
            if f"{it[0]}\t{it[1]}\t{t}" in undone:
                continue
            rec = (iid, t, lg["r"][n])
            if have.get(rec, 0) > 0:
                have[rec] -= 1
                continue
            self.db.execute("INSERT INTO logs(item_id, ts, rating, mode, elapsed_ms, state_before, was_new) VALUES(?,?,?,?,?,?,?)",
                            (*rec, "spell" if lg["m"][n] else "recall", lg["e"][n] * 100, lg["s"][n], lg["n"][n]))
            logs_added += 1
        self.db.commit()
        return {"added": added, "updated": updated, "kept": kept, "logs_added": logs_added}

    def api_sync_status(self, p: dict) -> dict:
        return self.sync.status()

    def api_sync_firewall(self, p: dict) -> dict:
        return {"started": self.sync.open_firewall()}

    def api_clipboard_copy(self, p: dict) -> dict:
        if self.clipboard and p.get("text"):
            self.clipboard(p["text"])
            return {"copied": True}
        return {"copied": False}

    def api_reset_progress(self, p: dict) -> dict:
        """清空全部学习记录（词库保留）。清空前自动备份。"""
        if p.get("confirm") != "RESET":
            raise ApiError("需要确认")
        backup = self.api_backup({})
        self.db.execute("DELETE FROM cards")
        self.db.execute("DELETE FROM logs")
        self._event("reset", "", 0)
        self.db.commit()
        self._undo.clear()
        return backup

    def api_open_data_dir(self, p: dict) -> dict:
        path = str(self.dir)
        if self.opener:
            self.opener(path)
            return {"opened": True, "path": path}
        return {"opened": False, "path": path}

    def close(self) -> None:
        self.sync.stop()
        with self.lock:
            self.db.commit()
            self.db.close()
