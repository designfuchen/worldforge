// Fetch wrapper: every call surfaces errors as a toast (unless silent).
import { toast } from './dom.js';

export class ApiError extends Error {
  constructor(msg, status) { super(msg); this.status = status; }
}

function detailMsg(data, status) {
  if (data && typeof data === 'object') {
    const d = data.detail ?? data.error ?? data.message;
    if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('；');
    if (d) return typeof d === 'string' ? d : JSON.stringify(d);
  }
  if (typeof data === 'string' && data.length < 200 && data.trim()) return data.trim();
  if (status === 502 || status === 503 || status === 504) return '远端 GPU 服务不可达（隧道未连接或服务未启动）';
  if (status === 404) return '接口不存在 (404)';
  return `HTTP ${status}`;
}

/**
 * api(path, {method, body, raw, query, silent, errTitle, timeout})
 */
export async function api(path, opts = {}) {
  const { body, raw, query, silent = false, errTitle, timeout = raw ? 600000 : 30000 } = opts;
  let url = path;
  if (query) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v != null) q.set(k, v);
    const qs = q.toString();
    if (qs) url += (url.includes('?') ? '&' : '?') + qs;
  }
  const init = { method: opts.method || (body !== undefined || raw ? 'POST' : 'GET'), headers: {} };
  if (raw) {
    init.body = raw;
    init.headers['Content-Type'] = 'application/octet-stream';
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers['Content-Type'] = 'application/json';
  }
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  init.signal = ctl.signal;
  try {
    const res = await fetch(url, init);
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!res.ok) throw new ApiError(detailMsg(data, res.status), res.status);
    return data;
  } catch (e) {
    let err = e;
    if (e.name === 'AbortError') err = new ApiError('请求超时');
    else if (!(e instanceof ApiError)) err = new ApiError('无法连接本地服务（forge.py 是否在运行？）', 0);
    if (!silent) toast(err.message, 'error', { title: errTitle || '请求失败' });
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export const local = (p, o) => api('/api/local' + p, o);
export const remote = (p, o) => api('/api/remote' + p, o);
export const remoteFileUrl = (p) => '/api/remote/files?path=' + encodeURIComponent(p);

/* ---------- image sources (shared by 视频 / 3D 世界) ---------- */
export function srcFromGallery(g) {
  return { type: 'gallery', galleryId: g.id, url: g.url, preview: g.thumb || g.url, name: g.name, localPath: g.path, meta: g.meta };
}
export function srcFromRemote(path, name, meta) {
  const u = remoteFileUrl(path);
  return { type: 'remote', remotePath: path, url: u, preview: u, name: name || path.split('/').pop(), meta };
}
export function srcFromFile(file) {
  const u = URL.createObjectURL(file);
  return { type: 'file', file, url: u, preview: u, name: file.name };
}
/** Ensure the source exists on the remote VM; returns remote path */
export async function resolveRemote(src) {
  if (!src) throw new ApiError('请先选择图片');
  if (src.remotePath) return src.remotePath;
  if (src.type === 'gallery') {
    const r = await local('/to_remote', { body: { gallery_id: src.galleryId }, errTitle: '上传图片到 GPU 失败', timeout: 300000 });
    src.remotePath = r.remote_path;
    return src.remotePath;
  }
  if (src.type === 'file') {
    const safe = src.file.name.replace(/[^\w.\-]+/g, '_') || 'input.png';
    const r = await local('/upload', { query: { filename: safe }, raw: src.file, errTitle: '上传图片失败' });
    src.remotePath = r.remote_path;
    src.localPath = r.local_path;
    return src.remotePath;
  }
  throw new ApiError('无效的图片来源');
}
