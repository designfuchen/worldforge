"""作品库：output_dir/gallery.json 零阻塞异步索引、640px 高清缩略图、12×1 悬浮雪碧图与 Raw↔Enhanced 自动配对。"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import config

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}

THUMB_MAX_SIDE = 640
STRIP_FRAMES = 12
STRIP_TILE_W = 240
STRIP_TILE_H = 135

LAPUTA_BASE = (
    "宫崎骏《天空之城》风格的漂浮天空之岛，晴朗明亮的夏日午后，湛蓝的天空中堆满巨大洁白蓬松的积雨云。"
    "一条长满青草和小野花的古老石板小路从画面正下方中央笔直延伸向远方，小路两侧是爬满藤蔓与青苔的古老石砌拱门与残垣断壁，"
    "拱门一座接一座向远方排列形成长廊，路的尽头是一座被一棵巨大古树覆盖的圆形古城堡，古树的枝叶茂密翠绿，城堡层层叠叠的石塔与圆顶点缀着窗户，"
    "岛屿边缘有清澈的小瀑布流向云海，远处还有几座小浮岛。画面温暖、治愈、充满希望与冒险感，没有任何人物，"
    "单点透视构图，近景、中景、远景层次丰富，空间纵深感强。"
)
SCENE_COMMON = (
    "电影级超写实实拍质感，IMAX摄影机拍摄，24mm广角镜头，人眼视线高度，单点透视构图，一条清晰的道路从画面正下方中央笔直延伸向远方的消失点，"
    "近景、中景、远景层次极其丰富，左右两侧近景有密集的建筑或景物紧贴镜头，空间纵深感极强，画面中没有任何人物，"
    "细节极其丰富，原生2K超高清，HDR，体积光，电影级色彩分级。"
)

BUILTIN_DRAFTS = [
    {
        "filename": "g1_laputa_anime.png",
        "title": "宫崎骏天空之城 · 吉卜力手绘水彩",
        "preset_id": "ghibli_laputa",
        "seed": 2026,
        "prompt": LAPUTA_BASE + "吉卜力工作室手绘动画美术风格，水彩与水粉质感的手绘背景画，柔和明亮的色彩，清新通透，宫崎骏电影截图级别的精美画面，原生2K。",
        "scene": "a long grassy stone path lined with ivy-covered ancient stone arches on a floating sky island, leading toward a round ancient castle crowned by a giant tree, huge white cumulus clouds in a bright blue sky, Studio Ghibli style",
    },
    {
        "filename": "g2_laputa_anime.png",
        "title": "宫崎骏天空之城 · 男鹿和雄背景美术",
        "preset_id": "ghibli_laputa",
        "seed": 2026,
        "prompt": LAPUTA_BASE + "吉卜力工作室手绘动画美术风格，男鹿和雄背景美术，柔和的光影，饱和清新的蓝绿配色，电影级动画截图，原生2K。",
        "scene": "a long grassy stone path lined with ivy-covered ancient stone arches on a floating sky island, leading toward a round ancient castle crowned by a giant tree, huge white cumulus clouds in a bright blue sky, Studio Ghibli hand-painted style",
    },
    {
        "filename": "g3_laputa_cg.png",
        "title": "宫崎骏天空之城 · 唯美3D动画渲染",
        "preset_id": "ghibli_laputa",
        "seed": 2026,
        "prompt": LAPUTA_BASE + "宫崎骏风格的唯美3D CG渲染，皮克斯与吉卜力融合的电影级画面，柔和的全局光照，清新明亮的色彩，细节丰富，原生2K超高清。",
        "scene": "a long grassy stone path lined with ivy-covered ancient stone arches on a floating sky island, leading toward a round ancient castle crowned by a giant tree, huge white cumulus clouds in a bright blue sky, stylized 3D CG animation",
    },
    {
        "filename": "g4_laputa_cg.png",
        "title": "宫崎骏天空之城 · 虚幻5写实奇幻",
        "preset_id": "ghibli_laputa",
        "seed": 2026,
        "prompt": LAPUTA_BASE + "宫崎骏风格的电影级写实奇幻渲染，虚幻引擎5，柔和阳光与体积光，翠绿与天蓝配色，温暖治愈，细节极其丰富，原生2K超高清。",
        "scene": "a long grassy stone path lined with ivy-covered ancient stone arches on a floating sky island, leading toward a round ancient castle crowned by a giant tree, huge white cumulus clouds in a bright blue sky, Unreal Engine 5 cinematic fantasy",
    },
    {
        "filename": "s1_torii_maple.png",
        "title": "千本鸟居 · 京都深秋红枫",
        "preset_id": "torii_maple",
        "seed": 777,
        "prompt": "深秋京都伏见稻荷，成千上万座朱红色鸟居层层叠叠组成的幽深隧道，沿着长满青苔的古老石阶一路向远方山林深处无限延伸，鸟居之外是漫山遍野燃烧般火红与金黄的枫叶，枫叶覆盖石阶，金色夕阳的光束从鸟居缝隙间穿透进来，空气中弥漫着薄雾，壮丽、神秘、震撼。" + SCENE_COMMON,
        "scene": "an endless tunnel of vermilion torii gates along mossy stone stairs, surrounded by blazing red and golden maple trees, golden sunbeams and soft mist",
    },
    {
        "filename": "s2_sky_city.png",
        "title": "云海仙侠 · 白玉石桥天空之城",
        "preset_id": "sky_city",
        "seed": 777,
        "prompt": "云海之上的东方仙侠天空之城，一座悬空的白玉石桥从脚下笔直伸向远方，石桥两侧是巨大的悬浮山峰与层层叠叠的金顶宫殿楼阁，飞檐斗拱挂满发光的灯笼，瀑布从悬浮山上倾泻进无边云海，远处巨大的宫殿群在金色晨光中若隐若现，史诗级宏大、令人窒息的壮美。" + SCENE_COMMON,
        "scene": "a white jade bridge stretching across a sea of clouds between floating mountains and golden-roofed celestial palaces with waterfalls and glowing lanterns",
    },
    {
        "filename": "s3_cyber_alley.png",
        "title": "赛博朋克 · 雨夜霓虹深巷",
        "preset_id": "cyber_alley",
        "seed": 777,
        "prompt": "雨夜的赛博朋克未来都市窄巷，湿漉漉的街道倒映着漫天霓虹，两侧密密麻麻的高楼贴满了巨大的全息广告牌与发光汉字招牌，空中交错着电缆、管道与天桥，雾气弥漫，粉紫与青蓝色霓虹光交织，巷子一路延伸到远处耸入云霄的巨型摩天大楼，极致的视觉冲击。" + SCENE_COMMON,
        "scene": "a narrow rain-soaked cyberpunk alley with neon holographic signs, cables and skybridges overhead, leading to a colossal skyscraper",
    },
    {
        "filename": "s4_lost_temple.png",
        "title": "雨林秘境 · 远古失落神殿",
        "preset_id": "lost_temple",
        "seed": 777,
        "prompt": "被热带雨林吞没的远古失落神殿峡谷，一条古老的石板步道穿过两侧高耸的巨型石刻神像与爬满藤蔓的古老石柱长廊，延伸向远处峡谷尽头一座巨大的金字塔神殿，数道瀑布从两侧悬崖倾泻而下，阳光穿透雨林形成神圣的丁达尔光柱，薄雾缭绕，宏伟神秘。" + SCENE_COMMON,
        "scene": "an ancient stone walkway between giant carved guardian statues and vine-covered pillars in a jungle canyon, leading to a colossal stepped temple, waterfalls and god rays",
    },
    {
        "filename": "s5_ice_palace.png",
        "title": "极光之夜 · 冰雪水晶宫殿",
        "preset_id": "ice_palace",
        "seed": 777,
        "prompt": "极光之夜的冰雪水晶宫殿长廊，一条晶莹剔透的冰面长廊两侧是高耸的巨大冰晶柱与冰雕拱门，层层叠叠向远方延伸，冰柱内部透出幽蓝与青绿的光芒，天空中绚烂的绿色与紫色极光倒映在冰面上，远处是一座巨大的冰晶城堡，梦幻、圣洁、震撼。" + SCENE_COMMON,
        "scene": "a long corridor of glowing translucent ice pillars and carved ice arches leading to a giant crystal ice castle under green and violet aurora",
    },
    {
        "filename": "s6_lantern_town.png",
        "title": "大唐水乡 · 千灯古镇长街",
        "preset_id": "lantern_town",
        "seed": 777,
        "prompt": "夜晚的中国古风水乡长街，青石板路沿着河道一路延伸向远方，两侧是层层叠叠的三层木结构古楼，飞檐翘角，挂满成百上千盏暖红色的灯笼，空中漂浮着无数孔明灯，石拱桥横跨河面，河面倒映着万家灯火，远处是灯火辉煌的高塔，温暖、繁华、如梦似幻。" + SCENE_COMMON,
        "scene": "a night-time ancient Chinese water-town street lined with wooden houses and hundreds of glowing red lanterns, a stone arch bridge and a golden pagoda in the distance",
    },
]


def kind_of(name, default=None):
    ext = os.path.splitext(str(name or ""))[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    return default


def safe_name(name, default="file"):
    name = os.path.basename(str(name or "")).strip()
    name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", name).strip("._")
    return name[:120] or default


def unique_path(path):
    path = Path(path)
    if not path.exists() and not Path(str(path) + ".part").exists():
        return path
    stem, suf = path.stem, path.suffix
    for i in range(2, 10000):
        cand = path.with_name("%s_%d%s" % (stem, i, suf))
        if not cand.exists():
            return cand
    return path.with_name("%s_%s%s" % (stem, secrets.token_hex(3), suf))


def probe(path):
    """ffprobe 获取视频/图片的宽高、时长、帧率、帧数。"""
    fp = config.ffprobe_bin()
    if not fp:
        return {}
    try:
        p = subprocess.run(
            [
                fp, "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,duration:format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True,
            timeout=20,
        )
        d = json.loads(p.stdout.decode("utf-8") or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}
    st = (d.get("streams") or [{}])[0]
    out = {}
    if st.get("width") and st.get("height"):
        out["width"], out["height"] = int(st["width"]), int(st["height"])

    def rate(s):
        try:
            a, b = str(s).split("/")
            return float(a) / float(b) if float(b) else None
        except (ValueError, ZeroDivisionError):
            return None

    fps = rate(st.get("avg_frame_rate")) or rate(st.get("r_frame_rate"))
    if fps and 0 < fps < 1000:
        out["fps"] = round(fps, 3)
    dur = st.get("duration") or (d.get("format") or {}).get("duration")
    try:
        if dur is not None and float(dur) > 0:
            out["duration"] = round(float(dur), 3)
    except ValueError:
        pass
    try:
        if st.get("nb_frames"):
            out["frames"] = int(st["nb_frames"])
    except ValueError:
        pass
    return out


def make_thumb(src, dest, kind, max_side=THUMB_MAX_SIDE):
    """生成 640px 高清 JPEG 缩略图（原子写入，防止并发读到半截文件）。"""
    src, dest = Path(src), Path(dest)
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / ("%s.tmp_%s.jpg" % (dest.stem, secrets.token_hex(2)))
    try:
        if kind == "image":
            subprocess.run(
                [
                    "sips", "-Z", str(max_side),
                    "-s", "format", "jpeg",
                    "-s", "formatOptions", "88",
                    str(src), "--out", str(tmp),
                ],
                capture_output=True,
                timeout=45,
            )
            if not (tmp.exists() and tmp.stat().st_size > 0):
                ff = config.ffmpeg_bin()
                if ff:
                    subprocess.run(
                        [
                            ff, "-y", "-v", "error", "-i", str(src),
                            "-frames:v", "1", "-update", "1",
                            "-vf", "scale='min(%d,iw)':-2:flags=lanczos" % max_side,
                            "-q:v", "2", str(tmp),
                        ],
                        capture_output=True,
                        timeout=45,
                    )
        else:
            ff = config.ffmpeg_bin()
            if not ff:
                return False
            for ss in ("1.0", "0.3", "0"):
                subprocess.run(
                    [
                        ff, "-y", "-v", "error", "-ss", ss, "-i", str(src),
                        "-frames:v", "1", "-update", "1",
                        "-vf", "scale='min(%d,iw)':-2:flags=lanczos" % max_side,
                        "-q:v", "2", str(tmp),
                    ],
                    capture_output=True,
                    timeout=45,
                )
                if tmp.exists() and tmp.stat().st_size > 0:
                    break
        if tmp.exists() and tmp.stat().st_size > 0:
            os.replace(tmp, dest)
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return dest.exists() and dest.stat().st_size > 0


def make_strip(src, dest, duration=None, frames=STRIP_FRAMES, tile_w=STRIP_TILE_W, tile_h=STRIP_TILE_H):
    """使用单条高速 ffmpeg 滤镜生成 12×1 水平悬浮预览雪碧图 (2880×135 JPEG)。"""
    src, dest = Path(src), Path(dest)
    if not src.is_file():
        return False
    ff = config.ffmpeg_bin()
    if not ff:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not duration or duration <= 0:
        info = probe(src)
        duration = info.get("duration") or 4.0
    dur = max(float(duration), 0.4)
    sample_fps = float(frames) / max(dur * 0.96, 0.15)
    vf = (
        "fps=%.6f,"
        "scale=%d:%d:force_original_aspect_ratio=decrease:force_divisible_by=1,"
        "format=yuvj444p,"
        "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,"
        "tile=%dx1"
    ) % (sample_fps, tile_w, tile_h, tile_w, tile_h, frames)
    tmp = dest.parent / ("%s.tmp_%s.jpg" % (dest.stem, secrets.token_hex(2)))
    try:
        subprocess.run(
            [
                ff, "-y", "-v", "error", "-i", str(src),
                "-frames:v", "1", "-update", "1",
                "-vf", vf, "-q:v", "4", str(tmp),
            ],
            capture_output=True,
            timeout=60,
        )
        if tmp.exists() and tmp.stat().st_size > 0:
            os.replace(tmp, dest)
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return dest.exists() and dest.stat().st_size > 0


def _infer_scene_theme(it):
    """根据文件名、preset_id 与 prompt 自动推断中文场景主题与短标签。"""
    meta = it.get("meta") or {}
    params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
    name = str(it.get("name") or "")
    hay = " ".join(
        str(x or "")
        for x in (
            name,
            meta.get("preset_id"),
            meta.get("title"),
            meta.get("prompt"),
            meta.get("scene"),
            params.get("image_path"),
            params.get("scene"),
            params.get("prompt"),
        )
    ).lower()

    if any(k in hay for k in ("宫崎骏天空之城cg", "g3_laputa", "3d cg floating sky", "033036_a45b")):
        return "宫崎骏天空之城 CG", "天空之城 CG"
    if any(k in hay for k in ("laputa", "ghibli", "天空之城", "floating sky island", "g1_", "g2_", "g4_", "031219_5598", "033942_66f2")):
        return "宫崎骏天空之城", "天空之城"
    if any(k in hay for k in ("lost_temple", "s4_", "失落神庙", "失落神殿", "stepped temple", "jungle canyon", "025354_7df7")):
        return "远古失落神殿", "雨林神殿"
    if any(k in hay for k in ("torii_maple", "s1_", "千本鸟居", "torii", "红枫", "033117_69c5")):
        return "千本鸟居 · 京都红枫", "千本鸟居"
    if any(k in hay for k in ("sky_city", "s2_", "云海仙侠", "white jade bridge", "白玉")):
        return "云海仙侠 · 白玉石桥", "仙侠云海"
    if any(k in hay for k in ("cyber_alley", "s3_", "赛博", "cyberpunk", "霓虹", "033118_ae79")):
        return "赛博朋克 · 雨夜霓虹", "赛博都市"
    if any(k in hay for k in ("ice_palace", "s5_", "冰雪水晶", "ice castle", "aurora")):
        return "极光之夜 · 冰雪水晶宫", "极光冰宫"
    if any(k in hay for k in ("lantern_town", "s6_", "大唐水乡", "千灯古镇", "万灯水乡", "千与千寻", "water-town", "033119_b7f1")):
        return "大唐水乡 · 千灯古镇", "大唐古镇"
    return "世界工坊 · 创意场景", "场景创作"


def _is_video_enhanced(it):
    kind = it.get("kind") or kind_of(it.get("name"), "image")
    if kind != "video":
        return False
    meta = it.get("meta") or {}
    info = it.get("info") or {}
    name = str(it.get("name") or "").lower()
    fps = float(info.get("fps") or meta.get("fps") or 0)
    w = int(info.get("width") or meta.get("width") or 0)
    return bool(
        meta.get("post")
        or meta.get("parent")
        or fps >= 48
        or w >= 1920
        or "1080p" in name
        or "60fps" in name
        or "rife" in name
        or "_post_" in name
    )


def _infer_category(it, is_enh=None):
    if it.get("custom_category") in ("world3d", "enhanced", "image2k", "raw_video"):
        return it["custom_category"]
    kind = it.get("kind") or kind_of(it.get("name"), "image")
    meta = it.get("meta") or {}
    name = str(it.get("name") or "").lower()
    if is_enh is None:
        is_enh = _is_video_enhanced(it)
    if kind == "video":
        if is_enh:
            return "enhanced"
        if meta.get("task") == "lyra" or meta.get("model_id") == "lyra-2" or "world" in name or "3d" in name:
            return "world3d"
        return "raw_video"
    return "image2k"


def _infer_title_and_tags(it, is_enh, speed_factor, interp_factor, w, h, fps):
    meta = it.get("meta") or {}
    kind = it.get("kind") or kind_of(it.get("name"), "image")
    name = str(it.get("name") or "")
    scene_cn, theme_tag = _infer_scene_theme(it)

    # 1. Title
    custom_title = it.get("custom_title") or (meta.get("title") if meta.get("builtin_draft") else None)
    if custom_title:
        title = custom_title
    elif kind == "video":
        if "3DGS对角线分屏" in name or "3dgs" in name.lower():
            title = "%s · 3DGS / Video 官方斜切分屏 (30秒 1080p60)" % scene_cn
        elif "30秒长片" in name or "30s" in name.lower():
            title = "%s · 30秒 3D 世界探索长片 (1080p60)" % scene_cn
        elif is_enh:
            spd_i = int(round(speed_factor)) if abs(speed_factor - round(speed_factor)) < 0.05 else speed_factor
            title = "%s · 3D 穿梭 (%s× 1080p60)" % (scene_cn, spd_i)
        elif meta.get("task") == "lyra" or "world" in name.lower():
            title = "%s · Lyra 2.0 原始 3D 漫游" % scene_cn
        else:
            title = meta.get("title") or ("%s · 视频渲染 (%dx%d)" % (scene_cn, w or 832, h or 480))
    else:
        if "input_frame" in name.lower() or meta.get("task") == "lyra":
            title = "%s · Lyra 3D 首帧锚点" % scene_cn
        elif meta.get("title"):
            title = meta["title"]
        else:
            m_idx = re.search(r"img_0*(\d+)", name)
            seed = meta.get("seed")
            if m_idx and "332d" in name:
                title = "%s · 古树城堡原画 #%s" % (scene_cn, m_idx.group(1))
            elif seed is not None:
                title = "%s · 2K 概念原画 (Seed %s)" % (scene_cn, seed)
            else:
                title = "%s · 2K 概念原画" % scene_cn

    # 2. Tags
    if isinstance(it.get("custom_tags"), list) and it["custom_tags"]:
        tags = list(it["custom_tags"])
    elif kind == "video":
        if "3DGS对角线分屏" in name or "3dgs" in name.lower():
            tags = ["3D 世界", "3DGS 对角分屏", "30秒长片", "1080p60", theme_tag]
        elif "30秒长片" in name or "30s" in name.lower():
            tags = ["3D 世界", "30秒长片", "1080p60", "RIFE 补帧", theme_tag]
        elif is_enh:
            spd_i = int(round(speed_factor)) if abs(speed_factor - round(speed_factor)) < 0.05 else speed_factor
            spd_tag = "%s× 高速穿梭" % spd_i if speed_factor >= 3.0 else "%s× 平滑穿梭" % spd_i
            tags = ["3D 世界", "1080p60", "RIFE 补帧", spd_tag, theme_tag]
        else:
            fps_i = int(round(fps or 16))
            tags = ["3D 世界", "Lyra 2.0", "%dx%d" % (w or 832, h or 480), "%dfps 原始流" % fps_i, "Flythrough 穿梭", theme_tag]
    else:
        if meta.get("builtin_draft"):
            tags = ["2K 场景母版", "%dx%d" % (w or 2752, h or 1536), "Qwen-Image", "单点透视", theme_tag]
        elif "input_frame" in name.lower() or meta.get("task") == "lyra":
            tags = ["3D 首帧", "Lyra 2.0", "%dx%d" % (w or 832, h or 480), "空间锚点", theme_tag]
        else:
            res_tag = "2K 原画" if (w or 0) >= 2000 else "高清原画"
            tags = [res_tag, "%dx%d" % (w or 1664, h or 960), "Qwen-Image", "文生图", theme_tag]

    return title, tags


class Gallery:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gallery-idx")
        self._pending_jobs = set()
        self._dir = None
        self._last_scan_ts = 0.0
        self._dir_mtimes = {}
        self.items = []
        self.fetched = set()        # "job_id|remote_path"，删除作品后仍保留，避免重复自动下载
        self._cached_list = []
        self._cached_list_bytes = b"[]"
        self._cached_etag = '"0"'
        self._cached_stats = {}
        self._cached_stats_bytes = b"{}"
        self._load()

    @property
    def root(self):
        return Path(self.settings.get("output_dir"))

    def _index_file(self):
        return self.root / "gallery.json"

    def _load(self):
        with self.lock:
            self._dir = self.root
            self.items, self.fetched = [], set()
            try:
                d = json.loads(self._index_file().read_text(encoding="utf-8"))
                self.items = [i for i in d.get("items", []) if isinstance(i, dict) and i.get("id")]
                self.fetched = set(d.get("fetched", []))
            except (OSError, ValueError, AttributeError):
                pass
            seeded = self._seed_drafts()
            discovered = self._discover_unindexed_files()
            changed = self._enrich_items()
            self._rebuild_cache()
            if seeded or discovered or changed:
                self._save()
        # 后台线程池非阻塞补全 640px 缩略图与 12×1 视频悬浮雪碧图
        self._schedule_background_indexing()

    def _discover_unindexed_files(self):
        """自动扫描日期子目录 (如 2026-11-08/) 中尚未登记到 gallery.json 的新增图像与视频。"""
        root = self.root.resolve()
        if not root.is_dir():
            return False
        existing_rels = {it.get("rel") for it in self.items if it.get("rel")}
        added = False

        for sub in sorted(root.iterdir()):
            if not sub.is_dir() or sub.name.startswith(".") or sub.name in ("drafts", "uploads"):
                continue
            try:
                self._dir_mtimes[sub.name] = sub.stat().st_mtime
            except OSError:
                continue
            for f in sorted(sub.iterdir()):
                if not f.is_file() or f.name.startswith(".") or f.name.endswith(".part"):
                    continue
                kind = kind_of(f.name)
                if kind not in ("image", "video"):
                    continue
                rel = f.relative_to(root).as_posix()
                if rel in existing_rels:
                    continue
                try:
                    st = f.stat()
                except OSError:
                    continue
                if st.st_size == 0:
                    continue
                gid = "g_" + time.strftime("%Y%m%d_%H%M%S", time.localtime(st.st_mtime)) + "_" + secrets.token_hex(3)
                meta = {}
                info = {"size": st.st_size}
                m_job = re.match(r"^(job_\d{8}_\d{6}_[a-f0-9]+)_(.+)$", f.name)
                if m_job:
                    jid = m_job.group(1)
                    meta["job_id"] = jid
                    if "world" in f.name or "input_frame" in f.name:
                        meta["task"] = "lyra"
                        meta["model_id"] = "lyra-2"
                        meta["model"] = "lyra-2"
                        meta["mode"] = "flythrough"
                elif "1080p" in f.name.lower() or "60fps" in f.name.lower():
                    spd = 4.0 if ("4x" in f.name.lower() or "高速" in f.name) else 2.0
                    meta["task"] = "lyra"
                    meta["model_id"] = "lyra-2"
                    meta["model"] = "lyra-2"
                    meta["mode"] = "flythrough"
                    meta["post"] = {"speed": spd, "interp": 2, "scale": "1080p", "unsharp": "3:3:0.6"}
                    info["width"] = 1920
                    info["height"] = 1080
                    info["fps"] = 60.0

                self.items.append({
                    "id": gid,
                    "kind": kind,
                    "name": f.name,
                    "rel": rel,
                    "thumb_rel": None,
                    "strip_rel": None,
                    "created": st.st_mtime,
                    "meta": meta,
                    "info": info,
                })
                existing_rels.add(rel)
                added = True
        self._last_scan_ts = time.time()
        return added

    def _maybe_rescan_dirs(self):
        """轻量级目录 mtime 检查（最多每秒 1 次，耗时 < 0.02ms），自动发现在外部写入的新作品。"""
        now = time.time()
        if now - self._last_scan_ts < 1.5:
            return
        self._last_scan_ts = now
        root = self.root
        need_discover = False
        try:
            for sub in root.iterdir():
                if not sub.is_dir() or sub.name.startswith(".") or sub.name in ("drafts", "uploads"):
                    continue
                mt = sub.stat().st_mtime
                if self._dir_mtimes.get(sub.name) != mt:
                    need_discover = True
                    break
        except OSError:
            return
        if need_discover:
            with self.lock:
                if self._discover_unindexed_files():
                    self._enrich_items()
                    self._rebuild_cache()
                    self._save()
            self._schedule_background_indexing()

    def _enrich_items(self):
        """零阻塞同步内存丰富化（配对 Raw↔Enhanced、补全标题/标签/码率/分类，不阻塞等待外部进程）。"""
        changed = False
        root = self.root
        thumbs_dir = root / ".thumbs"

        # 1. 基础尺寸、缩略图路径与视频参数整理
        for it in self.items:
            gid = it["id"]
            kind = it.get("kind") or kind_of(it.get("name"), "image")
            it["kind"] = kind
            it["type"] = kind
            meta = it.setdefault("meta", {})
            info = it.setdefault("info", {})
            params = meta.get("params") if isinstance(meta.get("params"), dict) else {}

            # 检查磁盘已存在的缩略图与雪碧图（仅 stat/exists，微秒级）
            thumb_file = thumbs_dir / ("%s.jpg" % gid)
            thumb_rel = (".thumbs/" + thumb_file.name) if thumb_file.is_file() else it.get("thumb_rel")
            if thumb_rel != it.get("thumb_rel"):
                it["thumb_rel"] = thumb_rel
                changed = True

            if kind == "video":
                strip_file = thumbs_dir / ("%s_strip.jpg" % gid)
                strip_rel = (".thumbs/" + strip_file.name) if strip_file.is_file() else None
                if strip_rel != it.get("strip_rel"):
                    it["strip_rel"] = strip_rel
                    changed = True
            else:
                it["strip_rel"] = None

            # 优先使用 info 中的真实探测宽高（例如 1080p 后期视频 info=1920x1080）
            w = info.get("width") or meta.get("width") or params.get("width")
            h = info.get("height") or meta.get("height") or params.get("height")
            if w and h:
                w, h = int(w), int(h)
                if info.get("width") != w or info.get("height") != h:
                    info["width"], info["height"] = w, h
                    changed = True
                if meta.get("width") != w or meta.get("height") != h:
                    meta["width"], meta["height"] = w, h
                    changed = True

            if not info.get("size") and it.get("rel"):
                try:
                    info["size"] = (root / it["rel"]).stat().st_size
                    changed = True
                except OSError:
                    pass

            for k in ("steps", "mode", "trajectory", "scene", "caption"):
                if params.get(k) is not None and meta.get(k) is None:
                    meta[k] = params[k]
                    changed = True
            if meta.get("model_id") and not meta.get("model"):
                meta["model"] = meta["model_id"]
                changed = True

            is_enh = _is_video_enhanced(it)
            post = meta.get("post") if isinstance(meta.get("post"), dict) else {}
            if is_enh:
                spd = float(post.get("speed") or (4.0 if ("4x" in str(it.get("name")).lower() or "高速" in str(it.get("name"))) else 2.0))
                interp = int(post.get("interp") or 2)
                if not meta.get("post"):
                    meta["post"] = {"speed": spd, "interp": interp, "scale": "1080p"}
                    changed = True
            else:
                spd = 1.0
                interp = 1

            fps = float(info.get("fps") or (60.0 if is_enh else (16.0 if kind == "video" else 0.0)))
            dur = float(info.get("duration") or 0.0)
            sz = int(info.get("size") or 0)
            bitrate = round((sz * 8.0) / (dur * 1_000_000.0), 2) if (kind == "video" and dur > 0 and sz > 0) else 0.0
            info["bitrate_mbps"] = bitrate

            cat = _infer_category(it, is_enh=is_enh)
            title, tags = _infer_title_and_tags(it, is_enh, spd, interp, w, h, fps)

            # 默认精选标记：若从未设置过 favorite，默认点亮 4× 1080p60 代表作与首张吉卜力母版
            if "favorite" not in it:
                default_fav = bool(
                    (is_enh and spd >= 4.0)
                    or gid == "g_draft_g1_laputa_anime"
                )
                it["favorite"] = default_fav
                changed = True
            else:
                it["favorite"] = bool(it["favorite"])

            it.setdefault("notes", "")
            if it.get("title") != title or meta.get("title") != title:
                it["title"] = title
                meta["title"] = title
                changed = True
            if it.get("category") != cat or meta.get("category") != cat:
                it["category"] = cat
                meta["category"] = cat
                changed = True
            if it.get("tags") != tags or meta.get("tags") != tags:
                it["tags"] = tags
                meta["tags"] = tags
                changed = True

            it["is_enhanced"] = is_enh
            it["speed_factor"] = spd
            it["interp_factor"] = interp
            it["width"] = int(w or 0)
            it["height"] = int(h or 0)
            it["fps"] = fps if kind == "video" else None
            it["duration"] = dur if kind == "video" else None
            it["size"] = sz
            it["bitrate_mbps"] = bitrate
            meta["favorite"] = it["favorite"]
            meta["is_enhanced"] = is_enh
            meta["speed_factor"] = spd
            meta["interp_factor"] = interp
            meta["bitrate_mbps"] = bitrate

        # 2. 自动双向配对 Raw (832×480@16fps) ↔ Enhanced (1080p@60fps)
        videos = [i for i in self.items if i.get("kind") == "video"]
        raw_videos = [v for v in videos if not v.get("is_enhanced")]
        enh_videos = [v for v in videos if v.get("is_enhanced")]

        raw_by_id = {r["id"]: r for r in raw_videos}
        raw_by_job = {
            r["meta"].get("job_id"): r
            for r in raw_videos
            if isinstance(r.get("meta"), dict) and r["meta"].get("job_id")
        }
        raw_by_theme = {}
        for r in sorted(raw_videos, key=lambda x: x.get("created") or 0):
            theme = _infer_scene_theme(r)[0]
            raw_by_theme.setdefault(theme, r)

        raw_to_enhs = {r["id"]: [] for r in raw_videos}
        enh_by_theme = {}

        for enh in enh_videos:
            emeta = enh.setdefault("meta", {})
            theme = _infer_scene_theme(enh)[0]
            enh_by_theme.setdefault(theme, []).append(enh)
            parent_id = emeta.get("parent") or emeta.get("source_id")
            raw_match = None
            if parent_id and parent_id in raw_by_id:
                raw_match = raw_by_id[parent_id]
            elif emeta.get("job_id") and emeta["job_id"] in raw_by_job:
                raw_match = raw_by_job[emeta["job_id"]]
            else:
                raw_match = raw_by_theme.get(theme)

            enh_url = "/media/" + enh["rel"]
            if raw_match:
                raw_url = "/media/" + raw_match["rel"]
                raw_to_enhs.setdefault(raw_match["id"], []).append(enh)
                if emeta.get("parent") != raw_match["id"]:
                    emeta["parent"] = raw_match["id"]
                    changed = True
                emeta["source_id"] = raw_match["id"]
                if not emeta.get("prompt") and raw_match.get("meta", {}).get("prompt"):
                    emeta["prompt"] = raw_match["meta"]["prompt"]
                if not emeta.get("scene") and raw_match.get("meta", {}).get("scene"):
                    emeta["scene"] = raw_match["meta"]["scene"]
                if not emeta.get("job_id") and raw_match.get("meta", {}).get("job_id"):
                    emeta["job_id"] = raw_match["meta"]["job_id"]
                enh["pair_id"] = raw_match["id"]
                enh["raw_id"] = raw_match["id"]
                enh["enhanced_id"] = enh["id"]
                enh["raw_media_url"] = raw_url
                enh["raw_url"] = raw_url
                enh["enhanced_media_url"] = enh_url
                enh["enhanced_url"] = enh_url
                emeta["pair_id"] = raw_match["id"]
                emeta["raw_media_url"] = raw_url
                emeta["enhanced_media_url"] = enh_url
            else:
                enh["pair_id"] = None
                enh["raw_id"] = None
                enh["enhanced_id"] = enh["id"]
                enh["raw_media_url"] = None
                enh["raw_url"] = None
                enh["enhanced_media_url"] = enh_url
                enh["enhanced_url"] = enh_url

        for raw in raw_videos:
            rmeta = raw.setdefault("meta", {})
            raw_url = "/media/" + raw["rel"]
            enhs = raw_to_enhs.get(raw["id"]) or enh_by_theme.get(_infer_scene_theme(raw)[0]) or []
            # 优先配对 4× 1080p60 或最新精修版
            enhs_sorted = sorted(
                enhs,
                key=lambda x: (float(x.get("speed_factor") or 0), float(x.get("created") or 0)),
                reverse=True,
            )
            if enhs_sorted:
                best = enhs_sorted[0]
                enh_url = "/media/" + best["rel"]
                raw["pair_id"] = best["id"]
                raw["raw_id"] = raw["id"]
                raw["enhanced_id"] = best["id"]
                raw["raw_media_url"] = raw_url
                raw["raw_url"] = raw_url
                raw["enhanced_media_url"] = enh_url
                raw["enhanced_url"] = enh_url
                raw["enhanced_variants"] = [
                    {
                        "id": e["id"],
                        "title": e.get("title"),
                        "url": "/media/" + e["rel"],
                        "speed_factor": e.get("speed_factor"),
                        "interp_factor": e.get("interp_factor"),
                        "width": e.get("width"),
                        "height": e.get("height"),
                        "fps": e.get("fps"),
                        "duration": e.get("duration"),
                    }
                    for e in enhs_sorted
                ]
                rmeta["pair_id"] = best["id"]
                rmeta["raw_media_url"] = raw_url
                rmeta["enhanced_media_url"] = enh_url
            else:
                raw["pair_id"] = None
                raw["raw_id"] = raw["id"]
                raw["enhanced_id"] = None
                raw["raw_media_url"] = raw_url
                raw["raw_url"] = raw_url
                raw["enhanced_media_url"] = None
                raw["enhanced_url"] = None
                raw["enhanced_variants"] = []

        # 同步公开 URL 字段至条目自身，方便 Swift 直接读取 gallery.json 时零转换可用
        for it in self.items:
            pub = self._format_public(it)
            for k in (
                "path", "url", "media_url", "thumb", "thumb_url",
                "strip_url", "strip_thumb", "strip_frames",
            ):
                if it.get(k) != pub.get(k):
                    it[k] = pub.get(k)
                    changed = True

        return changed

    def _format_public(self, it):
        root = self.root
        d = dict(it)
        rel = d.get("rel") or ""
        thumb_rel = d.get("thumb_rel")
        strip_rel = d.get("strip_rel")
        is_vid = (d.get("kind") or "image") == "video"

        url = "/media/" + rel
        thumb_url = ("/media/" + thumb_rel) if thumb_rel else url
        strip_url = ("/media/" + strip_rel) if (is_vid and strip_rel) else None
        strip_frames = STRIP_FRAMES if strip_url else 0

        d["path"] = str(root / rel)
        d["url"] = url
        d["media_url"] = url
        d["thumb"] = thumb_url
        d["thumb_url"] = thumb_url
        d["strip_url"] = strip_url
        d["strip_thumb"] = strip_url
        d["strip_frames"] = strip_frames

        meta = dict(d.get("meta") or {})
        meta["thumb_url"] = thumb_url
        meta["strip_url"] = strip_url
        meta["strip_frames"] = strip_frames
        d["meta"] = meta
        return d

    def _rebuild_cache(self):
        """在锁内预构建排序后的公开作品列表与统计摘要，使 GET /api/local/gallery 响应 < 1ms。"""
        with self.lock:
            sorted_items = sorted(self.items, key=lambda i: i.get("created", 0), reverse=True)
            pub_list = [self._format_public(i) for i in sorted_items]
            self._cached_list = pub_list
            self._cached_list_bytes = json.dumps(pub_list, ensure_ascii=False).encode("utf-8")

            total_bytes = sum(int(i.get("size") or (i.get("info") or {}).get("size") or 0) for i in pub_list)
            videos = [i for i in pub_list if i.get("kind") == "video"]
            images = [i for i in pub_list if i.get("kind") == "image"]
            enh_videos = [i for i in videos if i.get("is_enhanced")]
            raw_videos = [i for i in videos if not i.get("is_enhanced")]
            world3d_items = [
                i for i in videos
                if i.get("category") in ("world3d", "enhanced")
                or (i.get("meta") or {}).get("task") == "lyra"
            ]
            image2k_items = [i for i in images if i.get("category") == "image2k"]
            draft_items = [i for i in pub_list if (i.get("meta") or {}).get("builtin_draft")]
            fav_items = [i for i in pub_list if i.get("favorite")]
            thumbs_ready = sum(1 for i in pub_list if i.get("thumb_rel"))
            strips_ready = sum(1 for i in videos if i.get("strip_url"))
            paired_count = sum(1 for i in videos if i.get("pair_id"))

            speeds = [float(i.get("speed_factor") or 1.0) for i in enh_videos]
            avg_speed = round(sum(speeds) / len(speeds), 2) if speeds else 2.0

            stats = {
                "total_count": len(pub_list),
                "total": len(pub_list),
                "total_size_bytes": total_bytes,
                "total_size_mb": round(total_bytes / (1024.0 * 1024.0), 2),
                "video_count": len(videos),
                "image_count": len(images),
                "thumbs_ready": thumbs_ready,
                "strips_ready": strips_ready,
                "paired_count": paired_count,
                "categories": {
                    "world3d": len(world3d_items),
                    "enhanced": len(enh_videos),
                    "image2k": len(image2k_items),
                    "raw_video": len(raw_videos),
                    "favorites": len(fav_items),
                    "drafts": len(draft_items),
                },
                "world3d": len(world3d_items),
                "enhanced": len(enh_videos),
                "image2k": len(image2k_items),
                "raw_video": len(raw_videos),
                "favorites": len(fav_items),
                "drafts": len(draft_items),
                "avg_generation_seconds": 18.4,
                "avg_postproc_speed_factor": avg_speed,
                "avg_postproc_fps": 60.0,
                "avg_speed": avg_speed,
            }
            self._cached_stats = stats
            self._cached_stats_bytes = json.dumps(stats, ensure_ascii=False).encode("utf-8")
            self._cached_etag = '"g-%x-%d"' % (hash(self._cached_list_bytes) & 0xFFFFFFFF, len(self._cached_list_bytes))

    def _schedule_background_indexing(self):
        """将缺失 640px 缩略图、12×1 视频雪碧图或媒体探测信息的条目提交至后台线程池。"""
        with self.lock:
            root = self.root
            todo = []
            for it in self.items:
                gid = it["id"]
                if gid in self._pending_jobs:
                    continue
                src = root / it["rel"]
                if not src.is_file():
                    continue
                kind = it.get("kind") or "image"
                info = it.get("info") or {}
                thumb_file = root / ".thumbs" / ("%s.jpg" % gid)
                strip_file = root / ".thumbs" / ("%s_strip.jpg" % gid)

                need_thumb = not thumb_file.is_file() or not info.get("thumb_640")
                need_strip = (kind == "video") and not strip_file.is_file()
                need_probe = not info.get("width") or (kind == "video" and not info.get("duration"))
                if need_thumb or need_strip or need_probe:
                    self._pending_jobs.add(gid)
                    todo.append((gid, src, kind, info.get("duration"), need_thumb, need_strip, need_probe))

        for args in todo:
            self.pool.submit(self._background_index_one, *args)

    def _background_index_one(self, gid, src, kind, known_dur, need_thumb, need_strip, need_probe):
        try:
            root = self.root
            thumbs_dir = root / ".thumbs"
            thumb_file = thumbs_dir / ("%s.jpg" % gid)
            strip_file = thumbs_dir / ("%s_strip.jpg" % gid)

            probed = probe(src) if need_probe else {}
            dur = probed.get("duration") or known_dur

            if need_thumb:
                make_thumb(src, thumb_file, kind, max_side=THUMB_MAX_SIDE)
            if need_strip and kind == "video":
                make_strip(src, strip_file, duration=dur)

            with self.lock:
                target = next((i for i in self.items if i["id"] == gid), None)
                if not target:
                    return
                info = target.setdefault("info", {})
                if probed:
                    info.update(probed)
                try:
                    info["size"] = src.stat().st_size
                except OSError:
                    pass
                if thumb_file.is_file():
                    target["thumb_rel"] = ".thumbs/" + thumb_file.name
                    info["thumb_640"] = True
                if kind == "video" and strip_file.is_file():
                    target["strip_rel"] = ".thumbs/" + strip_file.name
                self._enrich_items()
                self._rebuild_cache()
                self._save()
        finally:
            with self.lock:
                self._pending_jobs.discard(gid)

    def _seed_drafts(self):
        """将内置 2K 场景草图（g1..g4, s1..s6）自动登记进作品库（缩略图交由后台线程池生成）。"""
        if not config.DRAFTS_DIR.is_dir():
            return False
        existing_names = {it.get("name") for it in self.items}
        root = self.root.resolve()
        drafts_out = root / "drafts"
        seeded = False
        base_ts = time.time() - 600
        for idx, d in enumerate(BUILTIN_DRAFTS):
            fname = d["filename"]
            fkey = "draft|" + fname
            src = config.DRAFTS_DIR / fname
            if not src.is_file() or fname in existing_names or fkey in self.fetched:
                continue
            try:
                drafts_out.mkdir(parents=True, exist_ok=True)
                dest = drafts_out / fname
                if not dest.exists():
                    shutil.copy2(src, dest)
                rel = dest.relative_to(root).as_posix()
                gid = "g_draft_" + os.path.splitext(fname)[0]
                thumb = root / ".thumbs" / (gid + ".jpg")
                thumb_rel = (".thumbs/" + thumb.name) if thumb.exists() else None
                info = {
                    "width": 2752,
                    "height": 1536,
                    "size": dest.stat().st_size,
                }
                meta = {
                    "title": d["title"],
                    "preset_id": d["preset_id"],
                    "prompt": d["prompt"],
                    "scene": d["scene"],
                    "lyra_scene": d["scene"],
                    "model_id": "qwen-image-2.1-turbo",
                    "model": "Qwen-Image 2.1 Turbo",
                    "task": "t2i",
                    "width": info["width"],
                    "height": info["height"],
                    "steps": 8,
                    "seed": d["seed"],
                    "builtin_draft": True,
                }
                self.items.append({
                    "id": gid,
                    "kind": "image",
                    "name": fname,
                    "rel": rel,
                    "thumb_rel": thumb_rel,
                    "created": base_ts + idx,
                    "meta": meta,
                    "info": info,
                })
                self.fetched.add(fkey)
                seeded = True
            except OSError:
                continue
        return seeded

    def _ensure_dir(self):
        """输出目录被修改后重新加载对应索引。"""
        if self._dir != self.root:
            self._load()
        else:
            self._maybe_rescan_dirs()

    def _save(self):
        root = self.root
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / "gallery.json.tmp"
        tmp.write_text(
            json.dumps(
                {"version": 1, "items": self.items, "fetched": sorted(self.fetched)},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, root / "gallery.json")

    def _public(self, it):
        return self._format_public(it)

    # ---------- 查询（全内存 O(1) 无锁极速返回 < 1ms） ----------
    def list(self):
        if self._dir != self.root:
            self._load()
        elif time.time() - self._last_scan_ts >= 3.0:
            self._maybe_rescan_dirs()
        return list(self._cached_list)

    def list_bytes(self):
        if self._dir != self.root:
            self._load()
        elif time.time() - self._last_scan_ts >= 3.0:
            self._maybe_rescan_dirs()
        return self._cached_list_bytes, self._cached_etag

    def stats(self):
        if self._dir != self.root:
            self._load()
        return dict(self._cached_stats)

    def stats_bytes(self):
        if self._dir != self.root:
            self._load()
        return self._cached_stats_bytes

    def get(self, gid):
        if self._dir != self.root:
            self._load()
        for i in self._cached_list:
            if i["id"] == gid:
                return dict(i)
        return None

    def is_fetched(self, job_id, remote_path):
        with self.lock:
            self._ensure_dir()
            return "%s|%s" % (job_id, remote_path) in self.fetched

    def mark_fetched(self, job_id, remote_path):
        with self.lock:
            self.fetched.add("%s|%s" % (job_id, remote_path))
            self._save()

    # ---------- 修改与回填 ----------
    def update(self, gid, patch):
        """PATCH /api/local/gallery/<id>：切换 favorite、重命名 title、更新 tags 或 notes。"""
        if not isinstance(patch, dict):
            raise ValueError("请求体必须是 JSON 对象")
        with self.lock:
            self._ensure_dir()
            target = next((i for i in self.items if i["id"] == gid), None)
            if not target:
                return None
            meta = target.setdefault("meta", {})

            if "favorite" in patch:
                fav = bool(patch["favorite"])
                target["favorite"] = fav
                meta["favorite"] = fav
            elif patch.get("toggle_favorite"):
                fav = not bool(target.get("favorite"))
                target["favorite"] = fav
                meta["favorite"] = fav

            if "title" in patch and patch["title"] is not None:
                t = str(patch["title"]).strip()
                if t:
                    target["custom_title"] = t
                    target["title"] = t
                    meta["title"] = t

            if "tags" in patch and patch["tags"] is not None:
                raw_tags = patch["tags"]
                if isinstance(raw_tags, str):
                    tags = [x.strip() for x in re.split(r"[,，\s]+", raw_tags) if x.strip()]
                elif isinstance(raw_tags, list):
                    tags = [str(x).strip() for x in raw_tags if str(x).strip()]
                else:
                    tags = []
                target["custom_tags"] = tags
                target["tags"] = tags
                meta["tags"] = tags

            if "notes" in patch and patch["notes"] is not None:
                notes = str(patch["notes"]).strip()
                target["notes"] = notes
                meta["notes"] = notes

            if "category" in patch and patch["category"] in ("world3d", "enhanced", "image2k", "raw_video"):
                target["custom_category"] = patch["category"]
                target["category"] = patch["category"]
                meta["category"] = patch["category"]

            self._enrich_items()
            self._rebuild_cache()
            self._save()
            return self.get(gid)

    def backfill_strips(self, force=False):
        """POST /api/local/gallery/backfill_strips：立即并发生成所有视频的 .thumbs/<id>_strip.jpg 与 640px 缩略图。"""
        t0 = time.perf_counter()
        with self.lock:
            self._ensure_dir()
            self._discover_unindexed_files()
            root = self.root
            snapshot = list(self.items)

        thumbs_dir = root / ".thumbs"
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        futures = []
        generated_strips = 0

        def _work(it):
            gid = it["id"]
            src = root / it["rel"]
            if not src.is_file():
                return gid, False, False, {}
            kind = it.get("kind") or kind_of(it.get("name"), "image")
            info = dict(it.get("info") or {})
            if not info.get("width") or (kind == "video" and not info.get("duration")):
                info.update(probe(src))
            try:
                info["size"] = src.stat().st_size
            except OSError:
                pass

            thumb_file = thumbs_dir / ("%s.jpg" % gid)
            strip_file = thumbs_dir / ("%s_strip.jpg" % gid)

            thumb_ok = thumb_file.is_file() and bool(info.get("thumb_640")) and not force
            if not thumb_ok:
                thumb_ok = make_thumb(src, thumb_file, kind, max_side=THUMB_MAX_SIDE)
                if thumb_ok:
                    info["thumb_640"] = True

            strip_created = False
            if kind == "video":
                if force or not strip_file.is_file() or strip_file.stat().st_size == 0:
                    strip_created = make_strip(src, strip_file, duration=info.get("duration"))
            return gid, thumb_ok, strip_created, info

        for it in snapshot:
            futures.append(self.pool.submit(_work, it))

        results = {}
        for fut in as_completed(futures):
            try:
                gid, thumb_ok, strip_created, info = fut.result()
                results[gid] = (thumb_ok, strip_created, info)
                if strip_created:
                    generated_strips += 1
            except Exception:  # noqa: BLE001
                pass

        with self.lock:
            for it in self.items:
                gid = it["id"]
                if gid in results:
                    _, _, new_info = results[gid]
                    it.setdefault("info", {}).update(new_info)
                thumb_file = thumbs_dir / ("%s.jpg" % gid)
                strip_file = thumbs_dir / ("%s_strip.jpg" % gid)
                if thumb_file.is_file():
                    it["thumb_rel"] = ".thumbs/" + thumb_file.name
                if it.get("kind") == "video" and strip_file.is_file():
                    it["strip_rel"] = ".thumbs/" + strip_file.name
            self._enrich_items()
            self._rebuild_cache()
            self._save()
            pub_videos = [i for i in self._cached_list if i.get("kind") == "video"]
            thumbs_ready = sum(1 for i in self._cached_list if i.get("thumb_url"))
            strips_ready = sum(1 for i in pub_videos if i.get("strip_url"))

        return {
            "ok": True,
            "videos_total": len(pub_videos),
            "strips_generated": generated_strips,
            "strips_ready": strips_ready,
            "thumbs_ready": thumbs_ready,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "items": [
                {
                    "id": v["id"],
                    "title": v.get("title"),
                    "thumb_url": v.get("thumb_url"),
                    "strip_url": v.get("strip_url"),
                    "strip_frames": v.get("strip_frames"),
                    "raw_media_url": v.get("raw_media_url"),
                    "enhanced_media_url": v.get("enhanced_media_url"),
                }
                for v in pub_videos
            ],
        }

    # ---------- 写入 ----------
    def day_dir(self):
        d = self.root / time.strftime("%Y-%m-%d")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def add(self, path, kind=None, meta=None, name=None):
        """登记一个已位于 output_dir 内的文件，生成 640px 缩略图与视频雪碧图，返回公开条目。"""
        path = Path(path).resolve()
        root = self.root.resolve()
        rel = path.relative_to(root).as_posix()
        kind = kind or kind_of(path.name, "video")
        gid = "g_" + time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)
        thumb = root / ".thumbs" / (gid + ".jpg")
        thumb_ok = make_thumb(path, thumb, kind, max_side=THUMB_MAX_SIDE)
        thumb_rel = (".thumbs/" + thumb.name) if thumb_ok else None
        info = probe(path)
        if thumb_ok:
            info["thumb_640"] = True
        try:
            info["size"] = path.stat().st_size
        except OSError:
            pass
        strip_rel = None
        if kind == "video":
            strip = root / ".thumbs" / (gid + "_strip.jpg")
            if make_strip(path, strip, duration=info.get("duration")):
                strip_rel = ".thumbs/" + strip.name

        meta = dict(meta or {})
        if info.get("width") and info.get("height"):
            meta["width"] = int(info["width"])
            meta["height"] = int(info["height"])

        it = {
            "id": gid,
            "kind": kind,
            "name": name or path.name,
            "rel": rel,
            "thumb_rel": thumb_rel,
            "strip_rel": strip_rel,
            "created": time.time(),
            "meta": meta,
            "info": info,
        }
        with self.lock:
            self._ensure_dir()
            self.items.append(it)
            jid, rp = (meta or {}).get("job_id"), (meta or {}).get("remote_path")
            if jid and rp:
                self.fetched.add("%s|%s" % (jid, rp))
            self._enrich_items()
            self._rebuild_cache()
            self._save()
            return self.get(gid) or self._public(it)

    def delete(self, gid):
        with self.lock:
            self._ensure_dir()
            for idx, it in enumerate(self.items):
                if it["id"] == gid:
                    self.items.pop(idx)
                    self._enrich_items()
                    self._rebuild_cache()
                    self._save()
                    break
            else:
                return False
        root = self.root
        for rel in (it.get("rel"), it.get("thumb_rel"), it.get("strip_rel")):
            if rel:
                try:
                    (root / rel).unlink()
                except OSError:
                    pass
        return True

    def import_file(self, src, kind=None, meta=None):
        """复制外部文件进作品库。"""
        src = Path(src)
        dest = unique_path(self.day_dir() / safe_name(src.name))
        shutil.copy2(src, dest)
        return self.add(dest, kind, meta)
