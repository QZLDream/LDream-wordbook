"""局域网同步：同一个 Wi-Fi（同一个局域网）下的手机和电脑都打开小梦的词书时，自动互相合并学习进度。

怎么找到对方：每台设备每 2 秒在局域网里广播一条很短的 UDP 消息（端口 47819），里面有设备名、
同步用的端口和一个“进度指纹”（进度有没有变）。收到别人的广播时也单独回一条，这样即使一边收不到广播
（有些手机省电时会过滤广播，电脑的防火墙也可能挡住），只要另一边能收到就能连上。

怎么同步：发现对方的进度指纹和上次同步时不一样，就把自己的进度（和“进度文件”是同一份数据）发过去；
对方合并后把它合并完的进度发回来，这边再合并一次，两边就一样了。合并规则和导入进度文件相同：
每个词以最近复习过的那一边为准，复习记录取并集；删掉的词、移出的词书、撤销的复习、清空进度也会同步。

安全：两台设备要填同一个同步码。广播里只有同步码算出来的组号；每次同步的内容都用同步码签名，
同步码不一样的设备既看不到也改不了你的进度。数据只在局域网里直接传，不经过任何服务器。
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import lzma
import secrets
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote

PORT = 47819
MAGIC = "xmcs-lan/1"
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 去掉了容易看错的 0 O 1 I L
BEACON_EVERY = 2.0
ONLINE_FOR = 12.0       # 多久没收到广播就算对方已经离开
SETTLE = 3.0            # 进度刚变（正在背）时等这么久再同步，攒一批
MAX_BODY = 64 * 1024 * 1024


class LanSync:
    def __init__(self, core):
        self.core = core
        self.id = secrets.token_hex(8)   # 每次启动换一个，只用来区分设备、决定谁先发起
        self.gen = 0                      # 每次启动 / 停止加一，旧的线程看到就退出
        self.running = False
        self.code = ""
        self.key = b""
        self.group = ""
        self.port = 0
        self.udp: socket.socket | None = None
        self.httpd: ThreadingHTTPServer | None = None
        self.peers: dict[str, dict] = {}
        self.plock = threading.Lock()
        self.syncing: str | None = None
        self.error = ""
        self.backed_up = False
        self.merged = {"at": 0.0, "from": "", "changes": 0}
        self._fp = (None, "")
        self._fp_changed = 0.0
        self._ips: tuple[float, list[str]] = (0.0, [])

    # ------------------------------------------------------------ 开关
    @staticmethod
    def new_code() -> str:
        return "".join(secrets.choice(ALPHABET) for _ in range(8))

    @property
    def name(self) -> str:
        if self.core.device_name:
            return self.core.device_name
        try:
            return socket.gethostname() or "电脑"
        except OSError:
            return "电脑"

    @property
    def kind(self) -> str:
        return "phone" if self.core.android else "pc"

    def apply(self) -> None:
        """按设置打开 / 关闭 / 换同步码后重新开始。"""
        st = self.core.settings
        want = bool(st.get("lan_sync")) and bool(st.get("sync_code"))
        if want and self.running and st["sync_code"] == self.code:
            return
        self.stop()
        if want:
            self.start(st["sync_code"])

    def start(self, code: str) -> None:
        self.gen += 1
        gen = self.gen
        self.code = code
        self.key = hashlib.pbkdf2_hmac("sha256", code.encode(), b"xmcs-lan-sync", 20000)
        self.group = hmac.new(self.key, b"group", hashlib.sha256).hexdigest()[:16]
        self.error = ""
        self.peers = {}
        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", 0), self._handler())
            self.httpd.daemon_threads = True
            self.port = self.httpd.server_address[1]
        except OSError as e:
            self.error = f"开不了同步用的端口：{e}"
            return
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.udp.bind(("", PORT))
        except OSError:  # 端口被占用（比如同一台电脑开了两个）：只能收到对方的单独回复
            self.udp.bind(("", 0))
        self.udp.settimeout(1.0)
        self.running = True
        threading.Thread(target=self.httpd.serve_forever, name="shici-sync-http", daemon=True).start()
        threading.Thread(target=self._recv_loop, args=(gen, self.udp), name="shici-sync-recv", daemon=True).start()
        threading.Thread(target=self._beacon_loop, args=(gen, self.udp), name="shici-sync-beacon", daemon=True).start()

    def stop(self) -> None:
        self.gen += 1
        self.running = False
        if self.httpd:
            httpd, self.httpd = self.httpd, None
            threading.Thread(target=lambda: (httpd.shutdown(), httpd.server_close()), daemon=True).start()
        if self.udp:
            try:
                self.udp.close()
            except OSError:
                pass
            self.udp = None

    # ------------------------------------------------------------ 进度指纹
    def fingerprint(self) -> str:
        """进度变没变：几条汇总数字的哈希。数据库没改动时直接用上次算的。"""
        db = self.core.db
        with self.core.lock:
            tc = db.total_changes
            if self._fp[0] == tc:
                return self._fp[1]
            q = lambda sql: tuple(db.execute(sql).fetchone())  # noqa: E731
            parts = (q("SELECT COUNT(*), TOTAL(ts), TOTAL(rating) FROM logs"),
                     q("SELECT COUNT(*), TOTAL(last_review), TOTAL(due), TOTAL(reps) FROM cards"),
                     q("SELECT COUNT(*), TOTAL(LENGTH(note) + LENGTH(examples) + IFNULL(LENGTH(definition), 0) + "
                       "IFNULL(LENGTH(reading), 0) + suspended * 7 + prio * 3) FROM items"),
                     q("SELECT COUNT(*), TOTAL(ts), TOTAL(val) FROM sync_events"),
                     q("SELECT COUNT(*) FROM item_sources"))
            v = hashlib.sha1(repr(parts).encode()).hexdigest()[:12]
            if self._fp[1] and v != self._fp[1]:
                self._fp_changed = time.time()
            self._fp = (tc, v)
            return v

    # ------------------------------------------------------------ 发现
    def _local_ips(self) -> list[str]:
        at, ips = self._ips
        if time.time() - at < 30:
            return ips
        found = set()
        try:
            found.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass
        try:  # 不会真的发包，只是让系统选出默认网卡的地址
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            found.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
        ips = sorted(ip for ip in found if not ip.startswith(("127.", "169.254.", "0.")))
        self._ips = (time.time(), ips)
        return ips

    def _beacon(self, reply: bool = False) -> bytes:
        msg = {"m": MAGIC, "g": self.group, "id": self.id, "n": self.name, "k": self.kind, "p": self.port,
               "fp": self.fingerprint()}
        if reply:
            msg["r"] = 1
        return json.dumps(msg, ensure_ascii=False).encode("utf-8")

    def _beacon_loop(self, gen: int, sock: socket.socket) -> None:
        while gen == self.gen:
            try:
                data = self._beacon()
                targets = {"255.255.255.255"} | {ip.rsplit(".", 1)[0] + ".255" for ip in self._local_ips()}
                for t in targets:
                    try:
                        sock.sendto(data, (t, PORT))
                    except OSError:
                        pass
                for pid in list(self.peers):
                    self._consider(pid)
            except Exception:  # 网络变化之类：下一轮再试
                pass
            time.sleep(BEACON_EVERY)

    def _recv_loop(self, gen: int, sock: socket.socket) -> None:
        while gen == self.gen:
            try:
                data, addr = sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                if gen != self.gen:
                    return
                time.sleep(1)
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
                if msg.get("m") != MAGIC or msg.get("g") != self.group or msg.get("id") == self.id:
                    continue
                pid = str(msg["id"])[:32]
                now = time.time()
                with self.plock:
                    p = self.peers.setdefault(pid, {"id": pid, "rec": None, "need_since": 0.0, "last_try": 0.0,
                                                    "last_ok": 0.0, "error": "", "replied": 0.0, "fp_at": now})
                    if p.get("fp") != msg.get("fp"):
                        p["fp_at"] = now
                    p.update(name=str(msg.get("n") or "设备")[:40], kind=msg.get("k") or "pc", ip=addr[0],
                             port=int(msg["p"]), fp=str(msg.get("fp") or ""), seen=now)
                    reply = not msg.get("r") and now - p["replied"] > 1.0
                    if reply:
                        p["replied"] = now
                if reply:  # 单独回一条：对方收不到广播时，靠这条也能找到我们
                    sock.sendto(self._beacon(reply=True), addr)
                self._consider(pid)
            except Exception:
                continue

    # ------------------------------------------------------------ 什么时候同步
    def _consider(self, pid: str) -> None:
        p = self.peers.get(pid)
        if not p or not self.running or time.time() - p.get("seen", 0) > ONLINE_FOR:
            return
        now = time.time()
        mine = self.fingerprint()
        if p["rec"] == (mine, p["fp"]):
            p["need_since"] = 0.0
            return
        if not p["need_since"]:
            p["need_since"] = now
        if now - self._fp_changed < SETTLE or now - p["fp_at"] < SETTLE:
            return  # 有一边正在背，进度一直在变：等停下来几秒再同步，免得每背一个词就传一次
        if self.syncing or now - p["last_try"] < (20 if p["error"] else 4):
            return
        if self.id > pid and now - p["need_since"] < 8:
            return  # 两边同时发现不一样时让 id 小的先发起；它连不上我们（比如被防火墙挡住）时再由我们发起
        self.syncing = pid
        threading.Thread(target=self._sync_with, args=(pid,), name="shici-sync-push", daemon=True).start()

    # ------------------------------------------------------------ 同步本身
    def _sig(self, *parts) -> str:
        raw = b"\n".join(x if isinstance(x, bytes) else str(x).encode("utf-8") for x in parts)
        return hmac.new(self.key, raw, hashlib.sha256).hexdigest()

    def _pack(self) -> tuple[bytes, str]:
        with self.core.lock:
            payload = self.core._progress_payload()
            fp = self.fingerprint()
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return lzma.compress(raw, preset=1), fp

    def _merge(self, body: bytes, who: str) -> None:
        d = self.core._unpack(body, "对方发来的进度不完整")
        with self.core.lock:
            try:
                if not self.backed_up:
                    self._backup()
                    self.backed_up = True
                res = self.core._merge_progress(d)
            except Exception:
                self.core.db.rollback()
                raise
        changes = res["added"] + res["updated"] + res["logs_added"]
        if changes:
            self.merged = {"at": time.time(), "from": who, "changes": changes}

    def _backup(self) -> None:
        """第一次同步前备份一次（每天一份，只留最近 7 天的）。"""
        import sqlite3
        out = self.core.dir / "backups"
        out.mkdir(exist_ok=True)
        path = out / f"sync-{datetime.fromtimestamp(self.core.clock()):%Y%m%d}.db"
        if not path.exists():
            dst = sqlite3.connect(path)
            self.core.db.backup(dst)
            dst.close()
        for old in sorted(out.glob("sync-*.db"))[:-7]:
            try:
                old.unlink()
            except OSError:
                pass

    def _headers(self, body: bytes, nonce: str) -> dict:
        return {"X-Xm-Group": self.group, "X-Xm-Id": self.id, "X-Xm-Name": quote(self.name), "X-Xm-Kind": self.kind,
                "X-Xm-Port": str(self.port), "X-Xm-Nonce": nonce,
                "X-Xm-Sig": self._sig("req", nonce, self.id, hashlib.sha256(body).hexdigest()),
                "Content-Type": "application/octet-stream"}

    def _post(self, p: dict, path: str, body: bytes, timeout: float) -> tuple[bytes, dict]:
        nonce = secrets.token_hex(12)
        conn = http.client.HTTPConnection(p["ip"], p["port"], timeout=timeout)  # 直连，不走系统代理
        try:
            conn.request("POST", path, body, self._headers(body, nonce))
            r = conn.getresponse()
            data = r.read(MAX_BODY + 1)
            if r.status != 200:
                raise ConnectionError(f"对方拒绝了（{r.status}），两边的同步码可能不一样")
            fp = r.getheader("X-Xm-Fp") or ""
            if not hmac.compare_digest(r.getheader("X-Xm-Sig") or "", self._sig("resp", nonce, fp, hashlib.sha256(data).hexdigest())):
                raise ConnectionError("对方的回复对不上同步码")
            return data, {"fp": fp}
        finally:
            conn.close()

    def _sync_with(self, pid: str) -> None:
        p = self.peers.get(pid)
        try:
            if not p:
                return
            body, _ = self._pack()
            data, info = self._post(p, "/xmcs-sync", body, timeout=max(8.0, len(body) / 200_000))
            self._merge(data, p.get("name", ""))
            mine = self.fingerprint()
            p.update(rec=(mine, info["fp"]), last_ok=time.time(), error="", need_since=0.0)
            try:  # 告诉对方我们合并完的指纹，它就不用再反过来同步一次
                self._post(p, "/xmcs-ack", json.dumps({"fp": mine}).encode(), timeout=4)
            except Exception:
                pass
        except (OSError, ConnectionError, http.client.HTTPException) as e:
            if p is not None:
                p["error"] = str(e) if isinstance(e, ConnectionError) else "连不上（可能被防火墙挡住了）"
        except Exception as e:
            if p is not None:
                p["error"] = f"同步出错：{e}"
        finally:
            if p is not None:
                p["last_try"] = time.time()
            self.syncing = None

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _reply(self, code: int, body: bytes = b"", headers: dict | None = None):
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                h = self.headers
                n = int(h.get("Content-Length") or 0)
                if self.path not in ("/xmcs-sync", "/xmcs-ack") or h.get("X-Xm-Group") != outer.group or not 0 < n <= MAX_BODY:
                    return self._reply(403)
                body = self.rfile.read(n)
                nonce, pid = h.get("X-Xm-Nonce") or "", (h.get("X-Xm-Id") or "")[:32]
                if not nonce or not hmac.compare_digest(h.get("X-Xm-Sig") or "", outer._sig("req", nonce, pid, hashlib.sha256(body).hexdigest())):
                    return self._reply(403)
                now = time.time()
                with outer.plock:
                    p = outer.peers.setdefault(pid, {"id": pid, "rec": None, "need_since": 0.0, "last_try": 0.0, "last_ok": 0.0,
                                                     "error": "", "replied": 0.0, "fp_at": 0.0, "fp": "", "seen": now})
                    p.update(name=unquote(h.get("X-Xm-Name") or "设备")[:40], kind=h.get("X-Xm-Kind") or "pc",
                             ip=self.client_address[0], port=int(h.get("X-Xm-Port") or 0) or p.get("port", 0), seen=now)
                if self.path == "/xmcs-ack":
                    try:
                        fp = str(json.loads(body)["fp"])
                    except Exception:
                        return self._reply(400)
                    if p.get("served"):
                        p.update(rec=(p["served"], fp), fp=fp, fp_at=0.0)
                    out, fp_mine = b"ok", ""
                else:
                    try:
                        outer._merge(body, p["name"])
                        out, fp_mine = outer._pack()
                    except Exception:
                        return self._reply(400)
                    p.update(served=fp_mine, last_ok=now, error="", need_since=0.0)
                self._reply(200, out, {"X-Xm-Fp": fp_mine, "X-Xm-Sig": outer._sig("resp", nonce, fp_mine, hashlib.sha256(out).hexdigest())})

        return Handler

    # ------------------------------------------------------------ 给界面看
    def status(self) -> dict:
        now = time.time()
        peers = []
        for p in list(self.peers.values()):
            online = now - p.get("seen", 0) < ONLINE_FOR
            if not online and not p.get("last_ok"):
                continue
            peers.append({"name": p.get("name", "设备"), "kind": p.get("kind", "pc"), "online": online,
                          "last_ok": int(p.get("last_ok") or 0), "syncing": self.syncing == p["id"],
                          "error": p.get("error", "") if online else "",
                          "pending": online and bool(p.get("need_since"))})
        peers.sort(key=lambda x: (not x["online"], -x["last_ok"]))
        return {"running": self.running, "name": self.name, "error": self.error, "peers": peers,
                "merged_at": int(self.merged["at"]), "merged_from": self.merged["from"], "merged_changes": self.merged["changes"],
                "now": int(now)}
