// Built-in fallback presets — used when the remote GPU server is offline.
export const CINEMA_CAMERA_RIGS = [
  {
    id: 'iwai_soft',
    name: '🌸 岩井俊二·逆光柔焦 (ARRI Alexa 65 + 85mm f/1.2L)',
    short: '🌸 岩井俊二·逆光柔焦',
    spec: 'ARRI Alexa 65 · Canon FD 85mm f/1.2L · Black Pro-Mist 1/4',
    suffix:
      ', shot on ARRI Alexa 65 with vintage Canon FD 85mm f/1.2L lens and Tiffen Black Pro-Mist 1/4 filter, Shunji Iwai poetic cinema aesthetic, dreamy golden hour rim lighting glowing through hair strands, creamy bokeh, translucent porcelain skin tones, Kodak Vision3 50D 35mm film grain, ethereal romantic atmosphere, 8K masterpiece',
  },
  {
    id: 'wkw_neon',
    name: '🌙 王家卫·霓虹变形镜 (Alexa Mini LF + Cooke 40mm T2.0)',
    short: '🌙 王家卫·霓虹变形镜',
    spec: 'ARRI Alexa Mini LF · Cooke Anamorphic/i SF 40mm T2.0',
    suffix:
      ', shot on ARRI Alexa Mini LF with Cooke Anamorphic/i Special Flare 40mm T2.0 lens, Wong Kar-wai & Christopher Doyle visual poetry, emerald and crimson neon reflections, oval anamorphic bokeh, horizontal amber lens flare, rich chiaroscuro shadows, Kodak Vision3 500T 5219 film stock, 8K cinematic',
  },
  {
    id: 'deakins_godray',
    name: '🌅 迪金斯·丁达尔神光 (IMAX 65mm + Panavision)',
    short: '🌅 迪金斯·丁达尔神光',
    spec: 'ARRI Alexa IMAX 65mm · Panavision Sphero 65',
    suffix:
      ', shot on ARRI Alexa IMAX 65mm with Panavision Sphero 65 primes, Roger Deakins Academy Award cinematography, monumental volumetric Tyndall god rays cutting through atmospheric mist, natural motivated golden-hour chiaroscuro, ultra-wide 2.39:1 epic scale, immaculate dynamic range, 8K',
  },
  {
    id: 'leica_noctilux',
    name: '💎 徕卡夜神·刀锐奶化 (Venice 2 + Noctilux 50mm f/0.95)',
    short: '💎 徕卡夜神·刀锐奶化',
    spec: 'Sony Venice 2 8K · Leica Noctilux-M 50mm f/0.95 ASPH',
    suffix:
      ', shot on Sony Venice 2 8K with Leica Noctilux-M 50mm f/0.95 ASPH wide open at f/0.95, razor-sharp focus on expressive eyes with melting painterly swirl bokeh, micro-contrast perfection, luminous catchlights, cinematic shallow depth of field, 8K',
  },
  {
    id: 'shinkai_twilight',
    name: '🌌 新海诚·暮光炫光 (Panavision DXL2 + Ultra Panatar)',
    short: '🌌 新海诚·暮光炫光',
    spec: 'Panavision Millennium DXL2 8K · Ultra Panatar 1.3x',
    suffix:
      ', shot on Panavision Millennium DXL2 8K with Ultra Panatar 1.3x anamorphic lens, Makoto Shinkai breathtaking magic-hour twilight palette, radiant cobalt blue sky meeting glowing rose-gold horizon clouds, crystalline lens flare, sparkling floating light particles, hyper-detailed emotional beauty, 8K',
  },
  {
    id: 'raw_direct',
    name: '📷 原生直出 (无镜头后缀)',
    short: '📷 原生直出',
    spec: '不追加额外摄影机光学后缀',
    suffix: '',
  },
];

export const GOD_TIER_MOVIE_SCENES = [
  {
    id: 'love_letter_sakura',
    name: '🌸 《情书》樱花逆光回眸',
    prompt:
      '岩井俊二《情书》唯美电影镜头，漫天飞舞的粉白樱花雨中，清冷绝美的东亚少女站在洒满夕阳余晖的木质图书室窗纱旁缓缓回眸，微风吹起白色半透明窗帘与柔顺发丝，温暖的金琥珀色逆光在发梢与睫毛上勾勒出神圣光晕，通透奶油感肌肤，极致浅景深空气感，Shot on ARRI Alexa 65, Canon FD 85mm f/1.2L, Black Pro-Mist 1/4, golden hour rim lighting, Kodak Vision3 50D film grain, 8K masterpiece',
    lyra_scene:
      'a poetic sunlit library window with sheer white curtains billowing in a gentle breeze amidst falling cherry blossom petals at golden hour, warm amber rim light, Shunji Iwai cinematic film aesthetic, shallow depth of field',
  },
  {
    id: 'in_the_mood_for_love',
    name: '🌧️ 《花样年华》暗夜霓虹雨窗',
    prompt:
      '王家卫《花样年华》杜可风摄影美学，1960年代香港雨夜街角，身着精致墨绿丝绸旗袍的东方美人倚在挂满晶莹雨珠的复古车窗前，街边红绿霓虹灯牌在湿润柏油路面与玻璃上折射出迷离光斑，慢门光影韵律，浓郁胶片颗粒与暗调丝绒质感，Shot on ARRI Alexa Mini LF, Cooke Anamorphic/i 40mm T2.0, Wong Kar-wai neon chiaroscuro, oval bokeh, Kodak Vision3 500T, 8K',
    lyra_scene:
      'a 1960s Hong Kong rain-soaked vintage street corner at night glowing with emerald and crimson neon reflections on wet cobblestones, warm tungsten streetlamps, Wong Kar-wai anamorphic cinema look',
  },
  {
    id: 'dune_godray_goddess',
    name: '🌅 《沙丘》丁达尔丝绸女神',
    prompt:
      '罗杰·迪金斯《沙丘》史诗级电影画面，金色黄昏下的古老砂岩神殿高耸拱廊，身披轻盈半透明香槟金丝绸长纱的神秘女神逆光缓步前行，长纱在微风中如波浪般优雅飘逸，巨型丁达尔体积光束穿透神殿穹顶薄雾，漫天细碎金沙在光柱中悬浮闪烁，Shot on IMAX 65mm, Panavision Sphero 65, volumetric god rays, golden hour chiaroscuro, 8K ultra-detailed',
    lyra_scene:
      'a monumental ancient sandstone temple colonnade at golden hour with towering arches, dramatic volumetric Tyndall god rays piercing through shimmering golden dust and silk drapes, Roger Deakins IMAX 65mm cinematography',
  },
  {
    id: 'black_swan_muse',
    name: '🦢 《黑天鹅》晨曦芭蕾缪斯',
    prompt:
      '唯美电影特写镜头，清晨巴黎歌剧院古典排练厅，巨大的拱形落地窗洒入柔和的玫瑰金晨光与丁达尔光束，身穿精致白色天鹅绒羽饰芭蕾舞裙的绝美少女优雅仰颈，天鹅绒与蓬松纱裙在逆光中晶莹剔透，空气中漂浮着闪亮的微尘，徕卡夜神刀锐奶化虚化，Shot on Sony Venice 2 8K, Leica Noctilux 50mm f/0.95, ethereal rim light, dreamy bokeh, 8K',
    lyra_scene:
      'a grand Parisian classical ballet rehearsal hall at dawn with tall arched windows, soft rose-gold sunbeams and floating dust motes illuminating polished oak floors and velvet drapes, ethereal cinema look',
  },
  {
    id: 'otaru_snow_aurora',
    name: '❄️ 《小樽雪国》极光雪原少女',
    prompt:
      '北海道小樽冬日黄昏蓝调时刻（Blue Hour），漫天晶莹鹅毛大雪静静飘落，身着米白色羊绒大衣与酒红围巾的清纯少女站在覆盖厚雪的运河煤气路灯下仰望天空，暖橘色复古街灯与天际绚丽的紫翠色极光交相辉映，睫毛沾着细碎雪花，呼吸化作淡淡白雾，Shot on ARRI Alexa 65, 85mm f/1.2L, cinematic blue hour & warm tungsten contrast, 8K',
    lyra_scene:
      'Otaru canal in Hokkaido during winter blue hour with gentle snowfall, warm vintage amber gas streetlamps reflecting on calm water beside snow-covered stone warehouses under a twilight aurora sky',
  },
  {
    id: 'malena_sicily_coast',
    name: '🌊 《西西里》盛夏阳光海岸',
    prompt:
      '意大利西西里岛盛夏黄金时刻（Golden Hour），阳光倾泻在白色石灰岩悬崖与宝石蓝地中海海面上，身穿复古碎花丝质长裙的绝美女子漫步在洒满夕阳的海滨石板长廊，海风轻柔吹拂微卷长发，波光粼粼的海面反射出梦幻星芒，温暖胶片色调，Shot on Kodak 65mm film, Panavision anamorphic lens, Mediterranean golden sunlight, dreamy lens flare, 8K',
    lyra_scene:
      'a sunlit Mediterranean coastal promenade in Sicily at golden hour, white limestone cliffs overlooking sparkling turquoise sea, warm golden sunbeams and gentle ocean breeze, Italian cinema aesthetic',
  },
  {
    id: 'spirited_lantern_water',
    name: '🏮 《千与千寻》万灯水乡画舫',
    prompt:
      '宫崎骏与新海诚电影美学融合，暮色苍茫的东方奇幻水乡神隐之城，成千上万盏暖金色手绘灯笼在层叠的飞檐楼阁间次第亮起，一叶雕花画舫轻轻滑过如镜面般倒映着漫天晚霞与繁星的河道，孔明灯缓缓升向紫金色苍穹，极致的透视纵深与梦幻光影，Shot on Panavision Millennium DXL2 8K, Ultra Panatar 1.3x, magic hour twilight, 8K masterpiece',
    lyra_scene:
      'an enchanted Oriental canal town at twilight illuminated by thousands of glowing golden paper lanterns along tiered wooden pavilions, calm water reflecting a purple-gold sunset sky and floating sky lanterns',
  },
  {
    id: 'laputa_cloud_sanctuary',
    name: '🏰 《天空之城》浮空古树云海',
    prompt:
      '殿堂级奇幻电影长镜头，漂浮在万米高空翻涌金色云海之上的远古天空之城拉普达，参天发光生命巨树的根系紧密环抱着长满青苔与繁花的汉白玉石砌神殿，银河般的瀑布从浮岛边缘倾泻入无尽云渊，清晨第一缕神圣金光刺破积云，飞鸟掠过天际，Shot on ARRI Alexa IMAX 65mm, volumetric god rays, epic wide angle, 8K',
    lyra_scene:
      'a floating ancient sky castle wrapped in giant glowing tree roots above a sea of golden clouds, moss-covered marble arches and waterfalls cascading into the sky, IMAX fantasy cinema masterpiece',
  },
];

export function expandCinemaMasterPrompt(rawPrompt, rigId = 'iwai_soft', isVideo = false) {
  const clean = (rawPrompt || '').trim();
  const rig = CINEMA_CAMERA_RIGS.find((r) => r.id === rigId) || CINEMA_CAMERA_RIGS[0];
  if (!clean) {
    const pick = GOD_TIER_MOVIE_SCENES[Math.floor(Math.random() * GOD_TIER_MOVIE_SCENES.length)];
    return pick.prompt;
  }
  if (/ARRI Alexa|Panavision|Sony Venice|Leica Noctilux/i.test(clean)) {
    return clean;
  }
  const motionClause = isVideo
    ? '，大师级电影推轨运镜（Smooth Steadicam Dolly Push-in），画面发丝、衣袂与光影粒子随微风自然灵动飘逸，180度快门电影级流畅动态模糊'
    : '，大师级电影黄金分割构图，发丝与睫毛被温暖逆光勾勒出晶莹光晕，眼神极具故事感与情绪张力，前景与背景呈奶油般柔美散景虚化';
  const suffix = rig.suffix || CINEMA_CAMERA_RIGS[0].suffix;
  return `殿堂级唯美电影画面：${clean}${motionClause}，丁达尔体积光束穿透空气微尘，通透细腻的胶片色彩分级${suffix}`;
}

export const DEFAULT_PRESETS = {
  caption_template:
    'A cinematic drone shot glides smoothly forward through {scene}. The entire world is frozen in time like a still tableau: no people, no animals, no wind, nothing moves. Rich parallax and depth, consistent lighting, highly detailed — only the camera travels.',
  lyra_trajectories: [
    { id: 'horizontal_zoom', name: '直线推进', desc: '镜头沿视线方向平稳前推，最稳、最像官方演示', directions: [], strength: { min: 0.1, max: 5, default: 1.0 } },
    { id: 'horizontal_zoom_bend', name: '推进 + 俯冲', desc: '先前推再缓缓下压，适合俯瞰峡谷、城市', directions: ['right', 'left'], strength: { min: 0.1, max: 5, default: 1.0 } },
    { id: 'horizontal_spiral', name: '螺旋推进', desc: '前进同时轻微旋转，更具动感', directions: ['right', 'left'], strength: { min: 0.1, max: 5, default: 1.0 } },
    { id: 'orbit_horizontal', name: '水平环绕', desc: '围绕画面中心主体水平环绕', directions: ['right', 'left'], strength: { min: 0.1, max: 3, default: 1.0 } },
    { id: 'orbit_vertical', name: '垂直环绕', desc: '围绕主体上下翻越', directions: ['up', 'down'], strength: { min: 0.1, max: 3, default: 1.0 } },
    { id: 'horizontal', name: '横移', desc: '镜头水平平移，展示宽阔场景', directions: ['right', 'left'], strength: { min: 0.1, max: 5, default: 1.0 } },
    { id: 'horizontal_lift', name: '升降', desc: '前进同时抬升，从地面飞向高空', directions: ['up', 'down'], strength: { min: 0.1, max: 5, default: 1.0 } },
    { id: 'rotate_spot', name: '原地环视', desc: '相机位置不动，原地转头环顾四周', directions: ['right', 'left'], strength: { min: 0.1, max: 3, default: 1.0 } },
    { id: 'spiral', name: '螺旋', desc: '螺旋形向外展开的探索路径', directions: ['right', 'left'], strength: { min: 0.1, max: 3, default: 1.0 } },
  ],
  scene_presets: GOD_TIER_MOVIE_SCENES,
  t2i_styles: [
    { id: 'cinematic', name: '电影写实', suffix: ', cinematic film still, anamorphic lens, dramatic lighting, shallow depth of field, film grain, ultra detailed' },
    { id: 'photoreal', name: '超写实摄影', suffix: ', photorealistic, shot on 35mm, natural light, 8k, sharp focus, high dynamic range' },
    { id: 'ghibli', name: '吉卜力手绘', suffix: ', Studio Ghibli style, hand-painted watercolor background, soft pastel colors, whimsical' },
    { id: 'anime', name: '日系动画', suffix: ', anime key visual, vibrant colors, crisp line art, detailed background' },
    { id: 'cyberpunk', name: '赛博朋克', suffix: ', cyberpunk, neon lights, rain, reflective surfaces, blade runner atmosphere' },
    { id: 'ink', name: '水墨国风', suffix: ', traditional Chinese ink wash painting, elegant brush strokes, negative space, xuan paper texture' },
    { id: 'render3d', name: '3D 渲染', suffix: ', octane render, unreal engine 5, global illumination, highly detailed 3D' },
    { id: 'concept', name: '概念原画', suffix: ', epic concept art, matte painting, artstation trending, grand scale' },
  ],
  aspect_presets: [
    { id: '16:9', name: '16:9 横屏 2K', width: 2752, height: 1536 },
    { id: '9:16', name: '9:16 竖屏 2K', width: 1536, height: 2752 },
    { id: '1:1', name: '1:1 方图', width: 2048, height: 2048 },
    { id: '4:3', name: '4:3', width: 2368, height: 1776 },
    { id: '3:4', name: '3:4', width: 1776, height: 2368 },
    { id: '21:9', name: '21:9 宽银幕', width: 3072, height: 1312 },
  ],
};

export const LYRA_ASPECT = { id: 'lyra', name: 'Lyra 832×480', width: 832, height: 480 };

export const VIDEO_RESOLUTIONS = [
  { id: '832x480', name: '832×480 横屏', width: 832, height: 480 },
  { id: '480x832', name: '480×832 竖屏', width: 480, height: 832 },
  { id: '1280x720', name: '1280×720 横屏 720p', width: 1280, height: 720 },
  { id: '720x1280', name: '720×1280 竖屏 720p', width: 720, height: 1280 },
  { id: '1024x1024', name: '1024×1024 方形', width: 1024, height: 1024 },
];

export const GPU_OPTIONS = [
  { id: 'T4', name: 'T4 · 16GB' },
  { id: 'L4', name: 'L4 · 24GB' },
  { id: 'G4', name: 'G4 · RTX PRO 6000 96GB' },
  { id: 'A100', name: 'A100 · 40/80GB' },
  { id: 'H100', name: 'H100 · 80GB' },
];

export const DIRECTION_LABEL = { right: '向右', left: '向左', up: '向上', down: '向下', forward: '向前', backward: '向后' };

export const KIND_LABEL = { t2i: '文生图', t2v: '文生视频', i2v: '图生视频', lyra: '3D 世界', tts: '语音合成' };

export const TASK_LABEL = {
  t2i: '生图', t2v: '文生视频', i2v: '图生视频', lyra: '3D 世界', tts: '语音合成', setup: '部署环境', download: '下载模型', load: '加载模型',
  connect: '连接', session_start: '启动实例', session_stop: '释放实例', fetch: '下载到作品库', post: '后期处理',
};

export const LYRA_FPS = 16;

export const LYRA_DURATION_PRESETS = [
  {
    id: '30s',
    label: '🎬 30秒官方长片 (481帧 · 推荐)',
    sub: '30.1s @ 16fps / 30.1s @ 60fps RIFE',
    zoom_out_frames: 241,
    zoom_in_frames: 241,
    frames: 481,
    recommended: true,
  },
  {
    id: '45s',
    label: '🚀 45秒史诗长镜头 (721帧 · 极限)',
    sub: '45.1s @ 16fps · 9段超长穿梭',
    zoom_out_frames: 241,
    zoom_in_frames: 481,
    frames: 721,
  },
  {
    id: '15s',
    label: '⚡ 15秒快速预览 (241帧)',
    sub: '15.1s @ 16fps · 极速出片',
    zoom_out_frames: 81,
    zoom_in_frames: 161,
    frames: 241,
  },
];

export const BUILTIN_MODELS = [
  {
    id: 'qwen-image-2.1-turbo',
    repo: 'Qwen/Qwen-Image-2.1-Turbo',
    name: 'Qwen-Image 2.1 Turbo',
    kind: 't2i',
    builtin: true,
    status: 'downloaded',
    storage_tier: 'ramdisk',
    size_gb: 57.7,
    description: '8 步 2K (2752×1536) 旗舰生图 · 中英文海报排版直出',
    defaults: { width: 2752, height: 1536, steps: 8, guidance: null },
  },
  {
    id: 'z-image-turbo',
    repo: 'Tongyi-MAI/Z-Image-Turbo',
    name: 'Z-Image Turbo (6B)',
    kind: 't2i',
    builtin: true,
    status: 'downloaded',
    storage_tier: 'ramdisk',
    size_gb: 12.8,
    description: '8 步超写实人像与光影摄影大模型 · 单流 DiT 极速出图',
    defaults: { width: 2048, height: 1152, steps: 9, guidance: 0.0 },
  },
  {
    id: 'minimax-h3-hybrid',
    repo: 'MiniMax-AI/MiniMax-H3-Hybrid-1.8',
    subfolder: '1.8-hybrid',
    name: 'MiniMax-H3 v1.8 Hybrid Turbo (音视频同步大模型)',
    kind: 't2v',
    also_t2i: true,
    featured_hybrid: true,
    builtin: true,
    status: 'downloaded',
    storage_tier: 'ramdisk',
    size_gb: 37.5,
    storage_hint: '30TB 云盘 + 88GB /dev/shm 内存盘',
    description: '旗舰版 MiniMax-H3 1.8-Hybrid · 8步音视频同生 & 高清生图',
    defaults: { width: 832, height: 480, num_frames: 81, fps: 24, steps: 8, guidance: 1.0 },
  },
  {
    id: 'minimax-h3-int8',
    repo: 'MiniMax-AI/MiniMax-H3-Hybrid-1.8',
    subfolder: '1.8-hybrid',
    name: 'MiniMax-H3 v1.8 INT8 (极速音视频模型)',
    kind: 'i2v',
    featured_hybrid: true,
    builtin: true,
    status: 'downloaded',
    storage_tier: 'ramdisk',
    size_gb: 21.4,
    storage_hint: '常驻 88GB /dev/shm 内存盘零延迟',
    description: 'INT8 极速量化版，常驻 /dev/shm 内存盘秒级加载，支持一句话或首尾帧生成视频',
    defaults: { width: 832, height: 480, num_frames: 81, fps: 24, steps: 8, guidance: 1.0 },
  },
  {
    id: 'lyra-2',
    repo: 'nvidia/Lyra-2.0',
    name: 'NVIDIA Lyra 2.0 (30s–45s 3D 世界长片)',
    kind: 'lyra',
    builtin: true,
    status: 'downloaded',
    storage_tier: 'drive',
    size_gb: 98.4,
    description: '一句话或单张图生成 30s–45s 可自由穿梭 3D 世界长片（Wan2.1 14B + DA3）',
    defaults: { width: 832, height: 480, steps: 50, guidance: 5.0 },
  },
  {
    id: 'breeze-tts-2',
    repo: 'BreezeBlue/Breeze-TTS-2',
    name: 'Breeze-TTS-2 语音合成 (云盘常驻)',
    kind: 'tts',
    zero_vram: true,
    builtin: true,
    status: 'downloaded',
    storage_tier: 'drive',
    size_gb: 2.8,
    storage_hint: '0显存 · Google Drive 云盘常驻',
    description: 'BreezeBlue/Breeze-TTS-2 自然中英语音合成与视频配音 · 部署于 Google Drive 云盘，0 GPU 显存占用',
    defaults: { steps: 8 },
  },
];

export const VIDEO_PROMPT_PRESETS = GOD_TIER_MOVIE_SCENES;
