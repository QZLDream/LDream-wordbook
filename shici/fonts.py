"""用户导入的字体：保存、读取字体名、删除。

字体文件放在数据文件夹的 fonts/ 里，索引在 fonts/fonts.json。
界面通过 /userfonts/<文件名> 加载它们（见 server.py）。
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import time
import zlib
from pathlib import Path

EXTS = {".ttf": "truetype", ".otf": "opentype", ".woff": "woff", ".woff2": "woff2"}
MAGIC = {b"\x00\x01\x00\x00": ".ttf", b"true": ".ttf", b"OTTO": ".otf", b"wOFF": ".woff", b"wOF2": ".woff2"}
MAX_BYTES = 40 * 1024 * 1024
FILE_RE = re.compile(r"^[0-9a-f]{12}\.(ttf|otf|woff|woff2)$")


def _decode(raw: bytes, platform: int) -> str:
    try:
        return raw.decode("utf-16-be") if platform in (0, 3) else raw.decode("latin-1")
    except UnicodeDecodeError:
        return ""


def _name_table(data: bytes) -> bytes | None:
    """从 TTF/OTF/WOFF 里取出 name 表。WOFF2 用了 Brotli 压缩，这里不解析。"""
    if data[:4] == b"wOFF":
        num = struct.unpack_from(">H", data, 12)[0]
        for i in range(num):
            tag, off, comp, orig, _ = struct.unpack_from(">4sIIII", data, 44 + i * 20)
            if tag == b"name":
                blob = data[off:off + comp]
                return zlib.decompress(blob) if comp < orig else blob
        return None
    num = struct.unpack_from(">H", data, 4)[0]
    for i in range(num):
        tag, _, off, length = struct.unpack_from(">4sIII", data, 12 + i * 16)
        if tag == b"name":
            return data[off:off + length]
    return None


def family_name(data: bytes) -> str | None:
    """字体的显示名：优先中文名，其次英文名；优先“排版用家族名”(ID 16)，其次家族名 (ID 1)。"""
    try:
        t = _name_table(data)
        if not t:
            return None
        _, count, base = struct.unpack_from(">HHH", t, 0)
        found = {}
        for i in range(count):
            plat, enc, lang, nid, length, off = struct.unpack_from(">HHHHHH", t, 6 + i * 12)
            if nid not in (1, 16):
                continue
            s = _decode(t[base + off: base + off + length], plat).strip("\x00 ").strip()
            if s:
                zh = plat == 3 and lang in (0x804, 0x404, 0xC04, 0x1004, 0x411)
                en = (plat == 3 and lang == 0x409) or plat in (0, 1)
                found.setdefault((0 if zh else 1 if en else 2, 0 if nid == 16 else 1), s)
        return found[min(found)] if found else None
    except (struct.error, zlib.error, IndexError):
        return None


class FontStore:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "fonts"
        self.index = self.dir / "fonts.json"

    def list(self) -> list[dict]:
        try:
            items = json.loads(self.index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [f for f in items if (self.dir / f["file"]).exists()]

    def _save(self, items: list[dict]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    def add(self, filename: str, data: bytes) -> dict:
        if len(data) > MAX_BYTES:
            raise ValueError("字体文件太大了（上限 40 MB）")
        ext = MAGIC.get(data[:4])
        if not ext:
            raise ValueError("这不是字体文件。支持 .ttf  .otf  .woff  .woff2（.ttc 字体集请先拆分）")
        fid = hashlib.sha1(data).hexdigest()[:12]
        items = self.list()
        for f in items:
            if f["id"] == fid:
                return f
        stem = Path(filename or "").stem
        name = (family_name(data) if ext != ".woff2" else None) or stem or "导入的字体"
        entry = {"id": fid, "name": name[:60], "file": fid + ext, "format": EXTS[ext], "size": len(data), "added": int(time.time())}
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / entry["file"]).write_bytes(data)
        self._save(items + [entry])
        return entry

    def remove(self, fid: str) -> bool:
        items = self.list()
        keep = [f for f in items if f["id"] != fid]
        for f in items:
            if f["id"] == fid:
                (self.dir / f["file"]).unlink(missing_ok=True)
        self._save(keep)
        return len(keep) != len(items)

    def path(self, file: str) -> Path | None:
        if not FILE_RE.match(file or ""):
            return None
        p = self.dir / file
        return p if p.is_file() else None
