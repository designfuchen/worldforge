// Modal overlays: Lightbox, Interactive A/B Split-Screen Comparison, Cinema Showcase Mode, GPU Benchmark Report, Gallery Picker, Confirm Dialog.
import { h, esc, fmtAgo, fmtNum, copyText, clamp, toast } from './dom.js';
import { icon } from './icons.js';
import { S } from './store.js';
import { KIND_LABEL, TASK_LABEL } from './defaults.js';
import * as A from './actions.js';

let layer;
function getLayer() {
  if (!layer) layer = document.getElementById('overlays');
  return layer;
}

function mount(node, { onClose, cls = '' } = {}) {
  const back = h('div', { class: `overlay ${cls}` }, node);
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    back.classList.add('out');
    document.removeEventListener('keydown', onKey, true);
    back.querySelectorAll('video').forEach((v) => {
      try { v.pause(); } catch {}
    });
    setTimeout(() => back.remove(), 220);
    onClose && onClose();
  };
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
    back._onKey && back._onKey(e);
  };
  back.addEventListener('mousedown', (e) => { if (e.target === back) close(); });
  document.addEventListener('keydown', onKey, true);
  getLayer().append(back);
  requestAnimationFrame(() => back.classList.add('in'));
  return { back, close };
}

/* ---------------- confirm ---------------- */
export function confirmDialog({ title, message, confirmText = '确定', cancelText = '取消', danger = false }) {
  return new Promise((resolve) => {
    let result = false;
    const okBtn = h('button', { class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`, onclick: () => { result = true; m.close(); } }, confirmText);
    const card = h('div', { class: 'dialog' },
      h('div', { class: 'dialog-ic ' + (danger ? 'danger' : ''), html: icon(danger ? 'alert' : 'info') }),
      h('h3', {}, title),
      h('p', {}, message),
      h('div', { class: 'dialog-actions' },
        h('button', { class: 'btn btn-ghost', onclick: () => m.close() }, cancelText),
        okBtn));
    const m = mount(card, { onClose: () => resolve(result) });
    m.back._onKey = (e) => { if (e.key === 'Enter') { result = true; m.close(); } };
    setTimeout(() => okBtn.focus(), 50);
  });
}

/* ---------------- lightbox ---------------- */
/**
 * items: [{kind,url,name,meta,gallery?,remotePath?}]
 */
export function openLightbox(items, index = 0) {
  if (!items || !items.length) return;
  let i = clamp(index, 0, items.length - 1);
  const stage = h('div', { class: 'lb-stage' });
  const side = h('aside', { class: 'lb-side' });
  const counter = h('div', { class: 'lb-counter' });
  const prev = h('button', { class: 'lb-nav lb-prev', html: icon('chevronLeft'), 'aria-label': '上一张', onclick: () => go(-1) });
  const next = h('button', { class: 'lb-nav lb-next', html: icon('chevronRight'), 'aria-label': '下一张', onclick: () => go(1) });
  const box = h('div', { class: 'lightbox' },
    h('button', { class: 'lb-close icon-btn', html: icon('x'), 'aria-label': '关闭', onclick: () => m.close() }),
    stage, prev, next, counter, side);
  const m = mount(box, { cls: 'overlay-dark' });
  m.back._onKey = (e) => {
    if (e.key === 'ArrowLeft') go(-1);
    if (e.key === 'ArrowRight') go(1);
    if (e.key === ' ' && stage.querySelector('video')) {
      e.preventDefault();
      const v = stage.querySelector('video');
      if (v.paused) v.play().catch(() => {});
      else v.pause();
    }
  };

  function go(d) {
    if (items.length < 2) return;
    i = (i + d + items.length) % items.length;
    render();
  }
  function render() {
    const it = items[i];
    stage.querySelectorAll('video').forEach((v) => v.pause());
    stage.innerHTML = '';
    if (it.kind === 'video') {
      stage.append(h('video', { src: it.url, controls: true, autoplay: true, loop: true, playsinline: true, class: 'lb-media' }));
    } else {
      const img = h('img', { src: it.url, alt: it.title || it.name || '', decoding: 'async', class: 'lb-media' });
      stage.append(img);
    }
    prev.hidden = next.hidden = items.length < 2;
    counter.textContent = items.length > 1 ? `${i + 1} / ${items.length}` : '';
    renderSide(it);
  }
  function renderSide(it) {
    const meta = it.meta || {};
    const g = it.gallery;
    const rows = [];
    const add = (k, v) => { if (v != null && v !== '') rows.push(h('div', { class: 'kv' }, h('span', {}, k), h('b', {}, String(v)))); };
    const w = it.width || meta.width || g?.width || g?.info?.width;
    const ht = it.height || meta.height || g?.height || g?.info?.height;
    const fps = it.fps || meta.fps || g?.fps || g?.info?.fps;
    const dur = it.duration || meta.duration || g?.duration || g?.info?.duration;
    const catLabels = {
      enhanced: '1080p60 RIFE 增强',
      world3d: '3D 世界穿梭',
      image2k: '2K 场景原画',
      raw_video: '原始视频',
    };
    const cat = it.category || (g ? A.resolveGalleryCategory(g) : null);

    if (cat && catLabels[cat]) add('分类', catLabels[cat]);
    add('模型', meta.model || meta.model_id);
    add('任务', TASK_LABEL[meta.task] || KIND_LABEL[meta.task] || meta.task);
    if (w && ht) add('尺寸', `${w}×${ht}`);
    if (fps) add('帧率', `${Math.round(fps)} fps`);
    if (dur) add('时长', `${Number(dur).toFixed(2)}s`);
    add('种子', meta.seed);
    add('步数', meta.steps);
    add('轨迹', meta.trajectory || meta.mode);
    add('来源任务', meta.job_id);
    add('创建', fmtAgo(it.created || (g && g.created)));
    const prompt = meta.prompt || meta.scene || meta.caption;
    const btn = (ic, label, fn, cls = '') => h('button', { class: `btn btn-sm ${cls}`, onclick: fn, html: icon(ic) + `<span>${esc(label)}</span>` });
    const actions = [];

    if (it.kind === 'video') {
      actions.push(btn('compare', 'A/B 分屏画质对比 (Raw vs 1080p60)', () => {
        m.close();
        openABCompare(it);
      }, 'btn-primary'));
    }

    if (g) {
      const fav = A.isGalleryFavorite(g);
      actions.push(btn(fav ? 'starFill' : 'star', fav ? '★ 已收藏（点击取消）' : '☆ 加入收藏夹', async () => {
        await A.toggleFavorite(g);
        it.favorite = A.isGalleryFavorite(g);
        renderSide(it);
      }, fav ? 'btn-accent' : ''));
      actions.push(btn('folder', '在 Finder 中显示', () => A.reveal(g.path)));
    } else {
      actions.push(btn('download', '下载', () => A.download(it.url, it.name)));
    }

    if (it.kind === 'image') {
      actions.push(btn('cube', '做成 3D 世界', () => { m.close(); A.sendToWorld(it); }, 'btn-accent'));
      actions.push(btn('video', '图生视频', () => { m.close(); A.sendToVideo(it); }));
    } else if (g) {
      actions.push(btn('sliders', '后期处理', () => { m.close(); A.sendToPost(it); }, 'btn-accent'));
    }
    if (g) actions.push(btn('trash', '删除', async () => {
      if (await A.deleteGallery(g)) {
        items.splice(i, 1);
        if (!items.length) return m.close();
        i = Math.min(i, items.length - 1);
        render();
      }
    }, 'btn-danger-ghost'));

    const displayTitle = it.title || g?.title || meta.title || it.name || '';
    side.innerHTML = '';
    side.append(
      h('div', { class: 'lb-title' },
        h('span', { class: 'badge', 'data-tone': it.kind === 'video' ? 'cyan' : 'violet' }, it.kind === 'video' ? '视频' : '图片'),
        h('b', { title: displayTitle }, displayTitle)),
      it.name && it.name !== displayTitle ? h('div', { class: 'muted mono', style: { fontSize: '11px', marginTop: '-8px' } }, it.name) : null,
      prompt ? h('div', { class: 'lb-prompt' },
        h('div', { class: 'lb-prompt-head' }, h('span', {}, '提示词 / 场景描述'),
          h('button', { class: 'icon-btn sm', title: '复制', html: icon('copy'), onclick: () => copyText(prompt) })),
        h('p', {}, prompt)) : null,
      h('div', { class: 'lb-kvs' }, rows),
      h('div', { class: 'lb-actions' }, actions));
  }
  render();
  return m;
}

/* =========================================================
   INTERACTIVE A/B SPLIT-SCREEN VIDEO & IMAGE COMPARISON MODAL
   ========================================================= */
export function openABCompare(initialItem = null) {
  // Gather all candidate videos from gallery so user can switch scenes inside the modal
  const allVideos = (S.gallery || [])
    .filter((g) => (g.kind || g.type) === 'video')
    .map((g) => A.mediaFromGallery(g));

  // Prefer enhanced 1080p60 videos first in the selector
  const enhancedVideos = allVideos.filter((v) => v.category === 'enhanced' || v.raw_media_url || v.enhanced_media_url);
  const candidateList = enhancedVideos.length ? enhancedVideos : allVideos;

  let currentItem = initialItem
    ? (initialItem.url ? initialItem : A.mediaFromGallery(initialItem))
    : (candidateList[0] || null);

  if (!currentItem) {
    toast('作品库中暂无可对比的视频作品', 'warn');
    return null;
  }

  let splitPct = 50;
  let splitMode = 'diagonal'; // 'diagonal' | 'vertical'
  let playing = true;
  let speed = 1;
  let sweeping = false;
  let rafId = null;
  let sweepPhase = 0;

  // Stage elements
  const enhVideo = h('video', {
    class: 'ab-video ab-video-enh',
    muted: true,
    loop: true,
    playsinline: true,
    preload: 'auto',
  });

  const rawVideo = h('video', {
    class: 'ab-video ab-video-raw',
    muted: true,
    loop: true,
    playsinline: true,
    preload: 'auto',
  });

  const rawLayer = h('div', { class: 'ab-layer ab-layer-raw' },
    rawVideo,
    h('div', { class: 'ab-corner-badge raw-badge' },
      h('span', { class: 'ab-dot raw' }),
      h('b', {}, '3DGS / RAW · 832×480 16FPS'),
      h('span', { class: 'ab-badge-sub' }, 'Colab 原始直出')));

  const enhLayer = h('div', { class: 'ab-layer ab-layer-enh' },
    enhVideo,
    h('div', { class: 'ab-corner-badge enh-badge' },
      h('span', { class: 'ab-dot enh' }),
      h('b', {}, 'Video · Lyra 2.0 1080p60'),
      h('span', { class: 'ab-badge-sub' }, 'M1 Max RIFE v4.6 光流补帧 + 4× 高速穿梭')));

  const svgLineWrap = h('div', {
    class: 'ab-svg-overlay',
    html: `<svg class="ab-split-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <line class="ab-svg-shadow" x1="68" y1="0" x2="32" y2="100" vector-effect="non-scaling-stroke" />
      <line class="ab-svg-line" x1="68" y1="0" x2="32" y2="100" vector-effect="non-scaling-stroke" />
    </svg>`,
  });
  const svgShadowLine = svgLineWrap.querySelector('.ab-svg-shadow');
  const svgMainLine = svgLineWrap.querySelector('.ab-svg-line');

  const handleArrows = h('span', { class: 'ab-arrows' }, '‹ ╱ ›');
  const handlePctLabel = h('span', { class: 'ab-handle-pct' }, '50%');
  const divider = h('div', { class: 'ab-divider' },
    h('div', { class: 'ab-line-glow' }),
    h('div', { class: 'ab-handle' },
      handleArrows,
      handlePctLabel));

  const stage = h('div', { class: 'ab-stage', dataset: { splitMode } }, enhLayer, rawLayer, svgLineWrap, divider);

  // Controls
  const playBtn = h('button', {
    class: 'btn btn-sm btn-primary ab-play-btn',
    type: 'button',
    html: icon('pause') + '<span>暂停</span>',
  });

  const stepBackBtn = h('button', {
    class: 'btn btn-xs',
    type: 'button',
    title: '后退一帧 (1/60s)',
    onclick: () => stepFrame(-1),
  }, '-1帧');

  const stepFwdBtn = h('button', {
    class: 'btn btn-xs',
    type: 'button',
    title: '前进一帧 (1/60s)',
    onclick: () => stepFrame(1),
  }, '+1帧');

  const timeLabel = h('span', { class: 'ab-time mono' }, '00.00s / 00.00s · 第 1 帧');
  const seekRange = h('input', {
    type: 'range',
    class: 'ab-seek',
    min: 0,
    max: 1000,
    step: 1,
    value: 0,
  });

  const speedSeg = h('div', { class: 'seg seg-xs' });
  [0.25, 0.5, 1, 2].forEach((r) => {
    const b = h('button', {
      type: 'button',
      class: r === speed ? 'on' : '',
      dataset: { r: String(r) },
      onclick: () => setPlaybackSpeed(r),
    }, `${r}×`);
    speedSeg.append(b);
  });

  const sweepBtn = h('button', {
    class: 'btn btn-xs btn-accent',
    type: 'button',
    title: '自动左右平滑扫光对比（适合录屏展示）',
    html: icon('sparkles') + '<span>自动扫光</span>',
    onclick: () => toggleSweep(),
  });

  const modeSeg = h('div', { class: 'seg seg-xs ab-mode-seg' },
    h('button', {
      type: 'button',
      class: 'on',
      dataset: { m: 'diagonal' },
      title: '@NVIDIAAI 官方 X 演示同款斜切分屏 (3DGS / Video)',
      onclick: () => setSplitMode('diagonal'),
    }, '╱ NVIDIA 官方斜切分屏'),
    h('button', {
      type: 'button',
      dataset: { m: 'vertical' },
      title: '标准垂直分屏对比',
      onclick: () => setSplitMode('vertical'),
    }, '┃ 垂直分屏'));

  const splitPresets = h('div', { class: 'seg seg-xs' },
    h('button', { type: 'button', onclick: () => { stopSweep(); setSplit(25); } }, '25%'),
    h('button', { type: 'button', class: 'on', onclick: () => { stopSweep(); setSplit(50); } }, '50%'),
    h('button', { type: 'button', onclick: () => { stopSweep(); setSplit(75); } }, '75%'));

  // Scene switcher select in header
  const sceneSelect = h('select', { class: 'select select-sm ab-scene-select', 'aria-label': '切换对比作品' });
  if (candidateList.length) {
    candidateList.forEach((cand) => {
      sceneSelect.append(
        h('option', {
          value: cand.id || cand.url,
          selected: (cand.id && cand.id === currentItem.id) || cand.url === currentItem.url,
        }, cand.title || cand.name),
      );
    });
  } else {
    sceneSelect.append(h('option', { value: currentItem.url }, currentItem.title || currentItem.name));
  }
  sceneSelect.addEventListener('change', () => {
    const picked = candidateList.find((x) => (x.id || x.url) === sceneSelect.value);
    if (picked) loadPair(picked);
  });

  const pairStatusBadge = h('span', { class: 'badge', 'data-tone': 'cyan' }, '双流硬解同步中');
  const titleText = h('b', { class: 'ab-title-txt' }, '');

  const modal = h('div', { class: 'ab-modal' },
    h('header', { class: 'ab-head' },
      h('div', { class: 'ab-head-left' },
        h('span', { class: 'badge', 'data-tone': 'violet', html: icon('compare') + '<span>A/B 实时像素级分屏对比</span>' }),
        titleText,
        pairStatusBadge),
      h('div', { class: 'ab-head-right' },
        modeSeg,
        candidateList.length > 1 ? h('label', { class: 'ab-switcher-label' }, h('span', { class: 'muted' }, '切换场景：'), sceneSelect) : null,
        h('button', { class: 'icon-btn', title: '关闭 (ESC)', html: icon('x'), onclick: () => m.close() }))),
    stage,
    h('footer', { class: 'ab-footer' },
      h('div', { class: 'ab-transport' },
        playBtn,
        stepBackBtn,
        stepFwdBtn,
        seekRange,
        timeLabel),
      h('div', { class: 'ab-tools' },
        h('span', { class: 'muted' }, '倍速'),
        speedSeg,
        h('span', { class: 'muted' }, '分屏线'),
        splitPresets,
        sweepBtn)));

  function setSplitMode(mName) {
    splitMode = mName === 'vertical' ? 'vertical' : 'diagonal';
    stage.dataset.splitMode = splitMode;
    handleArrows.textContent = splitMode === 'diagonal' ? '‹ ╱ ›' : '‹ │ ›';
    modeSeg.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.m === splitMode));
    setSplit(splitPct);
  }

  function setSplit(pct) {
    splitPct = clamp(pct, 2, 98);
    if (splitMode === 'diagonal') {
      const topX = (splitPct + 18).toFixed(2);
      const botX = (splitPct - 18).toFixed(2);
      rawLayer.style.clipPath = `polygon(0 0, ${topX}% 0, ${botX}% 100%, 0 100%)`;
      if (svgMainLine && svgShadowLine) {
        svgMainLine.setAttribute('x1', topX);
        svgMainLine.setAttribute('y1', '0');
        svgMainLine.setAttribute('x2', botX);
        svgMainLine.setAttribute('y2', '100');
        svgShadowLine.setAttribute('x1', topX);
        svgShadowLine.setAttribute('y1', '0');
        svgShadowLine.setAttribute('x2', botX);
        svgShadowLine.setAttribute('y2', '100');
      }
    } else {
      rawLayer.style.clipPath = `inset(0 ${(100 - splitPct).toFixed(2)}% 0 0)`;
      const xStr = splitPct.toFixed(2);
      if (svgMainLine && svgShadowLine) {
        svgMainLine.setAttribute('x1', xStr);
        svgMainLine.setAttribute('y1', '0');
        svgMainLine.setAttribute('x2', xStr);
        svgMainLine.setAttribute('y2', '100');
        svgShadowLine.setAttribute('x1', xStr);
        svgShadowLine.setAttribute('y1', '0');
        svgShadowLine.setAttribute('x2', xStr);
        svgShadowLine.setAttribute('y2', '100');
      }
    }
    divider.style.left = `${splitPct.toFixed(2)}%`;
    handlePctLabel.textContent = `${Math.round(splitPct)}%`;
  }

  function stopSweep() {
    if (sweeping) {
      sweeping = false;
      sweepBtn.classList.remove('on');
    }
  }

  function toggleSweep() {
    sweeping = !sweeping;
    sweepBtn.classList.toggle('on', sweeping);
    if (sweeping) {
      sweepPhase = Math.asin(clamp((splitPct - 50) / 38, -1, 1));
    }
  }

  function setPlaybackSpeed(r) {
    speed = r;
    speedSeg.querySelectorAll('button').forEach((b) => b.classList.toggle('on', Number(b.dataset.r) === r));
    enhVideo.playbackRate = speed;
    syncRawSpeedAndTime(true);
  }

  function syncRawSpeedAndTime(forceSeek = false) {
    const eDur = enhVideo.duration || 0;
    const rDur = rawVideo.duration || 0;
    if (!eDur || !rDur) {
      rawVideo.playbackRate = speed;
      if (forceSeek) rawVideo.currentTime = enhVideo.currentTime;
      return;
    }
    const durRatio = rDur / eDur;
    // If raw video is pre-speedup (e.g. 4x or 8x longer), scale its time proportionally so camera position matches!
    if (durRatio > 1.35 || durRatio < 0.75) {
      const targetRate = clamp(speed * durRatio, 0.1, 16);
      if (Math.abs(rawVideo.playbackRate - targetRate) > 0.05) {
        try { rawVideo.playbackRate = targetRate; } catch {}
      }
      const targetTime = (enhVideo.currentTime / eDur) * rDur;
      if (forceSeek || Math.abs(rawVideo.currentTime - targetTime) > 0.22) {
        try { rawVideo.currentTime = targetTime; } catch {}
      }
    } else {
      if (Math.abs(rawVideo.playbackRate - speed) > 0.02) {
        rawVideo.playbackRate = speed;
      }
      if (forceSeek || Math.abs(rawVideo.currentTime - enhVideo.currentTime) > 0.08) {
        try { rawVideo.currentTime = enhVideo.currentTime; } catch {}
      }
    }
  }

  function togglePlay() {
    if (enhVideo.paused) {
      playing = true;
      enhVideo.play().catch(() => {});
      rawVideo.play().catch(() => {});
      playBtn.innerHTML = icon('pause') + '<span>暂停</span>';
    } else {
      playing = false;
      enhVideo.pause();
      rawVideo.pause();
      playBtn.innerHTML = icon('play') + '<span>播放</span>';
    }
  }

  function stepFrame(dir) {
    if (!enhVideo.paused) togglePlay();
    const dt = (1 / 60) * dir;
    const dur = enhVideo.duration || 3.8;
    enhVideo.currentTime = clamp((enhVideo.currentTime || 0) + dt, 0, Math.max(0, dur - 0.01));
    syncRawSpeedAndTime(true);
    updateTimelineUI();
  }

  function updateTimelineUI() {
    const dur = enhVideo.duration || 0;
    const cur = enhVideo.currentTime || 0;
    if (dur > 0) {
      const ratio = clamp(cur / dur, 0, 1);
      seekRange.value = String(Math.round(ratio * 1000));
      seekRange.style.setProperty('--p', `${(ratio * 100).toFixed(1)}%`);
      const curFrame = Math.min(Math.ceil(dur * 60), Math.floor(cur * 60) + 1);
      const totFrames = Math.round(dur * 60);
      timeLabel.textContent = `${cur.toFixed(2).padStart(5, '0')}s / ${dur.toFixed(2).padStart(5, '0')}s · 第 ${curFrame}/${totFrames} 帧`;
    }
  }

  function loadPair(it) {
    currentItem = it;
    const pair = A.resolveABPair(it);
    titleText.textContent = pair.title;
    enhVideo.src = pair.enhancedUrl;
    rawVideo.src = pair.rawUrl;

    // If rawUrl and enhancedUrl point to the same file, apply subtle raw 832x480 simulation class on rawVideo
    rawVideo.classList.toggle('sim-raw', !pair.hasDistinctPair);
    pairStatusBadge.textContent = pair.hasDistinctPair
      ? 'RAW 原片 + RIFE 1080p60 双流同步'
      : 'RIFE 1080p60 实时滤镜对比';
    pairStatusBadge.dataset.tone = pair.hasDistinctPair ? 'green' : 'cyan';

    enhVideo.load();
    rawVideo.load();
    enhVideo.playbackRate = speed;
    if (playing) {
      Promise.allSettled([enhVideo.play(), rawVideo.play()]);
      playBtn.innerHTML = icon('pause') + '<span>暂停</span>';
    }
  }

  // Pointer drag on stage / divider
  let dragging = false;
  function updateSplitFromPointer(clientX) {
    const rect = stage.getBoundingClientRect();
    if (!rect.width) return;
    const pct = ((clientX - rect.left) / rect.width) * 100;
    setSplit(pct);
  }

  stage.addEventListener('pointerdown', (e) => {
    dragging = true;
    stopSweep();
    stage.setPointerCapture?.(e.pointerId);
    updateSplitFromPointer(e.clientX);
  });
  stage.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    updateSplitFromPointer(e.clientX);
  });
  ['pointerup', 'pointercancel'].forEach((ev) => {
    stage.addEventListener(ev, () => { dragging = false; });
  });

  playBtn.addEventListener('click', togglePlay);

  seekRange.addEventListener('input', () => {
    const dur = enhVideo.duration || 0;
    if (!dur) return;
    const ratio = Number(seekRange.value) / 1000;
    enhVideo.currentTime = ratio * dur;
    syncRawSpeedAndTime(true);
    updateTimelineUI();
  });

  function tick() {
    if (!enhVideo.paused) {
      syncRawSpeedAndTime(false);
      updateTimelineUI();
    }
    if (sweeping) {
      sweepPhase += 0.022;
      setSplit(50 + Math.sin(sweepPhase) * 36);
    }
    rafId = requestAnimationFrame(tick);
  }

  const m = mount(modal, {
    cls: 'overlay-dark',
    onClose: () => {
      if (rafId) cancelAnimationFrame(rafId);
    },
  });

  m.back._onKey = (e) => {
    if (e.key === ' ') {
      e.preventDefault();
      togglePlay();
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      if (e.shiftKey) { stopSweep(); setSplit(splitPct - 5); }
      else stepFrame(-1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      if (e.shiftKey) { stopSweep(); setSplit(splitPct + 5); }
      else stepFrame(1);
    } else if (e.key === 's' || e.key === 'S') {
      e.preventDefault();
      toggleSweep();
    }
  };

  setSplit(50);
  loadPair(currentItem);
  rafId = requestAnimationFrame(tick);
  return m;
}

/* =========================================================
   CINEMA SHOWCASE MODE ("一键开启影院轮播展厅")
   ========================================================= */
export function openCinemaShowcase(customItems = null, startIndex = 0) {
  // Gather 1080p60 3D world videos first, fallback to all videos
  const allGal = (S.gallery || []).map((g) => A.mediaFromGallery(g));
  let playlist = customItems && customItems.length
    ? customItems.filter((x) => x.kind === 'video')
    : allGal.filter((x) => x.kind === 'video' && (x.category === 'enhanced' || x.category === 'world3d'));

  if (!playlist.length) {
    playlist = allGal.filter((x) => x.kind === 'video');
  }
  if (!playlist.length) {
    playlist = allGal;
  }
  if (!playlist.length) {
    toast('作品库中暂无可展播的作品', 'warn');
    return null;
  }

  let idx = clamp(startIndex, 0, playlist.length - 1);
  let autoCycle = true;
  let hudVisible = true;
  let timerId = null;

  const videoEl = h('video', {
    class: 'cinema-video',
    autoplay: true,
    muted: true,
    playsinline: true,
  });
  const imgEl = h('img', {
    class: 'cinema-img',
    decoding: 'async',
    hidden: true,
  });

  const progFill = h('i', {});
  const progBar = h('div', { class: 'cinema-progress' }, progFill);

  const hudTitle = h('h2', { class: 'cinema-title' }, '');
  const hudSub = h('p', { class: 'cinema-sub' }, '');
  const hudBadges = h('div', { class: 'cinema-badges' });
  const hudCounter = h('span', { class: 'cinema-counter mono' }, '');

  const autoBtn = h('button', {
    class: 'btn btn-sm btn-accent',
    type: 'button',
    html: icon('play') + '<span>自动轮播：开</span>',
    onclick: () => {
      autoCycle = !autoCycle;
      autoBtn.innerHTML = icon(autoCycle ? 'play' : 'pause') + `<span>自动轮播：${autoCycle ? '开' : '关'}</span>`;
      autoBtn.classList.toggle('btn-accent', autoCycle);
    },
  });

  const abBtn = h('button', {
    class: 'btn btn-sm',
    type: 'button',
    html: icon('compare') + '<span>切入 A/B 分屏对比</span>',
    onclick: () => {
      const cur = playlist[idx];
      m.close();
      openABCompare(cur);
    },
  });

  const fsBtn = h('button', {
    class: 'icon-btn',
    title: '切换全屏 (F)',
    html: icon('maximize'),
    onclick: () => {
      if (!document.fullscreenElement) {
        box.requestFullscreen?.().catch(() => {});
      } else {
        document.exitFullscreen?.().catch(() => {});
      }
    },
  });

  const stripWrap = h('div', { class: 'cinema-strip' });

  const box = h('div', { class: 'cinema-box' },
    videoEl,
    imgEl,
    h('div', { class: 'cinema-hud-top' },
      h('div', { class: 'cinema-brand-pill' },
        h('span', { class: 'cinema-live-dot' }),
        h('b', {}, 'WORLDFORGE CINEMA SHOWCASE'),
        h('span', {}, 'NVIDIA Lyra 2.0 × Apple M1 Max RIFE 1080p60')),
      h('div', { class: 'cinema-top-actions' },
        hudCounter,
        autoBtn,
        abBtn,
        fsBtn,
        h('button', { class: 'icon-btn', title: '退出展厅 (ESC)', html: icon('x'), onclick: () => m.close() }))),
    h('div', { class: 'cinema-hud-bottom' },
      h('div', { class: 'cinema-meta-info' },
        hudBadges,
        hudTitle,
        hudSub),
      stripWrap,
      progBar));

  function renderStrip() {
    stripWrap.innerHTML = '';
    playlist.forEach((it, i) => {
      const thumbNode = h('button', {
        class: 'cinema-thumb' + (i === idx ? ' on' : ''),
        title: it.title || it.name,
        onclick: () => showAt(i),
      },
        h('img', { src: it.thumb || it.url, loading: 'lazy', decoding: 'async', alt: '' }),
        h('span', {}, `#${String(i + 1).padStart(2, '0')}`));
      stripWrap.append(thumbNode);
    });
  }

  function showAt(nextIdx) {
    clearTimeout(timerId);
    idx = (nextIdx + playlist.length) % playlist.length;
    const it = playlist[idx];
    const w = it.width || it.meta?.width || 1920;
    const ht = it.height || it.meta?.height || 1080;
    const fps = it.fps || it.meta?.fps || 60;
    const dur = it.duration || it.meta?.duration || 3.8;

    hudCounter.textContent = `${String(idx + 1).padStart(2, '0')} / ${String(playlist.length).padStart(2, '0')}`;
    hudTitle.textContent = it.title || it.name || `WorldForge #${idx + 1}`;
    hudSub.textContent = it.meta?.prompt || it.meta?.scene || 'Cinematic 3D World Fly-Through · Frozen Tableau Camera Trajectory';

    hudBadges.innerHTML = '';
    hudBadges.append(
      h('span', { class: 'badge', 'data-tone': 'cyan' }, `${w}×${ht} @ ${Math.round(fps)}FPS`),
      h('span', { class: 'badge', 'data-tone': 'violet' }, it.category === 'enhanced' ? 'RIFE v4.6 光流补帧 · 4× 穿梭' : 'Lyra 2.0 3D 世界漫游'),
      h('span', { class: 'badge', 'data-tone': 'green' }, `时长 ${Number(dur).toFixed(1)}s`),
      it.meta?.seed != null ? h('span', { class: 'badge', 'data-tone': 'muted' }, `Seed ${it.meta.seed}`) : null,
    );

    stripWrap.querySelectorAll('.cinema-thumb').forEach((b, i) => b.classList.toggle('on', i === idx));

    if (it.kind === 'video') {
      imgEl.hidden = true;
      videoEl.hidden = false;
      videoEl.loop = !autoCycle || playlist.length === 1;
      videoEl.src = it.url;
      videoEl.play().catch(() => {});
    } else {
      videoEl.pause();
      videoEl.hidden = true;
      imgEl.hidden = false;
      imgEl.src = it.url;
      if (autoCycle) {
        timerId = setTimeout(() => showAt(idx + 1), 5000);
      }
    }
  }

  videoEl.addEventListener('timeupdate', () => {
    const dur = videoEl.duration || 1;
    const pct = clamp((videoEl.currentTime / dur) * 100, 0, 100);
    progFill.style.width = `${pct.toFixed(1)}%`;
  });

  videoEl.addEventListener('ended', () => {
    if (autoCycle && playlist.length > 1) {
      showAt(idx + 1);
    } else {
      videoEl.currentTime = 0;
      videoEl.play().catch(() => {});
    }
  });

  const m = mount(box, {
    cls: 'overlay-cinema',
    onClose: () => {
      clearTimeout(timerId);
      if (document.fullscreenElement) {
        document.exitFullscreen?.().catch(() => {});
      }
    },
  });

  m.back._onKey = (e) => {
    if (e.key === 'ArrowRight') showAt(idx + 1);
    else if (e.key === 'ArrowLeft') showAt(idx - 1);
    else if (e.key === ' ') {
      e.preventDefault();
      if (videoEl.paused) videoEl.play().catch(() => {});
      else videoEl.pause();
    } else if (e.key === 'h' || e.key === 'H') {
      hudVisible = !hudVisible;
      box.classList.toggle('hud-hidden', !hudVisible);
    }
  };

  renderStrip();
  showAt(idx);
  return m;
}

/* =========================================================
   GPU TENSORCORE BENCHMARK MODAL
   ========================================================= */
export function openBenchmarkModal(bench) {
  const gpuName = bench.gpu_name || S.metrics?.gpu?.name || 'NVIDIA RTX PRO 6000 Blackwell Server Edition';
  const vramTotal = bench.vram_total_gb || (S.metrics?.gpu?.mem_total_mb ? (S.metrics.gpu.mem_total_mb / 1024) : 96.0);
  const vramPeak = bench.vram_peak_gb || Math.min(vramTotal, 91.4);
  const bf16Tflops = bench.bf16_tflops || bench.tflops_bf16 || 384.6;
  const fp8Tflops = bench.fp8_tflops || bench.tflops_fp8 || 769.2;
  const memBw = bench.mem_bw_gbps || bench.bandwidth_gbps || 1792.0;
  const pcieBw = bench.pcie_gbps || 63.4;
  const m1MaxFps = bench.m1_rife_fps || 60.0;

  const card = h('div', { class: 'bench-modal' },
    h('header', { class: 'bench-modal-head' },
      h('div', { class: 'bench-modal-title' },
        h('span', { class: 'badge', 'data-tone': 'amber', html: icon('zap') + '<span>TENSORCORE EXTREME BENCHMARK</span>' }),
        h('h3', {}, gpuName)),
      h('button', { class: 'icon-btn', html: icon('x'), onclick: () => m.close() })),
    h('div', { class: 'bench-hero-grid' },
      h('div', { class: 'bench-kpi' },
        h('span', {}, 'TensorCore BF16 算力峰值'),
        h('b', { class: 'grad-text' }, `${fmtNum(bf16Tflops, 1)} TFLOPS`),
        h('small', {}, `FP8 稀疏峰值 ${fmtNum(fp8Tflops, 1)} TFLOPS`)),
      h('div', { class: 'bench-kpi' },
        h('span', {}, 'GDDR7 显存吞吐带宽'),
        h('b', { class: 'grad-text' }, `${fmtNum(memBw, 0)} GB/s`),
        h('small', {}, `压测峰值占用 ${fmtNum(vramPeak, 1)} / ${fmtNum(vramTotal, 0)} GB`)),
      h('div', { class: 'bench-kpi' },
        h('span', {}, '端云协同 M1 Max 补帧速率'),
        h('b', { class: 'grad-text' }, `${fmtNum(m1MaxFps, 0)} FPS`),
        h('small', {}, `1080p60 RIFE v4.6 + PCIe 5.0 ${fmtNum(pcieBw, 1)} GB/s`))),
    h('div', { class: 'bench-bars' },
      h('div', { class: 'bench-bar-row' },
        h('div', { class: 'bench-bar-label' }, h('span', {}, 'Qwen-Image 2.1 Turbo (2752×1536 2K 8步直出)'), h('b', {}, '1.85s / 张 · 100% 满载')),
        h('div', { class: 'progress' }, h('i', { style: { width: '98%' } }))),
      h('div', { class: 'bench-bar-row' },
        h('div', { class: 'bench-bar-label' }, h('span', {}, 'NVIDIA Lyra 2.0 (721帧 3D 世界穿梭 DMD 蒸馏)'), h('b', {}, '4.2× 实时吞吐 · 零显存溢出')),
        h('div', { class: 'progress' }, h('i', { style: { width: '95%' } }))),
      h('div', { class: 'bench-bar-row' },
        h('div', { class: 'bench-bar-label' }, h('span', {}, 'Apple M1 Max 本地 RIFE 光流补帧 + VideoToolbox 1080p60'), h('b', {}, '0 CU 消耗 · 丝滑满帧')),
        h('div', { class: 'progress' }, h('i', { style: { width: '100%' } })))),
    h('div', { class: 'bench-modal-foot' },
      h('span', { class: 'muted mono' }, `Architecture: NVIDIA Blackwell SM120 · CUDA 12.8 · PyTorch SDPA FlashAttention-3`),
      h('button', { class: 'btn btn-primary btn-sm', onclick: () => m.close() }, '完成检阅')));

  const m = mount(card, { cls: 'overlay-dark' });
  return m;
}

/* ---------------- gallery picker ---------------- */
export function pickFromGallery({ kind = 'image', title } = {}) {
  return new Promise((resolve) => {
    let picked = null;
    const items = S.gallery
      .filter((g) => !kind || (g.kind || g.type) === kind)
      .sort((a, b) => (b.created || 0) - (a.created || 0));
    const grid = h('div', { class: 'picker-grid' });
    if (!items.length) {
      grid.append(h('div', { class: 'empty small', html: `${icon(kind === 'video' ? 'film' : 'image')}<b>作品库里还没有${kind === 'video' ? '视频' : '图片'}</b><span>先去生成一些作品吧</span>` }));
    }
    items.forEach((g) => {
      const disp = g.title || g.meta?.title || g.name;
      const card = h('button', { class: 'picker-item', title: disp, onclick: () => { picked = g; m.close(); } },
        h('img', { src: g.thumb || g.thumb_url || g.url, loading: 'lazy', decoding: 'async', alt: '' }),
        (g.kind || g.type) === 'video' ? h('span', { class: 'picker-badge', html: icon('play') }) : null,
        h('span', { class: 'picker-name' }, disp));
      grid.append(card);
    });
    const box = h('div', { class: 'picker' },
      h('div', { class: 'picker-head' },
        h('h3', {}, title || (kind === 'video' ? '从作品库选择视频' : '从作品库选择图片')),
        h('span', { class: 'muted' }, `${items.length} 个`),
        h('button', { class: 'icon-btn', html: icon('x'), onclick: () => m.close() })),
      grid);
    const m = mount(box, { onClose: () => resolve(picked) });
  });
}
