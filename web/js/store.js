// Global app state + tiny pub/sub.
import { DEFAULT_PRESETS, BUILTIN_MODELS } from './defaults.js';

function loadInitialModels() {
  try {
    const custom = JSON.parse(localStorage.getItem('wf.customModels') || '[]');
    if (Array.isArray(custom) && custom.length) {
      const ids = new Set(BUILTIN_MODELS.map((m) => m.id));
      return [...BUILTIN_MODELS, ...custom.filter((m) => m && m.id && !ids.has(m.id))];
    }
  } catch {}
  return [...BUILTIN_MODELS];
}

export function saveCustomModel(m) {
  if (!m || !m.id) return;
  try {
    const cur = JSON.parse(localStorage.getItem('wf.customModels') || '[]');
    const list = Array.isArray(cur) ? cur.filter((x) => x && x.id !== m.id) : [];
    list.push(m);
    localStorage.setItem('wf.customModels', JSON.stringify(list));
  } catch {}
}

export const S = {
  localOk: null,         // null=unknown, true/false
  local: null,           // /api/local/state payload
  connected: false,      // tunnel up && remote ok
  metrics: null,
  hist: { util: [], vram: [] },
  models: loadInitialModels(),
  modelsLoaded: false,
  jobs: [],
  jobsLoaded: false,
  tasks: [],
  gallery: [],
  galleryLoaded: false,
  presets: DEFAULT_PRESETS,
  presetsRemote: false,
  tab: 'image',
  heroDismissed: true,   // Never block or blur the 生图 / 视频 panels on startup!
};

const subs = new Map();
export function on(ev, fn) {
  if (!subs.has(ev)) subs.set(ev, []);
  subs.get(ev).push(fn);
}
export function emit(ev, data) {
  (subs.get(ev) || []).forEach((fn) => {
    try { fn(data); } catch (e) { console.error(`[${ev}]`, e); }
  });
}

export const settings = () => (S.local && S.local.settings) || {};
export const colab = () => (S.local && S.local.colab) || {};

export function modelById(id) {
  return S.models.find((m) => m.id === id) || BUILTIN_MODELS.find((m) => m.id === id);
}

export function modelsOfKind(...kinds) {
  const list = S.models && S.models.length ? S.models : BUILTIN_MODELS;
  return list.filter((m) => {
    if (kinds.includes(m.kind)) return true;
    if (kinds.includes('t2i') && (m.also_t2i || m.id === 'minimax-h3-hybrid')) return true;
    return false;
  });
}

/** Worker info for a model from metrics */
export function workerOf(modelId) {
  const ws = (S.metrics && S.metrics.workers) || [];
  return ws.find((w) => w.model_id === modelId);
}

/** Gallery item matching a remote job output */
export function galleryForOutput(job, out, idx) {
  const same = S.gallery.filter((g) => g.meta && g.meta.job_id === job.id);
  if (!same.length) return null;
  return (
    same.find((g) => g.meta.remote_path === out.path) ||
    same.find((g) => g.name === out.name) ||
    same.find((g) => g.name && out.name && g.name.endsWith(out.name)) ||
    (same.length === job.outputs.length ? sortByCreated(same)[idx] : null)
  );
}
function sortByCreated(a) { return [...a].sort((x, y) => (x.created || 0) - (y.created || 0)); }

/** Persisted UI prefs */
export function pref(key, val) {
  const k = 'wf.' + key;
  if (val === undefined) {
    try { return JSON.parse(localStorage.getItem(k)); } catch { return null; }
  }
  localStorage.setItem(k, JSON.stringify(val));
  return val;
}
