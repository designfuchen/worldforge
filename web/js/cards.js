// Shared UI components: dropzone controller, async media & sprite-scrub gallery tiles, job results, range slider fill.
import { $, $$, h, esc, fmtAgo, fmtDur, toast, clamp } from './dom.js';
import { icon } from './icons.js';
import { S, galleryForOutput, modelById } from './store.js';
import { remote, local, remoteFileUrl, srcFromFile, srcFromGallery } from './api.js';
import { openLightbox, openABCompare, pickFromGallery } from './overlays.js';
import { TASK_LABEL } from './defaults.js';
import * as A from './actions.js';

/* =========================================================
   SHARED ASYNC INTERSECTION OBSERVER & SPRITE SHEET CACHE
   ========================================================= */
const warmedStrips = new Map(); // url -> Promise<boolean>

function preloadSpriteSheet(url) {
  if (!url) return Promise.resolve(false);
  if (warmedStrips.has(url)) return warmedStrips.get(url);
  const p = new Promise((resolve) => {
    const img = new Image();
    img.decoding = 'async';
    img.onload = () => {
      if (typeof img.decode === 'function') {
        img.decode().then(() => resolve(true)).catch(() => resolve(true));
      } else {
        resolve(true);
      }
    };
    img.onerror = () => resolve(false);
    img.src = url;
  });
  warmedStrips.set(url, p);
  return p;
}

const tileObserver = typeof IntersectionObserver !== 'undefined'
  ? new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const tile = entry.target;
        tileObserver.unobserve(tile);
        if (typeof tile._onEnterViewport === 'function') {
          tile._onEnterViewport();
        }
      });
    }, { rootMargin: '280px 0px', threshold: 0.01 })
  : null;

/** Update CSS --p percentage on <input type="range"> for gradient track */
export function syncRange(input) {
  if (!input) return;
  const min = parseFloat(input.min) || 0;
  const max = parseFloat(input.max) || 100;
  const val = parseFloat(input.value) || 0;
  const pct = max > min ? clamp(((val - min) / (max - min)) * 100, 0, 100) : 0;
  input.style.setProperty('--p', pct.toFixed(1) + '%');
}

export function bindRanges(root = document) {
  $$('input[type="range"]', root).forEach((el) => {
    syncRange(el);
    el.addEventListener('input', () => syncRange(el));
  });
}

/**
 * Bind an image dropzone element (.dropzone).
 * Returns { get(), set(src), clear() }
 */
export function bindDropzone(el, { onChange } = {}) {
  const preview = $('.dz-preview', el);
  const fileIn = $('input[type="file"]', el);
  const pickBtn = $('[data-pick]', el);
  let current = null;

  function set(src) {
    current = src || null;
    if (!current) {
      el.classList.remove('has');
      preview.innerHTML = '';
    } else {
      el.classList.add('has');
      preview.innerHTML = '';
      const img = h('img', {
        src: current.preview || current.url,
        loading: 'lazy',
        decoding: 'async',
        alt: current.name || '',
      });
      const bar = h('div', { class: 'dz-bar' },
        h('span', { title: current.name || '' }, current.name || '已选图片'),
        h('button', {
          class: 'btn btn-xs',
          type: 'button',
          html: icon('grid') + '<span>作品库</span>',
          onclick: async (e) => {
            e.stopPropagation();
            const g = await pickFromGallery({ kind: 'image' });
            if (g) set(srcFromGallery(g));
          },
        }),
        h('button', {
          class: 'btn btn-xs',
          type: 'button',
          html: icon('upload') + '<span>更换</span>',
          onclick: (e) => {
            e.stopPropagation();
            fileIn && fileIn.click();
          },
        }),
        h('button', {
          class: 'icon-btn sm',
          type: 'button',
          title: '移除图片',
          html: icon('x'),
          onclick: (e) => {
            e.stopPropagation();
            set(null);
          },
        }),
      );
      preview.append(img, bar);
    }
    onChange && onChange(current);
  }

  function handleFiles(files) {
    const f = files && files[0];
    if (!f) return;
    if (!f.type.startsWith('image/')) {
      toast('请选择图片文件（PNG / JPG / WebP）', 'warn');
      return;
    }
    set(srcFromFile(f));
  }

  el.addEventListener('click', (e) => {
    if (el.classList.contains('has')) return;
    if (e.target.closest('[data-pick]')) return;
    fileIn && fileIn.click();
  });

  el.addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && !el.classList.contains('has')) {
      e.preventDefault();
      fileIn && fileIn.click();
    }
  });

  if (pickBtn) {
    pickBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const g = await pickFromGallery({ kind: 'image' });
      if (g) set(srcFromGallery(g));
    });
  }

  if (fileIn) {
    fileIn.addEventListener('change', () => {
      handleFiles(fileIn.files);
      fileIn.value = '';
    });
  }

  ['dragenter', 'dragover'].forEach((ev) => {
    el.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      el.classList.add('drag');
    });
  });
  ['dragleave', 'drop'].forEach((ev) => {
    el.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      el.classList.remove('drag');
    });
  });
  el.addEventListener('drop', (e) => {
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
      handleFiles(e.dataTransfer.files);
    }
  });

  return {
    get: () => current,
    set,
    clear: () => set(null),
  };
}

/** Normalize a remote job output + optional matched gallery item into a lightbox/action item */
export function mediaFromJobOutput(job, out, idx) {
  const g = galleryForOutput(job, out, idx);
  if (g) {
    const base = A.mediaFromGallery(g);
    return {
      ...base,
      remotePath: out.path,
    };
  }
  const p = job.params || {};
  const meta = {
    prompt: p.prompt || p.scene || p.caption || '',
    model: job.model_id,
    model_id: job.model_id,
    task: job.task,
    width: p.width,
    height: p.height,
    seed: out.seed ?? p.seed,
    steps: p.steps,
    trajectory: p.mode === 'flythrough' ? 'flythrough (一路穿梭)' : p.trajectory,
    job_id: job.id,
  };
  const kind = out.kind || (job.task === 't2i' ? 'image' : 'video');
  return {
    kind,
    type: kind,
    url: remoteFileUrl(out.path),
    thumb: remoteFileUrl(out.path),
    name: out.name || out.path.split('/').pop(),
    title: p.scene || p.prompt || out.name || out.path.split('/').pop(),
    width: p.width,
    height: p.height,
    meta,
    gallery: null,
    remotePath: out.path,
    created: job.finished || job.created,
  };
}

/**
 * Helper to wire non-blocking async decode on an <img> with skeleton shimmer fadeout.
 */
function bindAsyncImage(img, skeletonEl, tileEl) {
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    img.classList.add('decoded');
    if (skeletonEl) skeletonEl.classList.add('out');
    if (tileEl) tileEl.classList.add('media-ready');
  };
  img.addEventListener('load', () => {
    if (typeof img.decode === 'function') {
      img.decode().then(finish).catch(finish);
    } else {
      finish();
    }
  }, { once: true });
  img.addEventListener('error', finish, { once: true });
}

/**
 * Render a single media tile (.tile) used in job results and gallery.
 * Features:
 * - Async image & thumbnail decoding (<img loading="lazy" decoding="async">) + .tile-skeleton shimmer
 * - Shared IntersectionObserver that mounts media & pre-warms 12x1 sprite sheets on viewport entry
 * - 60fps Cursor-X Hover Filmstrip Scrubbing on video tiles with 0ms sprite sheet lookup,
 *   progress bar, and live frame timestamp pill (e.g. "01.8s / 03.8s · 第 6/12 帧")
 * - Inline 60fps <video> play toggle button & A/B Compare button & Favorite star toggle
 */
export function renderMediaTile(item, allItems, idx, { ar = '16 / 9', showDelete = false, showCaption = false } = {}) {
  const isVid = (item.kind || item.type) === 'video';
  const g = item.gallery;
  const stripUrl = item.strip_url || g?.strip_url || g?.meta?.strip_url || null;
  const stripFrames = Math.max(2, Number(item.strip_frames || g?.strip_frames || 12));
  const dur = Number(item.duration || g?.duration || g?.info?.duration || item.meta?.duration || 3.8);
  const w = Number(item.width || g?.width || g?.info?.width || item.meta?.width || 0);
  const ht = Number(item.height || g?.height || g?.info?.height || item.meta?.height || 0);
  const fps = Number(item.fps || g?.fps || g?.info?.fps || item.meta?.fps || 0);
  const cat = item.category || (g ? A.resolveGalleryCategory(g) : null);

  const skeleton = h('div', { class: 'tile-skeleton' });
  const thumbSrc = item.thumb || item.thumb_url || item.url;
  const imgEl = h('img', {
    class: 'tile-img',
    loading: 'lazy',
    decoding: 'async',
    alt: item.title || item.name || '',
  });

  let stripEl = null;
  let videoEl = null;
  let scrubHud = null;
  let scrubFill = null;
  let scrubPill = null;
  let playToggleBtn = null;
  let inlinePlaying = false;
  let stripReady = false;

  if (isVid) {
    // 12x1 Sprite Sheet Layer for 0ms 60fps Cursor-X Hover Scrubbing
    stripEl = h('div', {
      class: 'tile-strip',
      style: {
        backgroundSize: `${stripFrames * 100}% 100%`,
        backgroundPosition: '0% 0%',
      },
    });

    // Lazy <video> element — only decodes when user clicks inline play or if no sprite/thumb exists
    videoEl = h('video', {
      class: 'tile-inline-video',
      muted: true,
      loop: true,
      playsinline: true,
      preload: 'none',
    });

    // Build 12 tick marks on the bottom scrub bar
    const ticks = [];
    for (let t = 0; t < stripFrames; t++) {
      ticks.push(h('u', {}));
    }
    scrubFill = h('i', { class: 'tile-scrub-fill' });
    scrubPill = h('span', { class: 'tile-scrub-pill mono' },
      `00.0s / ${dur.toFixed(1).padStart(4, '0')}s · 第 1/${stripFrames} 帧`);

    scrubHud = h('div', { class: 'tile-scrub-hud' },
      scrubPill,
      h('div', { class: 'tile-scrub-bar' }, scrubFill, h('div', { class: 'tile-scrub-ticks' }, ticks)));
  }

  // Top action buttons
  const topBtns = [];

  if (g) {
    const isFav = A.isGalleryFavorite(g);
    const favBtn = h('button', {
      class: 'tbtn sq fav-btn' + (isFav ? ' on' : ''),
      type: 'button',
      title: isFav ? '取消收藏' : '加入收藏 (★)',
      html: icon(isFav ? 'starFill' : 'star'),
      onclick: async (e) => {
        e.stopPropagation();
        const nextFav = await A.toggleFavorite(g);
        item.favorite = nextFav;
        favBtn.classList.toggle('on', nextFav);
        favBtn.innerHTML = icon(nextFav ? 'starFill' : 'star');
        favBtn.title = nextFav ? '取消收藏' : '加入收藏 (★)';
        tile.dataset.fav = nextFav ? '1' : '0';
      },
    });
    topBtns.push(favBtn);
  }

  if (isVid) {
    playToggleBtn = h('button', {
      class: 'tbtn sq play-toggle-btn',
      type: 'button',
      title: '在卡片内直接播放 60fps 视频',
      html: icon('play'),
      onclick: (e) => {
        e.stopPropagation();
        toggleInlineVideo();
      },
    });
    topBtns.push(playToggleBtn);
  }

  if (g) {
    topBtns.push(
      h('button', {
        class: 'tbtn sq',
        type: 'button',
        title: '在 Finder 中显示',
        html: icon('folder'),
        onclick: (e) => { e.stopPropagation(); A.reveal(g.path); },
      }),
    );
  } else if (item.remotePath) {
    topBtns.push(
      h('button', {
        class: 'tbtn sq',
        type: 'button',
        title: '保存到本地作品库',
        html: icon('download'),
        onclick: async (e) => {
          e.stopPropagation();
          try {
            await local('/fetch', {
              body: { remote_path: item.remotePath, kind: item.kind, meta: item.meta || {} },
              errTitle: '保存失败',
            });
            toast('已加入下载队列', 'info', { timeout: 1800 });
          } catch {}
        },
      }),
    );
  }

  if (showDelete && g) {
    topBtns.push(
      h('button', {
        class: 'tbtn sq',
        type: 'button',
        title: '删除',
        html: icon('trash'),
        onclick: (e) => { e.stopPropagation(); A.deleteGallery(g); },
      }),
    );
  }

  // Bottom action buttons
  const botBtns = [];
  if (!isVid) {
    botBtns.push(
      h('button', {
        class: 'tbtn acc',
        type: 'button',
        html: icon('cube') + '<span>做成 3D 世界</span>',
        onclick: (e) => { e.stopPropagation(); A.sendToWorld(item); },
      }),
      h('button', {
        class: 'tbtn',
        type: 'button',
        html: icon('video') + '<span>图生视频</span>',
        onclick: (e) => { e.stopPropagation(); A.sendToVideo(item); },
      }),
    );
  } else {
    botBtns.push(
      h('button', {
        class: 'tbtn acc ab-trigger',
        type: 'button',
        title: '打开 M1 Max 1080p60 RIFE vs Colab 832×480 原始直出分屏对比',
        html: icon('compare') + '<span>A/B 对比</span>',
        onclick: (e) => { e.stopPropagation(); openABCompare(item); },
      }),
      h('button', {
        class: 'tbtn',
        type: 'button',
        html: icon('sliders') + '<span>后期</span>',
        onclick: (e) => { e.stopPropagation(); A.sendToPost(item); },
      }),
    );
  }

  // Top-left category & spec badges
  const badgesWrap = h('div', { class: 'tile-badges' });
  if (cat === 'enhanced' || (isVid && fps >= 48)) {
    badgesWrap.append(
      h('span', { class: 'tile-badge badge-enh', html: icon('zap') + '<span>1080p60 RIFE</span>' }),
    );
  } else if (cat === 'world3d' || (isVid && item.meta?.task === 'lyra')) {
    badgesWrap.append(
      h('span', { class: 'tile-badge badge-world', html: icon('cube') + '<span>3D 穿梭</span>' }),
    );
  } else if (!isVid && w >= 2000) {
    badgesWrap.append(
      h('span', { class: 'tile-badge badge-2k', html: icon('sparkles') + '<span>2K 原画</span>' }),
    );
  } else if (g) {
    badgesWrap.append(
      h('span', { class: 'tile-badge saved', html: icon('check') + '<span>已入库</span>' }),
    );
  } else {
    badgesWrap.append(
      h('span', { class: 'tile-badge', html: icon(isVid ? 'film' : 'image') + `<span>${isVid ? '云端视频' : '云端图片'}</span>` }),
    );
  }

  if (w && ht) {
    const specTxt = isVid && fps ? `${w}×${ht} · ${Math.round(fps)}fps` : `${w}×${ht}`;
    badgesWrap.append(h('span', { class: 'tile-badge badge-spec mono' }, specTxt));
  }

  // Optional caption bar for gallery cards
  const displayTitle = item.title || g?.title || item.meta?.title || item.name || '';
  const captionBar = showCaption && displayTitle
    ? h('div', { class: 'tile-caption' },
        h('span', { class: 'tile-caption-title', title: displayTitle }, displayTitle),
        isVid && dur ? h('span', { class: 'tile-caption-dur mono' }, `${dur.toFixed(1)}s`) : null)
    : null;

  const tile = h('div', {
    class: 'tile' + (isVid ? ' is-video' : ' is-image'),
    style: { '--ar': ar },
    dataset: {
      fav: g && A.isGalleryFavorite(g) ? '1' : '0',
      cat: cat || '',
    },
    onclick: () => openLightbox(allItems, idx),
  },
    skeleton,
    imgEl,
    stripEl,
    videoEl,
    badgesWrap,
    captionBar,
    scrubHud,
    h('div', { class: 'tile-ov' },
      h('div', { class: 'tile-top' }, topBtns),
      h('div', { class: 'tile-bottom' }, botBtns)));

  function toggleInlineVideo() {
    if (!videoEl) return;
    inlinePlaying = !inlinePlaying;
    tile.classList.toggle('is-playing', inlinePlaying);
    if (inlinePlaying) {
      tile.classList.remove('is-scrubbing');
      if (!videoEl.src) videoEl.src = item.url;
      videoEl.play().catch(() => {});
      if (playToggleBtn) {
        playToggleBtn.innerHTML = icon('pause');
        playToggleBtn.classList.add('on');
      }
    } else {
      videoEl.pause();
      if (playToggleBtn) {
        playToggleBtn.innerHTML = icon('play');
        playToggleBtn.classList.remove('on');
      }
    }
  }

  // 60fps Cursor-X Hover Filmstrip Scrubbing
  if (isVid) {
    tile.addEventListener('mouseenter', () => {
      if (stripUrl && !stripReady) {
        preloadSpriteSheet(stripUrl).then((ok) => {
          if (ok && stripEl) {
            stripReady = true;
            stripEl.style.backgroundImage = `url("${stripUrl}")`;
            tile.dataset.stripReady = '1';
          }
        });
      }
    });

    tile.addEventListener('mousemove', (e) => {
      if (inlinePlaying) return;
      const rect = tile.getBoundingClientRect();
      if (!rect.width) return;
      const offsetX = e.clientX - rect.left;
      const ratio = clamp(offsetX / rect.width, 0, 1);
      const frameIdx = Math.min(stripFrames - 1, Math.floor(ratio * stripFrames));

      tile.classList.add('is-scrubbing');

      if (stripUrl && stripEl) {
        if (!stripEl.style.backgroundImage) {
          stripEl.style.backgroundImage = `url("${stripUrl}")`;
        }
        const posPct = (frameIdx / Math.max(1, stripFrames - 1)) * 100;
        stripEl.style.backgroundPosition = `${posPct.toFixed(4)}% 0`;
      } else if (videoEl) {
        // Fallback when sprite sheet does not exist yet
        if (!videoEl.src) {
          videoEl.src = item.url;
          videoEl.preload = 'metadata';
        }
        if (videoEl.readyState >= 1 && videoEl.duration) {
          videoEl.currentTime = ratio * videoEl.duration;
        }
      }

      if (scrubFill) {
        scrubFill.style.width = `${(ratio * 100).toFixed(1)}%`;
      }
      if (scrubPill) {
        const curSec = (ratio * dur).toFixed(1).padStart(4, '0');
        const totSec = dur.toFixed(1).padStart(4, '0');
        scrubPill.textContent = `${curSec}s / ${totSec}s · 第 ${frameIdx + 1}/${stripFrames} 帧`;
      }
    });

    tile.addEventListener('mouseleave', () => {
      tile.classList.remove('is-scrubbing');
      if (inlinePlaying && videoEl) {
        inlinePlaying = false;
        tile.classList.remove('is-playing');
        videoEl.pause();
        if (playToggleBtn) {
          playToggleBtn.innerHTML = icon('play');
          playToggleBtn.classList.remove('on');
        }
      }
    });
  }

  // Viewport entry lifecycle: mount thumbnail src & pre-warm sprite sheet off the main thread
  bindAsyncImage(imgEl, skeleton, tile);
  tile._onEnterViewport = () => {
    imgEl.src = thumbSrc;
    if (isVid && stripUrl) {
      preloadSpriteSheet(stripUrl).then((ok) => {
        if (ok && stripEl) {
          stripReady = true;
          stripEl.style.backgroundImage = `url("${stripUrl}")`;
          tile.dataset.stripReady = '1';
        }
      });
    }
  };

  if (tileObserver) {
    tileObserver.observe(tile);
  } else {
    tile._onEnterViewport();
  }

  return tile;
}

/**
 * Render job results into a container for given task types (e.g. ['t2i'], ['t2v','i2v'], ['lyra']).
 */
export function renderTaskResults(container, tasks, { emptyIcon = 'sparkles', emptyTitle = '还没有生成记录', emptySub = '设置好参数后点击生成即可开始创作' } = {}) {
  if (!container) return;
  const jobs = S.jobs.filter((j) => tasks.includes(j.task));
  const jobIds = new Set(jobs.map((j) => j.id));

  // Also include historical gallery items created by these tasks that aren't in the current remote job list
  const orphanGallery = S.gallery.filter((g) => {
    const t = g.meta && g.meta.task;
    const jid = g.meta && g.meta.job_id;
    if (jid && jobIds.has(jid)) return false;
    if (t && tasks.includes(t)) return true;
    if (!t && tasks.includes('t2i') && (g.kind || g.type) === 'image' && !(g.meta && g.meta.post)) return true;
    return false;
  }).slice(0, 12);

  if (!jobs.length && !orphanGallery.length) {
    container.innerHTML = '';
    container.append(
      h('div', { class: 'empty', html: `${icon(emptyIcon)}<b>${esc(emptyTitle)}</b><span>${esc(emptySub)}</span>` }),
    );
    return;
  }

  const isVideoPanel = tasks.includes('t2v') || tasks.includes('lyra');
  const blocks = [];

  jobs.forEach((job) => {
    const p = job.params || {};
    const prompt = p.prompt || p.scene || p.caption || TASK_LABEL[job.task] || job.id;
    const m = modelById(job.model_id);
    const mName = (m && m.name) || job.model_id || '';
    const ar = p.width && p.height ? `${p.width} / ${p.height}` : '16 / 9';
    const count = Math.max(1, Number(p.count) || 1);

    let statusBadge;
    if (job.status === 'running') {
      statusBadge = h('span', { class: 'badge spin', 'data-tone': 'amber', html: icon('refresh') + `<span>${esc(job.stage || '生成中')}</span>` });
    } else if (job.status === 'queued') {
      statusBadge = h('span', { class: 'badge', 'data-tone': 'muted' }, '排队中');
    } else if (job.status === 'done') {
      statusBadge = h('span', { class: 'badge', 'data-tone': 'green' }, '完成');
    } else if (job.status === 'cancelled') {
      statusBadge = h('span', { class: 'badge', 'data-tone': 'muted' }, '已取消');
    } else {
      statusBadge = h('span', { class: 'badge', 'data-tone': 'red' }, '失败');
    }

    const durTxt = job.finished && job.started
      ? `耗时 ${fmtDur(job.finished - job.started)}`
      : fmtAgo(job.created);

    const head = h('div', { class: 'job-head' },
      statusBadge,
      mName ? h('span', { class: 'badge', 'data-tone': 'violet' }, mName) : null,
      h('span', { class: 'jp', title: prompt }, prompt),
      h('span', { class: 'jt' }, durTxt),
      (job.status === 'running' || job.status === 'queued')
        ? h('button', {
            class: 'btn btn-xs btn-danger-ghost',
            html: icon('stop') + '<span>取消</span>',
            onclick: async () => {
              try {
                await remote(`/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' });
                toast('已请求取消任务', 'info');
              } catch {}
            },
          })
        : null,
    );

    const tilesWrap = h('div', { class: 'tiles' + (isVideoPanel ? ' video' : '') });
    if (job.status === 'running' || job.status === 'queued') {
      const pct = Math.round((job.progress || 0) * 100);
      const nTiles = job.task === 't2i' ? count : 1;
      for (let i = 0; i < nTiles; i++) {
        tilesWrap.append(
          h('div', { class: 'tile pending shimmer', style: { '--ar': ar } },
            h('div', { class: 'pend' },
              h('b', {}, job.status === 'queued' ? '排队中' : `${pct}%`),
              h('div', { class: 'progress' + (job.progress ? '' : ' indet') },
                h('i', { style: { width: `${pct}%` } })),
              h('span', {}, job.stage || (job.eta_s ? `预计剩余 ${fmtDur(job.eta_s)}` : '正在 GPU 上推理…')))),
        );
      }
    } else if (job.status === 'error' || job.status === 'cancelled') {
      tilesWrap.append(
        h('div', { class: 'tile failed', style: { '--ar': ar } },
          h('div', {},
            h('div', { html: icon('alert') }),
            h('b', {}, job.status === 'cancelled' ? '任务已取消' : '生成失败'),
            job.error ? h('div', { class: 'muted', style: { marginTop: '4px', fontSize: '11px' } }, job.error) : null)),
      );
    } else {
      const outs = job.outputs || [];
      const items = outs.map((o, idx) => mediaFromJobOutput(job, o, idx));
      items.forEach((it, idx) => {
        tilesWrap.append(renderMediaTile(it, items, idx, { ar }));
      });
    }

    blocks.push(h('div', { class: 'job-block', dataset: { jid: job.id } }, head, tilesWrap));
  });

  if (orphanGallery.length) {
    const items = orphanGallery.map((g) => A.mediaFromGallery(g));
    const tilesWrap = h('div', { class: 'tiles' + (isVideoPanel ? ' video' : '') });
    items.forEach((it, idx) => {
      tilesWrap.append(renderMediaTile(it, items, idx, { ar: '16 / 9', showCaption: true }));
    });
    blocks.push(
      h('div', { class: 'job-block' },
        h('div', { class: 'job-head' },
          h('span', { class: 'badge', 'data-tone': 'cyan' }, '历史作品库'),
          h('span', { class: 'jp' }, '保存在本地作品库中的生成结果')),
        tilesWrap),
    );
  }

  container.innerHTML = '';
  container.append(...blocks);
}
