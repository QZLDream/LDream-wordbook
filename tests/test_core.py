"""核心逻辑的自动化测试：python -m pytest"""
import base64
import io
from datetime import datetime, timedelta, timezone

import pytest
from fsrs import Card, Scheduler, State

from shici.core import ApiError, Core
from shici.importer import detect_lang, parse_file
from shici.scheduler import Srs, fmt_interval


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 16, 9, 0).timestamp()

    def __call__(self):
        return self.t

    def add(self, **kw):
        self.t += timedelta(**kw).total_seconds()


@pytest.fixture
def core(tmp_path):
    clock = Clock()
    c = Core(tmp_path, clock=clock)
    c.clock_obj = clock
    yield c
    c.close()


def test_dictionary_lookup(core):
    e = core.dict.lookup("en", "abandon")
    assert e and "放弃" in e["translation"] and e["phonetic"].startswith("ə")
    assert core.dict.lookup("en", "Abandon")["word"] == "abandon"       # 忽略大小写
    assert core.dict.lookup("en", "abandoned")["word"] in ("abandoned", "abandon")
    assert core.dict.lookup("en", "zzzzqqq") is None
    assert core.dict.examples("en", "abandon")
    ja = core.dict.lookup("ja", "食べる")
    assert ja["phonetic"] == "たべる" and "吃" in ja["translation"]
    ids = {b["id"] for b in core.dict.books()}
    assert {"cet4", "cet6", "ky", "toefl", "ielts", "gre", "jlpt-n5", "jlpt-n1"} <= ids


def test_book_enable_and_daily_new_limit(core):
    r = core.call("book_enable", {"id": "cet4"})
    assert r["added"] > 3000
    assert core.call("book_enable", {"id": "cet4"})["added"] == 0      # 重复添加不会重复
    core.call("settings_set", {"new_per_day": 3})
    n = core.call("next")
    assert n["counts"]["new"] == 3 and n["card"]["is_new"] and n["card"]["definition"]
    assert set(n["card"]["intervals"]) == {"1", "2", "3", "4"}
    seen = []
    while n["card"] and n["card"]["is_new"]:
        seen.append(n["card"]["term"])
        n = core.call("answer", {"id": n["card"]["id"], "rating": 4})  # 太简单：直接毕业
    assert len(seen) == 3 and len(set(seen)) == 3
    assert n["card"] is None and n["counts"]["total"] == 0 and n["counts"]["done"] == 3
    # 第二天又有 3 个新词；昨天学的还没到期
    core.clock_obj.add(days=1)
    n = core.call("next")
    assert n["counts"]["new"] == 3 and n["counts"]["review"] == 0


def test_learning_steps_and_review_schedule(core):
    core.call("add_word", {"term": "ubiquitous"})
    n = core.call("next")
    cid = n["card"]["id"]
    assert n["card"]["term"] == "ubiquitous" and n["card"]["is_new"]
    n = core.call("answer", {"id": cid, "rating": 3})                   # 认识 → 进入学习步骤
    assert n["counts"]["learning"] == 1 and n["card"]["id"] == cid      # 没别的词时提前再出现
    n = core.call("answer", {"id": cid, "rating": 3})                   # 再认识 → 毕业
    assert n["card"] is None
    card = core.db.execute("SELECT * FROM cards WHERE item_id=?", (cid,)).fetchone()
    assert card["state"] == int(State.Review) and card["reps"] == 2
    days = (card["due"] - core.clock()) / 86400
    assert 1 <= days <= 5
    core.clock_obj.add(days=int(days) + 1)
    n = core.call("next")
    assert n["counts"]["review"] == 1 and n["card"]["id"] == cid and not n["card"]["is_new"]
    n = core.call("answer", {"id": cid, "rating": 1})                   # 忘记 → 重新学习，记一次遗忘
    card = core.db.execute("SELECT * FROM cards WHERE item_id=?", (cid,)).fetchone()
    assert card["state"] == int(State.Relearning) and card["lapses"] == 1
    assert n["card"]["id"] == cid


def test_interval_grows_with_successful_reviews(core):
    core.call("add_word", {"term": "serendipity", "definition": "n. 意外发现珍奇事物的本领"})
    cid = core.call("next")["card"]["id"]
    core.call("answer", {"id": cid, "rating": 3})
    core.call("answer", {"id": cid, "rating": 3})
    gaps = []
    for _ in range(5):
        card = core.db.execute("SELECT * FROM cards WHERE item_id=?", (cid,)).fetchone()
        gap = card["due"] - core.clock()
        gaps.append(gap)
        core.clock_obj.t = card["due"] + 3600
        core.call("answer", {"id": cid, "rating": 3})
    assert all(b > a for a, b in zip(gaps, gaps[1:])), gaps
    assert gaps[-1] > 30 * 86400


def test_undo_restores_everything(core):
    core.call("add_word", {"term": "abandon"})
    n = core.call("next")
    cid = n["card"]["id"]
    core.call("answer", {"id": cid, "rating": 3})
    before = dict(core.db.execute("SELECT * FROM cards WHERE item_id=?", (cid,)).fetchone())
    core.call("answer", {"id": cid, "rating": 1})
    u = core.call("undo")
    assert u["undone"] and u["card"]["id"] == cid
    assert dict(core.db.execute("SELECT * FROM cards WHERE item_id=?", (cid,)).fetchone()) == before
    u = core.call("undo")                                               # 撤销第一次：回到“没学过”
    assert u["undone"] and u["card"]["is_new"]
    assert core.db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
    assert core.db.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 0
    assert core.call("undo")["undone"] is False


def test_custom_words_come_before_book_words(core):
    core.call("book_enable", {"id": "cet4"})
    core.call("add_word", {"term": "kerfuffle", "definition": "n. 骚动"})
    assert core.call("next")["card"]["term"] == "kerfuffle"


def test_add_word_validation(core):
    with pytest.raises(ApiError):
        core.call("add_word", {"term": "qwzxqwzx"})                     # 词典没有又没给释义
    with pytest.raises(ApiError):
        core.call("add_word", {"term": "  "})
    r = core.call("add_word", {"term": "Abandon"})
    assert r["added"] and r["term"] == "abandon"
    assert core.call("add_word", {"term": "abandon"})["added"] is False
    r = core.call("add_word", {"term": "勉強", "reading": "べんきょう", "definition": "学习"})
    item = core.call("item", {"id": r["id"]})
    assert item["lang"] == "ja" and item["definition"] == "学习" and item["reading"] == "べんきょう"


def test_item_edit_note_examples_suspend_reset(core):
    cid = core.call("add_word", {"term": "abandon"})["id"]
    d = core.call("item_update", {"id": cid, "note": "a band on → 放弃", "definition": "v. 放弃（自定义）",
                                  "examples": [{"en": "Never abandon hope.", "zh": "永不放弃希望。"}, {"en": "", "zh": "空的"}]})
    assert d["note"].startswith("a band") and d["definition"] == "v. 放弃（自定义）" and d["custom_definition"]
    assert d["examples"][0]["en"] == "Never abandon hope." and len(d["my_examples"]) == 1
    d = core.call("item_update", {"id": cid, "definition": ""})         # 清空 = 恢复词典释义
    assert "放弃" in d["definition"] and not d["custom_definition"]
    core.call("answer", {"id": cid, "rating": 4})
    assert core.call("item", {"id": cid})["card"]["curve"][0][1] == 1.0
    core.call("item_update", {"id": cid, "suspended": True})
    assert core.call("next")["card"] is None
    assert core.call("items", {"filter": "suspended"})["total"] == 1
    d = core.call("item_update", {"id": cid, "suspended": False, "reset": True})
    assert d["status"] == "new"
    core.call("item_delete", {"ids": [cid]})
    assert core.call("items", {})["total"] == 0


def test_importer_formats():
    rows = parse_file("a.txt", "apple\nbanana\n\napple\n1. cherry\n".encode())
    assert [r["term"] for r in rows] == ["apple", "banana", "cherry"]
    rows = parse_file("a.csv", "单词,释义,音标\nfoo,n. 测试,fu:\nbar,\"a, b\",\n".encode("utf-8-sig"))
    assert rows[0] == {"term": "foo", "definition": "n. 测试", "reading": "fu:"} and rows[1]["definition"] == "a, b"
    rows = parse_file("a.tsv", "meaning\tword\n苹果\tapple\n".encode())
    assert rows == [{"term": "apple", "definition": "苹果", "reading": ""}]
    rows = parse_file("a.txt", "take off   起飞；脱下\nlook up  查阅\n".encode("gb18030"))
    assert rows[0] == {"term": "take off", "definition": "起飞；脱下", "reading": ""}
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["word", "definition"])
    wb.active.append(["ephemeral", "短暂的"])
    buf = io.BytesIO()
    wb.save(buf)
    assert parse_file("w.xlsx", buf.getvalue()) == [{"term": "ephemeral", "definition": "短暂的", "reading": ""}]
    with pytest.raises(ValueError):
        parse_file("old.xls", b"x")
    assert detect_lang("食べる") == "ja" and detect_lang("ubiquitous") == "en"


def test_import_preview_and_commit(core):
    data = base64.b64encode("abandon\nqwzxqwzx\nmyword,我的释义\n食べる\n".encode()).decode()
    pv = core.call("import_preview", {"filename": "list.txt", "data": data})
    assert pv["total"] == 4 and pv["missing"] == 1 and pv["found"] == 3
    assert [r["lang"] for r in pv["rows"]] == ["en", "en", "en", "ja"]
    r = core.call("import_commit", {"name": "我的词表", "rows": [x for x in pv["rows"] if x["ok"]]})
    assert r["added"] == 3
    lists = core.call("books")["lists"]
    assert lists and lists[0]["title"] == "我的词表" and lists[0]["in_plan"] == 3
    items = core.call("items", {"source": "list:我的词表"})
    assert items["total"] == 3 and all(i["status"] == "new" for i in items["items"])
    assert core.call("source_remove", {"id": "list:我的词表"})["removed"] == 3


def test_source_remove_keeps_learned_words(core):
    core.call("book_enable", {"id": "zk"})
    n = core.call("next")
    core.call("answer", {"id": n["card"]["id"], "rating": 4})
    r = core.call("source_remove", {"id": "zk"})
    assert r["kept"] == 1 and core.call("items", {})["total"] == 1
    assert not any(b["enabled"] for b in core.call("books")["books"])


def test_stats_and_home(core):
    core.call("book_enable", {"id": "zk"})
    core.call("settings_set", {"new_per_day": 5})
    for day in range(3):
        n = core.call("next")
        while n["card"]:
            n = core.call("answer", {"id": n["card"]["id"], "rating": 3, "elapsed_ms": 4000})
        core.clock_obj.add(days=1)
    core.clock_obj.add(days=-1)
    s = core.call("stats")
    assert s["streak"] == 3 and s["today"]["new"] == 5 and s["today"]["reviews"] >= 10
    assert len(s["daily"]) == 30 and s["daily"][-1]["new"] == 5 and len(s["forecast"]) == 30
    assert s["states"]["unseen"] + s["states"]["learning"] + s["states"]["young"] + s["states"]["mature"] == s["states"]["total"]
    assert s["heatmap"][-1]["count"] == s["today"]["reviews"] and s["totals"]["days"] == 3
    assert sum(f["count"] for f in s["forecast"]) == 15
    h = core.call("home")
    assert h["has_items"] and h["streak"] == 3 and h["counts"]["total"] == 0
    assert core.call("items", {"filter": "learned", "sort": "due"})["total"] == 15


def test_review_cap(core):
    core.call("book_enable", {"id": "zk"})
    core.call("settings_set", {"new_per_day": 6})
    n = core.call("next")
    while n["card"]:
        n = core.call("answer", {"id": n["card"]["id"], "rating": 4})
    core.clock_obj.add(days=40)
    core.call("settings_set", {"new_per_day": 0, "review_per_day": 2})
    n = core.call("next")
    assert n["counts"]["review"] == 2
    n = core.call("answer", {"id": n["card"]["id"], "rating": 3})
    n = core.call("answer", {"id": n["card"]["id"], "rating": 3})
    assert n["card"] is None and n["counts"]["review"] == 0


def test_settings_validation_and_persistence(core, tmp_path):
    s = core.call("settings_set", {"new_per_day": 99999, "retention": 0.5, "theme": "dark", "bogus": 1})["settings"]
    assert s["new_per_day"] == 500 and s["retention"] == 0.70 and s["theme"] == "dark" and "bogus" not in s
    with pytest.raises(ApiError):
        core.call("settings_set", {"order": "sideways"})
    again = Core(tmp_path, clock=core.clock)
    assert again.settings["theme"] == "dark" and again.srs.retention == 0.70
    again.close()


def test_higher_retention_means_shorter_intervals(core):
    lo, hi = Srs(0.80), Srs(0.95)
    now = core.clock()
    c = lo.review(None, 4, now).to_json()
    assert lo.review(c, 3, now + 86400 * 8).due > hi.review(c, 3, now + 86400 * 8).due


def test_forgetting_curve_matches_library():
    srs, sched = Srs(0.9), Scheduler(enable_fuzzing=False)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    card = Card(state=State.Review, stability=12.5, difficulty=5.0, due=now, last_review=now)
    for d in (0, 1, 7, 30, 200):
        assert srs.recall(12.5, d) == pytest.approx(sched.get_card_retrievability(card, now + timedelta(days=d)), abs=1e-9)
    assert srs.recall(12.5, 12.5) == pytest.approx(0.9, abs=1e-6)       # 稳定度的定义：过 S 天保持率 90%
    assert fmt_interval(60) == "1 分钟" and fmt_interval(600) == "10 分钟" and fmt_interval(3 * 86400) == "3 天"
    assert fmt_interval(45 * 86400) == "1.5 个月" and fmt_interval(730 * 86400) == "2 年"


def test_backup_export_reset_speak(core):
    core.call("add_word", {"term": "abandon"})
    cid = core.call("next")["card"]["id"]
    core.call("answer", {"id": cid, "rating": 3})
    import pathlib
    assert pathlib.Path(core.call("backup")["path"]).stat().st_size > 0
    text = pathlib.Path(core.call("export")["path"]).read_text(encoding="utf-8-sig")
    assert "abandon" in text and "学习中" in text
    with pytest.raises(ApiError):
        core.call("reset_progress", {})
    core.call("reset_progress", {"confirm": "RESET"})
    assert core.call("items", {"filter": "learned"})["total"] == 0 and core.call("items", {})["total"] == 1
    with pytest.raises(ApiError):
        core.call("nope")


MP3 = b"\xff\xf3" + b"\x00" * 600


def test_speak_source_chain(core, monkeypatch):
    calls = []
    monkeypatch.setattr(core.voice, "pack", lambda lang, text: MP3 if text == "abandon" else None)
    monkeypatch.setattr(core.voice, "online", lambda lang, text, accent: calls.append((lang, text, accent)) or (MP3 + b"x" if text != "zzz" else None))
    # 浏览器模式：内置语音包里有 → 直接返回音频
    r = core.call("speak", {"text": "abandon"})
    assert r["source"] == "builtin" and not r["handled"] and r["audio"] and not calls
    # 语音包里没有 → 联网取
    assert core.call("speak", {"text": "kerfuffle"})["source"] == "online" and calls == [("en", "kerfuffle", "us")]
    # 关掉联网补充 → 退回系统/浏览器朗读
    core.call("settings_set", {"online_fallback": False})
    assert core.call("speak", {"text": "kerfuffle"}) == {"handled": False, "source": "browser"}
    # 选了在线发音：先在线，取不到再用语音包
    core.call("settings_set", {"voice": "online", "accent": "uk"})
    assert core.call("speak", {"text": "abandon"})["source"] == "online" and calls[-1] == ("en", "abandon", "uk")
    # 桌面模式：交给播放器，传的是落盘后的音频文件
    played = []
    core.speaker = lambda text, lang, path: played.append((text, lang, path))
    core.voice_langs = set()
    r = core.call("speak", {"text": "abandon"})
    assert r == {"handled": True, "source": "online"} and played[0][2].endswith(".mp3")
    import pathlib
    assert pathlib.Path(played[0][2]).read_bytes() == MP3 + b"x"
    # 都没有，系统里也没有这种语言的语音 → 告诉界面缺语音
    assert core.call("speak", {"text": "zzz", "lang": "ja"}) == {"handled": True, "missing": "ja"}
    core.voice_langs = {"ja"}
    assert core.call("speak", {"text": "zzz", "lang": "ja"})["source"] == "system" and played[-1] == ("zzz", "ja", "")


def test_voicebank_online_cache(tmp_path, monkeypatch):
    from shici.voice import VoiceBank
    vb = VoiceBank(tmp_path / "cache", data_dir=tmp_path)   # 这个目录里没有语音包
    assert vb.pack("en", "abandon") is None and vb.pack_langs() == []
    n = []
    monkeypatch.setattr(vb, "_fetch", lambda url: n.append(url) or MP3)
    assert vb.online("en", "hello", "us") == MP3 and vb.online("en", "hello", "us") == MP3
    assert len(n) == 1 and "type=2" in n[0]                 # 第二次走缓存
    assert vb.online("ja", "食べる", "us") == MP3 and "le=jap" in n[1]
    def boom(url): raise OSError("offline")
    monkeypatch.setattr(vb, "_fetch", boom)
    assert vb.online("en", "other", "us") is None           # 断网不报错
    monkeypatch.setattr(vb, "_fetch", lambda url: None)
    assert vb.online("en", "junk", "us") is None and not list((tmp_path / "cache").rglob("*junk*"))


def test_builtin_voice_packs_cover_books(core):
    """内置语音包应该覆盖所有词书里的词（语音包还没生成时跳过）。"""
    import sqlite3
    from shici.paths import resource_dir
    for lang, sql in (("en", "SELECT DISTINCT word FROM book_words"), ("ja", "SELECT word FROM entries")):
        if lang not in core.voice.pack_langs():
            pytest.skip("语音包不在")
        words = [r[0] for r in sqlite3.connect(resource_dir() / "data" / f"dict_{lang}.db").execute(sql)]
        missing = [w for w in words if not core.voice.pack(lang, w)]
        assert len(missing) <= len(words) * 0.002, missing[:20]
        data = core.voice.pack(lang, words[0])
        assert data[:3] == b"ID3" or data[0] == 0xFF


def _study(core, days=3):
    core.call("book_enable", {"id": "zk"})
    core.call("add_word", {"term": "kerfuffle", "definition": "n. 骚动", "note": "记法"})
    core.call("settings_set", {"new_per_day": 6, "retention": 0.88})
    for _ in range(days):
        n = core.call("next")
        while n["card"]:
            n = core.call("answer", {"id": n["card"]["id"], "rating": 3, "elapsed_ms": 3000})
        core.clock_obj.add(days=1)


def test_progress_key_roundtrip(core, tmp_path):
    _study(core)
    exp = core.call("progress_export")
    key = exp["key"]
    assert key.startswith("XMCS1.") and exp["words"] == 18 and exp["logs"] == core.db.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
    assert set(key[6:]) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    other = Core(tmp_path / "new-device", clock=core.clock)
    info = other.call("progress_inspect", {"key": key})
    assert info["words"] == 18 and info["custom"] == 1 and info["books"] == ["中考"] and info["local_words"] == 0
    wrapped = "\n".join(key[i:i + 70] for i in range(0, len(key), 70)) + "  \n"     # 复制时带进了换行和空格也没关系
    r = other.call("progress_import", {"key": wrapped})
    assert r["updated"] == 18 and r["logs_added"] == exp["logs"]
    a, b = core.call("stats"), other.call("stats")
    for k in ("streak", "states", "forecast", "daily", "today", "retention"):
        assert a[k] == b[k], k
    assert other.settings["retention"] == 0.88 and other.settings["new_per_day"] == 6
    item = other.call("items", {"q": "kerfuffle"})["items"][0]
    full = other.call("item", {"id": item["id"]})
    assert full["note"] == "记法" and full["definition"] == "n. 骚动" and full["sources"] == ["自己添加"]
    # 两边接下来要复习的词、间隔完全一样
    core.clock_obj.add(days=2)
    x, y = core.call("next"), other.call("next")
    assert x["card"]["term"] == y["card"]["term"] and x["card"]["intervals"] == y["card"]["intervals"] and x["counts"] == y["counts"]
    # 再导一次不会重复
    again = other.call("progress_import", {"key": key})
    assert again["logs_added"] == 0 and again["updated"] == 0 and again["kept"] == 18
    other.close()


def test_progress_key_merge_keeps_newer(core, tmp_path):
    _study(core, days=1)
    key_old = core.call("progress_export")["key"]
    other = Core(tmp_path / "laptop", clock=core.clock)
    other.call("progress_import", {"key": key_old})
    # 笔记本上继续学了一天；台式机上没动
    n = other.call("next")
    while n["card"]:
        n = other.call("answer", {"id": n["card"]["id"], "rating": 3})
    learned = other.db.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    assert learned > 7
    r = other.call("progress_import", {"key": key_old})          # 把旧密钥再导进来：不能把新进度盖掉
    assert r["updated"] == 0 and other.db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == learned
    r = core.call("progress_import", {"key": other.call("progress_export")["key"]})   # 反过来同步回台式机
    assert r["updated"] >= learned - 7 and core.db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == learned
    assert core.db.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == other.db.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
    other.close()


def test_progress_key_rejects_garbage(core):
    key = core.call("progress_export")["key"]
    for bad in ("", "hello", "XMCS1.", "XMCS1.!!!!", key[:-20], key[:30] + "AAAA" + key[34:], "XMCS9." + key[6:]):
        with pytest.raises(ApiError):
            core.call("progress_inspect", {"key": bad})
    assert core.call("clipboard_copy", {"text": key}) == {"copied": False}
    got = []
    core.clipboard = got.append
    assert core.call("clipboard_copy", {"text": key}) == {"copied": True} and got == [key]


def test_japanese_and_extended_examples(core):
    ex = core.dict.examples("ja", "秋")
    assert ex and "秋" in ex[0]["en"] and ex[0]["zh"]
    assert core.dict.examples("en", "abandon")[0]["zh"]            # 常用词：带中文译文
    assert core.dict.examples("en", "ubiquitous")                   # 生僻一点的词也有例句（可能没有译文）


def test_every_exam_word_has_an_example(core):
    import sqlite3
    from shici.paths import resource_dir
    d = sqlite3.connect(resource_dir() / "data" / "dict_en.db")
    total = d.execute("SELECT COUNT(DISTINCT word) FROM book_words").fetchone()[0]
    missing = d.execute("SELECT COUNT(DISTINCT w.word) FROM book_words w WHERE NOT EXISTS"
                        "(SELECT 1 FROM examples e WHERE e.word=w.word)").fetchone()[0]
    assert total > 14000 and missing <= 5, (total, missing)
    ex = core.dict.examples("en", "acrimony")                           # 生僻词：自编例句，带中文译文
    assert ex and "acrimony" in ex[0]["en"] and ex[0]["zh"]
    assert core.dict.examples("en", "T-shirt")                          # 带连字符的词
    assert any(e["zh"] for e in core.dict.examples("en", "abandon"))    # 常用词：有中文译文
    ja = core.dict.examples("ja", "先生")
    assert ja and "先生" in ja[0]["en"] and ja[0]["zh"]


def test_multi_filter_and_bulk_actions(core):
    core.call("book_enable", {"id": "zk"})
    core.call("settings_set", {"new_per_day": 4})
    n = core.call("next")
    while n["card"]:
        n = core.call("answer", {"id": n["card"]["id"], "rating": 4})
    total = core.call("items", {})["total"]
    learned = core.call("items", {"filter": "learned"})["total"]
    assert learned == 4
    assert core.call("items", {"filter": ["new", "young", "mature", "learning"]})["total"] == total   # 多个状态取并集
    assert core.call("items", {"filter": ["young", "mature"]})["total"] == 4
    ids = core.call("item_ids", {"filter": "new"})["ids"]
    assert len(ids) == total - 4
    assert core.call("items_bulk", {"ids": ids[:700], "action": "suspend"})["count"] == 700          # 超过 500 也能分批处理
    assert core.call("items", {"filter": "suspended"})["total"] == 700
    assert core.call("items", {"filter": ["new", "suspended"]})["total"] == total - 4
    core.call("items_bulk", {"ids": ids[:700], "action": "resume"})
    assert core.call("items", {"filter": "suspended"})["total"] == 0
    # 优先学：选中的词排到新词队列最前面
    target = ids[-3:]
    core.call("items_bulk", {"ids": target, "action": "prioritize"})
    core.clock_obj.add(days=1)
    assert core.call("next")["card"]["id"] in target
    # 重新学、删除
    done = core.call("item_ids", {"filter": "learned"})["ids"]
    core.call("items_bulk", {"ids": done[:2], "action": "reset"})
    assert core.call("items", {"filter": "learned"})["total"] == 2
    core.call("items_bulk", {"ids": ids[:10], "action": "delete"})
    assert core.call("items", {})["total"] == total - 10
    with pytest.raises(ApiError):
        core.call("items_bulk", {"ids": [1], "action": "explode"})


def _tiny_font(family="测试字体", flavor=None):
    """用 fontTools 生成一个只有一个字形的小字体（中文名 + 英文名）。"""
    import io as _io
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({0x41: "A"})
    pen = TTGlyphPen(None); pen.moveTo((0, 0)); pen.lineTo((500, 700)); pen.lineTo((900, 0)); pen.closePath()
    g = pen.glyph()
    fb.setupGlyf({".notdef": g, "A": g})
    fb.setupHorizontalMetrics({".notdef": (1000, 0), "A": (1000, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": {"en": "Test Font", "zh-CN": family}, "styleName": "Regular"})
    fb.setupOS2(); fb.setupPost()
    if flavor:
        fb.font.flavor = flavor
    buf = _io.BytesIO(); fb.save(buf)
    return buf.getvalue()


def test_font_import_select_delete(core):
    from shici.fonts import family_name
    ttf, woff = _tiny_font(), _tiny_font("另一个字体", "woff")
    assert family_name(ttf) == "测试字体" and family_name(woff) == "另一个字体"   # 中文名优先，WOFF 也能读
    r = core.call("font_import", {"filename": "x.ttf", "data": base64.b64encode(ttf).decode()})
    f = r["font"]
    assert f["name"] == "测试字体" and f["format"] == "truetype" and (core.dir / "fonts" / f["file"]).exists()
    again = core.call("font_import", {"filename": "copy.ttf", "data": base64.b64encode(ttf).decode()})
    assert again["font"]["id"] == f["id"] and len(again["user"]) == 1                  # 同一个文件不会重复导入
    with pytest.raises(ApiError):
        core.call("font_import", {"filename": "a.ttf", "data": base64.b64encode(b"not a font at all").decode()})
    s = core.call("settings_set", {"font_title": "user:" + f["id"], "font_body": "system:Yu Gothic UI"})["settings"]
    assert s["font_title"] == "user:" + f["id"] and s["font_body"] == "system:Yu Gothic UI"
    with pytest.raises(ApiError):
        core.call("settings_set", {"font_title": "user:doesnotexist"})
    with pytest.raises(ApiError):
        core.call("settings_set", {"font_body": "builtin:comic"})
    assert core.call("bootstrap")["user_fonts"][0]["id"] == f["id"]
    d = core.call("font_delete", {"id": f["id"]})
    assert d["user"] == [] and d["settings"]["font_title"] == "" and d["settings"]["font_body"] == "system:Yu Gothic UI"
    assert not (core.dir / "fonts" / f["file"]).exists()
    assert core.settings["palette"] == "silver"                                         # 默认配色是简约白


def test_progress_file_roundtrip(core, tmp_path):
    core.call("book_enable", {"id": "zk"})
    core.call("add_word", {"term": "serendipity", "note": "意外的好运"})
    n = core.call("next")
    for _ in range(4):
        n = core.call("answer", {"id": n["card"]["id"], "rating": 3, "elapsed_ms": 3000})
    f = core.call("progress_export", {"as_file": True})
    assert f["filename"].endswith(".xmdb") and f["words"] >= 2 and f["bytes"] < 20000
    blob = base64.b64decode(f["data"])
    assert blob.startswith(b"XMDB1\n")
    other = Core(tmp_path / "other", clock=core.clock)
    info = other.call("progress_inspect", {"file": f["data"]})
    assert info["words"] == f["words"] and info["local_words"] == 0
    r = other.call("progress_import", {"file": f["data"]})
    assert r["updated"] == f["words"]
    assert other.call("items", {"q": "serendipity"})["items"][0]["note"] == "意外的好运" or \
        other.call("item", {"id": other.call("items", {"q": "serendipity"})["items"][0]["id"]})["note"] == "意外的好运"
    # 文件里放的是密钥文字也认；坏文件、截断的文件给出清楚的提示
    key = core.call("progress_export")["key"]
    assert other.call("progress_inspect", {"file": base64.b64encode(key.encode()).decode()})["words"] == f["words"]
    with pytest.raises(ApiError, match="不是小梦的词书的进度文件"):
        other.call("progress_inspect", {"file": base64.b64encode(b"hello world").decode()})
    with pytest.raises(ApiError, match="不完整或已损坏"):
        other.call("progress_inspect", {"file": base64.b64encode(blob[:len(blob) // 2]).decode()})
    other.close()


def test_sentence_speech_uses_cache_and_system_voice(core):
    sent = "Never abandon hope."
    played = []
    core.speaker = lambda text, lang, path: played.append((text, lang, path))
    core.voice_langs = {"en"}
    core.call("settings_set", {"voice": "builtin", "online_fallback": False})
    r = core.call("speak", {"text": sent, "lang": "en", "kind": "sentence"})       # 没有缓存、不许联网 → 系统语音
    assert r == {"handled": True, "source": "system"} and played[-1] == (sent, "en", "")
    cache = core.voice._sentence_path("en", sent, "us")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"ID3" + b"\x00" * 600)                                       # 有缓存 → 直接播放缓存的音频
    r = core.call("speak", {"text": sent, "lang": "en", "kind": "sentence"})
    assert r["source"] == "online" and played[-1][2].endswith(".mp3")
    core.voice_langs = set()
    r = core.call("speak", {"text": "誰もいない。", "lang": "ja", "kind": "sentence"})  # 没缓存、没语音、不许联网
    assert r.get("missing") == "ja" and r.get("kind") == "sentence"
    core.speaker = None
    assert core.call("speak", {"text": sent, "lang": "en", "kind": "sentence"})["audio"]  # 浏览器模式：把音频传回界面


def test_gloss_language_and_domain_switch(core):
    # 默认：英语词显示中文，专业领域释义（[计] 等）不显示
    e = core.dict.lookup("en", "propriety")
    assert "礼貌" in e["translation"] and "[计]" not in e["translation"]
    core.api_settings_set({"show_domain": True})
    assert "[计]" in core.dict.lookup("en", "propriety")["translation"]
    # 日英
    core.api_settings_set({"gloss_en": "ja"})
    assert any("぀" <= ch <= "ヿ" for ch in core.dict.lookup("en", "season")["translation"])
    # 日语词：默认中日，可切成英日
    zh = core.dict.lookup("ja", "勉強")["translation"]
    assert "学习" in zh
    core.api_settings_set({"gloss_ja": "en"})
    assert "study" in core.dict.lookup("ja", "勉強")["translation"]
    with pytest.raises(ApiError):
        core.api_settings_set({"gloss_ja": "fr"})


def test_example_translations(core):
    # 英语例句都有中文（人工或机翻），机翻的带标记，人工译文排在前面
    for w in ("barge", "carafe", "abandon", "season"):
        exs = core.dict.examples("en", w)
        assert exs and all(x["zh"] for x in exs), w
        assert [x["mt"] for x in exs] == sorted(x["mt"] for x in exs)
    # 日语例句默认中文译文；英日模式给英文
    ja = core.dict.examples("ja", "勉強")
    assert ja and all(any("一" <= ch <= "鿿" for ch in x["zh"]) for x in ja)
    core.api_settings_set({"gloss_ja": "en"})
    assert any(x["zh"].isascii() for x in core.dict.examples("ja", "勉強"))


def test_update_check_and_links(core, monkeypatch):
    import json as _json
    import urllib.request

    class Resp:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: Resp(_json.dumps({"tag_name": "v99.0.0", "html_url": "https://github.com/x"}).encode()))
    r = core.api_update_check({})
    assert r["ok"] and r["newer"] and r["latest"] == "99.0.0"
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: Resp(_json.dumps({"tag_name": "v0.0.1"}).encode()))
    assert core.api_update_check({})["newer"] is False

    def boom(req, timeout): raise OSError("offline")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert core.api_update_check({})["ok"] is False
    opened = []
    core.url_opener = opened.append
    assert core.api_open_url({"url": core.api_bootstrap({})["links"]["github"]})["opened"] and opened
    with pytest.raises(ApiError):
        core.api_open_url({"url": "file:///etc/passwd"})


def test_render_setting_and_restart(core):
    assert core.settings["render"] == "auto" and core.settings["sfx"] is True
    core.api_settings_set({"render": "opengl"})
    assert core.settings["render"] == "opengl"
    for bad in ({"render": "vulkan"}, {"render": "software"}, {"gpu": "fast"}):
        with pytest.raises(ApiError):
            core.api_settings_set(bad)
    core.api_settings_set({"gpu": "high", "render": "d3d11"})
    assert core.settings["gpu"] == "high" and core.settings["render"] == "d3d11"
    seen = []
    core.display_ok = seen.append
    core.api_display_ok({"renderer": "NVIDIA GeForce RTX 4060 Ti"})
    assert seen == ["NVIDIA GeForce RTX 4060 Ti"]
    looks = []
    core.look_changed = lambda dark, silver: looks.append((dark, silver))
    core.api_look({"dark": True, "palette": "silver"})
    assert looks == [(True, True)]
    assert core.api_restart({}) == {"restarting": False}       # 浏览器里打开时没法自己重启
    calls = []
    core.restarter = lambda: calls.append(1)
    core.render_trial = True
    assert core.api_restart({})["restarting"] and calls
    core.api_render_confirm({})
    assert core.api_bootstrap({})["render_trial"] is False


def test_roots_and_related(core):
    iid = core.api_add_word({"lang": "en", "term": "transportation"})["id"]
    assert "roots" not in core.api_item({"id": iid})  # 默认关闭
    m = core.dict.morph("transportation")
    assert [p["t"] for p in m["parts"]] == ["trans", "port", "ation"] and m["parts"][1]["k"] == "r"
    assert any(f["w"] == "export" or f["w"] == "report" for f in m["family"])
    assert core.dict.morph("went") is None  # 没有可信拆法的词不拆
    r = core.dict.related("happier")  # 变形词按原形查
    assert any(x["w"] == "glad" for x in r["syn"]) and any(x["w"] == "unhappy" for x in r["ant"])
    core.api_settings_set({"show_roots": True, "show_related": True})
    it = core.api_item({"id": iid})
    assert it["roots"]["parts"][1]["t"] == "port" and "syn" in it["related"]


def test_version_compare_pads_missing_parts():
    from shici.core import Core
    assert Core._ver("1.0") == Core._ver("1.0.0") == (1, 0, 0)
    assert Core._ver("1.0.1") > Core._ver("1.0")
    assert not Core._ver("1.0") > Core._ver("1.0.0")


def test_sync_merge_events(core, tmp_path):
    """局域网同步用的合并：删词、撤销、清空进度都要传到另一台设备，而且不会被对方同步回来。"""
    _study(core, days=1)
    other = Core(tmp_path / "phone", clock=core.clock)
    sync = lambda a, b: (b._merge_progress(a._progress_payload()), a._merge_progress(b._progress_payload()))  # noqa: E731
    count = lambda c, t: c.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    sync(core, other)
    assert count(other, "cards") == count(core, "cards") > 0 and count(other, "logs") == count(core, "logs")
    # 手机上背一个词再撤销：电脑上不能留下这次复习
    core.clock_obj.add(minutes=5)
    n = other.call("next")
    other.call("answer", {"id": n["card"]["id"], "rating": 3})
    sync(core, other)
    logs = count(core, "logs")
    other.call("undo")
    sync(core, other)
    assert count(core, "logs") == count(other, "logs") == logs - 1
    term = other.db.execute("SELECT term FROM items WHERE id=?", (n["card"]["id"],)).fetchone()[0]
    a = core.db.execute("SELECT c.last_review FROM cards c JOIN items i ON i.id=c.item_id WHERE i.term=?", (term,)).fetchone()
    b = other.db.execute("SELECT last_review FROM cards WHERE item_id=?", (n["card"]["id"],)).fetchone()
    assert (a and a[0]) == (b and b[0])
    # 电脑上删一个学过的词：手机上也删掉，再同步也不会回来
    victim = core.db.execute("SELECT i.id, i.term FROM items i JOIN cards c ON c.item_id=i.id LIMIT 1").fetchone()
    core.call("item_delete", {"ids": [victim["id"]]})
    sync(other, core)
    sync(core, other)
    for c in (core, other):
        assert not c.db.execute("SELECT 1 FROM items WHERE term=?", (victim["term"],)).fetchone()
    # 手机上清空进度：电脑上也清空
    core.clock_obj.add(minutes=1)
    other.call("reset_progress", {"confirm": "RESET"})
    sync(other, core)
    assert count(core, "cards") == count(other, "cards") == 0 and count(core, "logs") == 0
    other.close()
