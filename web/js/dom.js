// DOM helpers, toasts, formatters.
import { icon } from './icons.js';

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Hyperscript: h('div', {class:'x', onclick: fn, html:'<b>..</b>'}, child1, 'text') */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'text') el.textContent = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export function debounce(fn, ms = 300) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/* ---------------- formatters ---------------- */
export function fmtDur(sec) {
  if (sec == null || !isFinite(sec)) return '—';
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return `${sec} 秒`;
  const m = Math.floor(sec / 60), s = sec % 60;
  if (m < 60) return s ? `${m} 分 ${s} 秒` : `${m} 分钟`;
  const hh = Math.floor(m / 60), mm = m % 60;
  return mm ? `${hh} 小时 ${mm} 分` : `${hh} 小时`;
}
export function fmtClock(sec) {
  if (sec == null || !isFinite(sec)) return '--:--';
  sec = Math.max(0, Math.round(sec));
  const hh = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const p = (n) => String(n).padStart(2, '0');
  return hh ? `${hh}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
}
export function fmtAgo(ts) {
  if (!ts) return '';
  const d = Date.now() / 1000 - ts;
  if (d < 10) return '刚刚';
  if (d < 60) return `${Math.floor(d)} 秒前`;
  if (d < 3600) return `${Math.floor(d / 60)} 分钟前`;
  if (d < 86400) return `${Math.floor(d / 3600)} 小时前`;
  const dt = new Date(ts * 1000);
  return `${dt.getMonth() + 1}月${dt.getDate()}日 ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
}
export function fmtNum(n, d = 1) {
  if (n == null || !isFinite(n)) return '—';
  return Number(n).toLocaleString('zh-CN', { maximumFractionDigits: d, minimumFractionDigits: 0 });
}
export function fmtGB(gb) { return gb == null ? '—' : `${fmtNum(gb, gb < 10 ? 1 : 0)} GB`; }

/* ---------------- toasts ---------------- */
let toastWrap;
const TOAST_ICON = { info: 'info', success: 'check', error: 'alert', warn: 'alert' };
export function toast(message, type = 'info', opts = {}) {
  if (!toastWrap) toastWrap = $('#toasts');
  // de-dupe identical visible messages
  const key = type + '|' + (opts.title || '') + '|' + message;
  const dup = [...toastWrap.children].find((t) => t.dataset.key === key);
  if (dup) {
    const c = dup.querySelector('.toast-count');
    const n = (+dup.dataset.n || 1) + 1;
    dup.dataset.n = n;
    c.textContent = '×' + n;
    c.hidden = false;
    return dup;
  }
  const el = h('div', { class: `toast toast-${type}`, dataset: { key, n: 1 } },
    h('span', { class: 'toast-ic', html: icon(TOAST_ICON[type] || 'info') }),
    h('div', { class: 'toast-body' },
      opts.title ? h('div', { class: 'toast-title' }, opts.title) : null,
      h('div', { class: 'toast-msg' }, message)),
    h('span', { class: 'toast-count', hidden: true }),
    opts.action ? h('button', { class: 'toast-action', onclick: () => { opts.action.fn(); close(); } }, opts.action.label) : null,
    h('button', { class: 'toast-x', 'aria-label': '关闭', html: icon('x'), onclick: () => close() }),
  );
  function close() {
    el.classList.add('out');
    setTimeout(() => el.remove(), 260);
  }
  toastWrap.append(el);
  while (toastWrap.children.length > 5) toastWrap.firstElementChild.remove();
  setTimeout(close, opts.timeout ?? (type === 'error' ? 7000 : 4200));
  return el;
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('已复制到剪贴板', 'success', { timeout: 1600 });
  } catch {
    toast('复制失败', 'error');
  }
}

/** Animate number text */
export function setText(el, txt) {
  if (el && el.textContent !== String(txt)) el.textContent = txt;
}

/** Button busy state helper: await withBusy(btn, async () => {...}) */
export async function withBusy(btn, fn) {
  if (!btn || btn.classList.contains('busy')) return;
  btn.classList.add('busy');
  btn.disabled = true;
  try { return await fn(); } finally {
    btn.classList.remove('busy');
    btn.disabled = false;
  }
}

/** Snap value to 1+80k within [81, 961] */
export function snapFrames(v) {
  const k = clamp(Math.round((v - 1) / 80), 1, 12);
  return 1 + 80 * k;
}
