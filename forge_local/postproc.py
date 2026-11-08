"""本地后期（Mac）：裁剪 → RIFE 插帧 → 变速 → 缩放 → 尾帧定格（交叉淡化 + 缓推）→ x264 编码。"""

import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from . import config
from .gallery import probe, safe_name, unique_path, kind_of
from .tasks import TaskError

SCALES = {"orig": None, "720p": 1280, "1080p": 1920, "1440p": 2560, "2160p": 3840, "4k": 3840}
MAX_FPS = 60
HOLD_SECONDS = 3.0
XFADE_SECONDS = 0.6
FINAL_X264 = ["-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
              "-movflags", "+faststart"]
TEMP_X264 = ["-c:v", "libx264", "-crf", "10", "-preset", "fast", "-pix_fmt", "yuv420p"]


def _num(v, name, default=None, lo=None, hi=None, allow_none=False):
    if v is None or v == "":
        if allow_none:
            return None
        v = default
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise TaskError("%s 必须是数字" % name)
    if lo is not None and v < lo or hi is not None and v > hi:
        raise TaskError("%s 超出范围 [%s, %s]" % (name, lo, hi))
    return v


def normalize_params(body):
    """校验并规范化 POST /api/local/post 参数（在请求线程中调用，错误 → 400）。"""
    if not isinstance(body, dict) or not body.get("gallery_id"):
        raise TaskError("缺少 gallery_id")
    p = {"gallery_id": str(body["gallery_id"])}
    p["speed"] = _num(body.get("speed"), "speed", 1.0, 0.1, 32)
    interp = int(_num(body.get("interp"), "interp", 1, 1, 8))
    if interp not in (1, 2, 4, 8):
        raise TaskError("interp 只能是 1 / 2 / 4 / 8")
    p["interp"] = interp
    p["trim_start"] = _num(body.get("trim_start"), "trim_start", 0.0, 0)
    p["trim_end"] = _num(body.get("trim_end"), "trim_end", allow_none=True, lo=0)
    if p["trim_end"] is not None and p["trim_end"] <= p["trim_start"]:
        raise TaskError("trim_end 必须大于 trim_start")
    scale = str(body.get("scale") or "orig").lower()
    if scale not in SCALES:
        raise TaskError("scale 只能是 " + " / ".join(SCALES))
    p["scale"] = scale
    p["end_hold_image"] = body.get("end_hold_image") or None
    return p


# ---------------------------------------------------------------- 外部工具
def ensure_rife(task):
    if config.RIFE_BIN.exists() and (config.RIFE_DIR / config.RIFE_MODEL).is_dir():
        return config.RIFE_BIN
    task.log("未找到 rife-ncnn-vulkan，开始自动下载 …")
    config.AITOOLS_DIR.mkdir(parents=True, exist_ok=True)
    zpath = config.AITOOLS_DIR / "rife.zip"
    req = urllib.request.Request(config.RIFE_URL, headers={"User-Agent": "WorldForge"})
    with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, 0
        while True:
            chunk = r.read(512 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if time.time() - last > 2:
                last = time.time()
                task.log("  下载 RIFE %.1f / %.1f MB" % (got / 1e6, total / 1e6))
    subprocess.run(["ditto", "-x", "-k", str(zpath), str(config.AITOOLS_DIR)], check=True)
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(config.RIFE_DIR)])
    os.chmod(config.RIFE_BIN, 0o755)
    if not config.RIFE_BIN.exists():
        raise TaskError("RIFE 下载/解压失败")
    task.log("RIFE 已就绪：%s" % config.RIFE_BIN)
    return config.RIFE_BIN


def run_ffmpeg(args, task, expect_seconds, on_frac):
    """运行 ffmpeg（自动加 -progress），按 out_time 汇报 0..1 进度。"""
    ff = config.ffmpeg_bin()
    if not ff:
        raise TaskError("未找到 ffmpeg（brew install ffmpeg）")
    cmd = [ff, "-y", "-hide_banner", "-v", "error", "-nostats", "-progress", "pipe:1"] + args
    task.log("$ ffmpeg " + " ".join(a if " " not in a else repr(a) for a in args))
    errf = tempfile.TemporaryFile()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf, stdin=subprocess.DEVNULL)
    for raw in iter(p.stdout.readline, b""):
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                t = int(line.split("=", 1)[1]) / 1e6
            except ValueError:
                continue
            if expect_seconds and expect_seconds > 0:
                on_frac(min(1.0, t / expect_seconds))
    p.wait()
    errf.seek(0)
    err = errf.read().decode("utf-8", "replace").strip()
    errf.close()
    if p.returncode != 0:
        raise TaskError("ffmpeg 失败 (rc=%d): %s" % (p.returncode, err[-800:]))
    on_frac(1.0)


def run_rife(rife, src_dir, dst_dir, task, on_frac):
    n_in = len([n for n in os.listdir(src_dir) if n.endswith(".png")])
    expect = n_in * 2
    dst_dir.mkdir(parents=True, exist_ok=True)
    model = config.RIFE_DIR / config.RIFE_MODEL
    cmd = [str(rife), "-i", str(src_dir), "-o", str(dst_dir), "-m", str(model), "-f", "%08d.png"]
    task.log("$ rife-ncnn-vulkan -i %s -o %s -m %s  (%d → %d 帧)" % (src_dir.name, dst_dir.name,
                                                                   config.RIFE_MODEL, n_in, expect))
    errf = tempfile.TemporaryFile()
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=errf, stdin=subprocess.DEVNULL,
                         cwd=str(config.RIFE_DIR))
    while p.poll() is None:
        time.sleep(1.0)
        try:
            done = len(os.listdir(dst_dir))
        except OSError:
            done = 0
        on_frac(min(0.99, done / max(1, expect)))
    errf.seek(0)
    err = errf.read().decode("utf-8", "replace").strip()
    errf.close()
    got = len([n for n in os.listdir(dst_dir) if n.endswith(".png")])
    if p.returncode != 0 or got < max(2, expect - 2):
        raise TaskError("RIFE 插帧失败 (rc=%s, 输出 %d/%d 帧): %s" % (p.returncode, got, expect, err[-600:]))
    on_frac(1.0)
    return got


def scale_filter(scale, w, h):
    long_side = SCALES.get(scale)
    if not long_side or not w or not h:
        return "crop=trunc(iw/2)*2:trunc(ih/2)*2"
    if w >= h:
        return "scale=%d:-2:flags=lanczos,crop=trunc(iw/2)*2:trunc(ih/2)*2" % long_side
    return "scale=-2:%d:flags=lanczos,crop=trunc(iw/2)*2:trunc(ih/2)*2" % long_side


# ---------------------------------------------------------------- 主流程
class Stepper:
    """把多步骤的局部进度映射到整体 0..1。"""

    def __init__(self, task, weights):
        self.task = task
        self.weights = weights
        self.total = float(sum(w for _, w in weights)) or 1.0
        self.base = 0.0
        self.cur = None
        self._lock = threading.Lock()

    def begin(self, name):
        for n, w in self.weights:
            if n == name:
                self.cur = (n, w)
                break
        self.task.log("▶ " + name)
        self.task.set_progress(self.base / self.total)

    def frac(self, f):
        if self.cur:
            self.task.set_progress((self.base + self.cur[1] * f) / self.total)

    def end(self):
        if self.cur:
            self.base += self.cur[1]
            self.cur = None
            self.task.set_progress(self.base / self.total)


def run_post(task, params, gallery):
    src_item = gallery.get(params["gallery_id"])
    if not src_item:
        raise TaskError("作品不存在：%s" % params["gallery_id"])
    if src_item["kind"] != "video":
        raise TaskError("只能对视频做后期")
    src = Path(src_item["path"])
    if not src.exists():
        raise TaskError("源文件已丢失：%s" % src)

    hold_img = None
    ehi = params.get("end_hold_image")
    if ehi:
        it = gallery.get(ehi) if str(ehi).startswith("g_") else None
        hold_img = Path(it["path"]) if it else Path(os.path.expanduser(str(ehi)))
        if not hold_img.exists():
            raise TaskError("尾帧图片不存在：%s" % ehi)
        if kind_of(hold_img.name) != "image":
            raise TaskError("尾帧必须是图片")

    info = probe(src)
    if not info.get("width"):
        raise TaskError("无法读取视频信息（ffprobe 失败）")
    src_fps = info.get("fps") or 24.0
    dur = info.get("duration") or ((info.get("frames") or 0) / src_fps)
    s = params["trim_start"] or 0.0
    e = params["trim_end"] if params["trim_end"] is not None else dur
    e = min(e, dur) if dur else e
    seg = e - s
    if seg <= 0.05:
        raise TaskError("裁剪区间无效：%.2f–%.2f（视频时长 %.2fs）" % (s, e, dur))
    interp, speed = params["interp"], params["speed"]
    rate = src_fps * interp * speed               # 帧序列的播放帧率
    out_fps = min(rate, MAX_FPS)
    out_dur = seg / speed
    task.log("源视频：%dx%d @ %.3f fps，时长 %.2fs；区间 %.2f–%.2fs" % (
        info["width"], info["height"], src_fps, dur, s, e))
    task.log("插帧 ×%d，变速 ×%g → 序列帧率 %.2f，输出 %.2f fps，时长约 %.2fs" % (
        interp, speed, rate, out_fps, out_dur))

    weights = []
    if interp > 1:
        weights += [("抽帧", 1), ("RIFE 插帧", 6)]
    weights += [("编码", 3)]
    if hold_img:
        weights += [("尾帧定格", 1)]
    st = Stepper(task, weights)

    work = gallery.root / ".work" / task.id
    work.mkdir(parents=True, exist_ok=True)
    try:
        vf = []
        if interp > 1:
            rife = ensure_rife(task)
            st.begin("抽帧")
            frames = work / "f0"
            frames.mkdir()
            run_ffmpeg(["-ss", "%.3f" % s, "-i", str(src), "-t", "%.3f" % seg, "-an",
                        "-fps_mode", "passthrough", str(frames / "%08d.png")],
                       task, seg, st.frac)
            n = len(os.listdir(frames))
            task.log("  抽取 %d 帧" % n)
            st.end()
            st.begin("RIFE 插帧")
            passes = {2: 1, 4: 2, 8: 3}[interp]
            cur = frames
            for i in range(passes):
                nxt = work / ("f%d" % (i + 1))
                run_rife(rife, cur, nxt, task,
                         lambda f, i=i: st.frac((i + f) / passes))
                shutil.rmtree(cur, ignore_errors=True)   # 上一轮帧已不再需要
                cur = nxt
            n_out = len(os.listdir(cur))
            task.log("  插帧完成：%d 帧" % n_out)
            st.end()
            inputs = ["-framerate", "%.6f" % rate, "-i", str(cur / "%08d.png")]
            out_dur = n_out / rate
        else:
            inputs = ["-ss", "%.3f" % s, "-i", str(src), "-t", "%.3f" % seg]
            if abs(speed - 1.0) > 1e-6:
                vf.append("setpts=PTS/%.6f" % speed)
        vf.append("fps=%.6f" % out_fps)
        vf.append(scale_filter(params["scale"], info["width"], info["height"]))
        vf += ["setsar=1", "format=yuv420p"]

        out_name = "%s_post_%gx_i%d_%s.mp4" % (safe_name(src.stem, "video"), speed, interp, params["scale"])
        dest = unique_path(gallery.day_dir() / out_name)

        st.begin("编码")
        main_out = (work / "main.mp4") if hold_img else work / "final.mp4"
        run_ffmpeg(inputs + ["-vf", ",".join(vf), "-an"] +
                   (TEMP_X264 if hold_img else FINAL_X264) + [str(main_out)],
                   task, out_dur, st.frac)
        st.end()

        final = main_out
        if hold_img:
            st.begin("尾帧定格")
            mi = probe(main_out)
            W, H = mi.get("width"), mi.get("height")
            F = mi.get("fps") or out_fps
            mdur = (mi["frames"] / F) if mi.get("frames") else (mi.get("duration") or out_dur)
            xf = min(XFADE_SECONDS, max(0.1, mdur / 2))
            N = max(2, int(round(HOLD_SECONDS * F)))
            bw, bh = min(W * 4, 8000), min(H * 4, int(8000 * H / W))
            bw, bh = bw - bw % 2, bh - bh % 2
            fc = (
                "[0:v]fps={F},format=yuv420p,setsar=1,settb=AVTB[m];"
                "[1:v]scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=lanczos,"
                "crop={bw}:{bh},"
                "zoompan=z='1+0.06*on/{N1}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                ":d={N}:s={W}x{H}:fps={F},format=yuv420p,setsar=1,settb=AVTB[h];"
                "[m][h]xfade=transition=fade:duration={xf:.3f}:offset={off:.4f},format=yuv420p[v]"
            ).format(F="%.6f" % F, bw=bw, bh=bh, N=N, N1=N - 1, W=W, H=H, xf=xf, off=mdur - xf)
            final = work / "final.mp4"
            run_ffmpeg(["-i", str(main_out), "-i", str(hold_img), "-filter_complex", fc,
                        "-map", "[v]", "-an"] + FINAL_X264 + [str(final)],
                       task, mdur - xf + HOLD_SECONDS, st.frac)
            st.end()

        shutil.move(str(final), str(dest))
        meta = dict(src_item.get("meta") or {})
        meta.pop("remote_path", None)
        meta["post"] = dict(params, end_hold_image=str(hold_img) if hold_img else None)
        meta["parent"] = src_item["id"]
        item = gallery.add(dest, "video", meta)
        task.log("✓ 完成：%s" % dest)
        return {"gallery_id": item["id"], "path": item["path"]}
    finally:
        shutil.rmtree(work, ignore_errors=True)
