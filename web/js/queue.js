// Right Sidebar controller:
// 1. Compact Active Task Indicator (#activeTaskBanner)
// 2. Always-Visible Unified Media Library "🗂️ 统一素材库 (全部生成的图片与视频)" (#quickMediaLibrary)
// 3. Collapsible Terminal Log & Queue Drawer (#logBox)
import { $, $$, h, esc, fmtAgo, fmtDur, copyText, setText, toast, withBusy } from './dom.js';
import { icon } from './icons.js';
import { S, on, emit } from './store.js';
import { local, remote } from './api.js';
import { TASK_LABEL } from './defaults.js';
import { openLightbox, openABCompare } from './overlays.js';
import { mediaFromJobOutput } from './cards.js';
import * as A from './actions.js';

export function initQueue() {
  // Active task banner elements
  const atsBanner = $('#activeTaskBanner');
  const atsDot = $('#atsDot');
  const atsText = $('#atsText');
  const atsProgWrap = $('#atsProgWrap');
  const atsProgBar = $('#atsProgBar i');
  const countEl = $('#queueCount');
  const logSummaryHint = $('#logSummaryHint');

  // Unified Media Library (#quickMediaLibrary) elements
  const qmlCountEl = $('#qmlCount');
  const qmlFilterEl = $('#qmlFilter');
  const qmlGridEl = $('#qmlGrid');
  const qmlOpenFullBtn = $('#qmlOpenFull');
  const qmlRefreshBtn = $('#qmlRefresh');

  // Collapsible Log & Queue Drawer elements
  const listEl = $('#queueList');
  const followBtn = $('#logFollow');
  const copyBtn = $('#logCopy');
  const clearBtn = $('#logClear');
  const targetEl = $('#logTarget');
  const consoleEl = $('#console');

  let qmlFilter = 'all'; // 'all' | 'image' | 'video' | 'fav'
  let filter = 'all';    // 'all' | 'active'
  let follow = true;
  let pinned = null;     // { source: 'remote' | 'local', id: string, title: string }
  let currentLogKey = null;
  let logOffset = 0;
  let logDone = false;
  let logBusy = false;

  /* =========================================================
     1. UNIFIED MEDIA LIBRARY ("🗂️ 统一素材库")
     ========================================================= */
  $$('#qmlFilter button').forEach((b) => {
    b.classList.toggle('on', b.dataset.v === qmlFilter);
    b.addEventListener('click', () => {
      qmlFilter = b.dataset.v || 'all';
      $$('#qmlFilter button').forEach((x) => x.classList.toggle('on', x.dataset.v === qmlFilter));
      renderQuickMediaLibrary();
    });
  });

  qmlOpenFullBtn?.addEventListener('click', () => {
    emit('tab', 'gallery');
  });

  qmlRefreshBtn?.addEventListener('click', (e) => {
    withBusy(e.currentTarget, async () => {
      try {
        const res = await local('/gallery', { silent: true });
        if (res && Array.isArray(res.items)) {
          S.gallery = res.items;
          emit('gallery', S.gallery);
        }
        toast('素材库已刷新', 'info', { timeout: 1400 });
      } catch {}
    });
  });

  function collectUnifiedMediaItems() {
    const galleryItems = (S.gallery || []).map((g) => A.mediaFromGallery(g)).filter(Boolean);
    const seenGalleryIds = new Set(galleryItems.map((x) => x.id));

    // Also include any finished remote job outputs that haven't synced into S.gallery yet
    const jobExtras = [];
    (S.jobs || []).forEach((j) => {
      if (j.status !== 'done' || !Array.isArray(j.outputs)) return;
      j.outputs.forEach((out, idx) => {
        const item = mediaFromJobOutput(j, out, idx);
        if (item.gallery && seenGalleryIds.has(item.gallery.id)) return;
        jobExtras.push(item);
      });
    });

    const combined = [...jobExtras, ...galleryItems];
    // Sort Newest First (created descending)
    combined.sort((a, b) => {
      const ca = Number(a.created || a.gallery?.created || a.gallery?.mtime || 0);
      const cb = Number(b.created || b.gallery?.created || b.gallery?.mtime || 0);
      return cb - ca;
    });
    return combined;
  }

  function renderQuickMediaLibrary() {
    if (!qmlGridEl) return;
    const allMedia = collectUnifiedMediaItems();
    if (qmlCountEl) {
      qmlCountEl.textContent = String(allMedia.length);
    }

    const filtered = allMedia.filter((item) => {
      const kind = item.kind || item.type || 'image';
      if (qmlFilter === 'image') return kind === 'image';
      if (qmlFilter === 'video') return kind === 'video';
      if (qmlFilter === 'fav') return item.gallery ? A.isGalleryFavorite(item.gallery) : !!item.favorite;
      return true;
    });

    qmlGridEl.innerHTML = '';

    if (!filtered.length) {
      const emptyMsg = qmlFilter === 'fav'
        ? '还没有收藏的素材，点击缩略图右上角 ★ 即可收藏'
        : (qmlFilter === 'image'
            ? '暂无图片素材，在中间「生图」输入一句话即可生成'
            : (qmlFilter === 'video'
                ? '暂无视频素材，在中间「视频」输入一句话即可生成'
                : '暂无素材 · 生成的图片与视频会自动汇总到这里'));
      qmlGridEl.append(
        h('div', { class: 'qml-empty' },
          h('div', { class: 'qml-empty-ic', html: icon('grid') }),
          h('b', {}, '统一素材库为空'),
          h('span', {}, emptyMsg),
        ),
      );
      return;
    }

    const nowSec = Date.now() / 1000;

    filtered.slice(0, 60).forEach((item, idx) => {
      const isVid = (item.kind || item.type) === 'video';
      const g = item.gallery;
      const createdSec = Number(item.created || g?.created || g?.mtime || 0);
      // Show "✨ 最新" badge on items created in the last 3 minutes (180 seconds)
      const isRecent = createdSec > 0 && (nowSec - createdSec) <= 180;
      const isFav = g ? A.isGalleryFavorite(g) : !!item.favorite;
      const thumbUrl = item.thumb || item.thumb_url || item.url;
      const title = item.title || g?.title || item.meta?.prompt || item.meta?.scene || item.name || '未命名素材';
      const dur = Number(item.duration || g?.duration || g?.info?.duration || 0);

      const badges = [];
      if (isRecent) {
        badges.push(h('span', { class: 'qml-badge new' }, '✨ 最新'));
      }
      badges.push(
        h('span', { class: 'qml-badge ' + (isVid ? 'vid' : 'img') },
          isVid ? `🎬 视频${dur ? ` · ${dur.toFixed(0)}s` : ''}` : '🖼️ 图片'),
      );

      const favBtn = g
        ? h('button', {
            type: 'button',
            class: 'qml-fav-btn' + (isFav ? ' on' : ''),
            title: isFav ? '取消收藏' : '收藏此素材',
            html: icon(isFav ? 'starFill' : 'star'),
            onclick: async (e) => {
              e.stopPropagation();
              await A.toggleFavorite(g);
              renderQuickMediaLibrary();
            },
          })
        : null;

      // 1-click quick action buttons at the bottom of the tile
      const quickBtns = [];
      if (!isVid) {
        quickBtns.push(
          h('button', {
            type: 'button',
            class: 'qml-act-btn',
            title: '以此图作为首帧生成视频',
            onclick: (e) => {
              e.stopPropagation();
              A.sendToVideo(item);
            },
          }, '🎬 转视频'),
          h('button', {
            type: 'button',
            class: 'qml-act-btn accent',
            title: '将此图一键生成可漫游 3D 世界',
            onclick: (e) => {
              e.stopPropagation();
              A.sendToWorld(item);
            },
          }, '🌐 转3D'),
        );
      } else {
        quickBtns.push(
          h('button', {
            type: 'button',
            class: 'qml-act-btn',
            title: '打开 A/B 分屏画质对比',
            onclick: (e) => {
              e.stopPropagation();
              openABCompare(item);
            },
          }, '╱ A/B对比'),
          h('button', {
            type: 'button',
            class: 'qml-act-btn accent',
            title: '送入后期做 RIFE 60帧补帧增强',
            onclick: (e) => {
              e.stopPropagation();
              A.sendToPost(item);
            },
          }, '⚡ 60帧增强'),
        );
      }

      const card = h(
        'div',
        {
          class: 'qml-item' + (isRecent ? ' is-new' : ''),
          title: `${title}\n点击放大预览`,
          onclick: () => openLightbox(filtered, idx),
        },
        h('div', { class: 'qml-thumb-wrap' },
          h('img', {
            class: 'qml-thumb',
            src: thumbUrl,
            alt: title,
            loading: 'lazy',
            decoding: 'async',
          }),
          h('div', { class: 'qml-top-bar' },
            h('div', { class: 'qml-badges' }, badges),
            favBtn,
          ),
          h('div', { class: 'qml-hover-actions' }, quickBtns),
        ),
        h('div', { class: 'qml-caption' },
          h('span', { class: 'qml-title' }, title),
        ),
      );

      qmlGridEl.append(card);
    });
  }

  /* =========================================================
     2. COMPACT ACTIVE TASK BANNER & COLLAPSIBLE LOG DRAWER
     ========================================================= */
  $$('#queueFilter button').forEach((b) => {
    b.classList.toggle('on', b.dataset.v === filter);
    b.addEventListener('click', () => {
      filter = b.dataset.v || 'all';
      $$('#queueFilter button').forEach((x) => x.classList.toggle('on', x.dataset.v === filter));
      renderQueue();
    });
  });

  followBtn?.addEventListener('click', () => {
    follow = !follow;
    followBtn.classList.toggle('on', follow);
    if (follow && consoleEl) {
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }
  });

  copyBtn?.addEventListener('click', () => {
    const txt = consoleEl?.textContent || '';
    if (!txt.trim()) {
      toast('当前日志为空', 'info', { timeout: 1400 });
      return;
    }
    copyText(txt);
  });

  clearBtn?.addEventListener('click', () => {
    if (consoleEl) consoleEl.textContent = '';
  });

  function unifiedItems() {
    const rem = (S.jobs || []).map((j) => {
      const p = j.params || {};
      const sub = p.prompt || p.scene || p.caption || p.component || j.model_id || '';
      return {
        source: 'remote',
        id: j.id,
        task: j.task,
        title: `${TASK_LABEL[j.task] || j.task}${j.model_id ? ` · ${j.model_id}` : ''}`,
        sub: j.stage || sub,
        status: j.status,
        progress: j.progress,
        created: j.created || 0,
        started: j.started,
        finished: j.finished,
        error: j.error,
        eta_s: j.eta_s,
      };
    });

    const loc = (S.tasks || []).map((t) => ({
      source: 'local',
      id: t.id,
      task: t.type,
      title: t.title || TASK_LABEL[t.type] || t.type,
      sub: t.log_tail || '',
      status: t.status,
      progress: t.progress,
      created: t.created || 0,
      error: t.error,
    }));

    return [...rem, ...loc].sort((a, b) => (b.created || 0) - (a.created || 0));
  }

  function pickAutoTarget(items) {
    if (pinned) {
      const found = items.find((x) => x.source === pinned.source && x.id === pinned.id);
      if (found) return found;
    }
    const running = items.find((x) => x.status === 'running' || x.status === 'queued');
    if (running) return running;
    return items[0] || null;
  }

  function renderQueue() {
    const all = unifiedItems();
    const activeItems = all.filter((x) => x.status === 'running' || x.status === 'queued');
    const activeCount = activeItems.length;

    if (countEl) {
      countEl.textContent = activeCount > 0 ? `${activeCount} 运行中` : `${all.length}`;
      countEl.classList.toggle('hot', activeCount > 0);
    }

    // Update compact active task banner
    const runningTop = activeItems[0];
    if (runningTop) {
      const pct = runningTop.progress ? Math.round(runningTop.progress * 100) : null;
      atsBanner?.setAttribute('data-state', 'busy');
      if (atsDot) atsDot.className = 'dot busy';
      setText(
        atsText,
        `正在执行：${runningTop.title}${pct != null ? ` (${pct}%)` : ''}${runningTop.sub ? ` · ${runningTop.sub}` : ''}`,
      );
      if (atsProgWrap && atsProgBar) {
        atsProgWrap.hidden = false;
        atsProgWrap.parentElement?.classList.toggle('indet', pct == null);
        atsProgBar.style.width = `${pct ?? 35}%`;
      }
      setText(logSummaryHint, `${activeCount} 个任务运行中`);
    } else {
      atsBanner?.setAttribute('data-state', 'idle');
      if (atsDot) atsDot.className = 'dot ok';
      setText(atsText, '空闲待命 · 新生成的图片与视频将自动流入下方素材库');
      if (atsProgWrap) atsProgWrap.hidden = true;
      setText(logSummaryHint, all.length ? `共 ${all.length} 条记录` : '点击展开调试日志');
    }

    const shown = filter === 'active' ? activeItems : all;
    const activeTarget = pickAutoTarget(all);

    if (listEl) {
      listEl.innerHTML = '';
      if (!shown.length) {
        listEl.append(
          h('div', { class: 'q-empty' }, filter === 'active' ? '当前没有正在运行的任务' : '暂无任务记录'),
        );
      } else {
        shown.slice(0, 30).forEach((item) => {
          const isSel = activeTarget && activeTarget.source === item.source && activeTarget.id === item.id;
          const isAct = item.status === 'running' || item.status === 'queued';

          let badge;
          if (item.status === 'running') {
            const pct = item.progress ? ` ${Math.round(item.progress * 100)}%` : '';
            badge = h('span', { class: 'badge spin', 'data-tone': 'amber', html: icon('refresh') + `<span>运行中${pct}</span>` });
          } else if (item.status === 'queued') {
            badge = h('span', { class: 'badge', 'data-tone': 'muted' }, '排队中');
          } else if (item.status === 'done') {
            badge = h('span', { class: 'badge', 'data-tone': 'green' }, '完成');
          } else if (item.status === 'cancelled') {
            badge = h('span', { class: 'badge', 'data-tone': 'muted' }, '已取消');
          } else {
            badge = h('span', { class: 'badge', 'data-tone': 'red' }, '失败');
          }

          const cancelBtn = item.source === 'remote' && isAct
            ? h('button', {
                class: 'icon-btn sm',
                title: '取消任务',
                html: icon('stop'),
                onclick: async (e) => {
                  e.stopPropagation();
                  try {
                    await remote(`/jobs/${encodeURIComponent(item.id)}/cancel`, { method: 'POST' });
                    toast('已取消任务', 'info', { timeout: 1500 });
                    emit('poll:fast');
                  } catch {}
                },
              })
            : null;

          const progBar = isAct
            ? h('div', { class: 'progress sm' + (item.progress ? '' : ' indet') },
                h('i', { style: { width: `${Math.round((item.progress || 0) * 100)}%` } }))
            : null;

          const timeInfo = item.finished && item.started
            ? fmtDur(item.finished - item.started)
            : (item.eta_s && isAct ? `剩余 ~${fmtDur(item.eta_s)}` : fmtAgo(item.created));

          listEl.append(
            h('div', {
              class: 'q-item' + (isSel ? ' sel' : ''),
              onclick: () => {
                pinned = { source: item.source, id: item.id, title: item.title };
                renderQueue();
                pollLog(true);
              },
            },
              h('div', { class: 'q-top' },
                badge,
                h('b', { title: item.title }, item.title),
                cancelBtn),
              progBar,
              h('div', { class: 'q-sub' },
                h('span', { title: item.error || item.sub || '' }, item.error || item.sub || (item.source === 'local' ? '本地任务' : '云端 GPU')),
                h('span', {}, timeInfo))),
          );
        });
      }
    }

    syncLogTarget(activeTarget);
  }

  function syncLogTarget(target) {
    if (!target) {
      setText(targetEl, '未选择任务 · 自动跟随最新运行的任务');
      return;
    }
    const key = `${target.source}:${target.id}`;
    if (targetEl) {
      targetEl.innerHTML = '';
      targetEl.append(
        h('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } },
          `${pinned ? '已锁定' : '跟随'}：${target.title}`),
        pinned
          ? h('button', {
              class: 'btn btn-xs btn-ghost',
              type: 'button',
              onclick: () => {
                pinned = null;
                renderQueue();
                pollLog(true);
              },
            }, '自动跟随')
          : null,
      );
    }

    if (key !== currentLogKey) {
      currentLogKey = key;
      logOffset = 0;
      logDone = false;
      if (consoleEl) consoleEl.textContent = '';
      pollLog(true);
    }
  }

  async function pollLog(force = false) {
    if (logBusy && !force) return;
    const all = unifiedItems();
    const target = pickAutoTarget(all);
    if (!target) return;

    const key = `${target.source}:${target.id}`;
    if (key !== currentLogKey) {
      syncLogTarget(target);
      return;
    }
    if (logDone && target.status !== 'running' && target.status !== 'queued' && !force) {
      return;
    }

    logBusy = true;
    try {
      let res;
      if (target.source === 'local') {
        res = await local(`/tasks/${encodeURIComponent(target.id)}/log`, {
          query: { offset: logOffset },
          silent: true,
        });
      } else if (S.connected) {
        res = await remote(`/jobs/${encodeURIComponent(target.id)}/log`, {
          query: { offset: logOffset },
          silent: true,
        });
      }
      if (res && key === currentLogKey) {
        if (res.text && consoleEl) {
          consoleEl.textContent += res.text;
          if (follow) {
            consoleEl.scrollTop = consoleEl.scrollHeight;
          }
        }
        if (typeof res.offset === 'number') {
          logOffset = res.offset;
        }
        logDone = !!res.done;
      }
    } catch {
      // Ignore transient log polling errors
    } finally {
      logBusy = false;
    }
  }

  on('gallery', renderQuickMediaLibrary);
  on('gallery:fav', renderQuickMediaLibrary);
  on('jobs', () => {
    renderQueue();
    renderQuickMediaLibrary();
    pollLog();
  });
  on('tasks', () => {
    renderQueue();
    pollLog();
  });

  setInterval(() => pollLog(), 1800);
  renderQueue();
  renderQuickMediaLibrary();
}
