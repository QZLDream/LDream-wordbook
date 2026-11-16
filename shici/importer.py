"""把 txt / csv / tsv / xlsx 词表解析成 [{term, reading, definition}]。

支持的写法：
  - 每行一个单词
  - 每行“单词<分隔符>释义”，分隔符可以是制表符、逗号、分号、竖线或两个以上空格
  - 带表头的表格：表头里出现 word/单词/term、释义/definition/meaning、音标/读音/reading 会自动对应到列
"""
from __future__ import annotations

import csv
import io
import re

MAX_ROWS = 20000

HEAD_TERM = {"word", "words", "term", "单词", "词", "词汇", "単語", "英文", "vocabulary", "vocab"}
HEAD_DEF = {"definition", "meaning", "translation", "释义", "意思", "中文", "解释", "翻译", "意味"}
HEAD_READ = {"reading", "phonetic", "pronunciation", "音标", "读音", "发音", "读法", "読み", "かな", "假名"}

_JA = re.compile(r"[぀-ヿ㐀-鿿]")


def detect_lang(term: str) -> str:
    return "ja" if _JA.search(term) else "en"


def decode(data: bytes) -> str:
    """猜测文本编码：UTF-8 / UTF-16（带 BOM）/ GB18030（中文 Windows）/ Shift_JIS（日文 Windows）。"""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    cands = []
    for enc in ("gb18030", "cp932"):
        try:
            cands.append(data.decode(enc))
        except UnicodeDecodeError:
            continue
    if not cands:
        return data.decode("utf-8", errors="replace")
    kana = lambda t: sum(1 for ch in t if "\u3040" <= ch <= "\u30ff")  # noqa: E731
    # 两种都能解码时：只有按 Shift_JIS 解出假名、按 GB18030 解不出时才当作日文
    if len(cands) == 2 and kana(cands[1]) > kana(cands[0]) * 3 + 2:
        return cands[1]
    return cands[0]


def _rows_from_text(text: str) -> list[list[str]]:
    lines = [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()]
    if not lines:
        return []
    sample = lines[:50]
    delim = None
    for d in ("\t", ",", ";", "|", "，"):
        if sum(1 for ln in sample if d in ln) >= max(1, len(sample) * 0.6):
            delim = d
            break
    if delim in (",", ";"):
        return [[c.strip() for c in r] for r in csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)]
    if delim:
        return [[c.strip() for c in ln.split(delim)] for ln in lines]
    # 没有统一分隔符：逐行判断。制表符或两个以上空格拆成 单词 + 释义；
    # “word,中文释义” 这种逗号后面跟着非英文内容的也拆开；否则整行当作单词
    out = []
    for ln in lines:
        parts = re.split(r"\t|\s{2,}", ln.strip(), maxsplit=1)
        if len(parts) == 1:
            m = re.match(r"^([A-Za-z][A-Za-z\-' .]*?)\s*[,，;；|]\s*(.*[^\x00-\x7f].*)$", ln.strip())
            if m:
                parts = [m.group(1), m.group(2)]
        out.append([c.strip() for c in parts])
    return out


def _rows_from_xlsx(data: bytes) -> list[list[str]]:
    from openpyxl import load_workbook  # 只在导入 Excel 时才需要

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = []
    for r in ws.iter_rows(values_only=True):
        cells = ["" if c is None else str(c).strip() for c in r]
        if any(cells):
            rows.append(cells)
        if len(rows) > MAX_ROWS + 1:
            break
    return rows


def parse_file(filename: str, data: bytes) -> list[dict]:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        rows = _rows_from_xlsx(data)
    elif name.endswith(".xls"):
        raise ValueError("不支持旧版 .xls，请在 Excel 里另存为 .xlsx 或 .csv")
    else:
        rows = _rows_from_text(decode(data))
    if not rows:
        return []

    col = {"term": 0, "definition": 1, "reading": 2}
    head = [c.lower().strip() for c in rows[0]]
    if any(h in HEAD_TERM | HEAD_DEF | HEAD_READ for h in head):
        found = {}
        for i, h in enumerate(head):
            if h in HEAD_TERM:
                found.setdefault("term", i)
            elif h in HEAD_DEF:
                found.setdefault("definition", i)
            elif h in HEAD_READ:
                found.setdefault("reading", i)
        if "term" in found:
            col = {"term": found["term"], "definition": found.get("definition", -1), "reading": found.get("reading", -1)}
            rows = rows[1:]

    def cell(r, key):
        i = col[key]
        return r[i].strip() if 0 <= i < len(r) else ""

    out, seen = [], set()
    for r in rows:
        term = re.sub(r"^\s*\d+[.、)]\s*", "", cell(r, "term")).strip()  # 去掉“1. ”这类序号
        if not term or len(term) > 80:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"term": term, "definition": cell(r, "definition"), "reading": cell(r, "reading")})
        if len(out) >= MAX_ROWS:
            break
    return out
