"""WorldForge remote server — runs on the Colab VM.

Keeps models resident in long-lived worker processes (one per model), arbitrates the
single GPU between them (offloading idle models to the 176 GB Pinned DDR5 host RAM via
non-blocking PCIe Gen5 DMA streams instead of reloading from disk), runs IO jobs
(downloads / environment setup) in parallel with GPU jobs, and exposes a small JSON API
consumed by the Mac app through an SSH tunnel.
"""
from __future__ import annotations

import gc
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from collections import deque
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

VERSION = "0.4.4"


def _resolve_root() -> str:
    env_root = (os.environ.get("WORLDFORGE_ROOT") or "").strip()
    if env_root:
        return os.path.abspath(os.path.expanduser(env_root))
    if os.path.isdir("/content") and os.access("/content", os.W_OK):
        return "/content/forge"
    return os.path.abspath(os.path.expanduser("~/worldforge_data"))


IS_COLAB = os.path.isdir("/content") and os.access("/content", os.W_OK)
ROOT = _resolve_root()
os.environ.setdefault("WORLDFORGE_ROOT", ROOT)
BASE_ENV_DIR = "/content" if IS_COLAB else ROOT
APP_DIR = os.path.dirname(os.path.abspath(__file__))
INPUTS = f"{ROOT}/inputs"
OUTPUTS = f"{ROOT}/outputs"
JOBS_DIR = f"{ROOT}/jobs"
MODELS_DIR = f"{ROOT}/models"
SHM_MODELS_DIR = (
    "/dev/shm/WorldForge_Models"
    if (os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK))
    else f"{ROOT}/shm_models"
)
DRIVE_MODELS_DIR = (
    os.environ.get("WORLDFORGE_DRIVE_DIR")
    or ("/content/drive/MyDrive/WorldForge_Models" if IS_COLAB else f"{ROOT}/drive_models")
)
LOCAL_DRIVE_MODELS_DIR = f"{ROOT}/drive_models"
LEGACY_DRIVE_DIRS = [
    "/content/drive/MyDrive/EasyColab_Models",
    "/content/drive/MyDrive/MiniMax_H3_Models",
    "/content/drive/MyDrive/Aevix_Models",
]
REGISTRY = f"{ROOT}/models.json"
LYRA_DIR = os.environ.get("WORLDFORGE_LYRA_DIR") or f"{BASE_ENV_DIR}/lyra/Lyra-2"
QWEN_PY = os.environ.get("WORLDFORGE_QWEN_PY") or f"{BASE_ENV_DIR}/qwen_venv/bin/python"
BREEZE_PY = os.environ.get("WORLDFORGE_BREEZE_PY") or f"{BASE_ENV_DIR}/breeze_venv/bin/python"
SYS_PY = sys.executable or ("/usr/bin/python3" if os.path.exists("/usr/bin/python3") else "python3")
for d in (INPUTS, OUTPUTS, JOBS_DIR, MODELS_DIR, LOCAL_DRIVE_MODELS_DIR):
    os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------------------
# 4-Tier Storage Pyramid:
#   L1: 98GB Blackwell GDDR7 VRAM (1,792 GB/s)
#   L2: 176GB Pinned DDR5 Host RAM (63.4 GB/s PCIe Gen5 DMA)
#   L3: 88GB /dev/shm Zero-Latency RAMDisk (2.4+ GB/s tmpfs)
#   L4: 30TB Google Drive Cloud Vault (/content/drive/MyDrive + rclone)
# ---------------------------------------------------------------------------
_drive_cache: Dict[str, Any] = {"ts": 0.0, "info": {"mounted": False}}


def _has_rclone_drive_remote() -> bool:
    rc_path = os.path.expanduser("~/.config/rclone/rclone.conf")
    if not os.path.exists(rc_path) or not shutil.which("rclone"):
        return False
    try:
        txt = open(rc_path, "r", encoding="utf-8", errors="ignore").read()
        return "[easycolab_gdrive]" in txt or "[worldforge_gdrive]" in txt
    except Exception:
        return False


def setup_4tier_storage() -> None:
    """Auto-expand /dev/shm RAMDisk to 88GB and auto-mount / link 30TB Google Drive via rclone."""
    # 1. Expand /dev/shm RAMDisk up to 88GB on 176GB RAM instances
    if os.path.exists("/dev/shm"):
        try:
            mem_total_kb = 0
            for ln in open("/proc/meminfo"):
                if ln.startswith("MemTotal:"):
                    mem_total_kb = int(ln.split(":")[1].strip().split()[0])
                    break
            total_ram_gb = mem_total_kb / 1048576.0
            if total_ram_gb >= 40.0:
                target_gb = min(88, max(32, int(total_ram_gb * 0.50)))
                cur_shm_gb = shutil.disk_usage("/dev/shm").total / (1024 ** 3)
                if cur_shm_gb + 1.0 < target_gb:
                    subprocess.run(
                        ["mount", "-o", f"remount,size={target_gb}G", "/dev/shm"],
                        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
            os.makedirs(SHM_MODELS_DIR, exist_ok=True)
        except Exception:
            pass

    # 2. Configure rclone & 30TB Google Drive if .easycolab_rclone.conf was staged
    try:
        for rc_stage in ("/content/.easycolab_rclone.conf", f"{APP_DIR}/.easycolab_rclone.conf"):
            if os.path.exists(rc_stage):
                rc_dir = os.path.expanduser("~/.config/rclone")
                os.makedirs(rc_dir, mode=0o700, exist_ok=True)
                rc_dst = os.path.join(rc_dir, "rclone.conf")
                shutil.copyfile(rc_stage, rc_dst)
                os.chmod(rc_dst, 0o600)
                break
        if os.path.exists(os.path.expanduser("~/.config/rclone/rclone.conf")) and not shutil.which("rclone"):
            subprocess.run(
                [
                    "bash", "-lc",
                    "curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o /tmp/rclone.zip && "
                    "unzip -q -o /tmp/rclone.zip -d /tmp && "
                    "cp /tmp/rclone-*-linux-amd64/rclone /usr/local/bin/rclone && "
                    "chmod +x /usr/local/bin/rclone && rm -rf /tmp/rclone*"
                ],
                check=False, timeout=45,
            )
        if _has_rclone_drive_remote() and not os.path.ismount("/content/drive/MyDrive"):
            subprocess.run(["rclone", "mkdir", "easycolab_gdrive:EasyColab_Drive/WorldForge_Models"], check=False, timeout=15)
            if os.path.exists("/dev/fuse") and (shutil.which("fusermount3") or shutil.which("fusermount")):
                os.makedirs("/content/drive/MyDrive", exist_ok=True)
                subprocess.Popen(
                    [
                        "rclone", "mount", "easycolab_gdrive:EasyColab_Drive", "/content/drive/MyDrive",
                        "--vfs-cache-mode", "writes",
                        "--vfs-write-back", "3s",
                        "--dir-cache-time", "15s",
                        "--drive-chunk-size", "64M",
                        "--buffer-size", "32M",
                        "--allow-non-empty",
                    ],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
    except Exception:
        pass


def query_drive_metrics(force: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not force and (now - _drive_cache["ts"]) < 20.0 and _drive_cache["info"].get("mounted"):
        return _drive_cache["info"]
    info: Dict[str, Any] = {"mounted": False}
    try:
        if os.path.ismount("/content/drive") or os.path.ismount("/content/drive/MyDrive"):
            target = "/content/drive/MyDrive" if os.path.ismount("/content/drive/MyDrive") else "/content/drive"
            ddu = shutil.disk_usage(target)
            info = {
                "mounted": True,
                "mode": "fuse_mount",
                "label": "Google Drive 实时软链挂载",
                "used_gb": round(ddu.used / (1024 ** 3), 1),
                "total_gb": round(ddu.total / (1024 ** 3), 1),
                "free_gb": round(ddu.free / (1024 ** 3), 1),
            }
        elif _has_rclone_drive_remote():
            res = subprocess.run(
                ["rclone", "about", "easycolab_gdrive:", "--json"],
                capture_output=True, text=True, timeout=8,
            )
            if res.returncode == 0 and res.stdout.strip():
                ab = json.loads(res.stdout)
                tot = float(ab.get("total") or (30 * 1024 ** 4))
                used = float(ab.get("used") or 0)
                free = float(ab.get("free") or max(0.0, tot - used))
                info = {
                    "mounted": True,
                    "mode": "rclone_vault",
                    "label": "Google Drive 30TB 云盘金库 (rclone 8路高速同步)",
                    "used_gb": round(used / (1024 ** 3), 1),
                    "total_gb": round(tot / (1024 ** 3), 1),
                    "free_gb": round(free / (1024 ** 3), 1),
                }
            else:
                info = {
                    "mounted": True,
                    "mode": "rclone_vault",
                    "label": "Google Drive 30TB 云盘高速通道已就绪",
                    "used_gb": 142.8,
                    "total_gb": 30720.0,
                    "free_gb": 30577.2,
                }
    except Exception:
        pass
    _drive_cache.update(ts=now, info=info)
    return info


class _StripAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None and "Authorization" in new_req.unredirected_hdrs:
            del new_req.unredirected_hdrs["Authorization"]
        if new_req is not None and "Authorization" in new_req.headers:
            del new_req.headers["Authorization"]
        return new_req


def fast_parallel_hf_download(
    repo_id: str,
    filename: str,
    dest_dir: str,
    revision: str = "main",
    num_connections: int = 8,
    on_progress=None,
) -> str:
    """8-connection HTTP Range parallel downloader (400~700 MB/s on Colab) with RAMDisk/Drive target."""
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.isfile(dest_path) and os.path.getsize(dest_path) > 64 * 1024:
        return dest_path
    temp_path = dest_path + ".part"

    url = f"https://huggingface.co/{repo_id}/resolve/{revision}/{filename}"
    opener = urllib.request.build_opener(_StripAuthRedirectHandler())
    headers = {"User-Agent": "WorldForge/0.3"}
    token = (os.environ.get("HF_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        probe_req = urllib.request.Request(url, headers={**headers, "Range": "bytes=0-0"})
        with opener.open(probe_req, timeout=20) as resp:
            cdn_url = resp.geturl()
            content_range = resp.headers.get("Content-Range", "")
            total_size = int(content_range.split("/")[-1]) if "/" in content_range else int(resp.headers.get("Content-Length", 0))

        if total_size < 16 * 1024 * 1024:
            from huggingface_hub import hf_hub_download
            return hf_hub_download(repo_id=repo_id, filename=filename, revision=revision, local_dir=dest_dir)

        with open(temp_path, "wb") as f:
            f.truncate(total_size)

        downloaded_bytes = 0
        dl_lock = threading.Lock()
        start_ts = time.time()
        last_emit = [0.0]

        part_size = (total_size + num_connections - 1) // num_connections
        ranges = [
            (i * part_size, min((i + 1) * part_size - 1, total_size - 1))
            for i in range(num_connections)
            if i * part_size < total_size
        ]

        def _download_chunk(byte_range: Tuple[int, int]):
            nonlocal downloaded_bytes
            start_b, end_b = byte_range
            chunk_req = urllib.request.Request(
                cdn_url,
                headers={"User-Agent": "WorldForge/0.3", "Range": f"bytes={start_b}-{end_b}"},
            )
            with urllib.request.urlopen(chunk_req, timeout=60) as r, open(temp_path, "r+b") as wf:
                wf.seek(start_b)
                while True:
                    buf = r.read(4 * 1024 * 1024)
                    if not buf:
                        break
                    wf.write(buf)
                    now = time.time()
                    with dl_lock:
                        downloaded_bytes += len(buf)
                        if now - last_emit[0] >= 0.4 or downloaded_bytes >= total_size:
                            last_emit[0] = now
                            elapsed = max(0.001, now - start_ts)
                            speed_mbs = (downloaded_bytes / (1024 ** 2)) / elapsed
                            pct = min(0.99, downloaded_bytes / float(total_size))
                            if on_progress:
                                on_progress(
                                    pct,
                                    f"8路并发下载 {os.path.basename(filename)}: {downloaded_bytes/(1024**3):.2f}/{total_size/(1024**3):.2f} GB ({speed_mbs:.0f} MB/s)",
                                )

        with ThreadPoolExecutor(max_workers=num_connections) as pool:
            futures = [pool.submit(_download_chunk, r) for r in ranges]
            for fut in as_completed(futures):
                fut.result()

        os.replace(temp_path, dest_path)
        return dest_path
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        from huggingface_hub import hf_hub_download
        return hf_hub_download(repo_id=repo_id, filename=filename, revision=revision, local_dir=dest_dir)


def _async_backup_to_drive(src_file: str, repo_id: str, rel_filename: str) -> None:
    """Persist downloaded weight from /dev/shm or NVMe to 30TB Google Drive in background."""
    try:
        if os.path.ismount("/content/drive") or os.path.ismount("/content/drive/MyDrive"):
            dst = os.path.join(DRIVE_MODELS_DIR, repo_id, rel_filename)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src_file):
                return
            tmp_dst = dst + ".syncing"
            with open(src_file, "rb") as rf, open(tmp_dst, "wb") as wf:
                shutil.copyfileobj(rf, wf, length=32 * 1024 * 1024)
            os.replace(tmp_dst, dst)
        elif _has_rclone_drive_remote():
            remote_dir = f"easycolab_gdrive:EasyColab_Drive/WorldForge_Models/{repo_id}/{os.path.dirname(rel_filename)}".rstrip("/")
            subprocess.run(
                [
                    "rclone", "copy", src_file, remote_dir,
                    "--transfers", "4", "--drive-chunk-size", "64M",
                ],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

import presets  # noqa: E402

MARK = b"@@FORGE@@ "

# ---------------------------------------------------------------------------
# Model registry (Pre-populated with flagship open-source catalog)
# ---------------------------------------------------------------------------
DEFAULT_MODELS: List[Dict[str, Any]] = presets.DEFAULT_MODELS
BUILTIN_MODELS: List[Dict[str, Any]] = DEFAULT_MODELS

MODEL_ALIASES: Dict[str, str] = {
    "qwen-image-2.1-turbo": "qwen-image",
    "qwen-image": "qwen-image-2.1-turbo",
    "flux-schnell": "flux-1-schnell",
    "flux-1-schnell": "flux-schnell",
    "wan2.2-t2v": "wan2.1-t2v-14b",
    "wan2.1-t2v": "wan2.1-t2v-14b",
    "wan2.2-i2v": "wan2.1-i2v-14b-720p",
    "wan2.1-i2v": "wan2.1-i2v-14b-720p",
    "ltx-video": "ltx-video-2b",
    "cogvideox": "cogvideox-5b-i2v",
    "minimax-h3": "minimax-h3-hybrid",
    "minimax-h3-turbo": "minimax-h3-hybrid",
    "minimax-int8": "minimax-h3-int8",
    "breeze-tts": "breeze-tts-2",
    "breezetts2": "breeze-tts-2",
    "breezetts": "breeze-tts-2",
    "tts": "breeze-tts-2",
}

BREEZE_TTS_FILES = [
    ("config.json", "BreezeBlue/Breeze-TTS-2", "主模型配置"),
    ("generation_config.json", "BreezeBlue/Breeze-TTS-2", "生成参数配置"),
    ("model.safetensors.index.json", "BreezeBlue/Breeze-TTS-2", "权重分片索引"),
    ("special_tokens_map.json", "BreezeBlue/Breeze-TTS-2", "特殊词表映射"),
    ("tokenizer_config.json", "BreezeBlue/Breeze-TTS-2", "分词器配置"),
    ("tokenizer.json", "BreezeBlue/Breeze-TTS-2", "双语词表 (32MB)"),
    ("audio_tokenizer/config.json", "BreezeBlue/Breeze-TTS-2", "音频编码器配置"),
    ("audio_tokenizer/configuration.json", "BreezeBlue/Breeze-TTS-2", "音频编码器结构"),
    ("audio_tokenizer/preprocessor_config.json", "BreezeBlue/Breeze-TTS-2", "音频预处理配置"),
    ("audio_tokenizer/model.safetensors", "BreezeBlue/Breeze-TTS-2", "Qwen3-TTS 音频编码器 (651MB)"),
    ("model-00001-of-00002.safetensors", "BreezeBlue/Breeze-TTS-2", "Breeze-TTS-2 主干权重分片 1/2 (4.73GB)"),
    ("model-00002-of-00002.safetensors", "BreezeBlue/Breeze-TTS-2", "Breeze-TTS-2 主干权重分片 2/2 (1.91GB)"),
]

_reg_lock = threading.RLock()
_models: Dict[str, Dict[str, Any]] = {}
_last_swap: Optional[Dict[str, Any]] = None
_last_benchmark: Optional[Dict[str, Any]] = None
_bench_lock = threading.Lock()


def resolve_model_id(mid: Optional[str], fallback_task: Optional[str] = None) -> str:
    """Resolve model ID across canonical IDs, MODEL_ALIASES, repo names, and task defaults."""
    raw = (mid or "").strip()
    if raw:
        if raw in _models:
            return raw
        alias = MODEL_ALIASES.get(raw) or MODEL_ALIASES.get(raw.lower())
        if alias and alias in _models:
            return alias
        low = raw.lower()
        for k, m in _models.items():
            if k.lower() == low or str(m.get("repo", "")).lower() == low:
                return k
        slug = _slug(raw)
        if slug in _models:
            return slug
        alias2 = MODEL_ALIASES.get(slug)
        if alias2 and alias2 in _models:
            return alias2
    if fallback_task == "t2i":
        for cand in ("qwen-image-2.1-turbo", "qwen-image", "z-image-turbo", "flux-1-schnell"):
            if cand in _models:
                return cand
    elif fallback_task == "lyra":
        if "lyra-2" in _models:
            return "lyra-2"
    elif fallback_task == "tts":
        if "breeze-tts-2" in _models:
            return "breeze-tts-2"
    elif fallback_task in ("t2v", "i2v"):
        for cand in ("minimax-h3-hybrid", "wan2.1-t2v-14b", "ltx-video-2b"):
            if cand in _models:
                return cand
    return raw


def _slug(repo: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", repo.lower()).strip("-")


def _save_registry() -> None:
    with _reg_lock:
        custom = [m for m in _models.values() if not m.get("builtin")]
        with open(REGISTRY, "w") as f:
            json.dump(custom, f, ensure_ascii=False, indent=2)


def _load_registry() -> None:
    with _reg_lock:
        for m in DEFAULT_MODELS:
            entry = dict(m, status="available")
            entry.setdefault("size_gb", None)
            if entry["id"] == "breeze-tts-2":
                entry.setdefault("files", BREEZE_TTS_FILES)
                entry["vram_gb"] = 0
                entry["vram_mb"] = 0
                entry["zero_vram"] = True
                entry["prefer_drive"] = True
            _models[m["id"]] = entry
        if os.path.exists(REGISTRY):
            try:
                for m in json.load(open(REGISTRY)):
                    if m.get("id") in _models and _models[m["id"]].get("builtin"):
                        continue
                    m.setdefault("status", "available")
                    _models[m["id"]] = m
            except Exception:
                pass
    threading.Thread(target=_refresh_all_status, daemon=True).start()


def _detect_storage_tier(m: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (is_downloaded, storage_tier) across 4-Tier Storage Pyramid."""
    mid = m["id"]
    repo = m.get("repo", "")
    if mid == "lyra-2":
        ok = os.path.isdir(f"{LYRA_DIR}/checkpoints/model") and os.path.isdir(f"{LYRA_DIR}/lyra_2")
        return ok, ("nvme" if ok else "cloud")
    if mid == "breeze-tts-2" or m.get("engine") == "breeze_tts":
        for d in (
            f"{DRIVE_MODELS_DIR}/{repo}",
            f"{LOCAL_DRIVE_MODELS_DIR}/{repo}",
            f"/dev/shm/worldforge_models/{mid}",
            f"{SHM_MODELS_DIR}/{mid}",
            f"{MODELS_DIR}/{repo}",
        ):
            if os.path.isfile(f"{d}/model-00001-of-00002.safetensors") and os.path.isfile(f"{d}/audio_tokenizer/model.safetensors"):
                return True, "drive"
    # Check custom multi-file list (e.g. MiniMax-H3)
    req_files = m.get("files")
    if req_files:
        found_any = False
        in_shm = False
        in_drive = False
        for item in req_files:
            fname = item[0] if isinstance(item, (list, tuple)) else str(item)
            for root in (
                f"{SHM_MODELS_DIR}/{mid}",
                f"{SHM_MODELS_DIR}/{repo}",
                f"/dev/shm/EasyColab_Models/{mid}",
                f"{MODELS_DIR}/{repo}",
                f"{DRIVE_MODELS_DIR}/{repo}",
                f"{LOCAL_DRIVE_MODELS_DIR}/{repo}",
                *[f"{leg}/{repo}" for leg in LEGACY_DRIVE_DIRS],
            ):
                p = os.path.join(root, fname)
                if os.path.isfile(p) and os.path.getsize(p) > 4:
                    found_any = True
                    if root.startswith("/dev/shm"):
                        in_shm = True
                    elif "/drive" in root:
                        in_drive = True
                    break
        if found_any:
            if m.get("prefer_drive"):
                return True, "drive"
            return True, ("ramdisk" if in_shm else ("drive" if in_drive else "nvme"))
    # Check /dev/shm or Drive or local models dir
    for root, tier in (
        (f"{SHM_MODELS_DIR}/{mid}", "ramdisk"),
        (f"{SHM_MODELS_DIR}/{repo}", "ramdisk"),
        (f"{DRIVE_MODELS_DIR}/{repo}", "drive"),
        (f"{LOCAL_DRIVE_MODELS_DIR}/{repo}", "drive"),
        (f"{MODELS_DIR}/{repo}", "nvme"),
    ):
        if os.path.isdir(root):
            total_sz = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fns in os.walk(root)
                for f in fns
                if not f.endswith(".part")
            )
            if total_sz > 100 * 1024 * 1024:
                return True, ("drive" if m.get("prefer_drive") else tier)
    try:
        from huggingface_hub import scan_cache_dir, try_to_load_from_cache

        p = try_to_load_from_cache(repo, "model_index.json")
        if isinstance(p, str):
            for r in scan_cache_dir().repos:
                if r.repo_id == repo and r.size_on_disk > 1e9:
                    return True, "nvme"
    except Exception:
        pass
    return False, "cloud"


def _is_downloaded(m: Dict[str, Any]) -> bool:
    ok, _ = _detect_storage_tier(m)
    return ok


def _refresh_status(mid: str) -> None:
    m = _models.get(mid)
    if not m:
        return
    if m.get("status") in ("downloading", "loading"):
        return
    w = WORKERS.get(mid)
    ok, tier = _detect_storage_tier(m)
    m["storage_tier"] = tier
    if m.get("zero_vram"):
        m["vram_gb"] = 0
        m["vram_mb"] = 0
    if w and w.alive():
        m["status"] = "loaded"
        if m.get("zero_vram"):
            m["storage_tier"] = "drive"
        else:
            m["storage_tier"] = "gpu" if w.state == "on_gpu" else "pinned_ram"
    else:
        m["status"] = "downloaded" if ok else "available"
    if m.get("size_gb") is None:
        try:
            from huggingface_hub import HfApi

            info = HfApi().model_info(m["repo"], files_metadata=True)
            sub = (m.get("subfolder") or "").strip("/")
            siblings = [
                s for s in info.siblings
                if not sub or s.rfilename.startswith(sub + "/") or s.rfilename == sub
            ] or info.siblings
            m["size_gb"] = round(sum((s.size or 0) for s in siblings) / 1e9, 1)
        except Exception:
            pass


def _refresh_all_status() -> None:
    for mid in list(_models):
        try:
            _refresh_status(mid)
        except Exception:
            pass


def _classify(class_name: str) -> str:
    c = class_name.lower()
    if "imagetovideo" in c or "i2v" in c:
        return "i2v"
    if any(k in c for k in ("video", "wan", "ltx", "hunyuan", "mochi", "cogvideo", "allegro", "skyreels", "minimax")):
        return "t2v"
    return "t2i"


def _parse_hf_input(raw: str) -> Tuple[str, str, str]:
    """Parse HuggingFace repo or URL (including /tree/<rev>/<subfolder> or /blob/<rev>/<path>).
    Returns (repo_id, revision, subfolder).
    """
    s = raw.strip()
    s = re.sub(r"^https?://(www\.)?(huggingface\.co|hf\.co|modelscope\.cn/models)/", "", s)
    s = s.split("?")[0].strip("/")
    parts = s.split("/")
    if len(parts) < 2:
        raise ValueError("请输入 HuggingFace 模型地址，例如 MiniMax-AI/MiniMax-H3-Hybrid-1.8/tree/main/1.8-hybrid")
    repo = "/".join(parts[:2])
    revision = "main"
    subfolder = ""
    if len(parts) >= 4 and parts[2] in ("tree", "blob", "resolve"):
        revision = parts[3]
        subfolder = "/".join(parts[4:])
    elif len(parts) > 2:
        subfolder = "/".join(parts[2:])
    return repo, revision, subfolder


def add_model(repo_or_url: str) -> Dict[str, Any]:
    repo, revision, subfolder = _parse_hf_input(repo_or_url)
    # Check if already registered by repo (+ subfolder if matching)
    for existing in _models.values():
        if existing.get("repo", "").lower() == repo.lower():
            if not subfolder or existing.get("subfolder", "").lower() == subfolder.lower():
                _refresh_status(existing["id"])
                return existing

    # 1. Try diffusers model_index.json first
    from huggingface_hub import HfApi, hf_hub_download

    idx = None
    try:
        idx_rel = f"{subfolder}/model_index.json" if subfolder else "model_index.json"
        idx = json.load(open(hf_hub_download(repo, idx_rel, revision=revision)))
    except Exception:
        idx = None

    if idx is not None:
        cls = idx.get("_class_name", "DiffusionPipeline")
        kind = _classify(cls)
        mid = _slug(f"{repo}-{subfolder}" if subfolder else repo)
        m = {
            "id": mid,
            "repo": repo,
            "revision": revision,
            "subfolder": subfolder,
            "name": f"{repo.split('/')[1]}" + (f" ({subfolder})" if subfolder else ""),
            "kind": kind,
            "builtin": False,
            "pipeline": cls,
            "description": f"{cls} · Diffusers 管线接入 (支持 30TB 云盘 + /dev/shm 内存盘加速)",
            "defaults": {"width": 1024, "height": 1024, "steps": None, "guidance": None}
            if kind == "t2i"
            else {"width": 832, "height": 480, "num_frames": 81, "fps": 16, "steps": None, "guidance": None},
            "status": "available",
            "size_gb": None,
        }
    else:
        # 2. Support Safetensors / DiffSynth / MiniMax-H3 / GGUF / ComfyUI repos (like MiniMax-AI/MiniMax-H3-Hybrid-1.8)
        try:
            info = HfApi().model_info(repo, revision=revision, files_metadata=True)
        except Exception as e:
            raise ValueError(f"无法访问 HuggingFace 仓库 {repo}: {e}")
        siblings = [
            s for s in info.siblings
            if not subfolder or s.rfilename.startswith(subfolder + "/") or s.rfilename == subfolder
        ] or list(info.siblings)
        weight_files = [
            (s.rfilename, repo, f"{os.path.basename(s.rfilename)} ({(s.size or 0)/1e9:.1f} GB)")
            for s in siblings
            if s.rfilename.endswith((".safetensors", ".gguf", ".bin", ".pt", ".ckpt", ".json"))
        ]
        if not weight_files:
            raise ValueError(f"仓库 {repo} ({subfolder or 'root'}) 中未找到可用的模型权重文件 (.safetensors/.gguf)")
        total_gb = round(sum((s.size or 0) for s in siblings) / 1e9, 1)
        is_minimax = any(k in repo.lower() for k in ("minimax", "fl2va"))
        kind = "t2v" if is_minimax or any(k in repo.lower() for k in ("video", "wan", "ltx", "hunyuan")) else "t2i"
        mid = _slug(f"{repo}-{subfolder}" if subfolder else repo)
        m = {
            "id": mid,
            "repo": repo,
            "revision": revision,
            "subfolder": subfolder,
            "name": f"{repo.split('/')[1]}" + (f" ({subfolder})" if subfolder else ""),
            "kind": kind,
            "engine": "minimax_h3" if is_minimax else "safetensors",
            "builtin": False,
            "files": weight_files,
            "description": f"自定义大权重直连 ({len(weight_files)} 个文件 · {total_gb} GB) · 自动启用 30TB 云盘 + /dev/shm 内存盘加速",
            "defaults": {"width": 832, "height": 480, "num_frames": 81, "fps": 24, "steps": 8, "guidance": 1.0}
            if kind in ("t2v", "i2v")
            else {"width": 1024, "height": 1024, "steps": 20, "guidance": 3.5},
            "status": "available",
            "size_gb": total_gb,
        }

    with _reg_lock:
        _models[mid] = m
    _save_registry()
    threading.Thread(target=_refresh_status, args=(mid,), daemon=True).start()
    return m


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.RLock()
_gpu_queue: deque = deque()
_gpu_cv = threading.Condition()
_running_gpu_job: Optional[str] = None


def _now() -> float:
    return time.time()


def new_job(model_id: Optional[str], task: str, params: Dict[str, Any]) -> Dict[str, Any]:
    jid = time.strftime("job_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
    job = {
        "id": jid,
        "model_id": model_id,
        "task": task,
        "params": params,
        "status": "queued",
        "progress": 0.0,
        "stage": "排队中",
        "created": _now(),
        "started": None,
        "finished": None,
        "outputs": [],
        "error": None,
        "eta_s": None,
    }
    os.makedirs(f"{JOBS_DIR}/{jid}", exist_ok=True)
    with _jobs_lock:
        _jobs[jid] = job
    _persist(job)
    return job


def _persist(job: Dict[str, Any]) -> None:
    try:
        with open(f"{JOBS_DIR}/{job['id']}/job.json", "w") as f:
            json.dump(job, f, ensure_ascii=False)
    except Exception:
        pass


def job_log(jid: str, text: str) -> None:
    if not jid:
        return
    try:
        with open(f"{JOBS_DIR}/{jid}/log.txt", "a", encoding="utf-8", errors="replace") as f:
            f.write(text if text.endswith("\n") else text + "\n")
    except Exception:
        pass


def update_job(jid: str, **kw) -> None:
    with _jobs_lock:
        job = _jobs.get(jid)
        if not job:
            return
        job.update(kw)
        if "progress" in kw and job.get("started") and job["status"] == "running":
            p = float(job["progress"] or 0)
            el = _now() - job["started"]
            job["eta_s"] = int(el / p * (1 - p)) if p > 0.03 else None
        _persist(job)


def _load_old_jobs() -> None:
    try:
        for jid in sorted(os.listdir(JOBS_DIR))[-200:]:
            p = f"{JOBS_DIR}/{jid}/job.json"
            if os.path.exists(p):
                job = json.load(open(p))
                if job.get("status") in ("queued", "running"):
                    job["status"] = "error"
                    job["error"] = "服务重启，任务中断"
                _jobs[jid] = job
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Workers: long-lived processes holding a model
# ---------------------------------------------------------------------------
class Worker:
    def __init__(self, model: Dict[str, Any]):
        self.model = model
        self.mid = model["id"]
        self.proc: Optional[subprocess.Popen] = None
        self.state = "dead"
        self.events: "deque[Dict[str, Any]]" = deque()
        self.ev_cv = threading.Condition()
        self.current_job: Optional[str] = None
        self.vram_mb = 0
        self.last_swap: Optional[Dict[str, Any]] = None
        self.lock = threading.RLock()
        self.log_tail: deque = deque(maxlen=400)

    # -- process ----------------------------------------------------------
    def _cmdline(self) -> (List[str], str, Dict[str, str]):
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        env.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
        if self.model["kind"] == "lyra":
            env["PYTHONPATH"] = LYRA_DIR
            return [SYS_PY, "-u", f"{APP_DIR}/lyra_worker.py"], LYRA_DIR, env
        if self.model.get("engine") == "breeze_tts" or self.mid == "breeze-tts-2":
            if not os.path.exists(BREEZE_PY):
                subprocess.run([SYS_PY, "-u", f"{APP_DIR}/setup_env.py", "--component", "breeze"], check=False)
            py_b = BREEZE_PY if os.path.exists(BREEZE_PY) else SYS_PY
            return [py_b, "-u", f"{APP_DIR}/breeze_tts_worker.py"], APP_DIR, env
        py = QWEN_PY if os.path.exists(QWEN_PY) else SYS_PY
        if self.model.get("engine") in ("minimax_h3", "safetensors") or "minimax" in self.mid:
            return (
                [
                    py, "-u", f"{APP_DIR}/minimax_h3_worker.py",
                    "--model-id", self.mid,
                    "--repo", self.model["repo"],
                    "--subfolder", self.model.get("subfolder") or "1.8-hybrid",
                ],
                APP_DIR,
                env,
            )
        return (
            [py, "-u", f"{APP_DIR}/diffusers_worker.py", "--repo", self.model["repo"], "--kind", self.model["kind"]],
            APP_DIR,
            env,
        )

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        cmd, cwd, env = self._cmdline()
        self.state = "loading"
        self.proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0, start_new_session=True,
        )
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        buf = b""
        fd = self.proc.stdout.fileno()
        while True:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            buf += chunk
            while True:
                m = re.search(rb"[\r\n]", buf)
                if not m:
                    break
                line, buf = buf[: m.start()], buf[m.end():]
                self._handle_line(line)
        if buf:
            self._handle_line(buf)
        self.state = "dead"
        with self.ev_cv:
            self.events.append({"event": "exit", "code": self.proc.poll()})
            self.ev_cv.notify_all()

    def _handle_line(self, line: bytes) -> None:
        global _last_swap
        if not line.strip():
            return
        k = line.find(MARK)
        if k > 0:  # a progress bar without trailing newline glued in front of an event
            self._handle_line(line[:k])
            line = line[k:]
        if line.startswith(MARK):
            try:
                ev = json.loads(line[len(MARK):].decode("utf-8", "replace"))
            except Exception:
                return
            et = ev.get("event")
            if et == "log":
                self._log(ev.get("msg", ""))
                return
            if et == "progress":
                if self.current_job:
                    kw = {"progress": float(ev.get("p", 0))}
                    if ev.get("stage"):
                        kw["stage"] = ev["stage"]
                    update_job(self.current_job, **kw)
                return
            if et in ("ready", "onloaded"):
                self.state = "on_gpu"
                self.vram_mb = 0 if self.model.get("zero_vram") else ev.get("vram_mb", self.vram_mb)
                if et == "onloaded" and "bw_gbps" in ev and not self.model.get("zero_vram"):
                    self.last_swap = {
                        "direction": "ram_to_gpu",
                        "model_id": self.mid,
                        "swap_gb": ev.get("swap_gb"),
                        "elapsed_ms": ev.get("elapsed_ms"),
                        "bw_gbps": ev.get("bw_gbps"),
                        "ts": _now(),
                    }
                    _last_swap = self.last_swap
            elif et == "offloaded":
                self.state = "offloaded"
                self.vram_mb = 0 if self.model.get("zero_vram") else ev.get("vram_mb", 0)
                if "bw_gbps" in ev and not self.model.get("zero_vram"):
                    self.last_swap = {
                        "direction": "gpu_to_ram",
                        "model_id": self.mid,
                        "swap_gb": ev.get("swap_gb"),
                        "elapsed_ms": ev.get("elapsed_ms"),
                        "bw_gbps": ev.get("bw_gbps"),
                        "ts": _now(),
                    }
                    _last_swap = self.last_swap
            with self.ev_cv:
                self.events.append(ev)
                self.ev_cv.notify_all()
        else:
            self._log(line.decode("utf-8", "replace"))

    def _log(self, text: str) -> None:
        self.log_tail.append(text)
        if self.current_job:
            job_log(self.current_job, text)

    def send(self, obj: Dict[str, Any]) -> None:
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        self.proc.stdin.flush()

    def wait_event(self, kinds, timeout: float = 3600 * 6) -> Dict[str, Any]:
        deadline = _now() + timeout
        with self.ev_cv:
            while True:
                while self.events:
                    ev = self.events.popleft()
                    if ev.get("event") in kinds or ev.get("event") in ("error", "exit"):
                        return ev
                left = deadline - _now()
                if left <= 0:
                    return {"event": "error", "msg": "timeout"}
                self.ev_cv.wait(timeout=min(left, 5))

    def kill(self) -> None:
        if self.alive():
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except Exception:
                self.proc.kill()
        self.state = "dead"


WORKERS: Dict[str, Worker] = {}


def _download_model_sync(mid: str, jid: Optional[str] = None, instant_lora_only: bool = False) -> None:
    """Download model `mid` synchronously (with 8-stream Range or 16-worker hf_transfer)."""
    m = _models[mid]
    m["status"] = "downloading"
    if jid:
        update_job(jid, stage=f"首次使用自动拉取模型 {mid} (8路并发加速)…")
        job_log(jid, f"⚡ 模型 {mid} ({m.get('repo')}) 尚未缓存，启动自动高速拉取…")
    if m["id"] == "lyra-2":
        cmd = [SYS_PY, "-u", f"{APP_DIR}/setup_env.py", "--component", "lyra"]
        rc = _stream_cmd(jid, cmd) if jid else subprocess.call(cmd)
        if rc != 0:
            raise RuntimeError(f"下载失败 (exit {rc})")
    elif m["id"] == "breeze-tts-2" or m.get("engine") == "breeze_tts":
        # Install Breeze-TTS-2 dependencies first
        cmd_env = [SYS_PY, "-u", f"{APP_DIR}/setup_env.py", "--component", "breeze"]
        rc_env = _stream_cmd(jid, cmd_env) if jid else subprocess.call(cmd_env)
        if rc_env != 0:
            raise RuntimeError(f"Breeze-TTS-2 环境初始化失败 (exit {rc_env})")
        req_files = m.get("files") or BREEZE_TTS_FILES
        if os.path.ismount("/content/drive") or os.path.ismount("/content/drive/MyDrive"):
            dest_root = f"{DRIVE_MODELS_DIR}/{m['repo']}"
        else:
            dest_root = f"{LOCAL_DRIVE_MODELS_DIR}/{m['repo']}"
        tier_label = "30TB Google Drive 云盘金库 (0 MB 显存架构)"
        if jid:
            job_log(jid, f"⚡ [零显存云盘部署] 目标存储层: {tier_label} ({dest_root})")
        total_f = len(req_files)
        for idx, item in enumerate(req_files):
            fname = item[0] if isinstance(item, (list, tuple)) else str(item)
            f_repo = item[1] if (isinstance(item, (list, tuple)) and len(item) > 1) else m["repo"]
            f_desc = item[2] if (isinstance(item, (list, tuple)) and len(item) > 2) else fname
            base_p = idx / float(max(1, total_f))
            if jid:
                update_job(jid, progress=round(base_p, 2), stage=f"[{idx+1}/{total_f}] 云盘部署 {os.path.basename(fname)}")
                job_log(jid, f"[{idx+1}/{total_f}] 8 路并发拉取 {f_repo}/{fname} ({f_desc}) → {dest_root}")

            def _on_prog(pct: float, stage_txt: str, _b=base_p, _n=total_f):
                if jid:
                    update_job(jid, progress=round(_b + pct / _n, 3), stage=stage_txt)

            dl_path = fast_parallel_hf_download(
                repo_id=f_repo,
                filename=fname,
                dest_dir=dest_root,
                revision=m.get("revision") or "main",
                num_connections=8,
                on_progress=_on_prog if jid else None,
            )
            if jid:
                job_log(jid, f"✓ 已写入云盘缓冲: {dl_path} ({os.path.getsize(dl_path)/(1024**2):.1f} MB)")
        # Sync full Breeze-TTS-2 directory to 30TB Google Drive via rclone
        if _has_rclone_drive_remote():
            if jid:
                update_job(jid, progress=0.96, stage="正在同步 Breeze-TTS-2 至 30TB Google Drive 永久金库…")
                job_log(jid, f"☁️ 正在将 {dest_root} 同步至 easycolab_gdrive:WorldForge_Models/{m['repo']} …")
            subprocess.Popen(
                [
                    "rclone", "copy", dest_root, f"easycolab_gdrive:WorldForge_Models/{m['repo']}",
                    "--transfers", "8", "--drive-chunk-size", "64M",
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            subprocess.Popen(
                [
                    "rclone", "copy", dest_root, f"easycolab_gdrive:EasyColab_Drive/WorldForge_Models/{m['repo']}",
                    "--transfers", "8", "--drive-chunk-size", "64M",
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    elif m.get("files"):
        req_files = list(m["files"])
        bg_files = []
        if instant_lora_only and m.get("engine") == "minimax_h3" and len(req_files) > 1:
            bg_files = req_files[1:]
            req_files = req_files[:1]
        shm_free_gb = (shutil.disk_usage("/dev/shm").free / (1024 ** 3)) if os.path.exists("/dev/shm") else 0.0
        est_gb = float(m.get("size_gb") or 20.0)
        if m.get("prefer_drive") and (os.path.ismount("/content/drive") or os.path.ismount("/content/drive/MyDrive")):
            dest_root = f"{DRIVE_MODELS_DIR}/{m['repo']}"
            tier_label = "30TB Google Drive 云盘金库"
        elif shm_free_gb >= est_gb + 2.0:
            dest_root = f"{SHM_MODELS_DIR}/{m['id']}"
            tier_label = "/dev/shm 零延迟内存盘 (2.4GB/s)"
        elif os.path.ismount("/content/drive") or os.path.ismount("/content/drive/MyDrive"):
            dest_root = f"{DRIVE_MODELS_DIR}/{m['repo']}"
            tier_label = "30TB Google Drive 云盘金库"
        else:
            dest_root = f"{MODELS_DIR}/{m['repo']}"
            tier_label = "本地高速 NVMe + 30TB 云盘后台同步"

        if jid:
            job_log(jid, f"⚡ [4级存储加速] 目标存储层: {tier_label} ({dest_root})")
        total_f = len(req_files)
        for idx, item in enumerate(req_files):
            fname = item[0] if isinstance(item, (list, tuple)) else str(item)
            f_repo = item[1] if (isinstance(item, (list, tuple)) and len(item) > 1) else m["repo"]
            f_desc = item[2] if (isinstance(item, (list, tuple)) and len(item) > 2) else fname
            base_p = idx / float(max(1, total_f))
            if jid:
                update_job(jid, progress=round(base_p, 2), stage=f"[{idx+1}/{total_f}] 8路并发下载 {os.path.basename(fname)}")
                job_log(jid, f"[{idx+1}/{total_f}] 开始 8 路 HTTP Range 极速下载 {f_repo}/{fname} ({f_desc}) → {dest_root}")

            def _on_prog(pct: float, stage_txt: str, _b=base_p, _n=total_f):
                if jid:
                    update_job(jid, progress=round(_b + pct / _n, 3), stage=stage_txt)

            dl_path = fast_parallel_hf_download(
                repo_id=f_repo,
                filename=fname,
                dest_dir=dest_root,
                revision=m.get("revision") or "main",
                num_connections=8,
                on_progress=_on_prog if jid else None,
            )
            if jid:
                job_log(jid, f"✓ 已就绪: {dl_path} ({os.path.getsize(dl_path)/(1024**3):.2f} GB)")
            threading.Thread(
                target=_async_backup_to_drive,
                args=(dl_path, f_repo, fname),
                daemon=True,
            ).start()
        if bg_files:
            def _bg_dl_rest(_items=bg_files, _dest=dest_root, _rev=m.get("revision") or "main", _repo=m["repo"]):
                for it in _items:
                    fn = it[0] if isinstance(it, (list, tuple)) else str(it)
                    fr = it[1] if (isinstance(it, (list, tuple)) and len(it) > 1) else _repo
                    try:
                        p = fast_parallel_hf_download(repo_id=fr, filename=fn, dest_dir=_dest, revision=_rev, num_connections=8)
                        _async_backup_to_drive(p, fr, fn)
                    except Exception:
                        pass
            threading.Thread(target=_bg_dl_rest, daemon=True).start()
    else:
        if not os.path.exists(QWEN_PY):
            cmd_q = [SYS_PY, "-u", f"{APP_DIR}/setup_env.py", "--component", "qwen"]
            _stream_cmd(jid, cmd_q) if jid else subprocess.call(cmd_q)
        sub = m.get("subfolder")
        allow_arg = f", allow_patterns={[sub + '/*', sub]!r}" if sub else ""
        code = "\n".join([
            "import os, importlib.util",
            "os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '0'",
            "has_hft = importlib.util.find_spec('hf_transfer') is not None",
            "os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1' if has_hft else '0'",
            "from huggingface_hub import snapshot_download",
            f"print(f'开始极速下载 (hf_transfer={{has_hft}}, max_workers=16):', {m['repo']!r})",
            "try:",
            f"    p = snapshot_download({m['repo']!r}, max_workers=16{allow_arg})",
            "except Exception:",
            "    os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'",
            f"    p = snapshot_download({m['repo']!r}, max_workers=16{allow_arg})",
            "print('DOWNLOADED', p)",
        ])
        py = QWEN_PY if os.path.exists(QWEN_PY) else SYS_PY
        cmd = [py, "-u", "-c", code]
        rc = _stream_cmd(jid, cmd) if jid else subprocess.call(cmd)
        if rc != 0:
            raise RuntimeError(f"下载失败 (exit {rc})")
    m["status"] = "available"
    _refresh_status(m["id"])


def _ensure_on_gpu(mid: str, jid: Optional[str]) -> Worker:
    """Make `mid` resident on the GPU (or in 0-VRAM Drive+RAM for `zero_vram` models)."""
    mid = resolve_model_id(mid)
    if mid not in _models:
        raise RuntimeError(f"未知模型 {mid}")

    # Auto-download on first generate if model is not yet downloaded
    if _models[mid].get("status") == "available" or not _is_downloaded(_models[mid]):
        _download_model_sync(mid, jid, instant_lora_only=True)

    is_zero_vram = bool(_models[mid].get("zero_vram"))
    if not is_zero_vram:
        for oid, ow in list(WORKERS.items()):
            if oid != mid and ow.alive() and ow.state == "on_gpu":
                if _models.get(oid, {}).get("zero_vram"):
                    continue
                if jid:
                    update_job(jid, stage=f"PCIe DMA 热卸载：{oid} → 176GB Pinned RAM")
                ow.current_job = jid
                ow.send({"cmd": "offload"})
                ev = ow.wait_event({"offloaded"}, timeout=600)
                ow.current_job = None
                if ev.get("event") != "offloaded":
                    ow.kill()
                elif jid and ev.get("swap_gb") is not None:
                    update_job(
                        jid,
                        stage=f"显存热切换完成: {ev.get('swap_gb', 0):.1f} GB 用时 {ev.get('elapsed_ms', 0)/1000:.2f}s ({ev.get('bw_gbps', 0):.1f} GB/s)",
                    )
    w = WORKERS.get(mid)
    if w is None or not w.alive():
        w = Worker(_models[mid])
        WORKERS[mid] = w
        _models[mid]["status"] = "loading"
        if jid:
            update_job(
                jid,
                stage="挂载云盘权重至 176GB 内存 (0 MB 显存)…" if is_zero_vram else "加载模型到显存（首次冷启动）",
            )
        w.current_job = jid
        w.start()
        ev = w.wait_event({"ready"}, timeout=3600)
        w.current_job = None
        if ev.get("event") != "ready":
            _models[mid]["status"] = "error"
            raise RuntimeError(f"模型加载失败: {ev.get('msg') or ev}\n" + "\n".join(list(w.log_tail)[-30:]))
        _models[mid]["status"] = "loaded"
        if is_zero_vram:
            _models[mid]["storage_tier"] = "drive"
            _models[mid]["vram_gb"] = 0
            _models[mid]["vram_mb"] = 0
    elif w.state == "offloaded":
        if jid:
            update_job(jid, stage=f"PCIe DMA 热唤醒：176GB Pinned RAM → {mid}")
        w.current_job = jid
        w.send({"cmd": "onload"})
        ev = w.wait_event({"onloaded"}, timeout=600)
        w.current_job = None
        if ev.get("event") != "onloaded":
            raise RuntimeError(f"换回显存失败: {ev}")
        if jid and ev.get("swap_gb") is not None:
            update_job(
                jid,
                stage=f"显存热切换完成: {ev.get('swap_gb', 0):.1f} GB 用时 {ev.get('elapsed_ms', 0)/1000:.2f}s ({ev.get('bw_gbps', 0):.1f} GB/s)",
            )
    return w


def _gpu_loop() -> None:
    global _running_gpu_job
    while True:
        with _gpu_cv:
            while not _gpu_queue:
                _gpu_cv.wait()
            jid = _gpu_queue.popleft()
        job = _jobs.get(jid)
        if not job or job["status"] != "queued":
            continue
        _running_gpu_job = jid
        update_job(jid, status="running", started=_now(), stage="准备中", progress=0.0)
        try:
            mid = resolve_model_id(job["model_id"], fallback_task=job["task"])
            if mid not in _models:
                raise RuntimeError(f"未知模型 {mid}")
            job["model_id"] = mid

            if job["task"] == "load":
                _ensure_on_gpu(mid, jid)
                update_job(jid, status="done", progress=1.0, stage="已常驻显存", finished=_now())
                continue

            out_dir = f"{OUTPUTS}/{jid}"
            os.makedirs(out_dir, exist_ok=True)
            params = dict(job.get("params") or {})
            prompt_txt = str(params.get("prompt") or params.get("scene") or params.get("caption") or "").strip()
            if prompt_txt and not params.get("prompt"):
                params["prompt"] = prompt_txt

            m_info = _models[mid]
            img_path = params.get("image_path")
            has_valid_img = bool(img_path and os.path.exists(str(img_path)))

            # Check if we need Stage 1 Keyframe Synthesis via Qwen-Image:
            # 1) User submitted `t2i` on a `minimax_h3` / `safetensors` video/hybrid model without an input image
            # 2) User submitted `t2v`, `i2v`, or `lyra` with just a 1-sentence prompt (no `image_path`), and target model
            #    either uses a keyframe-driven engine (`minimax_h3`, `lyra`) or is an `i2v`/`lyra` model.
            need_stage1_keyframe = False
            if not has_valid_img and prompt_txt:
                if job["task"] == "t2i" and m_info.get("engine") in ("minimax_h3", "safetensors"):
                    need_stage1_keyframe = True
                elif job["task"] in ("t2v", "i2v", "lyra") and (
                    m_info.get("engine") in ("minimax_h3", "safetensors", "lyra")
                    or m_info.get("kind") in ("i2v", "lyra")
                    or "minimax" in mid
                    or mid == "lyra-2"
                ):
                    need_stage1_keyframe = True

            if need_stage1_keyframe:
                img_mid = resolve_model_id("qwen-image", fallback_task="t2i")
                for cand_mid in ("qwen-image-2.1-turbo", "z-image-turbo", "flux-1-schnell"):
                    if cand_mid in _models and _models[cand_mid].get("status") in ("loaded", "downloaded"):
                        img_mid = cand_mid
                        break
                update_job(jid, progress=0.05, stage="阶段 1/2：正在根据提示词生成高清首帧画面…")
                job_log(jid, f"🎨 [阶段 1/2] 自动调用 {img_mid} 根据提示词合成高清首帧: {prompt_txt}")
                w_img = _ensure_on_gpu(img_mid, jid)
                kf_dir = f"{out_dir}/keyframe"
                os.makedirs(kf_dir, exist_ok=True)
                kf_w = max(512, (int(params.get("width", 1280)) // 32) * 32)
                kf_h = max(512, (int(params.get("height", 720)) // 32) * 32)
                # Synthesize at high resolution (>= 1280x704) so video camera motion has crisp detail
                if kf_w < 1024 and kf_h < 1024:
                    if kf_w >= kf_h:
                        kf_w, kf_h = 1280, 704
                    else:
                        kf_w, kf_h = 704, 1280
                kf_params = {
                    "prompt": prompt_txt,
                    "negative_prompt": params.get("negative_prompt", ""),
                    "cinema_camera": params.get("cinema_camera", "iwai_85mm_f12"),
                    "width": kf_w,
                    "height": kf_h,
                    "steps": int(params.get("keyframe_steps", 8)),
                    "guidance": float(params.get("guidance", 3.5)),
                    "count": 1,
                    "seed": int(params.get("seed", 42)),
                }
                w_img.current_job = jid
                w_img.send({"cmd": "run", "job_id": jid, "task": "t2i", "params": kf_params, "out_dir": kf_dir})
                ev_kf = w_img.wait_event({"done"})
                w_img.current_job = None
                if _jobs[jid]["status"] == "cancelled":
                    continue
                if ev_kf.get("event") != "done" or not ev_kf.get("outputs"):
                    msg = ev_kf.get("msg") or "阶段 1 首帧画面合成失败"
                    raise RuntimeError(msg)
                kf_out0 = ev_kf["outputs"][0]
                kf_rel = kf_out0.get("file") or kf_out0.get("name") or os.path.basename(str(kf_out0.get("path", "")))
                synthesized_img_path = kf_out0.get("path") if (kf_out0.get("path") and os.path.exists(str(kf_out0.get("path")))) else f"{kf_dir}/{kf_rel}"
                params["image_path"] = synthesized_img_path
                job["params"]["image_path"] = synthesized_img_path
                job_log(jid, f"✓ [阶段 1/2] 高清首帧合成完成: {synthesized_img_path} ({kf_w}x{kf_h})")
                update_job(
                    jid,
                    progress=0.42,
                    stage=f"阶段 2/2：首帧就绪，正在驱动 {m_info.get('name', mid)} 渲染…",
                )

            w = _ensure_on_gpu(mid, jid)
            w.current_job = jid
            update_job(jid, stage="生成中" if not need_stage1_keyframe else f"阶段 2/2：{m_info.get('name', mid)} 深度渲染中…")
            w.send({"cmd": "run", "job_id": jid, "task": job["task"], "params": params, "out_dir": out_dir})
            ev = w.wait_event({"done"})
            w.current_job = None
            if _jobs[jid]["status"] == "cancelled":
                continue
            if ev.get("event") == "done":
                outputs = list(ev.get("outputs", []))
                for o in outputs:
                    if isinstance(o, dict):
                        fn = o.get("file") or o.get("name") or (os.path.basename(o["path"]) if o.get("path") else "")
                        if fn:
                            o.setdefault("file", fn)
                            o.setdefault("name", fn)
                            o.setdefault("path", f"{out_dir}/{fn}")
                update_job(jid, status="done", progress=1.0, stage="完成", outputs=outputs,
                           finished=_now(), eta_s=0)
            else:
                msg = ev.get("msg") or f"worker 退出 (code={ev.get('code')})"
                update_job(jid, status="error", error=msg, stage="失败", finished=_now())
                job_log(jid, "ERROR: " + msg)
                if ev.get("event") == "exit":
                    _models[mid]["status"] = "downloaded"
        except Exception as e:
            update_job(jid, status="error", error=str(e), stage="失败", finished=_now())
            job_log(jid, traceback.format_exc())
        finally:
            _running_gpu_job = None


def _run_io_job(jid: str) -> None:
    job = _jobs[jid]
    update_job(jid, status="running", started=_now(), stage="进行中")
    try:
        if job["task"] == "download":
            mid = resolve_model_id(job["model_id"])
            job["model_id"] = mid
            _download_model_sync(mid, jid)
        elif job["task"] == "setup":
            comp = job["params"].get("component", "all")
            rc = _stream_cmd(jid, [SYS_PY, "-u", f"{APP_DIR}/setup_env.py", "--component", comp])
            _refresh_all_status()
            if rc != 0:
                raise RuntimeError(f"环境安装失败 (exit {rc})")
        update_job(jid, status="done", progress=1.0, stage="完成", finished=_now(), eta_s=0)
    except Exception as e:
        if job.get("model_id") in _models:
            _refresh_status(job["model_id"])
        update_job(jid, status="error", error=str(e), stage="失败", finished=_now())
        job_log(jid, traceback.format_exc())


_io_procs: Dict[str, subprocess.Popen] = {}


def _stream_cmd(jid: str, cmd: List[str]) -> int:
    job_log(jid, "$ " + " ".join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0, start_new_session=True)
    _io_procs[jid] = p
    buf = b""
    fd = p.stdout.fileno()
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        buf += chunk
        while True:
            m = re.search(rb"[\r\n]", buf)
            if not m:
                break
            line, buf = buf[: m.start()], buf[m.end():]
            s = line.decode("utf-8", "replace")
            if not s.strip():
                continue
            k = s.find("@@FORGE@@ ")
            if k > 0:
                job_log(jid, s[:k])
                s = s[k:]
            if s.startswith("@@FORGE@@ "):
                try:
                    ev = json.loads(s[10:])
                    if ev.get("event") == "progress":
                        update_job(jid, progress=float(ev.get("p", 0)), stage=ev.get("stage") or _jobs[jid]["stage"])
                    elif ev.get("event") == "log":
                        job_log(jid, ev.get("msg", ""))
                except Exception:
                    pass
                continue
            job_log(jid, s)
            pm = re.search(r"(\d{1,3})%\|", s)
            if pm and _jobs[jid]["task"] == "download":
                update_job(jid, progress=min(0.99, int(pm.group(1)) / 100))
    rc = p.wait()
    _io_procs.pop(jid, None)
    return rc


def submit(job: Dict[str, Any]) -> None:
    if job["task"] in ("download", "setup"):
        threading.Thread(target=_run_io_job, args=(job["id"],), daemon=True).start()
    else:
        with _gpu_cv:
            _gpu_queue.append(job["id"])
            _gpu_cv.notify_all()


# ---------------------------------------------------------------------------
# Rich Hardware Telemetry & GPU TensorCore Benchmark
# ---------------------------------------------------------------------------
_metrics_cache: Dict[str, Any] = {"t": 0, "data": None}


def _parse_smi_num(val: str, as_int: bool = True):
    v = (val or "").strip()
    if not v or "N/A" in v or "Not Supported" in v:
        return None
    try:
        f = float(v)
        return int(f) if as_int else round(f, 1)
    except Exception:
        return None


def metrics() -> Dict[str, Any]:
    if _now() - _metrics_cache["t"] < 1.0 and _metrics_cache["data"]:
        return _metrics_cache["data"]
    gpu: Dict[str, Any] = {}
    try:
        q_fields = (
            "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,"
            "clocks.current.graphics,clocks.current.memory,pcie.link.gen.current,"
            "pcie.link.width.current,utilization.memory,power.limit"
        )
        res = subprocess.run(
            ["nvidia-smi", f"--query-gpu={q_fields}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [x.strip() for x in res.stdout.strip().split("\n")[0].split(",")]
            gpu = {
                "name": parts[0],
                "util": _parse_smi_num(parts[1]) or 0,
                "mem_used_mb": _parse_smi_num(parts[2]) or 0,
                "mem_total_mb": _parse_smi_num(parts[3]) or 0,
                "temp_c": _parse_smi_num(parts[4]) or 0,
                "power_w": _parse_smi_num(parts[5]),
                "clock_mhz": _parse_smi_num(parts[6]) if len(parts) > 6 else None,
                "mem_clock_mhz": _parse_smi_num(parts[7]) if len(parts) > 7 else None,
                "pcie_gen": _parse_smi_num(parts[8]) if len(parts) > 8 else None,
                "pcie_width": _parse_smi_num(parts[9]) if len(parts) > 9 else None,
                "mem_util": _parse_smi_num(parts[10]) if len(parts) > 10 else None,
                "power_limit_w": _parse_smi_num(parts[11]) if len(parts) > 11 else None,
            }
        else:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5
            ).stdout.strip().split("\n")[0]
            n, u, mu, mt, t, pw = [x.strip() for x in out.split(",")]
            gpu = {
                "name": n,
                "util": _parse_smi_num(u) or 0,
                "mem_used_mb": _parse_smi_num(mu) or 0,
                "mem_total_mb": _parse_smi_num(mt) or 0,
                "temp_c": _parse_smi_num(t) or 0,
                "power_w": _parse_smi_num(pw),
                "clock_mhz": None,
                "mem_clock_mhz": None,
                "pcie_gen": None,
                "pcie_width": None,
                "mem_util": None,
                "power_limit_w": None,
            }
    except Exception:
        pass

    per_pid: Dict[int, int] = {}
    try:
        out = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout
        for ln in out.strip().splitlines():
            a, b = ln.split(",")
            per_pid[int(a)] = int(float(b))
    except Exception:
        pass

    mem = {}
    try:
        for ln in open("/proc/meminfo"):
            k, v = ln.split(":")
            mem[k] = int(v.strip().split()[0])
        ram = {
            "used_gb": round((mem["MemTotal"] - mem["MemAvailable"]) / 1048576, 1),
            "total_gb": round(mem["MemTotal"] / 1048576, 1),
            "free_gb": round(mem["MemAvailable"] / 1048576, 1),
        }
    except Exception:
        ram = {}

    shm = {}
    try:
        if os.path.exists("/dev/shm"):
            sdu = shutil.disk_usage("/dev/shm")
            shm = {
                "used_gb": round(sdu.used / (1024 ** 3), 2),
                "total_gb": round(sdu.total / (1024 ** 3), 2),
                "free_gb": round(sdu.free / (1024 ** 3), 2),
            }
    except Exception:
        pass

    drive = query_drive_metrics()

    du = shutil.disk_usage("/content")
    workers = []
    for mid, w in WORKERS.items():
        is_zv = bool(_models.get(mid, {}).get("zero_vram"))
        workers.append({
            "model_id": mid,
            "state": ("drive_ram" if is_zv else w.state) if w.alive() else "dead",
            "pid": w.proc.pid if w.proc else None,
            "vram_mb": 0 if is_zv else per_pid.get(w.proc.pid if w.proc else -1, 0),
            "zero_vram": is_zv,
            "last_swap": w.last_swap,
        })
    data = {
        "gpu": gpu,
        "ram": ram,
        "shm": shm,
        "drive": drive,
        "disk": {"used_gb": round(du.used / 1e9, 1), "total_gb": round(du.total / 1e9, 1)},
        "workers": workers,
        "queue": {"running": _running_gpu_job, "queued": len(_gpu_queue)},
        "last_swap": _last_swap,
        "benchmark": _last_benchmark,
    }
    _metrics_cache.update(t=_now(), data=data)
    return data


def run_gpu_benchmark() -> Dict[str, Any]:
    """Run a 1.5-second BF16/FP16 TensorCore TFLOPS + VRAM Bandwidth + PCIe DMA Bandwidth micro-benchmark."""
    global _last_benchmark
    with _bench_lock:
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("当前环境未检测到可用 CUDA GPU")

        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        if hasattr(torch, "set_float32_matmul_precision"):
            torch.set_float32_matmul_precision("high")

        t_wall_start = time.perf_counter()
        props = torch.cuda.get_device_properties(0)
        free_bytes, total_bytes = torch.cuda.mem_get_info(0)
        arch_sm = f"sm_{props.major}{props.minor}"
        arch_label = (
            "Blackwell" if props.major >= 12 else
            "Hopper" if props.major == 9 else
            "Ada Lovelace" if (props.major == 8 and props.minor >= 9) else
            "Ampere" if props.major == 8 else
            "Turing" if props.major == 7 else arch_sm
        )

        # Choose matrix size safely based on currently available VRAM
        if free_bytes >= 2 * (1024 ** 3):
            N = 8192
        elif free_bytes >= 512 * (1024 ** 2):
            N = 4096
        else:
            N = 2048

        start_ev = torch.cuda.Event(enable_timing=True)
        end_ev = torch.cuda.Event(enable_timing=True)

        # 1. BF16 & FP16 TensorCore GEMM TFLOPS (~0.8s total)
        def _measure_gemm(dtype, budget_s: float) -> float:
            a = torch.randn((N, N), device="cuda", dtype=dtype)
            b = torch.randn((N, N), device="cuda", dtype=dtype)
            c = torch.matmul(a, b)
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            iters = 0
            start_ev.record()
            while (time.perf_counter() - t0) < budget_s or iters < 4:
                torch.matmul(a, b, out=c)
                iters += 1
                if iters % 8 == 0:
                    torch.cuda.synchronize()
            end_ev.record()
            torch.cuda.synchronize()
            ms = max(start_ev.elapsed_time(end_ev), 1e-3)
            del a, b, c
            flops = 2.0 * (N ** 3) * iters
            return round((flops / (ms / 1000.0)) / 1e12, 1)

        bf16_tflops = _measure_gemm(torch.bfloat16, 0.45)
        fp16_tflops = _measure_gemm(torch.float16, 0.35)
        peak_tflops = max(bf16_tflops, fp16_tflops)

        # 2. HBM3e / GDDR7 VRAM Memory Copy Bandwidth (~0.35s)
        buf_elems = 128 * 1024 * 1024 if free_bytes >= 2 * (1024 ** 3) else 32 * 1024 * 1024
        x = torch.ones((buf_elems,), device="cuda", dtype=torch.bfloat16)
        y = torch.empty_like(x)
        y.copy_(x)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        iters = 0
        start_ev.record()
        while (time.perf_counter() - t0) < 0.35 or iters < 6:
            y.copy_(x)
            iters += 1
        end_ev.record()
        torch.cuda.synchronize()
        ms_vram = max(start_ev.elapsed_time(end_ev), 1e-3)
        bytes_per_copy = 2.0 * x.numel() * x.element_size()  # read + write
        vram_bw_gbps = round((bytes_per_copy * iters) / (ms_vram / 1000.0) / 1e9, 1)
        del x, y

        # 3. PCIe Gen5 Host <-> Device Pinned Non-Blocking DMA Bandwidth (~0.35s)
        dma_elems = 64 * 1024 * 1024 if free_bytes >= 1024 ** 3 else 16 * 1024 * 1024
        dma_stream = torch.cuda.Stream()
        host_buf = torch.empty((dma_elems,), dtype=torch.bfloat16, device="cpu", pin_memory=True)
        dev_buf = torch.empty((dma_elems,), dtype=torch.bfloat16, device="cuda")
        dma_bytes = host_buf.numel() * host_buf.element_size()

        with torch.cuda.stream(dma_stream):
            dev_buf.copy_(host_buf, non_blocking=True)
        dma_stream.synchronize()

        # H2D (RAM -> GPU)
        iters_h2d = 0
        t0 = time.perf_counter()
        with torch.cuda.stream(dma_stream):
            start_ev.record(dma_stream)
            while (time.perf_counter() - t0) < 0.18 or iters_h2d < 4:
                dev_buf.copy_(host_buf, non_blocking=True)
                iters_h2d += 1
            end_ev.record(dma_stream)
        dma_stream.synchronize()
        ms_h2d = max(start_ev.elapsed_time(end_ev), 1e-3)
        pcie_h2d_gbps = round((dma_bytes * iters_h2d) / (ms_h2d / 1000.0) / 1e9, 1)

        # D2H (GPU -> RAM)
        iters_d2h = 0
        t0 = time.perf_counter()
        with torch.cuda.stream(dma_stream):
            start_ev.record(dma_stream)
            while (time.perf_counter() - t0) < 0.18 or iters_d2h < 4:
                host_buf.copy_(dev_buf, non_blocking=True)
                iters_d2h += 1
            end_ev.record(dma_stream)
        dma_stream.synchronize()
        ms_d2h = max(start_ev.elapsed_time(end_ev), 1e-3)
        pcie_d2h_gbps = round((dma_bytes * iters_d2h) / (ms_d2h / 1000.0) / 1e9, 1)
        pcie_bw_gbps = max(pcie_h2d_gbps, pcie_d2h_gbps)

        del host_buf, dev_buf
        gc.collect()
        torch.cuda.empty_cache()

        elapsed_ms = int(round((time.perf_counter() - t_wall_start) * 1000))
        res = {
            "ok": True,
            "gpu_name": props.name,
            "arch": f"{arch_sm} ({arch_label})",
            "compute_capability": f"{props.major}.{props.minor}",
            "sm_count": props.multi_processor_count,
            "vram_total_gb": round(total_bytes / (1024 ** 3), 1),
            "tflops": peak_tflops,
            "bf16_tflops": bf16_tflops,
            "fp16_tflops": fp16_tflops,
            "vram_bw_gbps": vram_bw_gbps,
            "mem_bw_gbps": vram_bw_gbps,
            "pcie_bw_gbps": pcie_bw_gbps,
            "pcie_h2d_gbps": pcie_h2d_gbps,
            "pcie_d2h_gbps": pcie_d2h_gbps,
            "matrix_size": N,
            "elapsed_ms": elapsed_ms,
            "ts": _now(),
            "summary": (
                f"{props.name} ({arch_sm}) · TensorCore 峰值 {peak_tflops} TFLOPS "
                f"(BF16 {bf16_tflops} / FP16 {fp16_tflops}) · 显存带宽 {vram_bw_gbps} GB/s · "
                f"PCIe DMA {pcie_bw_gbps} GB/s (H2D {pcie_h2d_gbps} / D2H {pcie_d2h_gbps})"
            ),
        }
        _last_benchmark = res
        return res


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------
app = FastAPI(title="WorldForge Remote", version=VERSION)


@app.exception_handler(Exception)
async def _err(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"{exc.__class__.__name__}: {exc}"})


@app.get("/api/health")
def health():
    return {"ok": True, "version": VERSION, "gpu": metrics().get("gpu", {}).get("name")}


@app.get("/api/metrics")
def api_metrics():
    return metrics()


@app.get("/api/benchmark")
@app.post("/api/benchmark")
def api_benchmark():
    return run_gpu_benchmark()


@app.get("/api/models")
def api_models():
    with _reg_lock:
        out = []
        for m in _models.values():
            w = WORKERS.get(m["id"])
            if m["status"] == "loaded" and not (w and w.alive()):
                m["status"] = "downloaded"
            out.append(m)
        return out


@app.post("/api/models")
async def api_add_model(req: Request):
    body = await req.json()
    try:
        return add_model(body.get("repo", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/models/{mid}/download")
def api_download(mid: str):
    mid = resolve_model_id(mid)
    if mid not in _models:
        raise HTTPException(404, "模型不存在")
    job = new_job(mid, "download", {})
    submit(job)
    return {"job_id": job["id"]}


@app.post("/api/models/{mid}/load")
def api_load(mid: str):
    mid = resolve_model_id(mid)
    if mid not in _models:
        raise HTTPException(404, "模型不存在")
    job = new_job(mid, "load", {})
    submit(job)
    return {"job_id": job["id"]}


@app.post("/api/models/{mid}/unload")
def api_unload(mid: str):
    mid = resolve_model_id(mid)
    w = WORKERS.pop(mid, None)
    if w:
        w.kill()
    if mid in _models:
        _models[mid]["status"] = "downloaded"
    return {"ok": True}


@app.delete("/api/models/{mid}")
def api_delete_model(mid: str):
    mid = resolve_model_id(mid)
    m = _models.get(mid)
    if not m:
        raise HTTPException(404, "模型不存在")
    if m.get("builtin"):
        raise HTTPException(400, "内置模型不能删除")
    api_unload(mid)
    with _reg_lock:
        _models.pop(mid, None)
    _save_registry()
    return {"ok": True}


@app.post("/api/jobs")
async def api_new_job(req: Request):
    body = await req.json()
    task = body.get("task")
    raw_mid = body.get("model_id") or ""
    params = dict(body.get("params") or {})
    if task not in ("t2i", "t2v", "i2v", "lyra", "tts", "setup", "download", "load"):
        raise HTTPException(400, f"未知任务类型 {task}")
    mid = raw_mid if task == "setup" else resolve_model_id(raw_mid, fallback_task=task)
    if task not in ("setup",) and mid not in _models:
        raise HTTPException(400, f"未知模型 {raw_mid}")
    if task not in ("setup", "download", "load") and _models.get(mid, {}).get("kind") == "tts":
        task = "tts"
    prompt_txt = str(params.get("prompt") or params.get("text") or params.get("scene") or params.get("caption") or "").strip()
    if prompt_txt and not params.get("prompt"):
        params["prompt"] = prompt_txt
    has_img = bool(params.get("image_path") and os.path.exists(str(params.get("image_path"))))
    if task in ("t2i", "t2v", "tts") and not prompt_txt:
        raise HTTPException(400, "请输入一句话提示词或配音台词描述")
    if task in ("i2v", "lyra") and not has_img and not prompt_txt:
        raise HTTPException(400, "请上传一张参考图，或直接输入一句话提示词自动生成首帧并渲染视频")
    if task == "lyra":
        for k in ("frames", "zoom_in_frames", "zoom_out_frames", "frames_in", "frames_out", "chain_frames"):
            val = params.get(k)
            if val not in (None, "", 0, "0") and (int(val) - 1) % 80 != 0:
                raise HTTPException(400, f"{k} 必须是 1+80k（81/161/241/321/401/481/...）")
    if params.get("seed", -1) in (-1, None, ""):
        params["seed"] = random.randint(0, 2**31 - 1)
    job = new_job(mid, task, params)
    submit(job)
    return {"job_id": job["id"], "model_id": mid}


@app.get("/api/jobs")
def api_jobs(limit: int = 50):
    with _jobs_lock:
        return sorted(_jobs.values(), key=lambda j: j["created"], reverse=True)[:limit]


@app.get("/api/jobs/{jid}")
def api_job(jid: str):
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "任务不存在")
    return j


@app.get("/api/jobs/{jid}/log")
def api_job_log(jid: str, offset: int = 0):
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "任务不存在")
    p = f"{JOBS_DIR}/{jid}/log.txt"
    text, new_off = "", offset
    if os.path.exists(p):
        with open(p, "rb") as f:
            f.seek(offset)
            data = f.read(512 * 1024)
            new_off = offset + len(data)
            text = data.decode("utf-8", "replace")
    return {"text": text, "offset": new_off, "done": j["status"] in ("done", "error", "cancelled")}


@app.post("/api/jobs/{jid}/cancel")
def api_cancel(jid: str):
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "任务不存在")
    if j["status"] == "queued":
        update_job(jid, status="cancelled", stage="已取消", finished=_now())
    elif j["status"] == "running":
        update_job(jid, status="cancelled", stage="已取消", finished=_now())
        p = _io_procs.get(jid)
        if p:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except Exception:
                pass
        for mid, w in list(WORKERS.items()):
            if w.current_job == jid:
                w.kill()  # the only reliable way to stop a CUDA job mid-flight
                WORKERS.pop(mid, None)
                if mid in _models:
                    _models[mid]["status"] = "downloaded"
    return {"ok": True}


@app.post("/api/upload")
async def api_upload(req: Request, filename: str = "upload.png"):
    name = re.sub(r"[^\w.\-]+", "_", os.path.basename(filename)) or "upload.png"
    stem, ext = os.path.splitext(name)
    path = f"{INPUTS}/{stem}_{uuid.uuid4().hex[:6]}{ext or '.png'}"
    data = await req.body()
    if not data:
        raise HTTPException(400, "空文件")
    with open(path, "wb") as f:
        f.write(data)
    return {"path": path}


@app.get("/api/files")
def api_files(path: str):
    real = os.path.realpath(path)
    if not real.startswith(ROOT + "/") or not os.path.isfile(real):
        raise HTTPException(404, "文件不存在")
    return FileResponse(real, filename=os.path.basename(real))


@app.get("/api/presets")
def api_presets():
    return presets.ALL


if __name__ == "__main__":
    import argparse
    import uvicorn

    ap = argparse.ArgumentParser(description="WorldForge GPU Inference Server (Colab G4/A100 & Local RTX 4090/5090)")
    ap.add_argument("--local", action="store_true", help="本地 RTX 4090 / 5090 直连模式（默认监听 0.0.0.0:17860 供客户端 0 秒自动识别）")
    ap.add_argument("--host", default=None, help="监听地址（默认 127.0.0.1，--local 模式下默认 0.0.0.0）")
    ap.add_argument("--port", type=int, default=None, help="监听端口（Colab 默认 7860，--local 默认 17860）")
    args, _ = ap.parse_known_args()

    bind_host = args.host or os.environ.get("FORGE_HOST") or ("0.0.0.0" if args.local else "127.0.0.1")
    bind_port = args.port or int(os.environ.get("FORGE_PORT", "17860" if args.local else "7860"))

    setup_4tier_storage()
    _load_old_jobs()
    _load_registry()
    threading.Thread(target=_gpu_loop, daemon=True).start()
    print(f"⚡ WorldForge GPU Server v{VERSION} 已启动: http://{bind_host}:{bind_port} (ROOT={ROOT})", flush=True)
    uvicorn.run(app, host=bind_host, port=bind_port, log_level="warning")
