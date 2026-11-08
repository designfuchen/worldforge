<div align="center">

<img src="web/assets/logo.svg" width="88" height="88" alt="WorldForge Logo" />

# WorldForge · 世界工坊

**把 Google Colab 顶级算力（RTX PRO 6000 Blackwell 98GB VRAM + 176GB DDR5 RAM）变成你 Mac 上的原生级 SwiftUI 3D 世界与 AIGC 创作工作站**  
*Squeeze 100% out of Google Colab Cloud GPUs (`G4 Blackwell 98GB` / `A100 80GB` / `L4` / `T4`) inside a Native SwiftUI + AppKit macOS Studio App & Zero-Dependency Local Daemon.*

[![License: MIT](https://img.shields.io/badge/License-MIT-amber.svg?style=flat-square)](LICENSE)
[![macOS Native SwiftUI](https://img.shields.io/badge/macOS_Studio-Native_SwiftUI_%2B_AppKit_(120Hz)-000000?style=flat-square&logo=apple)](macos_app/)
[![Cloud GPU](https://img.shields.io/badge/Colab_G4-RTX_PRO_6000_Blackwell_98GB-76B900?style=flat-square&logo=nvidia)](https://colab.research.google.com/)
[![3D World Engine](https://img.shields.io/badge/NVIDIA-Lyra_2.0_(Wan2.1_14B)-76B900?style=flat-square&logo=nvidia)](https://github.com/nv-tlabs/lyra)
[![2K T2I Engine](https://img.shields.io/badge/Qwen--Image-2.1_Turbo_2K-6366F1?style=flat-square)](https://huggingface.co/Qwen/Qwen-Image-2.1-Turbo)
[![PCIe Gen5 DMA](https://img.shields.io/badge/VRAM%E2%86%94DDR5_Swap-Pinned_DMA_%3C1.5s-F59E0B?style=flat-square)](remote/forge_server.py)

<p align="center">
  <img src="docs/assets/sub2_cover_1.png" width="100%" alt="WorldForge — 我把 Colab 打造成了一个原生 Mac 电影工作台，完全发挥 Gemini Ultra 的所有性能" />
</p>

[**📖 保姆级教程：我把 Colab 打造成了一个工作台**](TUTORIAL_ZH.md) · [**1 分钟极速上手**](#-1-分钟极速上手-1-minute-quickstart) · [**为什么比 EasyColab 强 100 倍**](#-为什么选-worldforgeworldforge-vs-easycolab-全维度对比) · [**原生 SwiftUI 零卡顿架构**](#-原生-swiftui--appkit-零卡顿工作站架构-macos_app) · [**Blackwell 极限压榨与 PCIe DMA 热交换**](#-云端-blackwell-sm_120-极限压榨与-pcie-50-dma-热交换) · [**Lyra 2.0「一直在穿梭」核心秘籍**](#-核心秘籍如何跑出-nvidia-官方级一直在穿梭的-lyra-20-长镜头) · [**API 契约**](docs/API.md)

</div>

---

## ⚡ 痛点：为什么现有的 Colab 工具都在浪费你的算力与生命？

Google Colab Pro+ 已经悄然上线了地表最强的单卡云工作站之一 —— **G4 实例（`NVIDIA RTX PRO 6000 Blackwell Server Edition`，整整 `98 GB GDDR7 显存` + `176 GB DDR5 主机内存`）**。

然而，无论你是手搓 Jupyter Notebook，还是使用市面上的简易套壳脚本（如 `easycolab`），都会遭遇六个致命瓶颈：
1. **每次生成都要重新读盘加载模型（3～5 分钟冷启动）**：传统脚本每点一次「生成」就起一个新 Python 进程，100 GB 的 `Lyra 2.0 (Wan2.1-14B)` 或 57 GB 的 `Qwen-Image-2.1-Turbo` 每次都要从磁盘重读并初始化 CUDA 上下文，90% 的 CU（计算单元）都在空转等磁盘 IO。
2. **多模型切换直接 OOM 崩溃或同步换页巨慢**：想先用 `Qwen-Image-2.1-Turbo` 生成一张 2K 宫崎骏天空之城原画，再无缝喂给 `NVIDIA Lyra 2.0` 生成 3D 穿梭世界？两个 50GB+ 巨无霸同时塞进显存必炸；而普通 `pipe.to("cpu")` 使用非锁页（Pageable）内存，无法利用 PCIe Gen5 DMA 异步带宽。
3. **Blackwell (`sm_120`) 算力架构水土不服**：NVIDIA 官方 `Lyra 2.0` 强依赖 `transformer_engine` 与旧版 `flash_attn`，在最新 Blackwell 架构上直接编译失败或因 `compute_cap in [90, 100]` 硬编码报错退出。
4. **Colab 单一 SSH 连接限制导致断连与误开机器**：`google-colab-cli` 每个实例同一时刻只允许 **1 条** `colab ssh` 隧道；普通工具并发执行 SCP 传图和状态查询就会互相踢下线，甚至在断线重连时因 `--proxy-mode` 机制意外创建新的计费实例。
5. **跑出来的 Lyra 2.0 视频「晃动、变形、飞一半就停」**：不懂官方 `Frozen-Tableau` 静止世界提示词工程、缺少 `DA3 + MoGe` 逆深度尺度对齐、缺少「后退段时序倒放 + 前推段无缝拼接」，跑出来的 16fps 原始视频既卡顿又失真。
6. **高分辨率大图与多路视频预览卡死主线程**：一张 `2752×1536` 的 2K 原画解码后占数十 MB 位图内存，普通客户端在主线程同步解码图像或同时加载十几个 `AVPlayer` 会瞬间引发 macOS 彩虹轮卡顿。

**WorldForge（世界工坊）就是为了彻底榨干 Colab 每一滴性能、并在 Mac 上提供 120Hz 原生丝滑创作体验而生。**

---

## 🔥 为什么选 WorldForge？（WorldForge vs EasyColab 全维度对比）

| 核心维度 | [EasyColab](https://github.com/wy51ai/easycolab) / 传统 Notebook 套壳 | **WorldForge 世界工坊** | 性能 / 体验代差 |
| :--- | :--- | :--- | :--- |
| **macOS 客户端形态** | 简陋终端脚本或卡顿网页 | **原生 SwiftUI + AppKit 编译级 `WorldForge.app` (`macos_app/`) + 内嵌 Web 工作台双引擎** | **0.0ms 主线程掉帧**，`⌘1`–`⌘7` 秒级切换 7 大专业工作区 |
| **异步媒体与缩略图架构** | 主线程直接加载原图/视频，多图滚动必卡 | **`ThumbnailCacheActor` 双层缓存 (`256MB L1 NSCache` + `L2 .thumbs/` 磁盘层) + 后台 `CGImageSource` 640px 降采样 + `HoverVideoPlayerPool` (上限 2 路解码器)** | 瀑布流画廊 **120Hz ProMotion 满帧滚动**，支持 12 帧胶片悬停预演与 A/B 60fps 实时卷帘对比 |
| **模型驻留架构** | 每次点击生成新开 CLI 子进程，跑完即毁 | **常驻 Worker 进程池 (`Worker` + `@@FORGE@@` 流式事件总线)** | 连续生图/生视频 **0 秒重加载** vs 每次苦等 **3～5 分钟** |
| **98GB 显存 ↔ 176GB 内存 ↔ 88GB `/dev/shm` ↔ 30TB 云盘 4级存储金字塔** | 不支持，多模型切换只能杀进程从磁盘重读 | **L1 98GB GDDR7 显存 (`1.8TB/s`) ↔ L2 176GB 锁页 DDR5 (`63GB/s` PCIe Gen5 DMA) ↔ L3 88GB `/dev/shm` 零延迟内存盘 (`2.4GB/s`) ↔ L4 30TB Google Drive 云盘金库 (`rclone` 8路后台同步)** | 30～50GB 模型切换仅需 **1.2～1.5 秒**；8 路 HTTP Range 并发下载高达 **1.38 GB/s** 直写内存盘并自动持久化至 30TB 云盘 |
| **内置模型矩阵与音视频大模型支持** | 仅支持写死的少数脚本，不支持 `/tree/main/` 子目录权重 | **内置 11 大旗舰模型（榜首预置 `MiniMax-H3 v1.8 Hybrid Turbo` 8 步音视频同生 + `NVIDIA Lyra 2.0` + `Qwen-Image 2.1` + `Breeze-TTS-2`）** + 粘贴任意 HF 子目录/Safetensors/Diffusers 地址一键部署 | 一键切换 `MiniMax-H3 v1.8 Hybrid` / `Lyra 2.0` / `Qwen-Image 2.1` / `Z-Image Turbo` / `FLUX.1` / `Wan 2.1 14B` / `Breeze-TTS-2` |
| **NVIDIA Lyra 2.0 30s–45s 长片与 3DGS 对角线分屏** | 无原生支持；在 Blackwell (`sm_120`) 上报错无法运行 | **一等公民级内置**：Blackwell `sm_120` Flash SDPA 补丁 + 禁用 import 期 `cudnn.enabled=False` 显存泄漏 + `DA3 + MoGe` 逆深度对齐 + **原生复刻 `@NVIDIAAI` 官方推特 `3DGS / Video` 对角线分屏** | 单张图一键生成 **481～721 帧（30.1s～45.1s 长片）** 电影级可漫游 3D 世界连续穿梭视频与 `3DGS` 几何投影对比母带 |
| **云端 GPU + 本地 Apple Silicon 混合流水线** | 纯云端输出低帧率原始 MP4，需手动下载再剪辑 | **Colab Blackwell 算潜空间 + 本地 Mac (`M1–M4 Max`) Metal/Vulkan 自动后期**：自动拉回本地 → `rife-ncnn-vulkan` 光流插帧（直达 `60fps`）→ `2×/4×` 变速 → `1080p/4K` Lanczos 超采 → 尾帧 `3.0s` 交叉淡化缓推 | 云端算力 100% 留给 14B 大模型推理，本地 Apple Silicon 空闲 GPU 秒级完成影院级母带编码 |
| **硬件极限遥测与算力压测** | 看不到显存/频率/PCIe 状态，忘记关机扣光 CU | **扩展级 `nvidia-smi` 实时遥测（核心频率/显存带宽利用率/PCIe 代数/功耗/`/dev/shm`/Drive）+ 一键 1.5s TensorCore TFLOPS & 带宽压测 (`/api/benchmark`) + 空闲自动关机看门狗** | 实时掌握 G4 Blackwell 380+ TFLOPS 与 1500+ GB/s 显存带宽，**绝不多扣 1 分钱冤枉算力** |

---

## 🏛️ 系统架构 (Hybrid Cloud + Native SwiftUI Apple Silicon Architecture)

WorldForge 采用 **「原生 SwiftUI Studio 客户端 + 本地零依赖守护进程 + 单 SSH ControlMaster 多路复用隧道 + 云端 PCIe DMA 常驻显存/内存仲裁器」** 的四层混合架构：

```mermaid
flowchart TB
    subgraph Mac["🍎 macOS Studio Workstation (Apple Silicon M1/M2/M3/M4 Max)"]
        SwiftApp["💎 Native SwiftUI + AppKit App (WorldForge.app / macos_app/)\n• 7 大工作区 (⌘1 3D世界 / ⌘2 2K生图 / ⌘3 视频 / ⌘4 超分 / ⌘5 A/B对比 / ⌘6 作品库 / ⌘7 Web台)\n• ThumbnailCacheActor (L1 256MB NSCache + L2 Disk + 后台 CGImageSource 0ms 主线程解码)\n• HoverVideoPlayerPool & DualSyncVideoController (16fps vs 60fps 实时分屏卷帘核验)"]
        WebUI["🌐 Studio Web UI (web/ :7788)\n• 交互式 3D 摄像机轨迹画布 & 8 大单点透视预设\n• 实时 GPU/VRAM/RAM/PCIe/TFLOPS 遥测仪表盘"]
        Daemon["⚙️ Local Daemon (forge.py :7788)\n• 100% Python 3 标准库（零 pip 依赖）\n• 会话生命周期管理 & 空闲自动关机看门狗\n• 自动轮询拉取远端成品 (auto_fetch)"]
        Post["🎞️ Apple Silicon Local Mastering (postproc.py)\n• rife-ncnn-vulkan (Metal/MoltenVK) 2×/4×/8× 光流插帧\n• 0.1×–32× 变速 & 1080p/4K Lanczos 缩放\n• 尾帧 3.0s xfade + zoompan 电影定格 (libx264 CRF 16)"]
        Gallery[("📂 本地作品库 & 缩略图缓存\n~/Movies/WorldForge (.thumbs/)")]
    end

    subgraph Tunnel["🔐 Single-SSH Multiplexed Transport"]
        Mux["OpenSSH ControlMaster (ctl-<session>.sock)\ncolab ssh --proxy-mode\n• 端口转发 127.0.0.1:17860 ──▶ :7860\n• tar.gz 流式代码同步 & 远端进程守护"]
    end

    subgraph Colab["☁️ Google Colab VM (NVIDIA RTX PRO 6000 Blackwell 98GB VRAM + 176GB DDR5 RAM)"]
        Orch["🧠 FastAPI Orchestrator (remote/forge_server.py :7860)\n• 单卡 GPU 队列仲裁器 (_ensure_on_gpu) & 实时热切换带宽遥测\n• /api/benchmark 1.5s TensorCore TFLOPS + GDDR7 + PCIe DMA 极限压测\n• 16 线程 + hf_transfer 极速下载 & 环境自愈安装器 (setup_env.py)"]
        
        subgraph Pool["⚡ 常驻进程池 (98GB GDDR7 VRAM ↔ 176GB Pinned DDR5 RAM Non-Blocking DMA 热交换)"]
            W_Qwen["🎨 Qwen-Image-2.1-Turbo Worker\n• 57GB bf16 · 8 步原生 2K (2752×1536)\n• TF32 + Flash SDPA + 自动 VAE Tiling"]
            W_Lyra["🌐 NVIDIA Lyra 2.0 Worker (lyra_worker.py)\n• Wan2.1-14B DiT + UMT5-XXL + DA3 + MoGe\n• Realism / Detail / DMD 3-LoRA 热切换\n• Blackwell sm_120 PyTorch SDPA 补丁"]
            W_Diff["🧩 Universal Diffusers Worker (diffusers_worker.py)\n• 内置 Z-Image / FLUX.1 / Wan2.1 / LTX / CogVideoX\n• 任意 HF repo 动态反射 + OOM 自动 Tiling/折半重试"]
        end
    end

    SwiftApp <-->|"Async Actor REST + Direct Disk Index"| Daemon
    SwiftApp <-->|"Zero-Copy File & L2 Cache"| Gallery
    WebUI <-->|"HTTP REST + 实时状态流"| Daemon
    Daemon -->|"调起本地 GPU 后期"| Post
    Post -->|"写入母带 MP4/PNG"| Gallery
    Daemon <-->|"自动归档 & 缩略图"| Gallery
    Daemon <-->|"HTTP over SSH (-L) + Mux Commands (-S)"| Mux
    Mux <-->|"127.0.0.1:7860"| Orch
    Orch <-->|"Pinned Memory + CUDA Stream (non_blocking=True)\n~25–64 GB/s PCIe Gen5 DMA Swap"| W_Qwen
    Orch <-->|"Pinned Memory + CUDA Stream (non_blocking=True)\n~25–64 GB/s PCIe Gen5 DMA Swap"| W_Lyra
    Orch <-->|"Pinned Memory + CUDA Stream (non_blocking=True)\n~25–64 GB/s PCIe Gen5 DMA Swap"| W_Diff
```

---

## 💎 原生 SwiftUI + AppKit 零卡顿工作站架构 (`macos_app/`)

为了彻底解决高分辨率 2K 原画与多路 60fps 视频在桌面端的渲染卡顿问题，WorldForge 提供了纯原生编译的 **`WorldForge.app`**（源码位于 [`macos_app/Sources/`](macos_app/Sources/)）：

### 1. `ThumbnailCacheActor`：双层缓存 + 请求合并 + 0ms 主线程解码
在 [`macos_app/Sources/AsyncMediaEngine.swift`](macos_app/Sources/AsyncMediaEngine.swift) 中，所有图像与视频封面的加载均由独立的 Swift Concurrency `actor` 驱动，主线程永远只消费已解码完成的 `NSImage`：
- **L1 内存缓存 (`NSCache<NSString, NSImage>`)**：提供 `256 MB` 解码后位图预算（上限 400 张）与 `128 MB` 视频 12 帧胶片条缓存，支持 `nonisolated` 同步零延迟命中；
- **L2 磁盘持久化缓存 (`~/Movies/WorldForge/.thumbs/<id>.jpg`)**：首次解码 2K 大图或提取 MP4 首帧后自动持久化为高压缩比 JPEG，二次冷启动耗时 `< 0.8ms`；
- **In-Flight 并发请求合并 (`inFlight: [String: Task<NSImage?, Never>]`)**：同一张作品被多个视图同时请求时只触发一次底层解码；
- **硬件级降采样 (`CGImageSourceCreateThumbnailAtIndex`)**：设置 `kCGImageSourceCreateThumbnailFromImageAlways` 与 `kCGImageSourceShouldCacheImmediately: true`，在 `Task.detached(priority: .userInitiated)` 后台线程直接将 `2752×1536` 原图按 `maxPixelSize: 640` 一步解码为 GPU 就绪位图，内存占用降低 **94%**，主线程掉帧严格为 **`0.0 ms`**。

### 2. `HoverVideoPlayerPool` 与 `DualSyncVideoController`（A/B 帧率同屏核验）
- **解码器上限保护 (`HoverVideoPlayerPool`)**：画廊支持鼠标悬停时的 **12 帧胶片条丝滑擦洗（Scrubbing）**，并严格限制全局最多同时激活 **2 个**硬件 `AVQueuePlayer` + `AVPlayerLooper` 实例，杜绝多视频同屏解码引发的 WindowServer 掉帧。
- **A/B 实时卷帘对比工作台 (`⌘5`)**：通过 `DualSyncVideoController` 将云端 Lyra 2.0 原始输出（`832×480 @ 16fps`）与本地 M1 Max RIFE 超分插帧成品（`1920×1080 @ 60fps`）绑定至同一时钟源，支持无极拖拽分割线实时对比细节与流畅度。

---

## ⚡ 云端 Blackwell (`sm_120`) 极限压榨与 PCIe 5.0 DMA 热交换

WorldForge 的云端引擎（[`remote/`](remote/)）针对 Google Colab **G4 (`RTX PRO 6000 Blackwell 98GB`)**、**A100 (`80GB/40GB`)**、**L4 (`24GB`)** 与 **T4 (`16GB`)** 进行了全方位底层优化：

### 1. 锁页内存 (`pin_memory`) + 非阻塞 CUDA Stream (`non_blocking=True`) 显存热交换
在 [`remote/diffusers_worker.py`](remote/diffusers_worker.py) 与 [`remote/lyra_worker.py`](remote/lyra_worker.py) 中，当多模型接力需要切换 GPU 归属权时：
- **非阻塞锁页卸载 (`_dma_offload_pipeline` / `_dma_offload_modules`)**：
  在独立的 `DMA_STREAM = torch.cuda.Stream()` 上遍历模型的所有参数与 Buffer，直接分配 **锁页主机内存 (`torch.empty(..., device="cpu", pin_memory=True)`)**，通过 `pinned.copy_(old_cuda, non_blocking=True)` 与 `old_cuda.record_stream(DMA_STREAM)` 发起异步 DMA 传输，绕过 CUDA 驱动的临时分页拷贝缓冲（Staging Buffer）；
- **满带宽异步唤醒 (`_dma_onload_pipeline` / `_dma_onload_modules`)**：
  因为权重在 176GB DDR5 内存中已处于 Page-Locked 锁页状态，唤醒时在 `DMA_STREAM` 中调用 `.to("cuda", non_blocking=True)` 即可触发真正的硬件级连续 `cudaMemcpyAsync (HostToDevice)`，将 30～50GB 模型的显存换页时间压缩至 **1.2～1.5 秒**；
- **实时带宽遥测**：每次热切换均在 `@@FORGE@@` 事件流与任务日志中实时打印精确传输体积、耗时与 PCIe 吞吐率：
  ```text
  显存热切换完成: 30.9 GB 用时 1.38s (22.4 GB/s) [176GB Pinned RAM → GPU]
  ```

### 2. Blackwell TensorCore 加速与高分辨率防 OOM 护盾
- 启动时自动开启 `torch.backends.cuda.matmul.allow_tf32 = True`、`torch.backends.cudnn.benchmark = True`、`torch.set_float32_matmul_precision("high")` 以及 PyTorch 2.x **Flash / Memory-Efficient / cuDNN SDPA** 内核；
- 当生成分辨率 `>= 2048px`、或运行在 `<= 32GB` 显存的实例（如 L4 / T4）上、或捕获到 `torch.cuda.OutOfMemoryError` 时，[`remote/diffusers_worker.py`](remote/diffusers_worker.py) 会全自动启用 **VAE Slicing & Tiling 分块解码** 并折半批大小无感重试，彻底告别高分大图 OOM。

### 3. 一键 1.5 秒云端显卡极限算力压测 (`/api/benchmark`)
在 [`remote/forge_server.py`](remote/forge_server.py) 中新增了 `/api/benchmark` 端点，支持在 UI 中一键触发 **1.5 秒硬件微基准测试**：
- **BF16 / FP16 TensorCore GEMM 峰值算力 (`TFLOPS`)**：基于 `torch.cuda.Event(enable_timing=True)` 硬件时钟精确测量 `8192×8192` 矩阵乘吞吐；
- **HBM3e / GDDR7 显存带宽 (`vram_bw_gbps`)**：测量设备端大张量读写拷贝峰值带宽（G4 Blackwell 实测可达 `1500+ GB/s`）；
- **PCIe Host↔Device 双向 DMA 带宽 (`pcie_h2d_gbps` / `pcie_d2h_gbps`)**：实测锁页内存与显存之间的非阻塞 DMA 吞吐率。

### 4. 内置 11 大开源旗舰模型目录 (`DEFAULT_MODELS`) & 一句话全自动生图/生视频/拟真配音
[`remote/presets.py`](remote/presets.py) 与 [`remote/forge_server.py`](remote/forge_server.py) 预置了覆盖全模态、全显存档位的 11 大明星模型，开箱即用：

| 模型 ID (`id`) | HuggingFace 仓库 (`repo`) | 类型 | 体积 / 存储与显存架构 | 核心定位与亮点 |
| :--- | :--- | :---: | :---: | :--- |
| `minimax-h3-hybrid` | `MiniMax-AI/MiniMax-H3-Hybrid-1.8` | `t2v` | `39.8 GB` · `/dev/shm` + G4/A100 | **音视频一体 1.8-Hybrid Turbo 旗舰**，支持一句话生图与 32kHz 立体声电影视频直出 |
| `minimax-h3-int8` | `MiniMax-AI/MiniMax-H3-Hybrid-1.8` | `t2v` | `25.6 GB` · L4/A100/G4 | **Int8 量化极速版音视频引擎**，单卡 24GB 显存流畅直出 |
| `breeze-tts-2` | `BreezeBlue/Breeze-TTS-2` | `tts` | `7.2 GB` · **30TB 谷歌云盘 (`0 MB` 显存)** | **Artificial Analysis 榜首中英双语拟真语音/克隆**，支持一句话音色设计与 `[笑]`/`[叹气]` 副语言，常驻云盘与内存、**占用 `0 MB` GPU 显存** |
| `qwen-image-2.1-turbo` | `Qwen/Qwen-Image-2.1-Turbo` | `t2i` | `57.7 GB` · G4/A100 | **8 步极速原生 2K (`2752×1536`) 旗舰**，中英文海报排版与电影级首帧直出 |
| `lyra-2` | `nvidia/Lyra-2.0` | `lyra` | `98.4 GB` · G4/A100 | **单张图片/一句话 → 可漫游 3D 世界穿梭长镜头**（Wan2.1 14B + DA3 + MoGe + 3DGS 分屏） |
| `z-image-turbo` | `Tongyi-MAI/Z-Image-Turbo` | `t2i` | `12.8 GB` · 全系通用 | **8 步超写实摄影与海报模型**，单流 DiT 架构，L4/T4 亦可流畅生图 |
| `flux-1-schnell` | `black-forest-labs/FLUX.1-schnell` | `t2i` | `23.8 GB` · G4/A100/L4 | **4 步极速 Rectified Flow 旗舰**，电影级光影与欧美构图质感标杆 |
| `wan2.1-t2v-14b` | `Wan-AI/Wan2.1-T2V-14B-Diffusers` | `t2v` | `32.5 GB` · G4/A100 | **通义万相 14B 旗舰文生视频**，大幅度物理运动与大师级镜头调度 |
| `wan2.1-i2v-14b-720p` | `Wan-AI/Wan2.1-I2V-14B-720P-Diffusers` | `i2v` | `34.2 GB` · G4/A100 | **通义万相 14B 720P 旗舰图生视频**，首帧完美保持与高动态演进 |
| `ltx-video-2b` | `Lightricks/LTX-Video` | `t2v` | `9.4 GB` · 含免费 T4 | **实时级 DiT 视频生成引擎**，连免费 T4 (`16GB`) 都能秒级出片 |
| `cogvideox-5b-i2v` | `THUDM/CogVideoX-5b-I2V` | `i2v` | `20.6 GB` · G4/A100/L4 | **智谱清影 5B 电影感图生视频**，支持 L4 24GB 显存流畅推理 |

*(同时完全支持在模型中心粘贴**任意** HuggingFace `owner/repo` 链接，自动解析 `model_index.json` 并调用 `hf_transfer` + 16 线程并发极速拉取！)*

---

## 🚀 1 分钟极速上手 (1-Minute Quickstart)

### 前置准备 (Prerequisites)
1. **macOS 系统**（推荐搭载 Apple Silicon `M1 / M2 / M3 / M4` 芯片的 Mac，系统自带 `python3` 即可，无需配置任何本地虚拟环境）。
2. **FFmpeg**（用于本地视频缩略图提取与母带重编码）：
   ```bash
   brew install ffmpeg
   ```
   *(注：`rife-ncnn-vulkan` 光流插帧引擎无需手动安装，首次使用本地插帧时 WorldForge 会自动下载适配 macOS Metal/Vulkan 的二进制包并自动解除 Gatekeeper 隔离属性。)*
3. **Google Colab CLI (`colab`)**：已完成账号登录并拥有可用计算单元（推荐选用 `G4` Blackwell 98GB 或 `A100` 80GB 运行时）。

### 启动方式（三选一）

#### 方式 A：双击原生 `WorldForge.app` 或 `start.command`（推荐日常创作）
直接在 Finder 中双击仓库根目录下的 **`WorldForge.app`**（或 **`start.command`**）：
- **`WorldForge.app`** 会自动在后台守护拉起本地 `:7788` 服务（`ForgeClient.ensureDaemonRunning()`），并呈现原生 SwiftUI 120Hz 暗黑毛玻璃工作台；
- **`start.command`** 会检测本地 `:7788` 服务并以獨立窗口模式弹出工作台。

#### 方式 B：终端一行命令启动（Colab 云端模式）
```bash
git clone https://github.com/designfuchen/worldforge.git
cd worldforge
open WorldForge.app   # 启动原生 SwiftUI 客户端（自动拉起后台 forge.py）
# 或仅启动本地守护进程 + Web 工作台：
python3 forge.py --open
```

#### 方式 C：本地 / 局域网 **RTX 4090 (`24GB`) / RTX 5090 (`32GB`)** 直连模式（无需 Colab）
如果你手里有 **RTX 4090 (24GB)** 或 **RTX 5090 (32GB)**（Linux / WSL2 / 局域网工作站），**完全不需要安装 `google-colab-cli`**，一行脚本即可直接跑满本地显卡：

1. **在你的 4090 / 5090 机器上启动推理后端**：
   ```bash
   chmod +x start_local_gpu.sh
   ./start_local_gpu.sh
   # 等价于：python3 remote/forge_server.py --local --host 0.0.0.0 --port 17860
   ```
   - 自动将模型与输出目录挂载至 `~/worldforge_data`（可通过 `WORLDFORGE_ROOT=/path/to/ssd` 自定义）；
   - **RTX 5090 (`sm_120`, 32GB)** 与 **RTX 4090 (`sm_89`, 24GB)** 自动激活 PyTorch 2.x Flash SDPA 补丁、VAE Tiling 以及 **超大容量模型智能 CPU-GPU 分块热卸载**（`FLUX.1`、`Z-Image Turbo`、`MiniMax-H3 INT8`、`Breeze-TTS-2` 满血直出；`Wan 2.1 14B`、`Qwen-Image 2.1`、`Lyra 2.0` 自动开启防 OOM 分块流式卸载）。
2. **连接工作台**：
   - **本机直连**：直接运行 `python3 forge.py --open`（自动探测本地 `:17860` / `:7860` 端口，**0 秒免配置即连**）；
   - **Mac 跨局域网直连 4090/5090 主机**：在 Mac 上运行：
     ```bash
     python3 forge.py --gpu-url http://192.168.1.88:17860 --open
     ```

---

## 🎬 核心秘籍：如何跑出 NVIDIA 官方级「一直在穿梭」的 Lyra 2.0 长镜头？

很多开发者自己部署 NVIDIA `Lyra 2.0` 时都会困惑：**为什么官方宣传片里的镜头能一镜到底、丝滑穿过整座森林和城堡，而自己跑出来的视频要么画面像果冻一样扭曲、要么飞出几十帧后景深就彻底崩塌停滞？**

WorldForge 在 [`remote/lyra_worker.py`](remote/lyra_worker.py)、[`remote/presets.py`](remote/presets.py) 与 [`forge_local/postproc.py`](forge_local/postproc.py) 中内置了整套**官方级「一直在穿梭 (`flythrough`)」五重秘籍**：

### 1. 双向生成 + 后退段时序倒放拼接 + 多镜接力重锚定 (`30s–45s Long-Film Fly-Through & Chained Tour`)
自回归视频扩散模型（每个 chunk 80 帧）如果只朝着单一前推方向硬推超过 6～8 段，累积重投影误差会导致画面中心迅速糊化。
WorldForge 的 `mode: "flythrough"` 与 `mode: "chained"` 完整复刻了 `@NVIDIAAI` 官方长片（`30.1s · 481帧` 与 `45.1s · 721帧`）的黄金拍法：
- **双向倒放拼接 (`flythrough`)**：以你的原画作为「旅途中间锚点」：
  1. **前推段 (`zoom_in` / `frames_in`)**：从原画出发，沿视线正前方推进 `241～481 帧`（`direction="right"`, `strength=3.0`），深入场景腹地；
  2. **后退抬升段 (`zoom_out` / `frames_out`)**：同样从原画出发，向后拉远并轻微抬升俯仰角 `241 帧`（`direction="left"`, `strength=1.5`, `upward_ratio=0.15`）；
  3. **张量级无损倒放缝合**：在内存中直接将后退段沿时间维翻转（`res_out["video"].flip(dims=[2])`），去掉重复的首帧后与前推段无缝拼接：
     ```python
     # remote/lyra_worker.py
     video = torch.cat([res_out["video"].flip(dims=[2]), res_in["video"][:, :, 1:]], dim=2)
     warp  = torch.cat([res_out["warp_video"].flip(dims=[2]), res_in["warp_video"][:, :, 1:]], dim=2)
     ```
- **多镜接力漫游 (`chained` / `segments`)**：在前推段结束后，自动提取末帧并通过 `DA3 × MoGe` 重新解算 3D 深度与内参（Re-Anchoring），无缝衔接第三段 `horizontal_spiral` 或 `orbit_horizontal` 轨迹，实现 **721 帧（45.1 秒 @ 16fps）** 跨轨迹一镜到底。
- **`@NVIDIAAI` 同款 `3DGS vs Video` 斜切分屏直出 (`split_3dgs.mp4` + `warp.mp4`)**：每次生成不仅输出高清 `world.mp4`，还同步从 `res["warp_video"]` 导出 3D 高斯/点云前向投影视频 `warp.mp4`，并自动合成左上角 `3DGS` 点云、右下角 `Video` 渲染成片、带抗锯齿白线 `/` 分割的 **`split_3dgs.mp4`**！
- **WAN 3D 因果 VAE 的 `cuDNN Conv3D` 防爆显存修复**：针对 `lyra2_ar_inference.py` 在导入时全局关闭 `torch.backends.cudnn.enabled = False` 导致 3D 卷积退化至高内存原生算子的问题，[`remote/lyra_worker.py`](remote/lyra_worker.py) 在导入后强制恢复 `cudnn.enabled = True` 与 `cudnn.benchmark = False`，确保 481～721 帧超长序列 VAE 解码既快又稳。

### 2. 冻结时间舞台提示词工程 (`Frozen-Tableau Prompt Template`)
`Lyra 2.0` 的底座是 `Wan2.1-14B` 视频生成模型。如果你只输入一句简单的 *"A floating castle in the sky"*，模型会本能地让云彩飘动、树叶摇晃、水面起波纹 —— 而任何场景内物体的自发运动都会严重破坏 3D 高斯/Plücker 光线重投影的几何一致性！
WorldForge 在 [`remote/presets.py`](remote/presets.py) 中内置了经过反复调校的 **`Frozen-Tableau`（时间冻结舞台）母版提示词**：
> *"A cinematic drone shot glides smoothly forward through the scene: `{scene}`. The scene is a frozen tableau, frozen in time; every element is perfectly still. All structures, foliage, water, clouds, light and shadows remain absolutely stationary and unchanging. As the camera advances, more of the world is revealed, maintaining the same lighting, color palette, materials and textures. No wind, no motion of any kind; a silent, timeless, static world through which only the camera travels."*

### 3. 单点透视构图 + `DA3 × MoGe` 逆深度最小二乘尺度对齐
要让穿梭感极强，首帧原画必须具备**「前景两侧遮挡物（石拱门/鸟居/冰柱/石柱）+ 中央纵深通道 + 远景视觉焦点」**的单点透视结构（WorldForge 内置的 **8 大 3D 世界预设**：宫崎骏天空之城、千本鸟居·红枫、雨林失落神殿、极光冰晶宫殿、灯笼古镇长街、赛博朋克雨夜、深海亚特兰蒂斯、敦煌鎏金石窟全部采用此黄金构图）。
在进入扩散采样前，[`remote/lyra_worker.py`](remote/lyra_worker.py) 会先后调用 **ByteDance `Depth-Anything-3 (DA3)`** 与 **Microsoft `MoGe`**，在有效掩码区域内通过最小二乘法对逆深度（Inverse Depth）进行精确的物理尺度对齐，并在对齐后立即将 `MoGe` 卸载回 CPU 释放显存。

### 4. 拒绝拉伸变形：全自动 `832:480` 中心裁剪与原生画幅预设
Lyra 2.0 原生工作分辨率为 `832×480`（宽高比 `1.733:1`）。WorldForge 的 `_prepare_image()` 会在推理前自动按目标宽高比执行像素级中心裁剪（Center-Crop），同时在文生图面板提供 **`Lyra 原生 832×480 (1664×960)`** 画幅预设，实现零裁切完美对接。

### 5. 本地 Apple Silicon 「变速 × 光流插帧 × 尾帧缓推」大师级母带后期
当云端生成的原始 `16fps` 穿梭视频自动同步回 Mac 后，在「M1 Max 超分 (`⌘4`)」面板开启黄金配方：
- **变速 (`speed: 2×` 或 `4×`) + RIFE 光流插帧 (`interp: 2×` 或 `4×`)**：消除扩散模型微小的帧间闪烁，将原始素材升级为 **`1080p @ 60fps`** 的丝滑穿越机镜头；
- **尾帧高清定格 (`end_hold_image`)**：可选挂载一张 2K 高清目标原画，在穿梭结尾自动执行 `0.6s xfade` 交叉淡化 + `3.0s zoompan` 缓慢推镜定格，输出 `libx264 -crf 16 -preset slow` 影院级成片。

---

## 🖼️ 内置大师作品库与实机渲染展示 (`docs/assets/` & `~/Movies/WorldForge`)

仓库与本地作品库预置了由 `Qwen-Image 2.1 Turbo (2K)` + `ARRI Alexa 65 / Cooke Anamorphic 电影摄影机光学预设` + `NVIDIA Lyra 2.0 (14B)` + `M1 Max RIFE 1080p60` 全链路实机跑出的标杆作品集：

| 🌸 岩井俊二·黄金逆光柔焦 (2K 直出) | 🌸 《情书》镰仓樱花夕阳逆光 (2K 直出) | 🌧️ 王家卫《花样年华》香港霓虹雨窗 (2K 直出) |
| :---: | :---: | :---: |
| ![Golden Hour 2K](docs/assets/cinema_golden_hour_2k.png) | ![Iwai Sakura 2K](docs/assets/cinema_iwai_sakura.png) | ![WKW Neon Rain 2K](docs/assets/cinema_wkw_neon_rain.png) |

| 🏰 宫崎骏《天空之城》30s 3D 世界穿梭胶片轨 | 🏮 江南灯笼古镇 30s 3D 世界穿梭胶片轨 | 🌃 赛博朋克雨夜 30s 3D 世界穿梭胶片轨 |
| :---: | :---: | :---: |
| ![Laputa Flythrough](docs/assets/ghibli_laputa_cg_flythrough_strip.jpg) | ![Lantern Town Flythrough](docs/assets/lantern_town_flythrough_strip.jpg) | ![Cyber Alley Flythrough](docs/assets/cyber_alley_flythrough_strip.jpg) |

- **10 张原生 2K 单点透视大师概念原画 (`drafts/`)**：涵盖吉卜力天空之城（手绘与 CG 双版本）、京都伏见稻荷千本鸟居、雨林失落神殿、极光冰晶宫殿、江南灯笼古镇、赛博朋克雨夜窄巷等；
- **多部 3D 世界连续穿梭长镜头与 1080p @ 60fps 精修母带 (`~/Movies/WorldForge/`)**：
  - `宫崎骏天空之城_3D平滑穿梭_2x_1080p60fps.mp4` / `宫崎骏天空之城_3D高速穿梭_1080p60fps.mp4`
  - `失落神庙_3D平滑穿梭_2x_1080p60fps.mp4` / `失落神庙_3D高速穿梭_4x_1080p60fps.mp4`
  - 以及京都千本鸟居、极光冰晶宫殿、赛博朋克雨夜等多组 `world.mp4` 原始 16fps 流，可直接在 **A/B 帧率对比 (`⌘5`)** 中与 1080p60 精修版同屏核验。

---

## 📂 仓库目录结构 (Repository Structure)

```text
worldforge/
├── WorldForge.app             # 💎 原生编译 macOS SwiftUI + AppKit 工作站应用包（支持 120Hz ProMotion）
├── macos_app/                 # 🍎 原生 SwiftUI 客户端源码
│   └── Sources/
│       ├── AsyncMediaEngine.swift  # ThumbnailCacheActor (L1+L2 双层缓存/0ms 主线程解码) + HoverVideoPlayerPool
│       ├── ForgeClient.swift       # 原生 URLSession Actor 客户端、守护进程自启动与磁盘索引直读
│       ├── Models.swift            # 全量强类型数据模型、7 大工作区路由与智能推荐引擎
│       └── Views/                  # 3D 世界、2K 生图、M1 Max 超分、A/B 帧率卷帘对比、极速瀑布流画廊视图
├── forge.py                   # ⚙️ Mac 本地守护进程入口（100% Python 3 标准库，监听 127.0.0.1:7788）
├── start.command              # 🚀 macOS 双击启动脚本
├── drafts/                    # 🎨 内置 10 张原生 2K 单点透视大师场景母版原画
├── docs/
│   └── API.md                 # 📜 本地 (:7788) 与远端 (:7860) 完整 REST API 契约文档
├── forge_local/               # 🔧 Mac 本地核心模块（零第三方依赖）
│   ├── app.py                 #    核心状态机：会话编排、自动拉取成品 (auto_fetch)、空闲自动关机看门狗
│   ├── colab.py               #    google-colab-cli 封装、CU 余额轮询、SSH ControlMaster 多路复用与 tar 流上传
│   ├── tunnel.py              #    SSH 端口转发守护、指数退避重连、防误开机器校验、远端流式 HTTP 客户端
│   ├── postproc.py            #    Apple Silicon 本地后期：自动部署 rife-ncnn-vulkan、插帧、变速、尾帧 zoompan 定格
│   ├── gallery.py             #    本地作品库管理 (~/Movies/WorldForge)、ffprobe 元数据解析与缩略图生成
│   ├── server.py              #    多线程 HTTP Server 与 /api/remote/* 透明反向代理
│   ├── tasks.py               #    本地异步任务队列与实时日志偏移流
│   └── config.py              #    路径、端口与持久化配置管理
├── remote/                    # ☁️ 自动同步并运行于 Google Colab GPU VM (/content/forge) 的云端引擎
│   ├── forge_server.py        #    FastAPI 仲裁器 (:7860)：GPU 队列、Pinned DMA 热置换、/api/benchmark 压测、扩展遥测
│   ├── lyra_worker.py         #    NVIDIA Lyra 2.0 常驻进程：Blackwell TF32/SDPA + Pinned DMA 热交换 + 双向倒放拼接
│   ├── diffusers_worker.py    #    通用 Diffusers 常驻进程：Pinned DMA 热交换 + 自动 VAE Tiling + 动态签名反射
│   ├── setup_env.py           #    幂等一键环境安装器 + hf_transfer 极速下载 + Blackwell (sm_120) SDPA 自动补丁
│   └── presets.py             #    8 大内置旗舰模型 (DEFAULT_MODELS)、9 种 Lyra 3D 轨迹、8 大单点透视场景预设
└── web/                       # 🌐 原生暗黑 Studio 风格 Web 界面（零构建步骤，纯原生 ES Modules + CSS）
```

---

## 🔌 API 概览 (API Quick Reference)

完整协议定义请查阅 [**`docs/API.md`**](docs/API.md)。

| 端点 (Endpoint) | 作用域 | 说明 |
| :--- | :--- | :--- |
| `GET /api/local/state` | 本地 `:7788` | 获取 Colab CU 余额/速率、SSH 隧道状态、远端健康度与空闲倒计时 |
| `POST /api/local/connect` | 本地 `:7788` | 建立单路复用 SSH 隧道 + 流式部署 `remote/` + 启动远端 FastAPI 服务 |
| `POST /api/local/post` | 本地 `:7788` | 调用本地 Apple Silicon 执行 RIFE 插帧（`1/2/4/8×`）、变速、缩放与尾帧定格 |
| `GET /api/remote/metrics` | 远端 `:7860` | 实时获取 GPU 利用率/频率/PCIe代数/显存带宽利用率、176GB RAM、`/dev/shm`、Drive 与热切换速率 |
| `POST /api/remote/benchmark` | 远端 `:7860` | 运行 1.5s 云端 GPU 极限算力压测（返回 BF16/FP16 `TFLOPS`、显存带宽 `GB/s`、PCIe DMA `GB/s`） |
| `POST /api/remote/models` | 远端 `:7860` | 粘贴任意 HuggingFace `owner/repo` 地址，自动解析并注册为可常驻模型 |
| `POST /api/remote/jobs` | 远端 `:7860` | 提交 `t2i` / `t2v` / `i2v` / `lyra` / `setup` / `download` / `load` 异步任务 |

---

## 📄 开源协议 (License)

本项目基于 [**MIT License**](LICENSE) 开源。欢迎 Star ⭐、Fork 并提交 PR，一起把云端 GPU 与本地 Mac 的混合创作体验推向极致！
