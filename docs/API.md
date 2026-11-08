# WorldForge 世界工坊 — API 契约 v0.1

架构：
```
Mac 浏览器 UI (web/)  ──HTTP──▶  Mac 本地服务 forge.py :7788  ──SSH 隧道(colab ssh --proxy-mode)──▶  Colab VM 服务 remote/forge_server.py :7860
                                   │ colab CLI (new/stop/status/usage)
                                   │ 本地后期 (ffmpeg / RIFE)
                                   └ 作品库 ~/Movies/WorldForge
```
所有 JSON 均为 UTF-8。时间戳为 Unix 秒（float）。

---------------------------------------------------------------------
## A. 远端 API（Colab VM，FastAPI，127.0.0.1:7860）
本地服务把 `/api/remote/<rest>` 透明代理到远端 `/api/<rest>`（方法、query、body 原样转发）。

### GET /api/health
`{"ok":true,"version":"0.1.0","gpu":"NVIDIA RTX PRO 6000 Blackwell Server Edition"}`

### GET /api/metrics
```json
{"gpu":{"name":"...","util":97,"mem_used_mb":75000,"mem_total_mb":97887,"temp_c":61,"power_w":420},
 "ram":{"used_gb":20.1,"total_gb":176.0},
 "disk":{"used_gb":134.0,"total_gb":236.0},
 "workers":[{"model_id":"qwen-image-2.1-turbo","state":"on_gpu","pid":1234,"vram_mb":52000}],
 "queue":{"running":"job_xxx","queued":2}}
```
worker.state ∈ `loading | on_gpu | offloaded | dead`

### GET /api/models
```json
[{"id":"qwen-image-2.1-turbo","repo":"Qwen/Qwen-Image-2.1-Turbo","name":"Qwen-Image 2.1 Turbo",
  "kind":"t2i","builtin":true,"status":"downloaded","size_gb":57.3,
  "description":"8 步 2K 生图，中英文排版直出",
  "defaults":{"width":2752,"height":1536,"steps":8,"guidance":null}}]
```
- kind ∈ `t2i | t2v | i2v | lyra`
- status ∈ `available | downloading | downloaded | loading | loaded | error`
  （loaded = 有常驻 worker；是否在 GPU 上看 metrics.workers）
- 内置：`qwen-image-2.1-turbo`(t2i)、`lyra-2`(lyra)。其余为用户粘贴 HF 地址添加的 diffusers 模型。

### POST /api/models   body `{"repo":"https://huggingface.co/xxx/yyy" 或 "xxx/yyy"}`
读取 model_index.json 自动判断类型，注册并返回 model 对象（不自动下载）。错误 → 400 `{"detail":"..."}`。

### POST /api/models/{id}/download → `{"job_id":"..."}`（task=download）
### POST /api/models/{id}/load → `{"job_id":"..."}`（task=load，常驻进 GPU）
### POST /api/models/{id}/unload → `{"ok":true}`（杀掉 worker 释放内存）
### DELETE /api/models/{id} → `{"ok":true}`（仅非内置）

### POST /api/jobs
```json
{"model_id":"qwen-image-2.1-turbo","task":"t2i","params":{...}}
```
返回 `{"job_id":"job_20261108_104512_ab12"}`

params：
- **t2i**：`prompt, negative_prompt?, width, height, steps?, guidance?, seed(-1=随机), count(1-8)`
- **t2v / i2v**：`prompt, negative_prompt?, width, height, num_frames, fps, steps?, guidance?, seed, image_path?(i2v)`
- **lyra**：
  ```json
  {"image_path":"/content/forge/inputs/x.png",
   "scene":"场景/画面描述（英文或中文均可）",
   "caption":"完整提示词（可选；为空时由 scene 自动套官方 frozen-tableau 模板）",
   "mode":"flythrough",            // flythrough=官方“一路穿梭”(倒放后退+前推)；single=单条轨迹
   "trajectory":"horizontal_zoom", // single 模式用，取值见 /api/presets
   "direction":"right",
   "strength":1.0,
   "frames":241,                   // single 模式总帧数 (1+80k)
   "zoom_in_frames":481, "zoom_in_strength":3.0,
   "zoom_out_frames":241, "zoom_out_strength":1.5,
   "dmd":true, "steps":50, "guidance":5.0, "shift":5.0, "seed":1,
   "ground_align":false, "upward_ratio":0.15}
  ```
- **setup**（model_id 可为 null）：`{"component":"lyra" | "qwen" | "all"}` 一键安装环境

### GET /api/jobs?limit=50 → `[job...]`（新的在前）
### GET /api/jobs/{id} → job
```json
{"id":"job_...","model_id":"lyra-2","task":"lyra","params":{},"status":"running",
 "progress":0.42,"stage":"生成第 3/9 段","created":1794105000.1,"started":1794105003.2,"finished":null,
 "outputs":[{"path":"/content/forge/outputs/job_x/video.mp4","kind":"video","name":"video.mp4"}],
 "error":null,"eta_s":310}
```
status ∈ `queued | running | done | error | cancelled`
### GET /api/jobs/{id}/log?offset=0 → `{"text":"...","offset":12345,"done":false}`
### POST /api/jobs/{id}/cancel → `{"ok":true}`

### POST /api/upload?filename=a.png   （raw body = 文件字节）→ `{"path":"/content/forge/inputs/a.png"}`
### GET /api/files?path=/content/forge/outputs/...  → 文件流（仅允许 /content/forge 下）
### GET /api/presets
```json
{"lyra_trajectories":[{"id":"horizontal_zoom","name":"直线推进","desc":"...","directions":["right","left"],"strength":{"min":0.1,"max":5,"default":1.0}}],
 "caption_template":"A cinematic drone shot glides forward ... {scene} ... only the camera travels.",
 "scene_presets":[{"id":"ghibli_laputa","name":"宫崎骏天空之城","prompt":"...","lyra_scene":"..."}],
 "t2i_styles":[{"id":"cinematic","name":"电影写实","suffix":"..."}],
 "aspect_presets":[{"id":"16:9","name":"16:9 横屏 2K","width":2752,"height":1536}]}
```

---------------------------------------------------------------------
## B. 本地 API（Mac，forge.py，127.0.0.1:7788）

### GET /api/local/state
```json
{"colab":{"cli_ok":true,"balance":2421.4,"rate":10.05,"sessions":[{"name":"lyra","host":"gpu-g4-...","hardware":"G4","status":"IDLE"}],"updated":1794105000},
 "tunnel":{"status":"up","local_port":17860,"session":"lyra","since":1794105000},
 "remote":{"status":"ok","version":"0.1.0","gpu":"..."},
 "settings":{"session_name":"lyra","gpu":"G4","idle_minutes":30,"output_dir":"/Users/x/Movies/WorldForge","auto_fetch":true},
 "idle":{"seconds":120,"will_stop_in":1680}}
```
tunnel.status ∈ `down | connecting | up | error`；remote.status ∈ `unreachable | deploying | ok`

### POST /api/local/settings  body：settings 的部分字段 → 新 settings
### POST /api/local/session/start `{"name":"lyra","gpu":"G4"}` → `{"task_id":"..."}`
### POST /api/local/session/stop `{"name":"lyra"}` → `{"task_id":"..."}`
### POST /api/local/connect `{"name":"lyra"}` → `{"task_id":"..."}`  （建隧道 + 上传 remote/ + 启动远端服务；已在跑则只建隧道）
### POST /api/local/disconnect → `{"ok":true}`

### GET /api/local/tasks → `[task...]`
```json
{"id":"t_...","type":"connect|session_start|session_stop|fetch|post","title":"下载 video.mp4","status":"running|done|error",
 "progress":0.5,"log_tail":"...","created":1794105000,"result":{"gallery_id":"g_..."},"error":null}
```
### GET /api/local/tasks/{id}/log?offset=0 → `{"text":"...","offset":N,"done":true}`

### POST /api/local/fetch `{"remote_path":"/content/forge/outputs/job_x/video.mp4","kind":"video","meta":{"prompt":"...","model":"lyra-2","job_id":"job_x"}}` → `{"task_id":"..."}`
（本地服务也会在 auto_fetch=true 时自动轮询远端已完成任务并下载输出）

### GET /api/local/gallery → `[{"id":"g_...","kind":"image|video","name":"x.png","path":"/Users/.../x.png","url":"/media/2026-11-08/x.png","thumb":"/media/.thumbs/x.jpg","created":1794105000,"meta":{...}}]`
### DELETE /api/local/gallery/{id} → `{"ok":true}`
### POST /api/local/reveal `{"path":"..."}` → 在 Finder 中显示
### POST /api/local/upload?filename=a.png （raw body）→ 先存本地再转发到远端 /api/upload → `{"remote_path":"...","local_path":"..."}`
### POST /api/local/to_remote `{"gallery_id":"g_..."}` → 把作品库图片上传到远端，返回 `{"remote_path":"..."}`
### POST /api/local/post
```json
{"gallery_id":"g_...","speed":4,"interp":2,"trim_start":0,"trim_end":null,"scale":"1080p","end_hold_image":null}
```
→ `{"task_id":"..."}`，完成后 result.gallery_id 为新作品。
### /media/<相对路径> → 作品库静态文件
### /api/remote/<rest> → 代理到远端 /api/<rest>
### / → web/index.html
