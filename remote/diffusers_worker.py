"""Generic long-lived diffusers worker (text-to-image / text-to-video / image-to-video).

Optimized for NVIDIA Blackwell (sm_120) / Hopper / Ada GPUs:
- TF32 + cuDNN benchmark + high-precision matmul + Flash/Mem-Efficient/cuDNN SDPA
- Uncensored generation: disables safety_checker & requires_safety_checker automatically
- Automatic VAE slicing & tiling on high-resolution (>= 2048px) or <= 32GB VRAM GPUs
- Pinned Host Memory (pin_memory=True) + Non-Blocking CUDA DMA Stream hot-swapping
  between GPU VRAM and 176GB DDR5 Host RAM with real-time GB/s bandwidth telemetry.

Protocol: JSON commands on stdin, events on stdout prefixed with "@@FORGE@@ ".
"""
import argparse
import gc
import inspect
import itertools
import json
import os
import sys
import time
import traceback

MARK = "@@FORGE@@ "


def emit(**ev):
    sys.stdout.write("\n" + MARK + json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def log(msg):
    emit(event="log", msg=str(msg))


ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--kind", default="t2i")
args = ap.parse_args()

try:
    import torch
    from diffusers import DiffusionPipeline

    # --- Extreme Blackwell (sm_120) TensorCore & PyTorch 2.x SDPA Optimizations ---
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")
    if hasattr(torch.backends.cuda, "enable_flash_sdp"):
        torch.backends.cuda.enable_flash_sdp(True)
    if hasattr(torch.backends.cuda, "enable_mem_efficient_sdp"):
        torch.backends.cuda.enable_mem_efficient_sdp(True)
    if hasattr(torch.backends.cuda, "enable_cudnn_sdp"):
        torch.backends.cuda.enable_cudnn_sdp(True)

    DMA_STREAM = torch.cuda.Stream()
    DEV_PROPS = torch.cuda.get_device_properties(0)
    TOTAL_VRAM_GB = DEV_PROPS.total_memory / (1024 ** 3)
    ARCH_SM = f"sm_{DEV_PROPS.major}{DEV_PROPS.minor}"

    t0 = time.time()
    log(
        f"加载 {args.repo} (bf16) · GPU={DEV_PROPS.name} ({ARCH_SM}, {TOTAL_VRAM_GB:.1f}GB VRAM, TF32+FlashSDPA 已开启) ..."
    )
    pipe = None
    for extra_kw in (
        {"safety_checker": None, "requires_safety_checker": False},
        {"safety_checker": None},
        {},
    ):
        for dt_kw in ({"dtype": torch.bfloat16}, {"torch_dtype": torch.bfloat16}):
            try:
                pipe = DiffusionPipeline.from_pretrained(args.repo, **dt_kw, **extra_kw)
                break
            except TypeError:
                continue
        if pipe is not None:
            break
    if pipe is None:
        pipe = DiffusionPipeline.from_pretrained(args.repo)
    if hasattr(pipe, "safety_checker"):
        pipe.safety_checker = None
    if hasattr(pipe, "requires_safety_checker"):
        pipe.requires_safety_checker = False

    pipe.to("cuda")
    try:
        pipe.set_progress_bar_config(disable=False)
    except Exception:
        pass

    # Pre-enable VAE slicing/tiling if running on <= 32GB VRAM GPUs (L4 24GB / T4 16GB)
    if TOTAL_VRAM_GB <= 32.0:
        for fn in ("enable_vae_slicing", "enable_vae_tiling"):
            if hasattr(pipe, fn):
                try:
                    getattr(pipe, fn)()
                except Exception:
                    pass

    SIG = set(inspect.signature(pipe.__call__).parameters)
    log(f"{pipe.__class__.__name__} 加载完成，用时 {time.time() - t0:.1f}s；支持参数: {sorted(SIG)}")
    emit(event="ready", vram_mb=int(torch.cuda.memory_allocated() / 2**20))
except Exception as e:
    emit(event="error", msg=f"加载失败: {e}\n{traceback.format_exc()}")
    sys.exit(1)


def _iter_pipeline_modules(p_obj):
    """Yield unique torch.nn.Module components inside a DiffusionPipeline."""
    seen = set()
    comps = getattr(p_obj, "components", None)
    items = comps.values() if isinstance(comps, dict) else [getattr(p_obj, k, None) for k in dir(p_obj)]
    for obj in items:
        if isinstance(obj, torch.nn.Module) and id(obj) not in seen:
            seen.add(id(obj))
            yield obj


def _dma_offload_pipeline(p_obj) -> tuple:
    """Offload all pipeline modules from GPU to Pinned DDR5 Host RAM via non-blocking DMA stream."""
    t0 = time.perf_counter()
    vram_before = torch.cuda.memory_allocated()
    total_bytes = 0
    seen_tensors = set()
    modules = list(_iter_pipeline_modules(p_obj))

    with torch.cuda.stream(DMA_STREAM):
        for mod in modules:
            for t in itertools.chain(mod.parameters(), mod.buffers()):
                tid = id(t)
                if tid in seen_tensors:
                    continue
                seen_tensors.add(tid)
                if t.is_cuda:
                    nbytes = t.numel() * t.element_size()
                    total_bytes += nbytes
                    old_cuda = t.data
                    old_cuda.record_stream(DMA_STREAM)
                    try:
                        pinned = torch.empty(
                            old_cuda.shape,
                            dtype=old_cuda.dtype,
                            layout=old_cuda.layout,
                            device="cpu",
                            pin_memory=True,
                        )
                        pinned.copy_(old_cuda, non_blocking=True)
                        t.data = pinned
                    except Exception:
                        t.data = old_cuda.to("cpu", non_blocking=True)
                    del old_cuda
            # Ensure any custom non-parameter tensor attributes are also on CPU
            try:
                mod.to("cpu", non_blocking=True)
            except Exception:
                pass
    DMA_STREAM.synchronize()
    gc.collect()
    torch.cuda.empty_cache()
    vram_after = torch.cuda.memory_allocated()
    if total_bytes == 0 and vram_before > vram_after:
        total_bytes = vram_before - vram_after
    elapsed_s = max(time.perf_counter() - t0, 1e-4)
    swap_gb = round(total_bytes / (1024 ** 3), 2)
    bw_gbps = round(swap_gb / elapsed_s, 1) if swap_gb > 0 else 0.0
    return swap_gb, elapsed_s, bw_gbps


def _dma_onload_pipeline(p_obj) -> tuple:
    """Onload all pipeline modules from Pinned DDR5 Host RAM to GPU via non-blocking PCIe DMA stream."""
    t0 = time.perf_counter()
    vram_before = torch.cuda.memory_allocated()
    total_bytes = 0
    seen_tensors = set()
    modules = list(_iter_pipeline_modules(p_obj))

    for mod in modules:
        for t in itertools.chain(mod.parameters(), mod.buffers()):
            tid = id(t)
            if tid not in seen_tensors:
                seen_tensors.add(tid)
                if not t.is_cuda:
                    total_bytes += t.numel() * t.element_size()

    with torch.cuda.stream(DMA_STREAM):
        if modules:
            for mod in modules:
                mod.to("cuda", non_blocking=True)
        else:
            p_obj.to("cuda")
    DMA_STREAM.synchronize()
    gc.collect()
    vram_after = torch.cuda.memory_allocated()
    if total_bytes == 0 and vram_after > vram_before:
        total_bytes = vram_after - vram_before
    elapsed_s = max(time.perf_counter() - t0, 1e-4)
    swap_gb = round(total_bytes / (1024 ** 3), 2)
    bw_gbps = round(swap_gb / elapsed_s, 1) if swap_gb > 0 else 0.0
    return swap_gb, elapsed_s, bw_gbps


def _enable_vae_tiling_if_needed(width: int, height: int, force: bool = False) -> None:
    """Automatically enable VAE slicing & tiling for >= 2048px outputs or on OOM retry."""
    if not (force or max(width, height) >= 2048 or TOTAL_VRAM_GB <= 32.0):
        return
    vae = getattr(pipe, "vae", None)
    for fn in ("enable_vae_slicing", "enable_vae_tiling"):
        if hasattr(pipe, fn):
            try:
                getattr(pipe, fn)()
            except Exception:
                pass
    if vae is not None:
        for fn in ("enable_slicing", "enable_tiling"):
            if hasattr(vae, fn):
                try:
                    getattr(vae, fn)()
                except Exception:
                    pass


def _align16(v: int, default: int = 1024) -> int:
    val = int(v or default)
    return max(256, (val // 32) * 32)


DEFAULT_CINEMA_SUFFIX = (
    ", Captured on ARRI Alexa 65 paired with vintage Canon FD 85mm f/1.2L lens wide open at f/1.2, "
    "Tiffen Black Pro-Mist 1/4 soft filter, warm golden hour backlighting creating a glowing amber rim light, "
    "translucent porcelain skin with delicate rosy blush and subsurface scattering, ultra-shallow depth of field, "
    "creamy dreamy bokeh, soft Tyndall light rays, Kodak Portra 400 film aesthetic, 8K masterpiece cinematography"
)

CINEMA_CAMERA_SUFFIXES = {
    "iwai_85mm_f12": DEFAULT_CINEMA_SUFFIX,
    "wong_kar_wai_anamorphic": (
        ", Wong Kar-wai and Christopher Doyle aesthetic, shot on ARRI Alexa Mini LF with vintage Cooke Anamorphic/i 40mm T2.0 lens, "
        "creamy oval anamorphic bokeh, subtle horizontal blue-and-gold anamorphic lens flare streaks, "
        "rich emerald and crimson-amber neon color grading, 35mm Kodak Vision3 500T film grain, 8K masterpiece"
    ),
    "deakins_imax_65mm": (
        ", Roger Deakins Academy Award cinematography, shot on IMAX 65mm film camera with Panavision Primo 70 50mm T1.9 lens, "
        "breathtaking volumetric god rays and Tyndall light shafts, chiaroscuro golden sculptural lighting, "
        "ultra-wide dynamic range, razor-sharp micro-contrast, 8K IMAX theatrical still"
    ),
    "leica_noctilux_f095": (
        ", Shot on Sony Venice 2 8K full-frame cinema camera paired with Leica Noctilux-M 50mm f/0.95 ASPH wide open at f/0.95, "
        "signature Leica 3D pop and painterly swirly cat-eye bokeh, luminous catchlights in eyes, "
        "flawless natural skin micro-texture with warm subsurface glow, 8K editorial cinema portrait"
    ),
    "shinkai_twilight_panavision": (
        ", Makoto Shinkai twilight magic hour aesthetic meets live-action Panavision Millennium DXL2 8K cinema camera, "
        "24mm T1.4 wide-angle cinema lens, luminous violet-gold-cobalt cumulus clouds, shimmering lens reflection, "
        "ethereal atmospheric perspective, ultra-vivid HDR color harmony, 8K masterpiece"
    ),
    "raw_lens": "",
}


def _enrich_cinema_prompt(raw_prompt: str, p: dict) -> str:
    prompt = str(raw_prompt or "").strip()
    if not prompt:
        return prompt
    cam_id = str(p.get("cinema_camera") or "iwai_85mm_f12").strip()
    if cam_id == "raw_lens" or p.get("disable_cinema_lens"):
        return prompt
    already_optical = any(
        kw in prompt
        for kw in ("ARRI", "Anamorphic", "Noctilux", "IMAX", "Panavision", "85mm", "50mm", "吉卜力", "Ghibli", "水墨")
    )
    if already_optical:
        return prompt
    suffix = CINEMA_CAMERA_SUFFIXES.get(cam_id, DEFAULT_CINEMA_SUFFIX)
    return prompt + suffix


def _kwargs(p, n_images=1, seeds=None):
    raw_prompt = str(p.get("prompt") or p.get("scene") or "")
    kw = {"prompt": _enrich_cinema_prompt(raw_prompt, p)}
    neg = p.get("negative_prompt") or "lowres, blurry, bad anatomy, deformed hands, extra fingers, plastic skin, overexposed, watermark, text, ugly"
    if neg and "negative_prompt" in SIG:
        kw["negative_prompt"] = neg
    if p.get("width") not in (None, "", 0) and "width" in SIG:
        kw["width"] = _align16(p["width"], 1024)
    if p.get("height") not in (None, "", 0) and "height" in SIG:
        kw["height"] = _align16(p["height"], 1024)
    for src, dst in (("steps", "num_inference_steps"), ("num_frames", "num_frames")):
        if p.get(src) not in (None, "", 0) and dst in SIG:
            kw[dst] = int(p[src])
    if p.get("guidance") not in (None, "") and "guidance_scale" in SIG:
        kw["guidance_scale"] = float(p["guidance"])
    if "use_kv_cache" in SIG:
        kw["use_kv_cache"] = True
    if seeds is not None:
        gens = [torch.Generator("cpu").manual_seed(int(s)) for s in seeds]
        kw["generator"] = gens if len(gens) > 1 else gens[0]
    if n_images > 1 and "num_images_per_prompt" in SIG:
        kw["num_images_per_prompt"] = n_images
    if p.get("image_path") and os.path.exists(str(p["image_path"])) and "image" in SIG:
        from PIL import Image

        img = Image.open(p["image_path"]).convert("RGB")
        if "width" in kw and "height" in kw and img.size != (kw["width"], kw["height"]):
            img = img.resize((kw["width"], kw["height"]), Image.Resampling.LANCZOS)
        kw["image"] = img
    return kw


def _progress_cb(base, span, label):
    def cb(pipe_, step, timestep, cb_kwargs):
        total = getattr(pipe_, "_num_timesteps", None) or getattr(pipe_, "num_timesteps", None) or 1
        emit(event="progress", p=round(base + span * (step + 1) / max(total, 1), 4),
             stage=f"{label} 第 {step + 1}/{total} 步")
        return cb_kwargs
    return cb


def run_t2i(p, out_dir):
    count = max(1, min(int(p.get("count", 1)), 16))
    seed = int(p.get("seed", 0))
    width = _align16(p.get("width"), 1024)
    height = _align16(p.get("height"), 1024)
    _enable_vae_tiling_if_needed(width, height)

    outputs, done = [], 0
    batch = count if "num_images_per_prompt" in SIG else 1
    retried_tiling = False
    while done < count:
        n = min(batch, count - done)
        seeds = [seed + done + i for i in range(n)]
        kw = _kwargs(p, n, seeds)
        if "callback_on_step_end" in SIG:
            kw["callback_on_step_end"] = _progress_cb(done / count, n / count, f"第 {done + 1}-{done + n} 张")
        t = time.time()
        try:
            images = pipe(**kw).images
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            if not retried_tiling:
                retried_tiling = True
                _enable_vae_tiling_if_needed(width, height, force=True)
                log("显存紧张，已自动开启 VAE Slicing/Tiling 分块解码重试")
                continue
            if batch > 1:
                batch = max(1, batch // 2)
                log(f"显存不足，批大小降为 {batch} 重试")
                continue
            raise
        for i, img in enumerate(images):
            name = f"img_{done + i + 1:02d}_seed{seeds[i]}.png"
            out_path = os.path.join(out_dir, name)
            img.convert("RGB").save(out_path)
            outputs.append({
                "path": out_path,
                "kind": "image",
                "name": name,
                "width": img.width,
                "height": img.height,
                "seed": seeds[i],
            })
        log(f"生成 {n} 张 ({width}×{height})，用时 {time.time() - t:.1f}s")
        done += n
        emit(event="progress", p=round(done / count, 4), stage=f"已完成 {done}/{count} 张")
    return outputs


def run_video(p, out_dir):
    from diffusers.utils import export_to_video

    seed = int(p.get("seed", 0))
    width = _align16(p.get("width"), 832)
    height = _align16(p.get("height"), 480)
    _enable_vae_tiling_if_needed(width, height)

    kw = _kwargs(p, 1, [seed])
    if "callback_on_step_end" in SIG:
        kw["callback_on_step_end"] = _progress_cb(0.0, 0.95, "去噪")
    t = time.time()
    try:
        res = pipe(**kw)
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        _enable_vae_tiling_if_needed(width, height, force=True)
        log("显存紧张，已自动开启 VAE Slicing/Tiling 分块解码重试")
        res = pipe(**kw)
    frames = res.frames[0] if hasattr(res, "frames") else res.images
    name = f"video_seed{seed}.mp4"
    path = os.path.join(out_dir, name)
    fps = int(p.get("fps", 16))
    export_to_video(frames, path, fps=fps)
    log(f"视频生成完成，用时 {time.time() - t:.1f}s，{len(frames)} 帧")
    return [{"path": path, "kind": "video", "name": name, "width": width, "height": height, "fps": fps, "frames": len(frames), "seed": seed}]


for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    try:
        cmd = json.loads(raw)
    except Exception:
        continue
    c = cmd.get("cmd")
    try:
        if c == "offload":
            swap_gb, el_s, bw = _dma_offload_pipeline(pipe)
            el_ms = int(round(el_s * 1000))
            log(f"显存热切换完成: {swap_gb:.1f} GB 用时 {el_s:.2f}s ({bw:.1f} GB/s) [GPU → 176GB Pinned RAM]")
            emit(
                event="offloaded",
                vram_mb=int(torch.cuda.memory_allocated() / 2**20),
                swap_gb=swap_gb,
                elapsed_ms=el_ms,
                bw_gbps=bw,
            )
        elif c == "onload":
            swap_gb, el_s, bw = _dma_onload_pipeline(pipe)
            el_ms = int(round(el_s * 1000))
            log(f"显存热切换完成: {swap_gb:.1f} GB 用时 {el_s:.2f}s ({bw:.1f} GB/s) [176GB Pinned RAM → GPU]")
            emit(
                event="onloaded",
                vram_mb=int(torch.cuda.memory_allocated() / 2**20),
                swap_gb=swap_gb,
                elapsed_ms=el_ms,
                bw_gbps=bw,
            )
        elif c == "run":
            p = cmd["params"]
            out_dir = cmd["out_dir"]
            os.makedirs(out_dir, exist_ok=True)
            with torch.inference_mode():
                if cmd["task"] == "t2i":
                    outs = run_t2i(p, out_dir)
                else:
                    outs = run_video(p, out_dir)
            emit(event="done", outputs=outs)
        elif c == "exit":
            break
    except Exception as e:
        torch.cuda.empty_cache()
        emit(event="error", msg=f"{e.__class__.__name__}: {e}\n{traceback.format_exc()[-2500:]}")
