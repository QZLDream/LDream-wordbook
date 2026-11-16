"""本机 HTTP 服务：给界面提供静态文件和 /api/<方法> 接口。

只监听 127.0.0.1，并且每次启动生成一个随机口令，界面每次请求都要带上，
所以同一台电脑上的其他网页调不了这些接口。
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import ApiError, Core
from .paths import resource_dir

MIME = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".html": "text/html",
        ".svg": "image/svg+xml", ".woff2": "font/woff2", ".json": "application/json", ".png": "image/png",
        ".ico": "image/x-icon"}


class Server:
    def __init__(self, core: Core, port: int = 0, web_dir: Path | None = None):
        self.core = core
        self.web = (web_dir or resource_dir() / "web").resolve()
        self.token = secrets.token_urlsafe(18)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # 不往控制台刷日志
                pass

            def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, obj):
                self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").split(":")[0]
                return host in ("127.0.0.1", "localhost")

            def do_GET(self):
                if not self._host_ok():
                    return self._send(403, b"forbidden", "text/plain")
                path = self.path.split("?", 1)[0]
                if path.startswith("/userfonts/"):  # 用户导入的字体（存在数据文件夹里）
                    f = outer.core.fonts.path(path[len("/userfonts/"):])
                    if not f:
                        return self._send(404, b"not found", "text/plain")
                    ctype = {".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2"}[f.suffix]
                    return self._send(200, f.read_bytes(), ctype, "max-age=31536000")
                rel = "index.html" if path in ("/", "") else path.lstrip("/")
                target = (outer.web / rel).resolve()
                if outer.web not in target.parents and target != outer.web or not target.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctype = MIME.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype == "application/json":
                    ctype += "; charset=utf-8"
                cache = "max-age=31536000" if target.suffix == ".woff2" else "no-store"
                self._send(200, target.read_bytes(), ctype, cache)

            def do_POST(self):
                if not self._host_ok() or not self.path.startswith("/api/"):
                    return self._send(403, b"forbidden", "text/plain")
                if not secrets.compare_digest(self.headers.get("X-Shici-Token") or "", outer.token):
                    return self._json(403, {"ok": False, "error": "口令不对，请从程序窗口打开"})
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    params = json.loads(self.rfile.read(n) or b"{}") if n else {}
                    data = outer.core.call(self.path[5:].split("?")[0], params)
                    self._json(200, {"ok": True, "data": data})
                except ApiError as e:
                    self._json(200, {"ok": False, "error": str(e)})
                except Exception as e:  # 程序错误：把信息带回界面，方便反馈问题
                    traceback.print_exc()
                    self._json(200, {"ok": False, "error": f"程序出错：{type(e).__name__}: {e}"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#t={self.token}"

    def start(self) -> None:
        threading.Thread(target=self.httpd.serve_forever, name="shici-http", daemon=True).start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
