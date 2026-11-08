"""Long-lived NVIDIA Lyra 2.0 worker.

Loads the 14B Lyra model + DA3 + MoGe ONCE (saves ~5 min per run versus the CLI scripts),
keeps all three LoRAs (realism, detail, DMD) attached so "fast mode" is a free per-job toggle,
and supports offloading the DiT to Pinned 176GB DDR5 Host RAM via non-blocking PCIe Gen5 DMA
when another model needs the GPU.

Optimized for NVIDIA Blackwell (sm_120) / Hopper / Ada GPUs:
- TF32 + high-precision matmul + Flash/Mem-Efficient/cuDNN SDPA
- Preserves torch.backends.cudnn.enabled = True & benchmark = False after Lyra imports
  so 3D causal VAE Conv3D layers use cuDNN without workspace OOM on 481–721 frame long films
- Exports world.mp4, warp.mp4 (3DGS point-cloud forward warp), and split_3dgs.mp4
  (@NVIDIAAI style diagonal 3DGS / Video split showcase)
- Supports 15s (241f), 30s (481f), and 45s+ (721f+) flythrough & multi-segment chained tours

Run with cwd = Lyra-2 repo and PYTHONPATH = Lyra-2.
"""
import gc
import itertools
import json
import os
import sys
import time
import traceback
import types

MARK = "@@FORGE@@ "


def emit(**ev):
    sys.__stdout__.write("\n" + MARK + json.dumps(ev, ensure_ascii=False) + "\n")
    sys.__stdout__.flush()


def log(msg):
    emit(event="log", msg=str(msg))


try:
    import cv2
    import numpy as np
    import torch

    # --- Extreme Blackwell (sm_120) TensorCore & PyTorch 2.x SDPA Optimizations ---
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
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

    from lyra_2._ext.imaginaire.utils import misc
    from lyra_2._ext.imaginaire.visualize.video import save_img_or_video
    from lyra_2._src.inference import lyra2_ar_inference as AR
    from lyra_2._src.inference import lyra2_zoomgs_inference as ZG
    from lyra_2._src.inference.depth_utils import load_da3_model, load_moge_model, moge_infer_depth_intrinsics
    from lyra_2._src.inference.get_t5_emb import get_umt5_embedding_offloaded
    from lyra_2._src.utils.model_loader import load_model_from_checkpoint

    # CRITICAL FIX (from Lyra-2/gui/api/lyra_persistent.py):
    # Both lyra2_ar_inference and lyra2_zoomgs_inference set cudnn.enabled = False at import time!
    # Re-enable cuDNN with benchmark = False so WAN 3D VAE Conv3D layers use cuDNN without workspace OOM.
    torch.backends.cudnn.enabled = True
    torch.backends.cudnn.benchmark = False

    sys.argv = ["lyra_worker", "--input_image_path", "/tmp"]
    ARGS = ZG.parse_arguments()
    ARGS.experiment = "lyra2"
    ARGS.checkpoint_dir = "checkpoints/model"

    LORAS = [
        ("checkpoints/lora/realism_boost.safetensors", 0.4),
        ("checkpoints/lora/detail_enhancer.safetensors", 0.4),
        ("checkpoints/lora/dmd_distillation.safetensors", 0.0),
    ]
    LORAS = [(p, w) for p, w in LORAS if os.path.exists(p)]

    t0 = time.time()
    log(
        f"加载 Lyra 2.0 (Wan2.1 14B) · GPU={DEV_PROPS.name} ({ARCH_SM}, {TOTAL_VRAM_GB:.1f}GB VRAM, TF32+FlashSDPA+cuDNN3D 已开启) ..."
    )
    negative_prompt_data = torch.load("checkpoints/text_encoder/negative_prompt.pt", map_location="cpu",
                                      weights_only=False)
    model, _cfg = load_model_from_checkpoint(
        config_file="lyra_2/_src/configs/config.py",
        experiment_name=ARGS.experiment,
        checkpoint_path=ARGS.checkpoint_dir,
        enable_fsdp=False,
        instantiate_ema=False,
        load_ema_to_reg=False,
        experiment_opts=["model.config.use_mp_policy_fsdp=False", "model.config.keep_original_net_dtype=False",
                         "model.config.net.postpone_checkpoint=True"],
    )
    LORA_NAMES = [model.load_lora_weights(p) for p, _ in LORAS]
    model.set_weights_and_activate_adapters(LORA_NAMES, [w for _, w in LORAS])
    if hasattr(model, "net") and hasattr(model.net, "enable_selective_checkpoint"):
        model.net.enable_selective_checkpoint(model.net.sac_config, model.net.blocks)
    DTYPE = model.tensor_kwargs.get("dtype")
    DEVICE = model.tensor_kwargs.get("device")
    model.net = model.net.to(device=DEVICE, dtype=DTYPE, non_blocking=True)
    model.eval()
    log(f"Lyra 主模型就绪 ({time.time() - t0:.0f}s)，加载 DA3 / MoGe ...")
    da3_model = load_da3_model(da3_model_name=ARGS.da3_model_name, da3_model_path_custom=ARGS.da3_model_path_custom,
                               device=DEVICE)
    da3_model.eval()
    moge_model = load_moge_model(DEVICE)
    moge_model.eval()
    moge_model.cpu()
    torch.cuda.empty_cache()
    log(f"全部加载完成，用时 {time.time() - t0:.0f}s")
    emit(event="ready", vram_mb=int(torch.cuda.memory_allocated() / 2**20))
except Exception as e:
    emit(event="error", msg=f"Lyra 加载失败: {e}\n{traceback.format_exc()[-3000:]}")
    sys.exit(1)


def _dma_offload_modules(*mods) -> tuple:
    """Offload modules from GPU to Pinned DDR5 Host RAM via non-blocking PCIe DMA stream."""
    t0 = time.perf_counter()
    vram_before = torch.cuda.memory_allocated()
    total_bytes = 0
    seen_tensors = set()

    with torch.cuda.stream(DMA_STREAM):
        for mod in mods:
            if not isinstance(mod, torch.nn.Module):
                continue
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


def _dma_onload_modules(*mods) -> tuple:
    """Onload modules from Pinned DDR5 Host RAM to GPU via non-blocking PCIe DMA stream."""
    t0 = time.perf_counter()
    vram_before = torch.cuda.memory_allocated()
    total_bytes = 0
    seen_tensors = set()

    for mod in mods:
        if not isinstance(mod, torch.nn.Module):
            continue
        for t in itertools.chain(mod.parameters(), mod.buffers()):
            tid = id(t)
            if tid not in seen_tensors:
                seen_tensors.add(tid)
                if not t.is_cuda:
                    total_bytes += t.numel() * t.element_size()

    with torch.cuda.stream(DMA_STREAM):
        model.to(DEVICE, non_blocking=True)
        model.net = model.net.to(device=DEVICE, dtype=DTYPE, non_blocking=True)
        da3_model.to(DEVICE, non_blocking=True)
    DMA_STREAM.synchronize()
    gc.collect()
    vram_after = torch.cuda.memory_allocated()
    if total_bytes == 0 and vram_after > vram_before:
        total_bytes = vram_after - vram_before
    elapsed_s = max(time.perf_counter() - t0, 1e-4)
    swap_gb = round(total_bytes / (1024 ** 3), 2)
    bw_gbps = round(swap_gb / elapsed_s, 1) if swap_gb > 0 else 0.0
    return swap_gb, elapsed_s, bw_gbps


# --- progress hook: replace the tqdm used inside run_lyra2_sample -----------------
class _Prog:
    done = 0
    total = 1
    label = ""


def _tqdm(iterable, *a, **k):
    n = 0
    for x in iterable:
        emit(event="progress", p=round(min(0.99, (_Prog.done + n) / max(_Prog.total, 1)), 4),
             stage=f"{_Prog.label}生成第 {_Prog.done + n + 1}/{_Prog.total} 段（每段 80 帧）")
        yield x
        n += 1
    _Prog.done += n


AR.tqdm = types.SimpleNamespace(tqdm=_tqdm)

TEMPLATE = (
    "A cinematic drone shot glides smoothly forward through the scene: {scene}. "
    "The scene is a frozen tableau, frozen in time; every element is perfectly still. "
    "All structures, foliage, water, clouds, light and shadows remain absolutely stationary and unchanging. "
    "As the camera advances, more of the world is revealed, maintaining the same lighting, color palette, "
    "materials and textures. No wind, no motion of any kind; a silent, timeless, static world through which "
    "only the camera travels."
)


def _prepare_image(path, H, W):
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError(f"无法读取图片 {path}")
    h, w = bgr.shape[:2]
    target = W / H
    if abs(w / h - target) > 0.01:  # center-crop to the model aspect instead of stretching
        if w / h > target:
            nw = int(round(h * target))
            x0 = (w - nw) // 2
            bgr = bgr[:, x0:x0 + nw]
        else:
            nh = int(round(w / target))
            y0 = (h - nh) // 2
            bgr = bgr[y0:y0 + nh]
    return torch.from_numpy(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _estimate_depth_and_intrinsics(rgb_t: torch.Tensor, H: int, W: int, ground_align: bool = False):
    """Run DA3 depth + intrinsics and align inverse depth scale with MoGe."""
    image_chw01, depth_hw, K_33, mask_hw = ZG._da3_infer_depth_intrinsics_single(
        da3_model=da3_model, img_rgb_uint8=rgb_t, target_hw=(H, W)
    )
    moge_model.to(DEVICE, non_blocking=True)
    with torch.nn.attention.sdpa_kernel([torch.nn.attention.SDPBackend.MATH]):
        _, moge_depth_hw, _, moge_mask_hw = moge_infer_depth_intrinsics(
            moge_model, rgb_t, depth_pred_hw=(H, W), target_hw=(H, W)
        )
    da3_d = depth_hw.to(moge_depth_hw.device, non_blocking=True)
    valid = (mask_hw.to(moge_mask_hw.device, non_blocking=True) > 0.5) & (moge_mask_hw > 0.5)
    if valid.sum() > 10:
        inv_da3 = 1.0 / (da3_d[valid] + 1e-6)
        inv_moge = 1.0 / (moge_depth_hw[valid] + 1e-6)
        den = (inv_da3 * inv_da3).sum()
        if den > 1e-8:
            scale = (inv_da3 * inv_moge).sum() / den
            if scale > 1e-6:
                depth_hw = depth_hw / scale.to(depth_hw.device)
                log(f"MoGe 尺度对齐系数 {scale.item():.4f}")
    moge_model.cpu()
    del moge_depth_hw, moge_mask_hw, da3_d, valid
    torch.cuda.empty_cache()

    img_bchw = image_chw01.to(device=DEVICE, non_blocking=True) * 2.0 - 1.0
    ground = None
    if ground_align:
        ground = ZG._fit_ground_normal_from_depth(depth_hw, K_33, mask_hw, bottom_frac=0.4)
    return image_chw01, img_bchw, depth_hw, K_33, mask_hw, ground


def _compose_diagonal_split(vid01: torch.Tensor, warp01: torch.Tensor) -> torch.Tensor:
    """Create @NVIDIAAI style diagonal split (top-left 3DGS warp_video / bottom-right rendered video)."""
    _, T, H, W = vid01.shape
    if warp01.shape[1] != T or warp01.shape[2] != H or warp01.shape[3] != W:
        warp01 = torch.nn.functional.interpolate(
            warp01.unsqueeze(0), size=(T, H, W), mode="trilinear", align_corners=False
        ).squeeze(0)

    yy = torch.linspace(0.0, 1.0, H, dtype=torch.float32).view(1, 1, H, 1)
    xx = torch.linspace(0.0, 1.0, W, dtype=torch.float32).view(1, 1, 1, W)
    # Slash '/' diagonal passing through center (top x=0.68 -> bottom x=0.32)
    dist = (xx + 0.36 * yy) - 0.68
    alpha = ((dist / 0.004) * 0.5 + 0.5).clamp(0.0, 1.0)
    split01 = warp01 * (1.0 - alpha) + vid01 * alpha
    # Crisp anti-aliased white divider line
    line_mask = ((1.0 - (dist.abs() / 0.0032).clamp(0.0, 1.0)) ** 2) * 0.92
    split01 = split01 * (1.0 - line_mask) + line_mask

    # Render static corner badges ("3DGS" top-left, "Video" bottom-right) once with OpenCV
    try:
        badge = np.zeros((H, W, 4), dtype=np.uint8)
        cv2.putText(badge, "3DGS", (20, 42), cv2.FONT_HERSHEY_DUPLEX, 0.95, (255, 255, 255, 220), 2, cv2.LINE_AA)
        cv2.putText(badge, "Video", (W - 110, H - 22), cv2.FONT_HERSHEY_DUPLEX, 0.95, (255, 255, 255, 220), 2, cv2.LINE_AA)
        b_rgb = torch.from_numpy(badge[:, :, :3].astype(np.float32) / 255.0).permute(2, 0, 1).unsqueeze(1)
        b_a = torch.from_numpy(badge[:, :, 3:4].astype(np.float32) / 255.0).permute(2, 0, 1).unsqueeze(1)
        split01 = split01 * (1.0 - b_a) + b_rgb * b_a
    except Exception:
        pass
    return split01.clamp(0.0, 1.0)


def run(p, out_dir):
    # Ensure cuDNN Conv3D stays enabled with benchmark=False for long-sequence VAE decoding
    torch.backends.cudnn.enabled = True
    torch.backends.cudnn.benchmark = False

    a = ARGS
    H, W = [int(x) for x in str(p.get("resolution", "480,832")).split(",")]
    a.resolution = f"{H},{W}"
    dmd = bool(p.get("dmd", True))
    a.use_dmd = dmd
    a.use_dmd_scheduler = dmd
    a.num_sampling_step = int(p.get("steps", 50))
    a.guidance = float(p.get("guidance", 5.0))
    a.shift = float(p.get("shift", 5.0))
    a.seed = int(p.get("seed", 1))
    a.fps = int(p.get("fps", 16))
    weights = [w for _, w in LORAS]
    if len(weights) == 3:
        weights[2] = 1.0 if dmd else 0.0
    model.set_weights_and_activate_adapters(LORA_NAMES, weights)
    misc.set_random_seed(seed=a.seed, by_rank=True)

    emit(event="progress", p=0.01, stage="深度估计 (DA3 + MoGe 逆深度尺度对齐)")
    rgb_t = _prepare_image(p["image_path"], H, W)
    ground_align = bool(p.get("ground_align", False))
    image_chw01, img_bchw, depth_hw, K_33, mask_hw, ground = _estimate_depth_and_intrinsics(
        rgb_t, H, W, ground_align=ground_align
    )

    caption = (p.get("caption") or "").strip()
    if not caption:
        scene = (p.get("scene") or "a breathtaking, richly detailed world").strip().rstrip(".")
        caption = TEMPLATE.format(scene=scene)
    log("提示词: " + caption)
    with open(os.path.join(out_dir, "caption.txt"), "w") as f:
        f.write(caption)
    t5 = get_umt5_embedding_offloaded(caption, device=DEVICE).to(dtype=DTYPE)
    if t5.dim() == 2:
        t5 = t5.unsqueeze(0)
    elif t5.dim() == 3 and t5.shape[0] != 1:
        t5 = t5[:1]
    neg_t5 = misc.to(negative_prompt_data["t5_text_embeddings"], **model.tensor_kwargs)

    common = dict(model=model, args=a, img_bchw=img_bchw, depth_hw=depth_hw, mask_hw=mask_hw, K_33=K_33,
                  t5_embeddings=t5, neg_t5_embeddings=neg_t5, da3_model=da3_model, process_group=None,
                  ground_normal_cam=ground)

    mode = p.get("mode", "flythrough")
    segments = p.get("segments")
    t_start = time.time()
    warp = None

    if mode in ("chained", "long_tour") or (isinstance(segments, list) and len(segments) > 0):
        # Multi-segment chained long-film tour (e.g. 481-721+ frames across multiple trajectories)
        if not isinstance(segments, list) or len(segments) == 0:
            n_out = int(p.get("zoom_out_frames") or p.get("frames_out") or 241)
            n_in = int(p.get("zoom_in_frames") or p.get("frames_in") or 241)
            n_chain = int(p.get("chain_frames") or 241)
            segments = [
                {
                    "trajectory": str(p.get("zoom_out_trajectory") or "horizontal_zoom"),
                    "direction": str(p.get("zoom_out_direction") or "left"),
                    "strength": float(p.get("zoom_out_strength") or p.get("strength_out") or 1.5),
                    "frames": n_out,
                    "reverse": True,
                    "upward_ratio": float(p.get("upward_ratio", 0.15)),
                    "label": "后退抬升段",
                },
                {
                    "trajectory": str(p.get("zoom_in_trajectory") or "horizontal_zoom"),
                    "direction": str(p.get("zoom_in_direction") or "right"),
                    "strength": float(p.get("zoom_in_strength") or p.get("strength_in") or 3.0),
                    "frames": n_in,
                    "reverse": False,
                    "label": "主轴前推段",
                },
                {
                    "trajectory": str(p.get("chain_trajectory") or "horizontal_spiral"),
                    "direction": str(p.get("chain_direction") or "right"),
                    "strength": float(p.get("chain_strength") or 2.0),
                    "frames": n_chain,
                    "reverse": False,
                    "reanchor": True,
                    "label": "接力漫游段",
                },
            ]
        _Prog.done = 0
        _Prog.total = sum(max(1, (int(s.get("frames", 241)) - 1) // 80) for s in segments if int(s.get("frames", 0)) > 1)
        vid_parts, warp_parts = [], []
        cur_common = dict(common)

        for idx, seg in enumerate(segments):
            n_seg = int(seg.get("frames", 241))
            if n_seg <= 1:
                continue
            if seg.get("reanchor") and vid_parts:
                emit(event="progress", p=round(_Prog.done / max(_Prog.total, 1), 4), stage=f"段间 3D 深度重锚定 (#{idx + 1})")
                last_f = vid_parts[-1][:, :, -1]  # [1, 3, H, W] in [-1, 1]
                last_rgb = ((last_f[0].clamp(-1, 1) * 0.5 + 0.5).permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
                _, next_bchw, next_depth, next_K, next_mask, next_ground = _estimate_depth_and_intrinsics(
                    torch.from_numpy(last_rgb), H, W, ground_align=ground_align
                )
                cur_common = dict(
                    common,
                    img_bchw=next_bchw,
                    depth_hw=next_depth,
                    mask_hw=next_mask,
                    K_33=next_K,
                    ground_normal_cam=next_ground,
                )

            _Prog.label = f"{seg.get('label') or f'第{idx + 1}镜'} · "
            up_ratio = float(seg.get("upward_ratio", 0.0))
            res_seg = ZG._generate_one_direction(
                **cur_common,
                trajectory=seg.get("trajectory", "horizontal_zoom"),
                direction=seg.get("direction", "right"),
                strength=float(seg.get("strength", 2.0)),
                N=n_seg,
                log_prefix=f"seg_{idx + 1}",
                upward_shift=a.zoom_out_upward_shift if up_ratio > 0 else 0.0,
                zoom_out_upward_ratio=up_ratio,
            )
            gc.collect()
            torch.cuda.empty_cache()
            v_seg = res_seg["video"].flip(dims=[2]) if seg.get("reverse") else res_seg["video"]
            w_seg = (
                (res_seg["warp_video"].flip(dims=[2]) if seg.get("reverse") else res_seg["warp_video"])
                if res_seg.get("warp_video") is not None
                else None
            )
            if vid_parts:
                v_seg = v_seg[:, :, 1:]
                if w_seg is not None:
                    w_seg = w_seg[:, :, 1:]
            vid_parts.append(v_seg)
            if w_seg is not None:
                warp_parts.append(w_seg)

        video = torch.cat(vid_parts, dim=2)
        if len(warp_parts) == len(vid_parts):
            warp = torch.cat(warp_parts, dim=2)

    elif mode == "flythrough":
        n_in = int(p.get("zoom_in_frames") or p.get("frames_in") or p.get("num_frames_zoom_in") or 241)
        n_out = int(p.get("zoom_out_frames") or p.get("frames_out") or p.get("num_frames_zoom_out") or 241)
        str_in = float(p.get("zoom_in_strength") or p.get("strength_in") or 3.0)
        str_out = float(p.get("zoom_out_strength") or p.get("strength_out") or 1.5)
        traj_in = str(p.get("zoom_in_trajectory") or p.get("trajectory_in") or "horizontal_zoom")
        traj_out = str(p.get("zoom_out_trajectory") or p.get("trajectory_out") or "horizontal_zoom")
        dir_in = str(p.get("zoom_in_direction") or p.get("direction_in") or "right")
        dir_out = str(p.get("zoom_out_direction") or p.get("direction_out") or "left")

        _Prog.done = 0
        _Prog.total = max(1, (max(n_in, 1) - 1) // 80 + (max(n_out, 1) - 1) // 80)
        res_in, res_out = None, None
        if n_in > 1:
            _Prog.label = "前推段 · "
            res_in = ZG._generate_one_direction(**common, trajectory=traj_in, direction=dir_in,
                                                strength=str_in, N=n_in, log_prefix="zoom_in")
            gc.collect(); torch.cuda.empty_cache()
        if n_out > 1:
            _Prog.label = "后退段 · "
            res_out = ZG._generate_one_direction(**common, trajectory=traj_out, direction=dir_out,
                                                 strength=str_out, N=n_out, log_prefix="zoom_out",
                                                 upward_shift=a.zoom_out_upward_shift,
                                                 zoom_out_upward_ratio=float(p.get("upward_ratio", 0.15)))
            gc.collect(); torch.cuda.empty_cache()

        # reversed retreat + forward push = one continuous forward fly-through (481-721 frames = 30s-45s)
        if res_out is not None and res_in is not None:
            video = torch.cat([res_out["video"].flip(dims=[2]), res_in["video"][:, :, 1:]], dim=2)
            if res_out.get("warp_video") is not None and res_in.get("warp_video") is not None:
                warp = torch.cat([res_out["warp_video"].flip(dims=[2]), res_in["warp_video"][:, :, 1:]], dim=2)
        elif res_in is not None:
            video = res_in["video"]
            warp = res_in.get("warp_video")
        else:
            video = res_out["video"].flip(dims=[2])
            warp = res_out["warp_video"].flip(dims=[2]) if res_out.get("warp_video") is not None else None
    else:
        n = int(p.get("frames") or p.get("zoom_in_frames") or p.get("frames_in") or 241)
        _Prog.done, _Prog.total, _Prog.label = 0, max(1, (n - 1) // 80), ""
        res = ZG._generate_one_direction(**common, trajectory=p.get("trajectory", "horizontal_zoom"),
                                         direction=p.get("direction", "right"),
                                         strength=float(p.get("strength", 1.5)), N=n, log_prefix="single")
        video = res["video"]
        warp = res.get("warp_video")

    emit(event="progress", p=0.992, stage="编码 3D 世界视频与 3DGS 点云对比视频")
    vid01 = (video[0].clamp(-1, 1) * 0.5 + 0.5).float().cpu()
    save_img_or_video(vid01, os.path.join(out_dir, "world"), fps=a.fps)

    outputs = [
        {"path": os.path.join(out_dir, "world.mp4"), "kind": "video", "name": "world.mp4", "label": "3D 世界穿梭成片"},
    ]

    if warp is not None:
        try:
            warp01 = (warp[0].clamp(-1, 1) * 0.5 + 0.5).float().cpu()
            if p.get("save_split", True):
                split01 = _compose_diagonal_split(vid01, warp01)
                save_img_or_video(split01, os.path.join(out_dir, "split_3dgs"), fps=a.fps)
                outputs.append({
                    "path": os.path.join(out_dir, "split_3dgs.mp4"),
                    "kind": "video",
                    "name": "split_3dgs.mp4",
                    "label": "3DGS vs Video 斜切分屏",
                })
                del split01
            if p.get("save_warp", True):
                save_img_or_video(warp01, os.path.join(out_dir, "warp"), fps=a.fps)
                outputs.append({
                    "path": os.path.join(out_dir, "warp.mp4"),
                    "kind": "video",
                    "name": "warp.mp4",
                    "label": "3DGS 点云投影",
                })
            del warp01
        except Exception as e:
            log(f"保存 3DGS 辅助视频跳过: {e}")

    first = (image_chw01[0].permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
    cv2.imwrite(os.path.join(out_dir, "input_frame.png"), cv2.cvtColor(first, cv2.COLOR_RGB2BGR))
    outputs.append({"path": os.path.join(out_dir, "input_frame.png"), "kind": "image", "name": "input_frame.png"})

    total_frames = int(vid01.shape[1])
    dur_s = total_frames / max(a.fps, 1)
    log(f"完成：{total_frames} 帧 ({dur_s:.1f}s @{a.fps}fps)，含 3DGS 分屏对比，总用时 {time.time() - t_start:.0f}s")
    del video, vid01, warp
    gc.collect(); torch.cuda.empty_cache()
    return outputs


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
            swap_gb, el_s, bw = _dma_offload_modules(model, da3_model)
            el_ms = int(round(el_s * 1000))
            log(f"显存热切换完成: {swap_gb:.1f} GB 用时 {el_s:.2f}s ({bw:.1f} GB/s) [Lyra GPU → 176GB Pinned RAM]")
            emit(
                event="offloaded",
                vram_mb=int(torch.cuda.memory_allocated() / 2**20),
                swap_gb=swap_gb,
                elapsed_ms=el_ms,
                bw_gbps=bw,
            )
        elif c == "onload":
            swap_gb, el_s, bw = _dma_onload_modules(model, da3_model)
            el_ms = int(round(el_s * 1000))
            log(f"显存热切换完成: {swap_gb:.1f} GB 用时 {el_s:.2f}s ({bw:.1f} GB/s) [176GB Pinned RAM → Lyra GPU]")
            emit(
                event="onloaded",
                vram_mb=int(torch.cuda.memory_allocated() / 2**20),
                swap_gb=swap_gb,
                elapsed_ms=el_ms,
                bw_gbps=bw,
            )
        elif c == "run":
            os.makedirs(cmd["out_dir"], exist_ok=True)
            with torch.no_grad():
                outs = run(cmd["params"], cmd["out_dir"])
            emit(event="done", outputs=outs)
        elif c == "exit":
            break
    except Exception as e:
        gc.collect(); torch.cuda.empty_cache()
        emit(event="error", msg=f"{e.__class__.__name__}: {e}\n{traceback.format_exc()[-3000:]}")
