// Cross-feature actions: reveal, delete, favorite pinning, A/B pair resolution, send-to-tab, download.
import { local, srcFromGallery, srcFromRemote } from './api.js';
import { S, emit } from './store.js';
import { toast, h } from './dom.js';
import { confirmDialog } from './overlays.js';

const FAV_STORAGE_KEY = 'wf.favIds';

function loadLocalFavSet() {
  try {
    const raw = JSON.parse(localStorage.getItem(FAV_STORAGE_KEY) || '[]');
    return new Set(Array.isArray(raw) ? raw : []);
  } catch {
    return new Set();
  }
}

function saveLocalFavSet(set) {
  try {
    localStorage.setItem(FAV_STORAGE_KEY, JSON.stringify([...set]));
  } catch {}
}

const localFavs = loadLocalFavSet();

export function isGalleryFavorite(g) {
  if (!g) return false;
  if (typeof g.favorite === 'boolean') return g.favorite;
  if (g.meta && typeof g.meta.favorite === 'boolean') return g.meta.favorite;
  return localFavs.has(g.id);
}

/**
 * Toggle favorite status on a gallery item with optimistic UI update + PATCH /api/local/gallery/<id>.
 */
export async function toggleFavorite(g) {
  if (!g || !g.id) return false;
  const next = !isGalleryFavorite(g);
  g.favorite = next;
  if (g.meta) g.meta.favorite = next;
  if (next) localFavs.add(g.id);
  else localFavs.delete(g.id);
  saveLocalFavSet(localFavs);

  // Sync in S.gallery array as well
  const inStore = S.gallery.find((x) => x.id === g.id);
  if (inStore) {
    inStore.favorite = next;
    if (inStore.meta) inStore.meta.favorite = next;
  }

  emit('gallery:fav', { id: g.id, favorite: next });
  toast(next ? `★ 已收藏「${g.title || g.meta?.title || g.name}」` : '已取消收藏', 'info', { timeout: 1500 });

  try {
    const updated = await local('/gallery/' + encodeURIComponent(g.id), {
      method: 'PATCH',
      body: { favorite: next },
      silent: true,
    });
    if (updated && typeof updated === 'object' && updated.id) {
      Object.assign(g, updated);
      if (inStore) Object.assign(inStore, updated);
    }
  } catch {
    // Optimistic state + localStorage fallback remains intact
  }
  return next;
}

/** Infer or return the canonical category of a gallery item */
export function resolveGalleryCategory(g) {
  if (!g) return 'image2k';
  if (g.category && ['world3d', 'enhanced', 'image2k', 'raw_video'].includes(g.category)) {
    return g.category;
  }
  const kind = g.kind || g.type || 'image';
  const meta = g.meta || {};
  const info = g.info || {};
  const name = (g.name || '').toLowerCase();
  const fps = Number(g.fps ?? info.fps ?? meta.fps ?? 0);
  const w = Number(g.width ?? info.width ?? meta.width ?? 0);

  if (kind === 'video') {
    if (meta.post || fps >= 48 || /1080p60|rife|_post|enhanced/i.test(name)) {
      return 'enhanced';
    }
    if (meta.task === 'lyra' || /lyra|world|flythrough|s\d_|g\d_/i.test(name)) {
      return 'world3d';
    }
    return 'raw_video';
  }
  if (w >= 1920 || meta.builtin_draft || /2k|laputa|s\d_|g\d_/i.test(name)) {
    return 'image2k';
  }
  return 'image2k';
}

/** Check if a gallery item matches one of the 7 filter tabs */
export function matchesGalleryFilter(g, filter) {
  if (!filter || filter === 'all') return true;
  const kind = g.kind || g.type || 'image';
  const cat = resolveGalleryCategory(g);
  const meta = g.meta || {};
  const name = (g.name || '').toLowerCase();
  const tags = Array.isArray(g.tags) ? g.tags : (Array.isArray(meta.tags) ? meta.tags : []);

  switch (filter) {
    case 'fav':
      return isGalleryFavorite(g);
    case 'video':
      return kind === 'video';
    case 'image':
      return kind === 'image';
    case 'enhanced':
      return (
        cat === 'enhanced' ||
        !!meta.post ||
        Number(g.fps ?? g.info?.fps ?? meta.fps ?? 0) >= 48 ||
        /1080p60|rife|_post/i.test(name) ||
        tags.some((t) => /1080p|60fps|rife|增强/i.test(t))
      );
    case 'world3d':
      return (
        kind === 'video' &&
        (cat === 'world3d' ||
          cat === 'enhanced' ||
          meta.task === 'lyra' ||
          !!meta.post ||
          /lyra|world|s\d_|g\d_/i.test(name) ||
          tags.some((t) => /3d|lyra|穿梭|漫游/i.test(t)))
      );
    case 'image2k':
      return kind === 'image' && (cat === 'image2k' || Number(g.width ?? g.info?.width ?? meta.width ?? 2048) >= 1500);
    default:
      return kind === filter || cat === filter;
  }
}

export async function reveal(path) {
  if (!path) return;
  try { await local('/reveal', { body: { path }, errTitle: '无法在 Finder 中显示' }); } catch {}
}

export function download(url, name) {
  const a = h('a', { href: url, download: name || '' });
  document.body.append(a);
  a.click();
  a.remove();
}

export async function deleteGallery(g) {
  const ok = await confirmDialog({
    title: '删除作品？',
    message: `「${g.title || g.name}」将从作品库和磁盘中删除，此操作不可撤销。`,
    confirmText: '删除',
    danger: true,
  });
  if (!ok) return false;
  try {
    await local('/gallery/' + encodeURIComponent(g.id), { method: 'DELETE', errTitle: '删除失败' });
    S.gallery = S.gallery.filter((x) => x.id !== g.id);
    emit('gallery', { removed: [g.id] });
    toast('已删除', 'success', { timeout: 1800 });
    return true;
  } catch { return false; }
}

/** item: normalized media {kind,url,name,gallery?,remotePath?} */
export function toSource(item) {
  if (item.gallery) return srcFromGallery(item.gallery);
  if (item.remotePath) return srcFromRemote(item.remotePath, item.name, item.meta);
  return null;
}

export function sendToWorld(item) {
  const src = toSource(item);
  if (!src) return;
  emit('use:world', src);
  emit('tab', 'world');
  toast('已载入 3D 世界', 'success', { timeout: 1600 });
}
export function sendToVideo(item) {
  const src = toSource(item);
  if (!src) return;
  emit('use:video', src);
  emit('tab', 'video');
  toast('已设为视频首帧', 'success', { timeout: 1600 });
}
export function sendToPost(item) {
  if (!item.gallery) {
    toast('该视频尚未保存到作品库，请稍候自动下载完成', 'warn');
    return;
  }
  emit('use:post', item.gallery);
  emit('tab', 'post');
}

export function saveOrReveal(item) {
  if (item.gallery) reveal(item.gallery.path);
  else download(item.url, item.name);
}

/** Extract scene key prefix (e.g. 's1_torii', 'g1_laputa') from filename for smart A/B pairing */
function extractSceneStem(name) {
  if (!name) return null;
  const m = String(name).toLowerCase().match(/\b([gs]\d+_[a-z0-9]+?)(?:_1080p|_rife|_raw|_lyra|_post|\.|$)/);
  if (m) return m[1];
  return String(name)
    .toLowerCase()
    .replace(/\.[a-z0-9]+$/, '')
    .replace(/(_post.*|_1080p.*|_rife.*|_raw.*|_832x480.*)$/, '');
}

/**
 * Resolve A/B comparison pair for a given media item or gallery object.
 * Always returns { rawUrl, enhancedUrl, hasDistinctPair, title, item, rawSpec, enhSpec }.
 */
export function resolveABPair(itemOrGallery) {
  const g = itemOrGallery?.gallery || itemOrGallery || {};
  const it = itemOrGallery?.url ? itemOrGallery : mediaFromGallery(g);
  const rawDirect = it.raw_media_url || g.raw_media_url || g.meta?.raw_media_url;
  const enhDirect = it.enhanced_media_url || g.enhanced_media_url || g.meta?.enhanced_media_url;

  let rawUrl = null;
  let enhancedUrl = null;

  if (rawDirect && enhDirect) {
    rawUrl = rawDirect;
    enhancedUrl = enhDirect;
  } else if (rawDirect) {
    rawUrl = rawDirect;
    enhancedUrl = it.url;
  } else if (enhDirect) {
    rawUrl = it.url;
    enhancedUrl = enhDirect;
  } else {
    // Search S.gallery for counterpart video
    const videos = (S.gallery || []).filter((x) => (x.kind || x.type) === 'video');
    const isEnh = resolveGalleryCategory(g) === 'enhanced';
    const stem = extractSceneStem(g.name || it.name);
    const srcId = g.meta?.source_id || g.meta?.post?.source_id;

    if (isEnh) {
      enhancedUrl = it.url;
      const matchRaw =
        (srcId && videos.find((v) => v.id === srcId)) ||
        (stem && videos.find((v) => v.id !== g.id && resolveGalleryCategory(v) !== 'enhanced' && extractSceneStem(v.name) === stem));
      rawUrl = matchRaw ? matchRaw.url : it.url;
    } else {
      rawUrl = it.url;
      const matchEnh =
        videos.find((v) => (v.meta?.source_id === g.id || v.meta?.post?.source_id === g.id)) ||
        (stem && videos.find((v) => v.id !== g.id && resolveGalleryCategory(v) === 'enhanced' && extractSceneStem(v.name) === stem));
      enhancedUrl = matchEnh ? matchEnh.url : it.url;
    }
  }

  return {
    rawUrl: rawUrl || it.url,
    enhancedUrl: enhancedUrl || it.url,
    hasDistinctPair: !!(rawUrl && enhancedUrl && rawUrl !== enhancedUrl),
    title: it.title || g.title || g.meta?.title || it.name || '3D 世界穿梭对比',
    prompt: it.meta?.prompt || it.meta?.scene || g.meta?.prompt || g.meta?.scene || '',
    rawSpec: 'Colab Raw · 832×480 @ 16fps (原始直出)',
    enhSpec: 'M1 Max Post · 1920×1080 @ 60fps (RIFE v4.6 光流补帧 + 4× 高速穿梭)',
    item: it,
  };
}

/** Normalize a gallery entry into a media item */
export function mediaFromGallery(g) {
  if (!g) return null;
  const kind = g.kind || g.type || 'image';
  const info = g.info || {};
  const meta = g.meta || {};
  const width = Number(g.width ?? info.width ?? meta.width ?? 0) || undefined;
  const height = Number(g.height ?? info.height ?? meta.height ?? 0) || undefined;
  const fps = Number(g.fps ?? info.fps ?? meta.fps ?? 0) || undefined;
  const duration = Number(g.duration ?? info.duration ?? meta.duration ?? 0) || undefined;
  const size = Number(g.size ?? info.size ?? 0) || undefined;
  const category = resolveGalleryCategory(g);
  const favorite = isGalleryFavorite(g);
  const title = g.title || meta.title || g.name || '';
  const tags = Array.isArray(g.tags) ? g.tags : (Array.isArray(meta.tags) ? meta.tags : []);
  const thumb = g.thumb || g.thumb_url || g.url;
  const strip_url = g.strip_url || meta.strip_url || null;
  const strip_frames = Number(g.strip_frames || meta.strip_frames || 12);
  const raw_media_url = g.raw_media_url || meta.raw_media_url || null;
  const enhanced_media_url = g.enhanced_media_url || meta.enhanced_media_url || null;

  return {
    id: g.id,
    kind,
    type: kind,
    category,
    favorite,
    tags,
    title,
    url: g.url,
    thumb,
    thumb_url: thumb,
    strip_url,
    strip_frames,
    raw_media_url,
    enhanced_media_url,
    width,
    height,
    fps,
    duration,
    size,
    name: g.name,
    meta: {
      ...meta,
      width: width || meta.width,
      height: height || meta.height,
      fps: fps || meta.fps,
      duration: duration || meta.duration,
      title,
    },
    gallery: g,
    created: g.created,
  };
}
