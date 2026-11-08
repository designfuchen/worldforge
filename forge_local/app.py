"""业务编排：连接/会话任务、自动下载、空闲看门狗、上传、后期。"""

import os
import subprocess
import threading
import time
from pathlib import Path

from . import VERSION, config
from .colab import Colab
from .gallery import Gallery, kind_of, safe_name, unique_path
from .postproc import normalize_params, run_post
from .tasks import TaskError, TaskRegistry
from .tunnel import RemoteUnreachable, Tunnel

KILL_REMOTE = ("for p in $(pgrep -f '^python3 forge_server.py'); do "
               "kill -TERM -- -$p 2>/dev/null; kill -TERM $p 2>/dev/null; done; "
               "sleep 3; pkill -9 -f '^python3 forge_server.py' 2>/dev/null; true")
START_REMOTE = ("mkdir -p /content/forge && cd {app} && "
                "(setsid nohup python3 forge_server.py > {log} 2>&1 < /dev/null &) ; "
                "sleep 1; echo started").format(app=config.REMOTE_APP_DIR, log=config.REMOTE_LOG)


class App:
    JOBS_POLL = 5
    MAX_PARALLEL_FETCH = 3

    def __init__(self):
        self.settings = config.Settings()
        try:
            Path(self.settings.get("output_dir")).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.colab = Colab(self.settings)
        self.tunnel = Tunnel(self.colab)
        self.tasks = TaskRegistry()
        self.gallery = Gallery(self.settings)
        self.lock = threading.Lock()
        self.last_activity = time.time()
        self.notices = []
        self.remote_jobs = []
        self.remote_jobs_at = None
        self.fetching = {}          # key -> task_id
        self.fetch_fails = {}       # key -> count
        self.auto_stop_task = None
        self._autotunnel_done = False
        self.auto_tunnel = True     # 启动时若会话存在则自动建隧道

    # ------------------------------------------------------------ 生命周期
    def start(self):
        self.colab.on_refresh(self._on_colab_refresh)
        self.colab.start()
        self.tunnel.start_threads()
        threading.Thread(target=self._jobs_loop, name="jobs-poll", daemon=True).start()
        threading.Thread(target=self._idle_loop, name="idle-watchdog", daemon=True).start()

    def shutdown(self):
        try:
            self.tunnel.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.gallery.pool.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass

    def _on_colab_refresh(self, snap):
        # 启动后首次拿到会话列表：若配置的会话存在，自动建立隧道（不部署、不新建会话）
        if self._autotunnel_done or not snap.get("cli_ok") or not self.auto_tunnel:
            return
        self._autotunnel_done = True
        name = self.settings.get("session_name")
        if any(s["name"] == name for s in snap.get("sessions", [])) and not self.tunnel.desired:
            self.notice("info", "检测到会话 %s，已自动建立隧道" % name)
            self.tunnel.start(name)

    def touch(self):
        self.last_activity = time.time()

    def notice(self, level, text):
        with self.lock:
            self.notices.append({"time": time.time(), "level": level, "text": text})
            del self.notices[:-20]

    # ------------------------------------------------------------ 状态
    def idle_info(self):
        idle = max(0, time.time() - self.last_activity)
        mins = self.settings.get("idle_minutes")
        exists = self.colab.cached_session(self.settings.get("session_name")) is not None
        will = None
        if mins and exists:
            will = max(0, int(mins * 60 - idle))
        return {"seconds": int(idle), "will_stop_in": will, "enabled": bool(mins)}

    def state(self):
        tunnel, remote = self.tunnel.snapshot()
        with self.lock:
            notices = list(self.notices)
        return {
            "colab": self.colab.snapshot(),
            "tunnel": tunnel,
            "remote": remote,
            "settings": self.settings.snapshot(),
            "idle": self.idle_info(),
            "notices": notices,
            "local": {
                "version": VERSION,
                "remote_code_version": config.remote_version(),
                "tasks_running": len(self.tasks.running()),
                "ffmpeg": bool(config.ffmpeg_bin()),
                "rife": config.RIFE_BIN.exists(),
            },
        }

    def update_settings(self, patch):
        new = self.settings.update(patch)
        self.touch()
        return new

    # ------------------------------------------------------------ 会话
    def _existing_task(self, ttype):
        r = self.tasks.running(ttype)
        return r[0] if r else None

    def session_start(self, name=None, gpu=None, connect=False):
        name = name or self.settings.get("session_name")
        gpu = (gpu or self.settings.get("gpu")).upper()
        if gpu not in config.GPU_CHOICES:
            raise ValueError("gpu 必须是 " + "/".join(config.GPU_CHOICES))
        cur = self._existing_task("session_start")
        if cur:
            return cur
        self.touch()
        return self.tasks.create("session_start", "启动会话 %s (%s)" % (name, gpu),
                                 self._session_start, name, gpu, connect)

    def _session_start(self, task, name, gpu, connect):
        task.log("检查会话 %s 是否已存在 …" % name)
        try:
            st = self.colab.status(name)
        except RuntimeError as e:
            raise TaskError("colab CLI 调用失败：%s" % e)
        if st:
            task.log("会话已存在：%s（%s，%s）" % (st["host"], st.get("hardware"), st.get("status")))
        else:
            task.set_progress(0.1)
            task.log("申请 %s GPU 运行时（通常需要 30–120 秒）…" % gpu)
            rc, out = self.colab.stream(["new", "-s", name, "--gpu", gpu], task, timeout=900)
            if rc != 0:
                raise TaskError("colab new 失败 (rc=%d)" % rc)
            st = self.colab.status(name)
            if not st:
                raise TaskError("创建后仍查不到会话 %s：%s" % (name, out[-300:]))
            task.log("✓ 会话已就绪：%s" % st["host"])
        self.colab.kick()
        self.touch()
        task.set_progress(0.5 if connect else 1.0)
        if connect:
            self._connect(task, name, base=0.5)
        return {"session": st}

    def session_stop(self, name=None, reason=None):
        name = name or self.settings.get("session_name")
        cur = self._existing_task("session_stop")
        if cur:
            return cur
        return self.tasks.create("session_stop", reason or "释放会话 %s" % name, self._session_stop, name)

    def _session_stop(self, task, name):
        if self.tunnel.session == name:
            task.log("关闭隧道 …")
            self.tunnel.stop()
        task.set_progress(0.2)
        rc, out = self.colab.stream(["stop", "-s", name], task, timeout=300)
        self.colab.kick()
        if rc != 0:
            raise TaskError("colab stop 失败 (rc=%d)" % rc)
        task.log("✓ 会话 %s 已释放" % name)
        return {"session": name}

    # ------------------------------------------------------------ 连接/部署
    def connect(self, name=None, gpu=None):
        if name or gpu:
            patch = {}
            if name:
                patch["session_name"] = name
            if gpu:
                patch["gpu"] = gpu
            try:
                self.settings.update(patch)
            except ValueError:
                pass
        name = name or self.settings.get("session_name")
        cur = self._existing_task("connect")
        if cur:
            return cur
        self.touch()
        return self.tasks.create("connect", "连接 %s" % name, self._connect, name)

    def disconnect(self):
        self.tunnel.stop()

    def _sync_rclone_drive_conf(self, session, task):
        """Automatically build rclone Google Drive config from ~/.config/colab-cli/token.json and push to Colab VM."""
        import json as _json
        tok_path = os.path.expanduser("~/.config/colab-cli/token.json")
        if not os.path.exists(tok_path):
            return
        try:
            raw = _json.load(open(tok_path, "r", encoding="utf-8"))
            scopes = raw.get("scopes") or []
            drive_scope = "drive" if any(s.endswith("/drive") for s in scopes) else (
                "drive.file" if any("drive.file" in s for s in scopes) else ""
            )
            if not drive_scope or not raw.get("token") or not raw.get("refresh_token"):
                return
            tok_obj = {
                "access_token": raw["token"],
                "token_type": "Bearer",
                "refresh_token": raw["refresh_token"],
            }
            if raw.get("expiry"):
                tok_obj["expiry"] = raw["expiry"]
            conf_text = "\n".join([
                "[easycolab_gdrive]",
                "type = drive",
                "client_id = %s" % raw.get("client_id", ""),
                "client_secret = %s" % raw.get("client_secret", ""),
                "scope = %s" % drive_scope,
                "token = %s" % _json.dumps(tok_obj, separators=(",", ":")),
                "",
            ])
            Colab.ssh_run(
                session,
                "mkdir -p ~/.config/rclone && cat > ~/.config/rclone/rclone.conf && chmod 600 ~/.config/rclone/rclone.conf && cp ~/.config/rclone/rclone.conf /content/.easycolab_rclone.conf",
                timeout=20,
                input_bytes=conf_text.encode("utf-8"),
            )
            task.log("   ✓ 已自动注入 30TB Google Drive 云盘金库 OAuth 凭据 (rclone + /dev/shm 内存盘 4 级加速)")
        except Exception:
            pass

    def _connect(self, task, name, base=0.0):
        def prog(p):
            task.set_progress(base + (1 - base) * p)

        local_ver = config.remote_version()
        if not (config.REMOTE_DIR / "forge_server.py").exists():
            raise TaskError("缺少远端代码：%s/forge_server.py" % config.REMOTE_DIR)
        task.log("① 检查会话 %s …" % name)
        st = self.colab.cached_session(name)
        if not st:
            last_err = None
            for _ in range(3):
                try:
                    st = self.colab.status(name)
                    last_err = None
                    break
                except RuntimeError as e:
                    last_err = e
                    time.sleep(1.5)
            if last_err and not st:
                raise TaskError("colab CLI 调用失败：%s" % last_err)
        if not st:
            raise TaskError("会话 %s 不存在，请先点击「启动会话」" % name)
        task.log("   %s | %s | %s" % (st["host"], st.get("hardware"), st.get("status")))
        prog(0.1)

        self.tunnel.deploying = True
        try:
            task.log("② 建立 SSH 隧道（主连接） 127.0.0.1:%d → VM:%d …" % (self.tunnel.local_port, config.REMOTE_PORT))
            self.tunnel.start(name)
            if not self.tunnel.wait_up(45):
                raise TaskError("隧道建立失败：%s" % (self.tunnel.error or "超时"))
            task.log("   隧道已建立（本地端口 %d）" % self.tunnel.local_port)
            prog(0.3)

            task.log("③ 上传远端代码 remote/ → %s …" % config.REMOTE_APP_DIR)
            t0 = time.time()
            rc, out, files = Colab.upload_dir(name, str(config.REMOTE_DIR), config.REMOTE_APP_DIR)
            if rc != 0:
                raise TaskError("上传失败 (rc=%d)：%s" % (rc, out[-500:]))
            task.log("   已上传 %d 个文件（%.1fs）" % (len(files), time.time() - t0))
            self._sync_rclone_drive_conf(name, task)
            prog(0.5)

            health = None
            for _ in range(3):
                health = self.tunnel.check_health()
                if health:
                    break
                time.sleep(1)
            need_start = True
            if health:
                rv = health.get("version")
                if rv == local_ver:
                    task.log("④ 远端服务已在运行（v%s，%s），无需重启" % (rv, health.get("gpu")))
                    need_start = False
                else:
                    task.log("④ 远端版本 %s ≠ 本地 %s，重启远端服务 …" % (rv, local_ver))
                    Colab.ssh_run(name, KILL_REMOTE, timeout=60)
            else:
                task.log("④ 远端服务未运行，启动中 …")
            if need_start:
                rc, out = Colab.ssh_run(name, START_REMOTE, timeout=60)
                if rc != 0:
                    raise TaskError("启动远端服务失败：%s" % out[-500:])
                task.log("   已启动，等待健康检查（最多 60 秒）…")
                deadline = time.time() + 60
                while time.time() < deadline:
                    if not self.tunnel.desired:
                        raise TaskError("隧道已被关闭")
                    health = self.tunnel.check_health(timeout=3)
                    if health:
                        break
                    prog(0.55 + 0.4 * (1 - (deadline - time.time()) / 60))
                    time.sleep(2)
                if not health:
                    rc, tail = Colab.ssh_run(name, "tail -n 40 %s" % config.REMOTE_LOG, timeout=40)
                    task.log("   远端日志尾部：\n" + tail)
                    raise TaskError("远端服务 60 秒内未就绪，请查看日志")
            self.tunnel._set_remote(status="ok", version=health.get("version"), gpu=health.get("gpu"))
            task.log("✓ 已连接：v%s · %s" % (health.get("version"), health.get("gpu")))
            self.touch()
            return {"version": health.get("version"), "gpu": health.get("gpu")}
        finally:
            self.tunnel.deploying = False

    # ------------------------------------------------------------ 下载
    def fetch(self, remote_path, kind=None, meta=None, auto=False):
        if not remote_path or not str(remote_path).startswith("/"):
            raise ValueError("remote_path 必须是远端绝对路径")
        meta = dict(meta or {})
        meta["remote_path"] = remote_path
        key = "%s|%s" % (meta.get("job_id"), remote_path)
        with self.lock:
            tid = self.fetching.get(key)
        if tid:
            t = self.tasks.get(tid)
            if t and t.status == "running":
                return t
        name = os.path.basename(remote_path)
        kind = kind or kind_of(name, "video")
        t = self.tasks.create("fetch", "下载 %s" % name, self._fetch, remote_path, kind, meta, key, auto)
        with self.lock:
            self.fetching[key] = t.id
        return t

    def _fetch(self, task, remote_path, kind, meta, key, auto):
        try:
            name = os.path.basename(remote_path)
            job_id = meta.get("job_id")
            fname = safe_name(("%s_%s" % (job_id, name)) if job_id else name)
            dest = unique_path(self.gallery.day_dir() / fname)
            task.log("下载 %s → %s" % (remote_path, dest))
            state = {"last": -1}

            def on_prog(got, total):
                if total:
                    task.set_progress(0.95 * got / total)
                    pct = int(100 * got / total) // 10
                    if pct != state["last"]:
                        state["last"] = pct
                        task.log("  %.1f / %.1f MB" % (got / 1e6, total / 1e6))
                self.touch()
            try:
                n = self.tunnel.download(remote_path, dest, on_prog)
            except RemoteUnreachable:
                raise TaskError("远端不可达（隧道未连接）")
            except RuntimeError as e:
                raise TaskError(str(e))
            task.log("已下载 %.1f MB，生成缩略图 …" % (n / 1e6))
            item = self.gallery.add(dest, kind, meta)
            if job_id is None:
                self.gallery.mark_fetched(None, remote_path)
            task.log("✓ 已加入作品库：%s" % item["id"])
            return {"gallery_id": item["id"], "path": item["path"]}
        except BaseException:
            if auto:
                with self.lock:
                    self.fetch_fails[key] = self.fetch_fails.get(key, 0) + 1
            raise
        finally:
            with self.lock:
                if self.fetching.get(key) == task.id:
                    self.fetching.pop(key, None)

    # ------------------------------------------------------------ 轮询远端任务
    def _jobs_loop(self):
        while True:
            time.sleep(self.JOBS_POLL)
            try:
                self._poll_jobs()
            except Exception:  # noqa: BLE001
                pass

    def _poll_jobs(self):
        _, remote = self.tunnel.snapshot()
        if remote["status"] != "ok":
            return
        try:
            jobs = self.tunnel.get_json("/api/jobs?limit=50", timeout=15)
        except (RemoteUnreachable, ValueError):
            return
        if not isinstance(jobs, list):
            return
        self.remote_jobs, self.remote_jobs_at = jobs, time.time()
        if any(j.get("status") in ("queued", "running") for j in jobs if isinstance(j, dict)):
            self.touch()
        if not self.settings.get("auto_fetch"):
            return
        for job in jobs:
            if not isinstance(job, dict) or job.get("status") != "done":
                continue
            for out in job.get("outputs") or []:
                path = out.get("path") if isinstance(out, dict) else None
                if not path:
                    continue
                kind = out.get("kind") or kind_of(out.get("name") or path)
                if kind not in ("image", "video"):
                    continue
                key = "%s|%s" % (job.get("id"), path)
                with self.lock:
                    busy = key in self.fetching or self.fetch_fails.get(key, 0) >= 3
                    nrun = len(self.fetching)
                if busy or self.gallery.is_fetched(job.get("id"), path):
                    continue
                if nrun >= self.MAX_PARALLEL_FETCH:
                    return
                params = job.get("params") or {}
                meta = {
                    "prompt": params.get("prompt") or params.get("caption") or params.get("scene"),
                    "scene": params.get("scene"),
                    "caption": params.get("caption"),
                    "model_id": job.get("model_id"),
                    "model": job.get("model_id"),
                    "task": job.get("task"),
                    "seed": out.get("seed", params.get("seed")),
                    "steps": params.get("steps"),
                    "width": params.get("width"),
                    "height": params.get("height"),
                    "mode": params.get("mode"),
                    "trajectory": params.get("trajectory"),
                    "params": params,
                    "job_id": job.get("id"),
                    "remote_finished": job.get("finished"),
                }
                self.fetch(path, kind, meta, auto=True)

    # ------------------------------------------------------------ 空闲看门狗
    def _idle_loop(self):
        while True:
            time.sleep(5)
            try:
                self._idle_check()
            except Exception as e:  # noqa: BLE001
                self.notice("error", "空闲看门狗异常：%s" % e)

    def _remote_busy_via_ssh(self, name):
        """隧道不通时，经 SSH 直接询问远端是否有任务在跑（防止误停正在生成的任务）。"""
        rc, out = Colab.ssh_direct(
            name, "curl -s -m 5 'http://127.0.0.1:%d/api/jobs?limit=20' || true" % config.REMOTE_PORT,
            timeout=90)
        if rc != 0:
            return True     # 连不上（例如 SSH 名额被他处占用 = 很可能有人在用）→ 保守起见不停
        return '"running"' in out or '"queued"' in out

    def _idle_check(self):
        name = self.settings.get("session_name")
        if self.colab.cached_session(name) is None:
            self.touch()            # 没有会话时不计空闲；会话出现后从零开始计时
            return
        if any(t.type in ("connect", "session_start", "session_stop", "fetch") for t in self.tasks.running()):
            self.touch()
            return
        mins = self.settings.get("idle_minutes")
        if not mins:
            return
        idle = time.time() - self.last_activity
        if idle < mins * 60:
            return
        if self.auto_stop_task and self.auto_stop_task.status == "running":
            return
        _, remote = self.tunnel.snapshot()
        if remote["status"] != "ok" and self._remote_busy_via_ssh(name):
            self.touch()
            return
        if remote["status"] == "ok":
            try:
                jobs = self.tunnel.get_json("/api/jobs?limit=20", timeout=10)
                if any(j.get("status") in ("queued", "running") for j in jobs):
                    self.touch()
                    return
            except (RemoteUnreachable, ValueError):
                pass
        msg = "空闲已超过 %d 分钟，已自动释放会话 %s 以节省算力" % (mins, name)
        self.notice("warning", msg)
        self.auto_stop_task = self.session_stop(name, reason="空闲自动释放 %s" % name)
        self.touch()

    # ------------------------------------------------------------ 上传 / 其他
    def upload(self, filename, data):
        fname = safe_name(filename, "upload.png")
        updir = Path(self.settings.get("output_dir")) / "uploads"
        updir.mkdir(parents=True, exist_ok=True)
        local = unique_path(updir / (time.strftime("%Y%m%d_%H%M%S_") + fname))
        local.write_bytes(data)
        self.touch()
        res = self.tunnel.upload_bytes(fname, data)   # 可能抛 RemoteUnreachable / RuntimeError
        return {"remote_path": res.get("path"), "local_path": str(local)}

    def to_remote(self, gallery_id):
        it = self.gallery.get(gallery_id)
        if not it:
            raise LookupError("作品不存在")
        data = Path(it["path"]).read_bytes()
        self.touch()
        res = self.tunnel.upload_bytes(safe_name(it["name"]), data)
        return {"remote_path": res.get("path")}

    def reveal(self, path=None, gallery_id=None):
        if gallery_id:
            it = self.gallery.get(gallery_id)
            if not it:
                raise LookupError("作品不存在")
            path = it["path"]
        if not path:
            raise ValueError("缺少 path")
        p = Path(os.path.expanduser(str(path)))
        if not p.exists():
            raise LookupError("文件不存在：%s" % p)
        subprocess.Popen(["open", "-R", str(p)] if p.is_file() else ["open", str(p)])
        return {"ok": True}

    def post(self, body):
        params = normalize_params(body)
        it = self.gallery.get(params["gallery_id"])
        if not it:
            raise LookupError("作品不存在")
        if it["kind"] != "video":
            raise ValueError("只能对视频做后期")
        self.touch()
        return self.tasks.create("post", "后期 %s" % it["name"], run_post, params, self.gallery)

