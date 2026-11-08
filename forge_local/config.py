"""路径、外部程序定位、设置持久化。"""

import json
import os
import re
import shutil
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
REMOTE_DIR = ROOT / "remote"
DRAFTS_DIR = ROOT / "drafts"

HOST = "127.0.0.1"
PORT = int(os.environ.get("WORLDFORGE_PORT", "7788"))
REMOTE_PORT = 7860          # 远端 forge_server.py 监听端口
TUNNEL_PORT = 17860         # 本地隧道端口（被占用时依次 +1）
REMOTE_APP_DIR = "/content/forge/app"
REMOTE_LOG = "/content/forge/server.log"

SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "WorldForge"
SETTINGS_FILE = SUPPORT_DIR / "settings.json"

RIFE_RELEASE = "rife-ncnn-vulkan-20221029-macos"
RIFE_URL = ("https://github.com/nihui/rife-ncnn-vulkan/releases/download/"
            "20221029/rife-ncnn-vulkan-20221029-macos.zip")
AITOOLS_DIR = Path.home() / ".local" / "share" / "aitools"
RIFE_DIR = AITOOLS_DIR / RIFE_RELEASE
RIFE_BIN = RIFE_DIR / "rife-ncnn-vulkan"
RIFE_MODEL = "rife-v4.6"


def find_bin(name, *fallbacks):
    p = shutil.which(name)
    if p:
        return p
    for f in fallbacks:
        f = os.path.expanduser(f)
        if os.path.isfile(f) and os.access(f, os.X_OK):
            return f
    return None


def colab_bin():
    return find_bin("colab", "~/.local/bin/colab") or os.path.expanduser("~/.local/bin/colab")


def ffmpeg_bin():
    return find_bin("ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")


def ffprobe_bin():
    return find_bin("ffprobe", "/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe")


def remote_version():
    """读取 remote/forge_server.py 中的 VERSION = "..."。"""
    try:
        text = (REMOTE_DIR / "forge_server.py").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return m.group(1) if m else None


DEFAULT_SETTINGS = {
    "session_name": "lyra",
    "gpu": "G4",
    "idle_minutes": 30,
    "output_dir": str(Path.home() / "Movies" / "WorldForge"),
    "auto_fetch": True,
}

GPU_CHOICES = ("T4", "L4", "G4", "H100", "A100")


class Settings:
    def __init__(self, path=SETTINGS_FILE):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.data = dict(DEFAULT_SETTINGS)
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for k in DEFAULT_SETTINGS:
                    if k in loaded:
                        self.data[k] = loaded[k]
        except (OSError, ValueError):
            pass
        try:
            self.data = self._validate(self.data)
        except ValueError:
            self.data = dict(DEFAULT_SETTINGS)
        self._save()

    def get(self, key):
        with self.lock:
            return self.data[key]

    def snapshot(self):
        with self.lock:
            return dict(self.data)

    @property
    def output_dir(self):
        return Path(self.get("output_dir"))

    @staticmethod
    def _validate(d):
        out = dict(d)
        name = str(out.get("session_name") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name):
            raise ValueError("session_name 只能包含字母、数字、- 和 _")
        out["session_name"] = name
        gpu = str(out.get("gpu") or "G4").strip().upper()
        if gpu not in GPU_CHOICES:
            raise ValueError("gpu 必须是 " + "/".join(GPU_CHOICES))
        out["gpu"] = gpu
        try:
            idle = int(float(out.get("idle_minutes", 30)))
        except (TypeError, ValueError):
            raise ValueError("idle_minutes 必须是数字")
        out["idle_minutes"] = max(0, min(idle, 24 * 60))
        od = str(out.get("output_dir") or "").strip()
        if not od:
            raise ValueError("output_dir 不能为空")
        out["output_dir"] = str(Path(os.path.expanduser(od)).resolve())
        out["auto_fetch"] = bool(out.get("auto_fetch", True))
        return out

    def update(self, patch):
        if not isinstance(patch, dict):
            raise ValueError("body 必须是 JSON 对象")
        with self.lock:
            merged = dict(self.data)
            for k, v in patch.items():
                if k in DEFAULT_SETTINGS:
                    merged[k] = v
            merged = self._validate(merged)
            Path(merged["output_dir"]).mkdir(parents=True, exist_ok=True)
            self.data = merged
        self._save()
        return self.snapshot()

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass
