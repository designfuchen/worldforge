"""One-click environment installer for the Colab VM (idempotent; safe to re-run).

  python3 setup_env.py --component all|qwen|lyra

Lyra 2.0 on Blackwell (sm_120) needs two source patches (flash-attn / transformer-engine
are unavailable there); they are applied automatically.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

def _resolve_base_dir() -> str:
    env_root = (os.environ.get("WORLDFORGE_ROOT") or "").strip()
    if env_root:
        return os.path.abspath(os.path.expanduser(env_root))
    if os.path.isdir("/content") and os.access("/content", os.W_OK):
        return "/content"
    d = os.path.abspath(os.path.expanduser("~/worldforge_data"))
    os.makedirs(d, exist_ok=True)
    return d


BASE_DIR = _resolve_base_dir()
LYRA_ROOT = os.environ.get("WORLDFORGE_LYRA_ROOT") or f"{BASE_DIR}/lyra"
LYRA_DIR = os.environ.get("WORLDFORGE_LYRA_DIR") or f"{LYRA_ROOT}/Lyra-2"
QWEN_VENV = os.environ.get("WORLDFORGE_QWEN_VENV") or f"{BASE_DIR}/qwen_venv"


def emit(p, stage):
    print("@@FORGE@@ " + json.dumps({"event": "progress", "p": p, "stage": stage}, ensure_ascii=False), flush=True)


def sh(cmd, cwd=None, check=True):
    print(f"$ {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, cwd=cwd)
    if check and r.returncode != 0:
        raise SystemExit(f"命令失败 (exit {r.returncode}): {cmd}")
    return r.returncode


def py_ok(code, py="python3", cwd=None, env_extra=None):
    env = dict(os.environ, **(env_extra or {}))
    return subprocess.run([py, "-c", code], cwd=cwd, env=env, capture_output=True).returncode == 0


def _create_venv(venv_dir: str):
    if os.path.exists(f"{venv_dir}/bin/python"):
        return
    if shutil.which("uv"):
        sh(f"uv venv --seed --system-site-packages {venv_dir}")
    else:
        sh(f"{sys.executable} -m venv --system-site-packages {venv_dir}")


def setup_qwen(base, span):
    emit(base, "Qwen-Image：检查独立环境")
    _create_venv(QWEN_VENV)
    if not py_ok("import diffusers, transformers; from diffusers import QwenImage21Pipeline", f"{QWEN_VENV}/bin/python"):
        emit(base + span * 0.2, "Qwen-Image：安装 diffusers(main) + transformers>=5.17")
        sh(f'{QWEN_VENV}/bin/python -m pip install -q --upgrade git+https://github.com/huggingface/diffusers.git '
           f'"transformers>=5.17.0" accelerate pillow huggingface_hub hf_transfer safetensors sentencepiece imageio imageio-ffmpeg')
    else:
        print("Qwen 环境已就绪，跳过", flush=True)
    emit(base + span, "Qwen-Image 环境就绪（权重在首次加载时自动下载）")


WAN_OLD = """import transformer_engine as te
from flash_attn.layers.rotary import apply_rotary_emb as flash_apply_rotary_emb
from transformer_engine.pytorch.attention import DotProductAttention
from transformer_engine.pytorch.attention.rope import apply_rotary_pos_emb"""

WAN_NEW = '''import torch.nn.functional as _F
from einops import rearrange as _rearrange

def flash_apply_rotary_emb(x, cos, sin, interleaved=False, inplace=False):
    orig_dtype = x.dtype
    x_f = x.float()
    if interleaved:
        x1 = x_f[..., 0::2]
        x2 = x_f[..., 1::2]
        cos_u = cos.unsqueeze(-2) if x.ndim == 3 else cos.unsqueeze(0).unsqueeze(-2)
        sin_u = sin.unsqueeze(-2) if x.ndim == 3 else sin.unsqueeze(0).unsqueeze(-2)
        o1 = x1 * cos_u - x2 * sin_u
        o2 = x1 * sin_u + x2 * cos_u
        out = torch.stack([o1, o2], dim=-1).flatten(-2)
    else:
        d = x_f.shape[-1] // 2
        x1, x2 = x_f[..., :d], x_f[..., d:]
        cos_u = cos.unsqueeze(-2) if x.ndim == 3 else cos.unsqueeze(0).unsqueeze(-2)
        sin_u = sin.unsqueeze(-2) if x.ndim == 3 else sin.unsqueeze(0).unsqueeze(-2)
        out = torch.cat([x1 * cos_u - x2 * sin_u, x1 * sin_u + x2 * cos_u], dim=-1)
    return out.to(orig_dtype)

class DotProductAttention(torch.nn.Module):
    def __init__(self, *args, **kwargs):
        super().__init__()
    def forward(self, q, k, v, *args, **kwargs):
        q_t = q.permute(1, 2, 0, 3).contiguous()
        k_t = k.permute(1, 2, 0, 3).contiguous()
        v_t = v.permute(1, 2, 0, 3).contiguous()
        out = _F.scaled_dot_product_attention(q_t, k_t, v_t, dropout_p=0.0, is_causal=False)
        return out.permute(2, 0, 1, 3).contiguous().flatten(2)'''


def _need_blackwell_patch():
    try:
        import torch

        return torch.cuda.get_device_capability(0)[0] >= 12
    except Exception:
        return False


def setup_lyra(base, span):
    emit(base, "Lyra 2.0：拉取源码")
    if not os.path.isdir(LYRA_DIR):
        sh(f"git clone --depth 1 https://github.com/nv-tlabs/lyra.git {LYRA_ROOT}")
    emit(base + span * 0.1, "Lyra 2.0：安装依赖")
    probe = ("import depth_anything_3, utils3d, moge, megatron.core, boto3, moviepy, pycolmap, loguru, peft, omegaconf, decord")
    if not py_ok(probe):
        sh("uv pip uninstall --system torchao || true", check=False)
        sh('uv pip install --system --no-build-isolation '
           '"git+https://github.com/EasternJournalist/utils3d.git@c5daf6f6c244d2a1f252102d0ebeff4b7b4fd911" '
           '"git+https://github.com/ByteDance-Seed/Depth-Anything-3.git@b972f56722ff9feb86ef6fc3ebfe6efe3ab5b4be" '
           '"git+https://github.com/microsoft/MoGe.git" '
           'loguru einops fvcore iopath ftfy pycocotools scikit-image matplotlib imageio imageio-ffmpeg attrs omegaconf '
           'decord peft plyfile trimesh diffusers transformers timm accelerate huggingface_hub hf_transfer safetensors addict '
           'pycolmap boto3 "megatron-core==0.12.1" evo moviepy')
    else:
        print("Lyra 依赖已就绪，跳过", flush=True)

    emit(base + span * 0.3, "Lyra 2.0：应用 Blackwell(sm_120) / Ada(sm_89 4090) 兼容补丁")
    att = f"{LYRA_DIR}/lyra_2/_src/modules/attention.py"
    code = open(att).read()
    if "[80, 86, 89, 90, 100, 120]" not in code:
        for old_cap in ("if compute_cap in [90, 100] and is_half:", "if compute_cap in [90, 100, 120] and is_half:"):
            if old_cap in code:
                code = code.replace(old_cap, "if compute_cap in [80, 86, 89, 90, 100, 120] and is_half:")
        open(att, "w").write(code)
    wan = f"{LYRA_DIR}/lyra_2/_src/networks/wan2pt1.py"
    wcode = open(wan).read()
    te_ok = py_ok("import transformer_engine, flash_attn")
    if WAN_OLD in wcode and (not te_ok or _need_blackwell_patch()):
        open(wan, "w").write(wcode.replace(WAN_OLD, WAN_NEW))
        print("已打补丁: wan2pt1.py → PyTorch SDPA (支持 RTX 4090 / RTX 5090 / PRO 6000)", flush=True)

    emit(base + span * 0.4, "Lyra 2.0：下载权重（约 100GB，16 线程并发）")
    ck = f"{LYRA_DIR}/checkpoints"
    if not os.path.isdir(f"{ck}/model") or not os.path.exists(f"{ck}/recon/model.pt"):
        from huggingface_hub import snapshot_download

        snapshot_download("nvidia/Lyra-2.0", allow_patterns=["checkpoints/*"], local_dir=LYRA_DIR, max_workers=16)
        nested = f"{ck}/checkpoints"
        if os.path.isdir(nested):  # flatten accidental nesting
            for n in os.listdir(nested):
                if not os.path.exists(f"{ck}/{n}"):
                    shutil.move(f"{nested}/{n}", f"{ck}/{n}")
    else:
        print("Lyra 权重已存在，跳过", flush=True)
    emit(base + span * 0.95, "Lyra 2.0：自检")
    ok = py_ok("from lyra_2._src.inference.depth_utils import _import_da3_api, load_moge_model; _import_da3_api()",
               cwd=LYRA_DIR, env_extra={"PYTHONPATH": LYRA_DIR})
    print("自检:", "通过" if ok else "失败（请查看日志）", flush=True)
    if not ok:
        raise SystemExit("Lyra 自检失败")
    emit(base + span, "Lyra 2.0 就绪")


BREEZE_VENV = os.environ.get("WORLDFORGE_BREEZE_VENV") or f"{BASE_DIR}/breeze_venv"
BREEZE_CODE = os.environ.get("WORLDFORGE_BREEZE_CODE") or f"{BASE_DIR}/breeze_tts"


def setup_breeze(base, span):
    emit(base, "Breeze-TTS-2：检查独立语音推理环境")
    _create_venv(BREEZE_VENV)
    if not os.path.isdir(BREEZE_CODE):
        emit(base + span * 0.2, "Breeze-TTS-2：拉取官方推理源码")
        sh(f"git clone --depth 1 https://github.com/breezeblue-ai/breeze-tts.git {BREEZE_CODE}")
    if not py_ok("import qwen_tts, soundfile, transformers", f"{BREEZE_VENV}/bin/python"):
        emit(base + span * 0.5, "Breeze-TTS-2：安装 qwen-tts==0.1.1 + soundfile")
        sh(f'{BREEZE_VENV}/bin/python -m pip install -q "qwen-tts==0.1.1" "transformers>=4.51.0,<5.0.0" soundfile accelerate safetensors')
    else:
        print("Breeze-TTS-2 依赖已就绪，跳过", flush=True)
    emit(base + span, "Breeze-TTS-2 环境就绪 (0 MB 显存云盘架构)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--component", default="all", choices=["all", "qwen", "lyra", "breeze"])
    c = ap.parse_args().component
    print(f"数据目录 ({BASE_DIR}) 磁盘剩余: {shutil.disk_usage(BASE_DIR).free / 1e9:.0f} GB", flush=True)
    if c == "qwen":
        setup_qwen(0.0, 1.0)
    elif c == "lyra":
        setup_lyra(0.0, 1.0)
    elif c == "breeze":
        setup_breeze(0.0, 1.0)
    else:
        setup_qwen(0.0, 0.2)
        setup_breeze(0.2, 0.1)
        setup_lyra(0.3, 0.7)
    emit(1.0, "全部完成")
    print("SETUP_DONE", flush=True)
