"""SSH 隧道管理（ssh -N -L）+ 远端健康检查 + 远端 HTTP 客户端。"""

import http.client
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse

from . import config
from .colab import Colab


def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def probe_existing_forge_tunnel(port, timeout=1.5):
    """检查指定本地端口是否已经有存活的 WorldForge 远端隧道转发。"""
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        conn.request("GET", "/api/health")
        r = conn.getresponse()
        body = r.read()
        conn.close()
        if r.status == 200:
            data = json.loads(body.decode("utf-8", "replace"))
            if isinstance(data, dict) and data.get("ok"):
                return data
    except Exception:  # noqa: BLE001
        pass
    return None


class RemoteUnreachable(Exception):
    pass


class Tunnel:
    HEALTH_EVERY = 5

    def __init__(self, colab):
        self.colab = colab
        self.lock = threading.RLock()
        self.proc = None
        self.desired = False
        self.session = None
        self.local_port = config.TUNNEL_PORT
        self.status = "down"            # down | connecting | up | error
        self.since = None
        self.error = None
        self.started_at = None
        self.fail_count = 0
        self.next_retry = 0
        self.remote = {"status": "unreachable", "version": None, "gpu": None, "checked": None}
        self.deploying = False
        self.errf = None
        self._adopted = False
        self._wake = threading.Event()
        self._health_listeners = []
        # 启动即探测本机是否已有存活隧道，做到 0ms 冷启动即连
        if not port_free(config.TUNNEL_PORT):
            h = probe_existing_forge_tunnel(config.TUNNEL_PORT, timeout=0.6)
            if h:
                self.desired = True
                self.session = "lyra"
                self.local_port = config.TUNNEL_PORT
                self._adopted = True
                self.status = "up"
                self.since = time.time()
                self.remote = {"status": "ok", "version": h.get("version"), "gpu": h.get("gpu"), "checked": time.time()}

    # ---------- 公共 API ----------
    def start_threads(self):
        threading.Thread(target=self._monitor, name="tunnel-monitor", daemon=True).start()
        threading.Thread(target=self._health_loop, name="remote-health", daemon=True).start()

    def on_health(self, fn):
        self._health_listeners.append(fn)

    def start(self, session):
        """启动（或切换到）指定会话的隧道。调用方须确认会话存在。"""
        with self.lock:
            if self.desired and self.session == session and self._alive():
                return
            self._kill()
            self.desired = True
            self.session = session
            self.fail_count = 0
            self.next_retry = 0
            self.error = None
            self._spawn()
        self._wake.set()

    def stop(self):
        with self.lock:
            self.desired = False
            self._kill()
            self._set_status("down")
            self.error = None
        self._set_remote(status="unreachable")

    def snapshot(self):
        with self.lock:
            t = {"status": self.status, "local_port": self.local_port,
                 "session": self.session, "since": self.since}
            if self.error:
                t["error"] = self.error
            r = dict(self.remote)
            if self.deploying and r["status"] != "ok":
                r["status"] = "deploying"
            return t, r

    def wait_up(self, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                if self.status == "up":
                    return True
                if self.status == "error" and not self.desired:
                    return False
                if self.proc is None and not self.desired:
                    return False
            time.sleep(0.3)
        return False

    # ---------- 进程管理 ----------
    def _alive(self):
        if getattr(self, "_adopted", False):
            return True
        return self.proc is not None and self.proc.poll() is None

    def _set_status(self, st):
        if st != self.status:
            self.status = st
            self.since = time.time()

    def _kill(self):
        self._adopted = False
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(3)
            except Exception:  # noqa: BLE001
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass

    def _spawn(self):
        # 优先复用本机已存活的 WorldForge SSH 隧道（避免重复开启 colab ssh 触发 HTTP 429）
        for cand in range(config.TUNNEL_PORT, config.TUNNEL_PORT + 5):
            if not port_free(cand):
                h = probe_existing_forge_tunnel(cand)
                if h:
                    self.local_port = cand
                    self._adopted = True
                    self.proc = None
                    self.error = None
                    self.fail_count = 0
                    self._set_status("up")
                    self._set_remote(status="ok", version=h.get("version"), gpu=h.get("gpu"))
                    return

        self._adopted = False
        port = config.TUNNEL_PORT
        for cand in range(config.TUNNEL_PORT, config.TUNNEL_PORT + 20):
            if port_free(cand):
                port = cand
                break
        self.local_port = port
        ctl = Colab.ctl_path(self.session)
        try:
            config.SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
            if os.path.exists(ctl):
                os.unlink(ctl)      # 残留的控制套接字会让 ssh 放弃成为 master
        except OSError:
            pass
        args = Colab.master_cmd(self.session, port, config.REMOTE_PORT)
        try:
            self.errf = tempfile.TemporaryFile()
            self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=self.errf,
                                         start_new_session=True)
        except OSError as e:
            self.proc = None
            self.error = "无法启动 ssh: %s" % e
            self._set_status("error")
            return
        self.started_at = time.time()
        self._set_status("connecting")

    def _monitor(self):
        while True:
            self._wake.wait(1.0)
            self._wake.clear()
            restart_session = None
            with self.lock:
                if not self.desired:
                    continue
                if self._alive():
                    if self.status != "up" and os.path.exists(Colab.ctl_path(self.session)):
                        # 主连接认证完成后才会创建控制套接字；ExitOnForwardFailure 保证转发已建立
                        self._set_status("up")
                        self.error = None
                        self.fail_count = 0
                    continue
                # 进程已退出
                if self.proc is not None:
                    err = b""
                    try:
                        self.errf.seek(0)
                        err = self.errf.read()[-2000:]
                        self.errf.close()
                    except Exception:  # noqa: BLE001
                        pass
                    msg = err.decode("utf-8", "replace").strip()[-300:]
                    self.error = "隧道断开" + ("：" + msg if msg else "")
                    self.proc = None
                    self.fail_count += 1
                    self.next_retry = time.time() + min(30, 2 ** min(self.fail_count, 5))
                    self._set_status("connecting" if self.fail_count < 8 else "error")
                    self._set_remote(status="unreachable")
                if time.time() >= self.next_retry:
                    restart_session = self.session
            if restart_session:
                # 重启前实时确认会话仍在：colab ssh --proxy-mode 会在会话缺失时自动新建会话
                exists = self.colab.session_exists_fresh(restart_session)
                with self.lock:
                    if not self.desired or self.session != restart_session or self._alive():
                        continue
                    if exists is False:
                        self.desired = False
                        self.error = "会话 %s 已不存在，隧道已停止" % restart_session
                        self._set_status("error")
                        continue
                    if exists is None:
                        self.next_retry = time.time() + 10
                        continue
                    self._spawn()

    # ---------- 健康检查 ----------
    def _set_remote(self, **kw):
        with self.lock:
            self.remote.update(kw)
            self.remote["checked"] = time.time()
            if kw.get("status") != "ok":
                self.remote["version"] = kw.get("version")
                self.remote["gpu"] = kw.get("gpu")

    def check_health(self, timeout=4):
        """返回健康 JSON 或 None。"""
        with self.lock:
            if not self._alive():
                return None
            port = self.local_port
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
            conn.request("GET", "/api/health")
            r = conn.getresponse()
            body = r.read()
            conn.close()
            if r.status != 200:
                return None
            data = json.loads(body.decode("utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, ValueError, http.client.HTTPException):
            return None

    def _health_loop(self):
        while True:
            h = self.check_health()
            if h:
                self._set_remote(status="ok", version=h.get("version"), gpu=h.get("gpu"))
                with self.lock:
                    if self._alive():
                        self._set_status("up")
            else:
                with self.lock:
                    if getattr(self, "_adopted", False):
                        self._adopted = False
                self._set_remote(status="unreachable")
            for fn in list(self._health_listeners):
                try:
                    fn(bool(h))
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(self.HEALTH_EVERY)

    # ---------- 远端 HTTP ----------
    def connection(self, timeout=60):
        with self.lock:
            if not self._alive():
                raise RemoteUnreachable("tunnel down")
            port = self.local_port
        return http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)

    def request(self, method, path, body=None, headers=None, timeout=60):
        """简单请求：返回 (status, headers_dict, body_bytes)。path 形如 /api/jobs。"""
        try:
            conn = self.connection(timeout)
            conn.request(method, path, body=body, headers=headers or {})
            r = conn.getresponse()
            data = r.read()
            hdrs = {k.lower(): v for k, v in r.getheaders()}
            conn.close()
            return r.status, hdrs, data
        except (OSError, http.client.HTTPException) as e:
            raise RemoteUnreachable(str(e))

    def get_json(self, path, timeout=20):
        st, _, data = self.request("GET", path, timeout=timeout)
        if st != 200:
            raise RemoteUnreachable("HTTP %d: %s" % (st, data[:200].decode("utf-8", "replace")))
        return json.loads(data.decode("utf-8"))

    def upload_bytes(self, filename, data, timeout=300):
        q = urllib.parse.urlencode({"filename": filename})
        st, _, body = self.request("POST", "/api/upload?" + q, body=data,
                                   headers={"Content-Type": "application/octet-stream",
                                            "Content-Length": str(len(data))},
                                   timeout=timeout)
        try:
            obj = json.loads(body.decode("utf-8"))
        except ValueError:
            obj = {"detail": body[:300].decode("utf-8", "replace")}
        if st != 200:
            raise RuntimeError("远端上传失败 HTTP %d: %s" % (st, obj.get("detail")))
        return obj

    def download(self, remote_path, dest, on_progress=None, timeout=120):
        """流式下载远端 /api/files 到本地 dest（Path），返回字节数。"""
        q = urllib.parse.urlencode({"path": remote_path})
        try:
            conn = self.connection(timeout)
            conn.request("GET", "/api/files?" + q)
            r = conn.getresponse()
        except (OSError, http.client.HTTPException) as e:
            raise RemoteUnreachable(str(e))
        if r.status != 200:
            detail = r.read()[:300].decode("utf-8", "replace")
            conn.close()
            raise RuntimeError("远端返回 HTTP %d: %s" % (r.status, detail))
        total = int(r.getheader("Content-Length") or 0)
        got = 0
        tmp = dest.with_name(dest.name + ".part")
        last = 0
        try:
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if on_progress and time.time() - last > 0.5:
                        last = time.time()
                        on_progress(got, total)
            if total and got != total:
                raise RuntimeError("下载不完整：%d / %d 字节" % (got, total))
            tmp.replace(dest)
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        finally:
            conn.close()
        if on_progress:
            on_progress(got, total or got)
        return got
