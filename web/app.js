// WorldForge 世界工坊 — Main Application Controller
import { hydrateIcons } from './js/icons.js';
import { S, on, emit } from './js/store.js';
import { local, remote } from './js/api.js';
import { toast, h } from './js/dom.js';
import { DEFAULT_PRESETS, BUILTIN_MODELS } from './js/defaults.js';
import { initSidebar } from './js/sidebar.js';
import { initPanels } from './js/panels.js';
import { initQueue } from './js/queue.js';

function injectSharedSvgDefs() {
  const svg = h('svg', {
    width: '0',
    height: '0',
    'aria-hidden': 'true',
    style: { position: 'absolute', width: 0, height: 0, overflow: 'hidden', pointerEvents: 'none' },
    html: `
      <defs>
        <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#a78bfa"/>
          <stop offset="100%" stop-color="#22d3ee"/>
        </linearGradient>
        <linearGradient id="trajGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#a78bfa"/>
          <stop offset="100%" stop-color="#22d3ee"/>
        </linearGradient>
      </defs>
    `,
  });
  document.body.prepend(svg);
}

/* ---------------- Data Fetching & Polling ---------------- */
let lastNoticeTs = Date.now() / 1000 - 5;
const prevJobStatus = new Map();
const prevTaskStatus = new Map();

export async function refreshLocalState() {
  try {
    const st = await local('/state', { silent: true, timeout: 8000 });
    const wasConnected = S.connected;
    S.localOk = true;
    S.local = st;
    S.connected = !!(st?.tunnel?.status === 'up' && st?.remote?.status === 'ok');
    emit('state', st);

    // Surface new backend notices as toasts
    if (Array.isArray(st?.notices)) {
      st.notices.forEach((n) => {
        if (n.time && n.time > lastNoticeTs) {
          lastNoticeTs = n.time;
          const levelMap = { warning: 'warn', error: 'error', info: 'info', success: 'success' };
          toast(n.text, levelMap[n.level] || 'info');
        }
      });
    }

    if (S.connected && !wasConnected) {
      refreshPresets();
      refreshModels(false);
      refreshMetrics();
      refreshJobs();
    } else if (!S.connected && wasConnected) {
      S.metrics = null;
      emit('metrics', null);
    }
  } catch {
    S.localOk = false;
    S.connected = false;
    emit('state', null);
  }
}

export async function refreshTasks() {
  if (S.localOk === false) return;
  try {
    const tasks = await local('/tasks', { silent: true, timeout: 8000 });
    if (!Array.isArray(tasks)) return;

    let needGallery = false;
    let needState = false;
    tasks.forEach((t) => {
      const prev = prevTaskStatus.get(t.id);
      if (prev && prev !== t.status) {
        if (t.status === 'done') {
          if (t.type === 'fetch' || t.type === 'post') needGallery = true;
          if (t.type === 'connect' || t.type === 'session_start' || t.type === 'session_stop') needState = true;
          if (t.type === 'post') toast('后期处理已完成并加入作品库', 'success');
        } else if (t.status === 'error') {
          toast(t.error || `${t.title} 失败`, 'error', { title: '任务失败' });
        }
      }
      prevTaskStatus.set(t.id, t.status);
    });

    S.tasks = tasks;
    emit('tasks', tasks);
    if (needGallery) refreshGallery();
    if (needState) refreshLocalState();
  } catch {}
}

export async function refreshGallery(manual = false) {
  try {
    const items = await local('/gallery', { silent: !manual, timeout: 10000 });
    if (Array.isArray(items)) {
      S.gallery = items;
      S.galleryLoaded = true;
      emit('gallery', items);
      if (manual) toast('作品库已刷新', 'info', { timeout: 1400 });
    }
  } catch {}
}

export async function refreshMetrics() {
  if (!S.connected) return;
  try {
    const m = await remote('/metrics', { silent: true, timeout: 8000 });
    if (!m) return;
    S.metrics = m;
    if (m.gpu) {
      S.hist.util.push(Number(m.gpu.util) || 0);
      if (S.hist.util.length > 60) S.hist.util.shift();
      const vramGb = m.gpu.mem_used_mb != null ? m.gpu.mem_used_mb / 1024 : 0;
      S.hist.vram.push(vramGb);
      if (S.hist.vram.length > 60) S.hist.vram.shift();
    }
    emit('metrics', m);
  } catch {}
}

export async function refreshModels(manual = false) {
  if (!S.connected) {
    if (manual) toast('当前处于本地预览模式，已加载内置旗舰模型列表', 'info');
    emit('models', S.models);
    return;
  }
  try {
    const models = await remote('/models', { silent: !manual, timeout: 10000 });
    if (Array.isArray(models)) {
      const merged = [...models];
      const seen = new Set(merged.map((m) => m.id));
      BUILTIN_MODELS.forEach((bm) => {
        if (!seen.has(bm.id)) {
          merged.push(bm);
          seen.add(bm.id);
        }
      });
      S.models.forEach((cm) => {
        if (cm && cm.id && !seen.has(cm.id)) {
          merged.push(cm);
          seen.add(cm.id);
        }
      });
      S.models = merged;
      S.modelsLoaded = true;
      emit('models', S.models);
      if (manual) toast('模型列表已刷新', 'info', { timeout: 1400 });
    }
  } catch {}
}

export async function refreshPresets() {
  if (!S.connected || S.presetsRemote) return;
  try {
    const p = await remote('/presets', { silent: true, timeout: 10000 });
    if (p && typeof p === 'object') {
      S.presets = {
        ...DEFAULT_PRESETS,
        ...p,
        lyra_trajectories: p.lyra_trajectories?.length ? p.lyra_trajectories : DEFAULT_PRESETS.lyra_trajectories,
        scene_presets: p.scene_presets?.length ? p.scene_presets : DEFAULT_PRESETS.scene_presets,
        t2i_styles: p.t2i_styles?.length ? p.t2i_styles : DEFAULT_PRESETS.t2i_styles,
        aspect_presets: p.aspect_presets?.length ? p.aspect_presets : DEFAULT_PRESETS.aspect_presets,
      };
      S.presetsRemote = true;
      emit('presets', S.presets);
    }
  } catch {}
}

export async function refreshJobs() {
  if (!S.connected) return;
  try {
    const jobs = await remote('/jobs', { query: { limit: 50 }, silent: true, timeout: 10000 });
    if (!Array.isArray(jobs)) return;

    let needModels = false;
    let needGallery = false;
    jobs.forEach((j) => {
      const prev = prevJobStatus.get(j.id);
      if (prev && prev !== j.status) {
        if (j.status === 'done') {
          if (['download', 'load', 'setup'].includes(j.task)) {
            needModels = true;
            toast(`任务完成：${j.stage || j.task}`, 'success');
          } else {
            needGallery = true;
            toast('云端生成完成', 'success');
          }
        } else if (j.status === 'error') {
          toast(j.error || '云端任务执行失败', 'error', { title: '生成失败' });
          if (['download', 'load', 'setup'].includes(j.task)) needModels = true;
        }
      }
      prevJobStatus.set(j.id, j.status);
    });

    S.jobs = jobs;
    S.jobsLoaded = true;
    emit('jobs', jobs);
    if (needModels) refreshModels(false);
    if (needGallery) setTimeout(() => refreshGallery(false), 1200);
  } catch {}
}

export async function refreshAll() {
  await Promise.allSettled([
    refreshLocalState(),
    refreshTasks(),
    refreshGallery(false),
  ]);
  if (S.connected) {
    await Promise.allSettled([
      refreshMetrics(),
      refreshJobs(),
      !S.modelsLoaded ? refreshModels(false) : Promise.resolve(),
      !S.presetsRemote ? refreshPresets() : Promise.resolve(),
    ]);
  }
}

/* ---------------- Keyboard Shortcuts ---------------- */
function bindShortcuts() {
  const tabOrder = ['image', 'video', 'world', 'post', 'gallery'];
  document.addEventListener('keydown', (e) => {
    // Ignore if modal overlay is open
    if (document.querySelector('#overlays .overlay')) return;

    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key >= '1' && e.key <= '5') {
      const idx = Number(e.key) - 1;
      if (tabOrder[idx]) {
        e.preventDefault();
        emit('tab', tabOrder[idx]);
      }
      return;
    }

    if (mod && e.key === 'Enter') {
      if (['image', 'video', 'world', 'post'].includes(S.tab)) {
        e.preventDefault();
        emit(`run:${S.tab}`);
      }
    }
  });
}

/* ---------------- Boot ---------------- */
function boot() {
  injectSharedSvgDefs();
  hydrateIcons(document);

  initSidebar({ refreshAll, refreshModels });
  initPanels({ refreshGallery, refreshAll });
  initQueue();
  bindShortcuts();

  // Initial fetch
  refreshAll();

  // Adaptive polling loop
  let fastUntil = 0;
  on('poll:fast', () => {
    fastUntil = Date.now() + 15000;
    setTimeout(() => {
      refreshLocalState();
      refreshTasks();
      if (S.connected) refreshJobs();
    }, 350);
  });

  setInterval(() => {
    refreshLocalState();
    refreshTasks();
    if (S.connected) {
      refreshMetrics();
      refreshJobs();
    }
  }, 2400);

  setInterval(() => {
    if (Date.now() < fastUntil) {
      refreshTasks();
      if (S.connected) refreshJobs();
    }
  }, 1200);

  setInterval(() => {
    if (S.localOk) refreshGallery(false);
  }, 8000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
