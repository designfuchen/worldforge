"""HTTP 服务：静态 web/、/media（支持 Range + 304 零拷贝缓存）、/api/local/*、/api/remote/* 代理。"""

import http.client
import json
import mimetypes
import os
import re
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config
from .tasks import TaskError
from .tunnel import RemoteUnreachable

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("video/mp4", ".mp4")

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
               "trailers", "transfer-encoding", "upgrade", "server", "date", "content-length"}
FWD_REQ_HEADERS = ("content-type", "range", "if-range", "accept", "if-none-match",
                   "if-modified-since", "last-event-id", "cache-control")
CHUNK = 256 * 1024

PLACEHOLDER = """<!doctype html><meta charset="utf-8"><title>WorldForge</title>
<body style="font:16px -apple-system;background:#0b0d12;color:#e6e6e6;padding:48px">
<h1>WorldForge 世界工坊</h1><p>本地服务已启动，但未找到 <code>web/index.html</code>。</p>
<p>API 状态：<a style="color:#8ab4ff" href="/api/local/state">/api/local/state</a></p></body>"""


def _etag_matches(header_val, etag):
    if not header_val or not etag:
        return False
    raw = header_val.strip()
    if raw == "*":
        return True
    clean_etag = etag.strip().removeprefix("W/")
    for part in raw.split(","):
        cand = part.strip().removeprefix("W/")
        if cand == clean_etag:
            return True
    return False


class HTTPError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "WorldForge"
    disable_nagle_algorithm = True
    app = None   # 由 make_server 注入

    # ------------------------------------------------------------ 基础
    def log_message(self, fmt, *args):
        pass

    def log_request(self, code="-", size="-"):
        try:
            code_i = int(code)
        except (TypeError, ValueError):
            code_i = 0
        path = self.path.split("?", 1)[0]
        if self.command not in ("GET", "HEAD") or code_i >= 400:
            sys.stderr.write("%s %s %s %s\n" % (time.strftime("%H:%M:%S"), self.command, path, code))

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return b""
        chunks, left = [], n
        while left > 0:
            c = self.rfile.read(min(left, 1 << 20))
            if not c:
                break
            chunks.append(c)
            left -= len(c)
        return b"".join(chunks)

    def _json_body(self):
        raw = self._body
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise HTTPError(400, "请求体不是合法 JSON")

    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_json_bytes(data, status=status)

    def send_json_bytes(self, data, status=200, etag=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_error_json(self, status, detail, **extra):
        d = {"detail": detail}
        d.update(extra)
        self.send_json(d, status)

    # ------------------------------------------------------------ 分发
    def do_GET(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_PATCH(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def do_OPTIONS(self):
        self._dispatch()

    def _dispatch(self):
        try:
            self._body = self._read_body()
        except (OSError, ValueError):
            self.close_connection = True
            return
        u = urllib.parse.urlsplit(self.path)
        path, self.query = urllib.parse.unquote(u.path), u.query
        self.qs = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        try:
            if path.startswith("/api/remote/") or path == "/api/remote":
                if self.command not in ("GET", "HEAD"):
                    self.app.touch()
                return self._proxy(u.path[len("/api/remote"):])
            if path.startswith("/api/local/"):
                if self.command in ("POST", "PATCH", "PUT", "DELETE"):
                    self.app.touch()
                return self._local(path[len("/api/local/"):].strip("/"))
            if path.startswith("/api/"):
                raise HTTPError(404, "not found")
            if path.startswith("/media/"):
                return self._media(path[len("/media/"):])
            if path.startswith("/drafts/"):
                return self._drafts(path[len("/drafts/"):])
            return self._static(path)
        except HTTPError as e:
            self.send_error_json(e.status, e.detail)
        except (TaskError, ValueError) as e:
            self.send_error_json(400, str(e))
        except LookupError as e:
            self.send_error_json(404, str(e).strip("'\"") or "not found")
        except RemoteUnreachable:
            self.send_error_json(502, "remote unreachable")
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            try:
                self.send_error_json(500, "%s: %s" % (type(e).__name__, e))
            except OSError:
                self.close_connection = True

    # ------------------------------------------------------------ 静态文件与媒体流
    def _static(self, path):
        if self.command not in ("GET", "HEAD"):
            raise HTTPError(405, "method not allowed")
        web = config.WEB_DIR.resolve()
        rel = path.lstrip("/") or "index.html"
        target = (web / rel).resolve()
        if target.is_dir():
            target = target / "index.html"
        if web not in target.parents and target != web:
            raise HTTPError(403, "forbidden")
        if not target.is_file():
            if rel == "index.html":
                data = PLACEHOLDER.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
                return
            raise HTTPError(404, "not found")
        self._send_file(target, cache="no-cache")

    def _media(self, rel):
        if self.command not in ("GET", "HEAD"):
            raise HTTPError(405, "method not allowed")
        root = Path(self.app.settings.get("output_dir")).resolve()
        target = (root / rel).resolve()
        if root not in target.parents:
            raise HTTPError(403, "forbidden")
        if not target.is_file():
            raise HTTPError(404, "not found")
        # .thumbs/* 与 drafts/* 启用 24h 强缓存 + ETag 304 零字节协商
        if rel.startswith(".thumbs/") or rel.startswith("drafts/"):
            cache = "public, max-age=86400"
        else:
            cache = "public, max-age=86400"
        self._send_file(target, cache=cache)

    def _drafts(self, rel):
        if self.command not in ("GET", "HEAD"):
            raise HTTPError(405, "method not allowed")
        root = config.DRAFTS_DIR.resolve()
        target = (root / rel).resolve()
        if root not in target.parents:
            raise HTTPError(403, "forbidden")
        if not target.is_file():
            raise HTTPError(404, "not found")
        self._send_file(target, cache="public, max-age=86400")

    def _send_file(self, target, cache="no-cache"):
        st = target.stat()
        size = st.st_size
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/json", "text/javascript"):
            ctype += "; charset=utf-8"
        etag = '"%x-%x"' % (int(st.st_mtime_ns // 1_000_000), size)
        last_mod = self.date_time_string(st.st_mtime)

        inm = self.headers.get("If-None-Match")
        if _etag_matches(inm, etag):
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", last_mod)
            self.send_header("Cache-Control", cache)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        rng = self.headers.get("Range")
        if not rng and not inm:
            ims = self.headers.get("If-Modified-Since")
            if ims and ims.strip() == last_mod:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Last-Modified", last_mod)
                self.send_header("Cache-Control", cache)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

        start, end = 0, size - 1
        status = 200
        if rng and size > 0:
            if_range = (self.headers.get("If-Range") or "").strip()
            honor_range = not if_range or _etag_matches(if_range, etag) or if_range == last_mod
            if honor_range:
                m = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*(?:,.*)?", rng)
                if m and (m.group(1) or m.group(2)):
                    if m.group(1):
                        start = int(m.group(1))
                        end = int(m.group(2)) if m.group(2) else size - 1
                    else:
                        start = max(0, size - int(m.group(2)))
                    end = min(end, size - 1)
                    if start > end or start >= size:
                        self.send_response(416)
                        self.send_header("Content-Range", "bytes */%d" % size)
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    status = 206

        length = end - start + 1 if size else 0
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", last_mod)
        self.send_header("Cache-Control", cache)
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if self.command == "HEAD" or length == 0:
            return
        with open(target, "rb") as f:
            if start:
                f.seek(start)
            left = length
            while left > 0:
                buf = f.read(min(CHUNK, left))
                if not buf:
                    break
                self.wfile.write(buf)
                left -= len(buf)

    # ------------------------------------------------------------ 代理
    def _proxy(self, rest):
        target = "/api" + (rest or "/")
        if self.query:
            target += "?" + self.query
        headers = {}
        for k in FWD_REQ_HEADERS:
            v = self.headers.get(k)
            if v:
                headers[k] = v
        if self._body or self.command in ("POST", "PUT", "PATCH"):
            headers["Content-Length"] = str(len(self._body))
        try:
            conn = self.app.tunnel.connection(timeout=300)
            conn.request(self.command, target, body=self._body or None, headers=headers)
            resp = conn.getresponse()
        except (RemoteUnreachable, OSError, http.client.HTTPException):
            raise RemoteUnreachable()
        try:
            self.send_response(resp.status)
            clen = resp.getheader("Content-Length")
            for k, v in resp.getheaders():
                if k.lower() not in HOP_HEADERS:
                    self.send_header(k, v)
            no_body = self.command == "HEAD" or resp.status in (204, 304) or 100 <= resp.status < 200
            if no_body:
                self.send_header("Content-Length", clen or "0")
                self.end_headers()
                return
            if clen is not None:
                self.send_header("Content-Length", clen)
                self.end_headers()
                left = int(clen)
                while left > 0:
                    buf = resp.read(min(CHUNK, left))
                    if not buf:
                        self.close_connection = True
                        break
                    self.wfile.write(buf)
                    left -= len(buf)
            else:
                # 未知长度（chunked / SSE）：以 chunked 编码逐块转发
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                while True:
                    buf = resp.read1(CHUNK) if hasattr(resp, "read1") else resp.read(CHUNK)
                    if not buf:
                        break
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(buf), buf))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
        except (OSError, http.client.HTTPException):
            self.close_connection = True
        finally:
            conn.close()

    # ------------------------------------------------------------ 本地 API
    def _local(self, route):
        app, m = self.app, self.command
        parts = route.split("/")

        if m == "GET" and route == "state":
            return self.send_json(app.state())
        if m == "POST" and route == "settings":
            return self.send_json(app.update_settings(self._json_body()))
        if m == "POST" and route == "refresh":
            app.colab.kick()
            return self.send_json({"ok": True})

        if m == "POST" and route == "session/start":
            b = self._json_body()
            t = app.session_start(b.get("name") or b.get("session"), b.get("gpu"), bool(b.get("connect")))
            return self.send_json({"task_id": t.id})
        if m == "POST" and route == "session/stop":
            b = self._json_body()
            t = app.session_stop(b.get("name") or b.get("session"))
            return self.send_json({"task_id": t.id})
        if m == "POST" and route == "connect":
            b = self._json_body()
            t = app.connect(b.get("name") or b.get("session"), b.get("gpu"))
            return self.send_json({"task_id": t.id})
        if m == "POST" and route == "disconnect":
            app.disconnect()
            return self.send_json({"ok": True})

        if m == "GET" and route == "tasks":
            return self.send_json(app.tasks.list())
        if parts[0] == "tasks" and len(parts) >= 2:
            t = app.tasks.get(parts[1])
            if not t:
                raise HTTPError(404, "task not found")
            if m == "GET" and len(parts) == 2:
                return self.send_json(t.to_dict())
            if m == "GET" and len(parts) == 3 and parts[2] == "log":
                try:
                    off = int(self.qs.get("offset") or 0)
                except ValueError:
                    raise HTTPError(400, "offset 必须是整数")
                return self.send_json(t.read_log(off))

        if m == "POST" and route == "fetch":
            b = self._json_body()
            t = app.fetch(b.get("remote_path"), b.get("kind"), b.get("meta") or {})
            return self.send_json({"task_id": t.id})

        if m == "GET" and route == "gallery":
            raw_bytes, etag = app.gallery.list_bytes()
            return self.send_json_bytes(raw_bytes, etag=etag)
        if m == "GET" and route == "gallery/stats":
            return self.send_json_bytes(app.gallery.stats_bytes())
        if m in ("POST", "GET") and route == "gallery/backfill_strips":
            b = self._json_body() if m == "POST" else {}
            force = bool(b.get("force") or self.qs.get("force"))
            return self.send_json(app.gallery.backfill_strips(force=force))
        if m == "GET" and route == "drafts":
            return self.send_json([i for i in app.gallery.list() if (i.get("meta") or {}).get("builtin_draft")])
        if parts[0] == "gallery" and len(parts) == 2 and parts[1] not in ("stats", "backfill_strips"):
            gid = parts[1]
            if m == "GET":
                it = app.gallery.get(gid)
                if not it:
                    raise HTTPError(404, "gallery item not found")
                return self.send_json(it)
            if m in ("PATCH", "POST", "PUT"):
                it = app.gallery.update(gid, self._json_body())
                if not it:
                    raise HTTPError(404, "gallery item not found")
                return self.send_json(it)
            if m == "DELETE":
                if not app.gallery.delete(gid):
                    raise HTTPError(404, "gallery item not found")
                return self.send_json({"ok": True})

        if m == "POST" and route == "reveal":
            b = self._json_body()
            return self.send_json(app.reveal(b.get("path"), b.get("gallery_id")))

        if m == "POST" and route == "upload":
            fname = self.qs.get("filename") or "upload.png"
            if not self._body:
                raise HTTPError(400, "请求体为空")
            try:
                return self.send_json(app.upload(fname, self._body))
            except RemoteUnreachable:
                raise
            except RuntimeError as e:
                raise HTTPError(502, str(e))
        if m == "POST" and route == "to_remote":
            b = self._json_body()
            if not b.get("gallery_id"):
                raise HTTPError(400, "缺少 gallery_id")
            try:
                return self.send_json(app.to_remote(b["gallery_id"]))
            except RuntimeError as e:
                raise HTTPError(502, str(e))

        if m == "POST" and route == "post":
            t = app.post(self._json_body())
            return self.send_json({"task_id": t.id})

        raise HTTPError(404 if m in ("GET", "POST", "PATCH", "PUT", "DELETE") else 405, "not found: /api/local/" + route)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def make_server(app, host=config.HOST, port=config.PORT):
    Handler.app = app
    return Server((host, port), Handler)
