"""colab CLI 封装：usage / sessions / status 缓存（后台线程 30s 刷新），new / stop，SSH 命令构造。"""

import io
import os
import re
import shlex
import subprocess
import tarfile
import threading
import time

from . import config

LINE_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s+(?P<host>\S+)\s*\|(?P<rest>.*)$")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(s):
    return ANSI_RE.sub("", s or "")


def parse_session_lines(text):
    """解析 `[name] host | Hardware: G4 | Shape: ... | Status: IDLE` 形式的行。"""
    out = []
    for raw in strip_ansi(text).splitlines():
        m = LINE_RE.match(raw.strip())
        if not m:
            continue
        info = {"name": m.group("name"), "host": m.group("host"),
                "hardware": None, "status": None}
        for part in m.group("rest").split("|"):
            if ":" in part:
                k, v = part.split(":", 1)
                k = k.strip().lower()
                v = v.strip()
                if k in ("hardware", "shape", "variant", "status"):
                    info[k] = v
        out.append(info)
    return out


def run(args, timeout=60, input_bytes=None):
    """运行命令，返回 (rc, 合并后的 stdout+stderr 文本)。"""
    try:
        p = subprocess.run(args, input=input_bytes, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout,
                           stdin=None if input_bytes is not None else subprocess.DEVNULL)
        return p.returncode, strip_ansi(p.stdout.decode("utf-8", "replace"))
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if e.stdout else ""
        return 124, strip_ansi(out) + "\n[超时 %ss]" % timeout
    except OSError as e:
        return 127, str(e)


class Colab:
    REFRESH = 30

    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.Lock()
        self.state = {"cli_ok": None, "balance": None, "rate": None,
                      "sessions": [], "updated": None, "error": None}
        self._kick = threading.Event()
        self._first = threading.Event()
        self._listeners = []

    # ---------- 缓存刷新 ----------
    def start(self):
        threading.Thread(target=self._loop, name="colab-refresh", daemon=True).start()

    def on_refresh(self, fn):
        self._listeners.append(fn)

    def kick(self):
        """请求立即刷新（不阻塞）。"""
        self._kick.set()

    def wait_first(self, timeout=None):
        return self._first.wait(timeout)

    def snapshot(self):
        with self.lock:
            d = dict(self.state)
            d["sessions"] = [dict(s) for s in self.state["sessions"]]
            return d

    def cached_session(self, name):
        with self.lock:
            for s in self.state["sessions"]:
                if s["name"] == name:
                    return dict(s)
        return None

    def _loop(self):
        while True:
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001
                with self.lock:
                    self.state["error"] = "刷新失败: %s" % e
            self._first.set()
            for fn in list(self._listeners):
                try:
                    fn(self.snapshot())
                except Exception:  # noqa: BLE001
                    pass
            self._kick.wait(self.REFRESH)
            self._kick.clear()

    def refresh(self):
        colab = config.colab_bin()
        if not os.path.exists(colab):
            with self.lock:
                self.state.update(cli_ok=False, error="未找到 colab CLI（google-colab-cli）",
                                  updated=time.time())
            return
        rc, out = run([colab, "usage"], timeout=40)
        balance = rate = None
        m = re.search(r"balance:\s*([\d.,]+)", out, re.I)
        if m:
            balance = float(m.group(1).replace(",", ""))
        m = re.search(r"rate:\s*([\d.,]+)", out, re.I)
        if m:
            rate = float(m.group(1).replace(",", ""))
        cli_ok = rc == 0 and balance is not None
        error = None if cli_ok else ("colab usage 失败: " + out.strip()[-400:])

        sessions = None
        rc2, out2 = run([colab, "sessions"], timeout=40)
        if rc2 == 0:
            sessions = parse_session_lines(out2)
        elif cli_ok:
            error = "colab sessions 失败: " + out2.strip()[-400:]
        if sessions is None:
            sessions = parse_session_lines(out)  # usage 中也可能带会话行
        # 状态（IDLE/BUSY）需要 status 命令，逐个查询
        for s in sessions:
            st = self.status(s["name"])
            if st and st.get("status"):
                s["status"] = st["status"]
        with self.lock:
            self.state.update(cli_ok=cli_ok, balance=balance, rate=rate,
                              sessions=sessions if (rc2 == 0 or sessions) else self.state["sessions"],
                              updated=time.time(), error=error)

    # ---------- 直接调用（阻塞，仅在后台线程/任务中使用） ----------
    def status(self, name):
        """返回 session dict，不存在返回 None；CLI 失败抛 RuntimeError。"""
        rc, out = run([config.colab_bin(), "status", "-s", name], timeout=40)
        for s in parse_session_lines(out):
            if s["name"] == name:
                return s
        if "not found" in out.lower():
            return None
        if rc != 0:
            raise RuntimeError(out.strip()[-400:] or "colab status 失败")
        return None

    def session_exists_fresh(self, name):
        """实时确认会话存在（用于隧道重启前，避免 proxy-mode 自动新建会话）。"""
        rc, out = run([config.colab_bin(), "sessions"], timeout=40)
        if rc != 0:
            return None  # 未知
        return any(s["name"] == name for s in parse_session_lines(out))

    def stream(self, args, task, timeout=900):
        """运行 colab 子命令并把输出逐行写入任务日志，返回 (rc, 全部输出)。"""
        cmd = [config.colab_bin()] + list(args)
        task.log("$ colab " + " ".join(shlex.quote(a) for a in args))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL)
        timer = threading.Timer(timeout, p.kill)
        timer.start()
        buf = []
        try:
            for raw in iter(p.stdout.readline, b""):
                line = strip_ansi(raw.decode("utf-8", "replace")).rstrip()
                if line:
                    buf.append(line)
                    task.log("  " + line)
            p.wait()
        finally:
            timer.cancel()
        return p.returncode, "\n".join(buf)

    # ---------- SSH ----------
    # Colab 每个运行时同一时刻只允许一个 `colab ssh` 连接，因此隧道进程作为 OpenSSH
    # ControlMaster（-M -S ctl），其余所有命令都经 -S ctl 复用这一条连接。
    @staticmethod
    def ctl_path(session):
        return str(config.SUPPORT_DIR / ("ctl-%s.sock" % session))

    @staticmethod
    def host(session):
        return "root@colab-" + session

    @staticmethod
    def ssh_opts(session):
        proxy = "%s ssh --proxy-mode -s %s" % (shlex.quote(config.colab_bin()), shlex.quote(session))
        return [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=40",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=4",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ProxyCommand=" + proxy,
        ]

    @classmethod
    def master_cmd(cls, session, local_port, remote_port):
        """隧道 + 主连接（前台运行，由 Tunnel 监控）。"""
        return (["ssh", "-M", "-S", cls.ctl_path(session), "-o", "ControlPersist=no"]
                + cls.ssh_opts(session)
                + ["-N", "-L", "%d:127.0.0.1:%d" % (local_port, remote_port), cls.host(session)])

    @classmethod
    def mux_cmd(cls, session, remote_cmd):
        """经主连接执行命令（不会新建 colab ssh 连接）。"""
        return ["ssh", "-S", cls.ctl_path(session), "-o", "ControlMaster=no",
                "-o", "BatchMode=yes", "-o", "LogLevel=ERROR",
                cls.host(session), remote_cmd]

    @classmethod
    def ssh_run(cls, session, remote_cmd, timeout=120, input_bytes=None):
        """经隧道主连接执行远端命令；主连接不存在时直接返回错误（绝不另开连接）。"""
        if not os.path.exists(cls.ctl_path(session)):
            return 255, "SSH 主连接未建立（请先连接）"
        return run(cls.mux_cmd(session, remote_cmd), timeout=timeout, input_bytes=input_bytes)

    @classmethod
    def ssh_direct(cls, session, remote_cmd, timeout=90):
        """一次性独立连接（仅在隧道关闭时使用；若他处占用 SSH 名额会失败）。"""
        return run(["ssh"] + cls.ssh_opts(session) + [cls.host(session), remote_cmd], timeout=timeout)

    @classmethod
    def upload_dir(cls, session, local_dir, remote_dir, timeout=300):
        """把 local_dir 递归打包（tar 流）经 SSH 解包到 remote_dir，等价于 scp -r，但只需一次连接。
        返回 (rc, 输出, 文件列表)。"""
        buf = io.BytesIO()
        files = []
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for root, dirs, names in os.walk(local_dir):
                dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git") and not d.startswith(".")]
                for n in sorted(names):
                    if n.startswith(".") or n.endswith((".pyc", ".pyo")):
                        continue
                    full = os.path.join(root, n)
                    rel = os.path.relpath(full, local_dir)
                    tar.add(full, arcname=rel, recursive=False)
                    files.append(rel)
        q = shlex.quote(remote_dir)
        cmd = "mkdir -p %s && tar -xzf - -C %s --no-same-owner && echo __UPLOAD_OK__" % (q, q)
        rc, out = cls.ssh_run(session, cmd, timeout=timeout, input_bytes=buf.getvalue())
        if rc == 0 and "__UPLOAD_OK__" not in out:
            rc = 1
        return rc, out.replace("__UPLOAD_OK__", "").strip(), files
