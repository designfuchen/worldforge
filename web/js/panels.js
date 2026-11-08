// Center workspace controller: Tabs + Image (t2i) + Video (t2v/i2v) + 3D World (Lyra 2.0) + Post + Gallery.
import { $, $$, h, esc, fmtDur, fmtNum, fmtGB, setText, toast, withBusy, snapFrames, clamp } from './dom.js';
import { icon, trajDiagram } from './icons.js';
import { S, on, emit, colab, modelById, modelsOfKind, workerOf, saveCustomModel } from './store.js';
import { local, remote, resolveRemote, srcFromGallery } from './api.js';
import { pickFromGallery, openABCompare, openCinemaShowcase } from './overlays.js';
import {
  LYRA_ASPECT,
  VIDEO_RESOLUTIONS,
  DIRECTION_LABEL,
  LYRA_FPS,
  LYRA_DURATION_PRESETS,
  VIDEO_PROMPT_PRESETS,
  KIND_LABEL,
  CINEMA_CAMERA_RIGS,
  GOD_TIER_MOVIE_SCENES,
  expandCinemaMasterPrompt,
} from './defaults.js';
import { bindDropzone, bindRanges, renderTaskResults, renderMediaTile } from './cards.js';
import * as A from './actions.js';

export function initPanels({ refreshGallery, refreshAll }) {
  initTabs();
  initImagePanel({ refreshAll });
  initVideoPanel({ refreshAll });
  initWorldPanel({ refreshAll });
  initPostPanel({ refreshGallery, refreshAll });
  initGalleryPanel({ refreshGallery });

  // Bind global dice buttons for random seed inputs
  $$('[data-dice]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.dice;
      const input = document.getElementById(id);
      if (!input) return;
      if (Number(input.value) === -1 || id === 'worldSeed') {
        input.value = String(Math.floor(Math.random() * 2147483647));
      } else {
        input.value = '-1';
      }
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  });
}

/* =========================================================
   SHARED: INLINE HUGGINGFACE MODEL REGISTRATION & CARD RENDERING
   ========================================================= */
function parseHfSpec(raw, fallbackKind = 't2i') {
  let s = (raw || '').trim();
  if (!s) return null;
  s = s.replace(/^https?:\/\/huggingface\.co\//i, '').replace(/\/+$/, '');
  let repo = s;
  let subfolder = '';
  const treeMatch = s.match(/^([^/]+\/[^/]+)\/(?:tree|blob)\/[^/]+\/(.+)$/i);
  if (treeMatch) {
    repo = treeMatch[1];
    subfolder = treeMatch[2];
  } else {
    const parts = s.split('/');
    if (parts.length >= 2) {
      repo = `${parts[0]}/${parts[1]}`;
      if (parts.length > 2) subfolder = parts.slice(2).join('/');
    }
  }
  const lower = `${repo}/${subfolder}`.toLowerCase();
  let kind = fallbackKind;
  if (lower.includes('breeze') || lower.includes('tts') || lower.includes('voice') || lower.includes('cosyvoice')) kind = 'tts';
  else if (lower.includes('lyra')) kind = 'lyra';
  else if (lower.includes('i2v')) kind = 'i2v';
  else if (lower.includes('t2v') || lower.includes('wan') || lower.includes('hunyuanvideo') || lower.includes('ltx') || lower.includes('minimax') || lower.includes('cogvideo')) {
    kind = fallbackKind === 't2i' ? 't2i' : 't2v';
  } else if (lower.includes('flux') || lower.includes('qwen-image') || lower.includes('z-image') || lower.includes('sdxl') || lower.includes('stable-diffusion') || lower.includes('kolors')) {
    kind = 't2i';
  }
  const baseName = repo.split('/').pop() || repo;
  const id = (subfolder ? `${baseName}-${subfolder}` : baseName)
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-');
  const featured_hybrid = /minimax|hybrid|fl2va/i.test(lower);
  const isTts = kind === 'tts' || id === 'breeze-tts-2';
  return {
    id,
    repo,
    subfolder: subfolder || undefined,
    name: subfolder ? `${baseName} (${subfolder})` : baseName,
    kind,
    zero_vram: isTts,
    also_t2i: fallbackKind === 't2i' && kind !== 't2i',
    featured_hybrid,
    builtin: false,
    status: isTts ? 'downloaded' : 'available',
    size_gb: isTts ? 2.8 : (kind === 't2i' ? 24.0 : 32.0),
    storage_tier: isTts ? 'drive' : 'ramdisk',
    description: isTts
      ? `0显存云盘常驻语音合成 · ${repo}`
      : `自定义接入 HuggingFace 模型 · ${repo}${subfolder ? '/' + subfolder : ''}`,
    defaults: kind === 't2i'
      ? { width: 2048, height: 1152, steps: 8, guidance: 3.5 }
      : { width: 832, height: 480, num_frames: 81, fps: 16, steps: 24, guidance: 5.0 },
  };
}

export async function addCustomHfModel(rawInput, defaultKind = 't2i', { refreshAll } = {}) {
  const spec = parseHfSpec(rawInput, defaultKind);
  if (!spec) {
    toast('请输入 HuggingFace 模型仓库地址（如 black-forest-labs/FLUX.1-schnell）', 'warn');
    return null;
  }

  let registered = spec;
  if (S.connected) {
    try {
      const m = await remote('/models', {
        body: { repo: rawInput.trim(), kind: defaultKind },
        silent: true,
      });
      if (m && m.id) {
        registered = { ...spec, ...m, also_t2i: spec.also_t2i || m.kind === 't2i' };
        if (registered.status === 'available') {
          remote(`/models/${encodeURIComponent(registered.id)}/download`, { method: 'POST', silent: true }).catch(() => {});
        }
      }
    } catch {
      // Fallback to local registration so UI always works immediately
    }
  }

  saveCustomModel(registered);
  const idx = S.models.findIndex((x) => x.id === registered.id);
  if (idx >= 0) S.models[idx] = { ...S.models[idx], ...registered };
  else S.models.unshift(registered);

  emit('models', S.models);
  toast(`已添加并选中模型：「${registered.name}」`, 'success');
  if (refreshAll && S.connected) refreshAll();
  return registered;
}

function modelStatusMeta(m) {
  if (m.kind === 'tts' || m.id === 'breeze-tts-2' || m.zero_vram) {
    return { label: '0显存 · 云盘常驻', tone: 'green' };
  }
  const w = workerOf(m.id);
  const activeJob = S.jobs.find(
    (j) => j.model_id === m.id && (j.status === 'running' || j.status === 'queued') && ['download', 'load', 'setup'].includes(j.task),
  );
  if (activeJob) {
    const pct = activeJob.progress ? ` ${Math.round(activeJob.progress * 100)}%` : '';
    return { label: `${activeJob.task === 'download' ? '拉取中' : '加载中'}${pct}`, tone: 'amber' };
  }
  if (w && w.state === 'on_gpu') return { label: 'GPU 常驻', tone: 'green' };
  if (w && w.state === 'offloaded') return { label: '内存盘待命', tone: 'cyan' };
  if (m.status === 'loaded') return { label: 'GPU 常驻', tone: 'green' };
  if (m.status === 'downloaded') return { label: '内存盘就绪', tone: 'cyan' };
  if (m.storage_tier === 'ramdisk') return { label: '内存盘就绪', tone: 'cyan' };
  return { label: '云端就绪', tone: 'blue' };
}

function renderModelSelectorCards(container, models, selectedId, onSelect) {
  if (!container) return;
  container.innerHTML = '';
  models.forEach((m) => {
    const isSel = m.id === selectedId;
    const isZeroVram = m.kind === 'tts' || m.id === 'breeze-tts-2' || m.zero_vram;
    const st = modelStatusMeta(m);
    const kindTag = m.kind === 'lyra' ? '3D 世界长片' : (KIND_LABEL[m.kind] || m.kind.toUpperCase());
    const card = h(
      'button',
      {
        type: 'button',
        class: 'mcard' + (isSel ? ' on' : '') + (m.featured_hybrid ? ' is-hybrid' : ''),
        'data-model-id': m.id,
        onclick: () => onSelect(m),
      },
      h('div', { class: 'mcard-top' },
        h('div', { class: 'mcard-title-wrap' },
          h('span', { class: 'mcard-check', html: isSel ? icon('check') : '' }),
          h('span', { class: 'mcard-name', title: m.name || m.id }, m.name || m.id),
        ),
        h('span', { class: 'badge mcard-status', 'data-tone': st.tone }, st.label),
      ),
      h('div', { class: 'mcard-meta' },
        m.featured_hybrid ? h('span', { class: 'mcard-pill hybrid' }, '⚡ 音视频同生') : null,
        isZeroVram ? h('span', { class: 'mcard-pill zero-vram' }, '☁️ 0显存 · 云盘常驻') : null,
        h('span', { class: 'mcard-pill' }, kindTag),
        m.size_gb ? h('span', { class: 'mcard-size' }, fmtGB(m.size_gb)) : null,
        isSel ? h('span', { class: 'mcard-active-lbl' }, '✓ 当前使用') : null,
      ),
      m.description ? h('div', { class: 'mcard-desc' }, m.description) : null,
    );
    container.append(card);
  });
}

function renderCinemaCamBar(container, activeCamId, onSelect) {
  if (!container) return;
  container.innerHTML = '';
  CINEMA_CAMERA_RIGS.forEach((rig) => {
    const isOn = rig.id === activeCamId;
    container.append(
      h(
        'button',
        {
          type: 'button',
          class: 'chip cinema-cam-pill' + (isOn ? ' on' : ''),
          title: `${rig.name}\n光学规格：${rig.spec}`,
          onclick: () => onSelect(rig),
        },
        rig.name,
      ),
    );
  });
}

function applyCinemaRigSuffix(prompt, rigId) {
  const clean = (prompt || '').trim();
  if (!clean) return '';
  const rig = CINEMA_CAMERA_RIGS.find((r) => r.id === rigId) || CINEMA_CAMERA_RIGS[0];
  if (!rig || !rig.suffix) return clean;
  // Avoid duplicating if the prompt already includes the camera signature
  if (clean.includes('ARRI Alexa') || clean.includes('Sony Venice') || clean.includes('Panavision') || clean.includes(rig.suffix.slice(0, 28))) {
    return clean;
  }
  return `${clean}${rig.suffix}`;
}

/* =========================================================
   TABS & INDICATOR
   ========================================================= */
function initTabs() {
  const indicator = $('#tabIndicator');
  const tabBtns = $$('#tabs .tab');
  const panels = $$('#panels .panel');

  function updateIndicator() {
    const active = $('#tabs .tab.on');
    if (!active || !indicator) return;
    indicator.style.left = `${active.offsetLeft}px`;
    indicator.style.width = `${active.offsetWidth}px`;
  }

  function setTab(name) {
    if (!name) return;
    S.tab = name;
    tabBtns.forEach((b) => b.classList.toggle('on', b.dataset.tab === name));
    panels.forEach((p) => p.classList.toggle('on', p.dataset.panel === name));
    requestAnimationFrame(updateIndicator);
  }

  tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => emit('tab', btn.dataset.tab));
  });

  on('tab', setTab);
  window.addEventListener('resize', updateIndicator);
  setTab(S.tab || 'image');
  setTimeout(updateIndicator, 60);
}

/* =========================================================
   PANEL 1: IMAGE (T2I) — 3-STEP STREAMLINED WORKFLOW
   ========================================================= */
function initImagePanel({ refreshAll }) {
  const modelCardsWrap = $('#t2iModelCards');
  const toggleAddBtn = $('#t2iToggleAdd');
  const addBox = $('#t2iAddBox');
  const addInput = $('#t2iAddInput');
  const addBtn = $('#t2iAddBtn');
  const expandPromptBtn = $('#t2iExpandPrompt');
  const dicePromptBtn = $('#t2iDicePrompt');
  const cinemaCamWrap = $('#t2iCinemaCam');

  const promptEl = $('#t2iPrompt');
  const charsEl = $('#t2iChars');
  const clearBtn = $('#t2iClear');
  const negEl = $('#t2iNeg');
  const stylesWrap = $('#t2iStyles');
  const scenesWrap = $('#t2iScenes');
  const aspectsWrap = $('#t2iAspects');
  const modelSel = $('#t2iModel');
  const countWrap = $('#t2iCount');
  const countInput = $('#t2iCount input');
  const seedInput = $('#t2iSeed');
  const stepsInput = $('#t2iSteps');
  const metaEl = $('#t2iMeta');
  const runBtn = $('#t2iRun');
  const resultsEl = $('#t2iResults');
  const resultsHint = $('#t2iResultsHint');

  let activeStyleId = null;
  let activeSceneId = null;
  let activeCamId = 'iwai_soft'; // Default: 🌸 岩井俊二·黄金逆光柔焦 (ARRI Alexa 65 + 85mm f/1.2L)
  let selectedModelId = 'qwen-image-2.1-turbo';
  let activeAspect = (S.presets.aspect_presets && S.presets.aspect_presets[0]) || { id: '16:9', name: '16:9 横屏 2K', width: 2752, height: 1536 };

  function getScenePresets() {
    // Always prioritize the 8 God-Tier Movie Scenes
    const remoteScenes = S.presets.scene_presets || [];
    const seen = new Set(GOD_TIER_MOVIE_SCENES.map((s) => s.id));
    const extra = remoteScenes.filter((s) => s && s.id && !seen.has(s.id));
    return [...GOD_TIER_MOVIE_SCENES, ...extra];
  }

  function getImageModels() {
    const list = modelsOfKind('t2i');
    // Ensure minimax-h3-hybrid is always selectable for hybrid image generation too
    const pc = modelById('minimax-h3-hybrid');
    if (pc && !list.some((m) => m.id === pc.id)) {
      list.push(pc);
    }
    return list;
  }

  function selectImageModel(mOrId, { focusPrompt = false, announce = false } = {}) {
    const id = typeof mOrId === 'string' ? mOrId : mOrId?.id;
    if (!id) return;
    selectedModelId = id;
    if (modelSel) modelSel.value = id;
    const m = modelById(id);
    if (m?.defaults?.steps && stepsInput) {
      stepsInput.value = String(m.defaults.steps);
    }
    syncModels();
    if (announce && m) {
      toast(`已选择生图模型：${m.name}，输入一句话提示词即可生成`, 'info', { timeout: 2200 });
    }
    if (focusPrompt) {
      setTimeout(() => promptEl?.focus(), 60);
    }
  }

  // Toggle inline "+ 添加生图模型" box
  toggleAddBtn?.addEventListener('click', () => {
    if (!addBox) return;
    addBox.hidden = !addBox.hidden;
    if (!addBox.hidden) setTimeout(() => addInput?.focus(), 50);
  });

  async function handleAddImageModel(rawVal) {
    const val = (rawVal ?? addInput?.value ?? '').trim();
    const added = await addCustomHfModel(val, 't2i', { refreshAll });
    if (added) {
      if (addInput) addInput.value = '';
      if (addBox) addBox.hidden = true;
      selectImageModel(added.id, { focusPrompt: true });
    }
  }

  addBtn?.addEventListener('click', () => withBusy(addBtn, () => handleAddImageModel()));
  addInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      withBusy(addBtn, () => handleAddImageModel());
    }
  });
  $$('[data-hf-t2i]').forEach((chip) => {
    chip.addEventListener('click', () => {
      const repo = chip.dataset.hfT2i;
      if (addInput) addInput.value = repo;
      withBusy(chip, () => handleAddImageModel(repo));
    });
  });

  // ✨ 电影级扩写 button
  expandPromptBtn?.addEventListener('click', () => {
    if (!promptEl) return;
    const expanded = expandCinemaMasterPrompt(promptEl.value, activeCamId, false);
    promptEl.value = expanded;
    updateChars();
    updateMeta();
    const rig = CINEMA_CAMERA_RIGS.find((r) => r.id === activeCamId) || CINEMA_CAMERA_RIGS[0];
    toast(`✨ 已为您扩写为「${rig.short}」大师级唯美电影提示词`, 'success', { timeout: 2200 });
    promptEl.focus();
  });

  // Random scene prompt button
  dicePromptBtn?.addEventListener('click', () => {
    const scenes = getScenePresets();
    if (!scenes.length || !promptEl) return;
    const pick = scenes[Math.floor(Math.random() * scenes.length)];
    activeSceneId = pick.id;
    promptEl.value = pick.prompt;
    updateChars();
    renderPresets();
    updateMeta();
    toast(`🎬 已填入电影级片段：${pick.name}`, 'info', { timeout: 1800 });
    promptEl.focus();
  });

  function updateChars() {
    if (charsEl && promptEl) charsEl.textContent = String(promptEl.value.length);
  }

  promptEl?.addEventListener('input', () => {
    updateChars();
    updateMeta();
  });

  clearBtn?.addEventListener('click', () => {
    if (!promptEl) return;
    promptEl.value = '';
    activeSceneId = null;
    renderPresets();
    updateChars();
    updateMeta();
    promptEl.focus();
  });

  // Stepper for batch count
  $$('button[data-d]', countWrap).forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!countInput) return;
      const d = Number(btn.dataset.d) || 0;
      countInput.value = String(clamp((Number(countInput.value) || 1) + d, 1, 8));
      updateMeta();
    });
  });
  countInput?.addEventListener('input', updateMeta);
  stepsInput?.addEventListener('input', updateMeta);

  modelSel?.addEventListener('change', () => {
    selectImageModel(modelSel.value);
  });

  function renderPresets() {
    renderCinemaCamBar(cinemaCamWrap, activeCamId, (rig) => {
      activeCamId = rig.id;
      renderPresets();
      updateMeta();
      toast(`🎥 已切换电影摄影机：${rig.name}`, 'info', { timeout: 1800 });
    });

    const styles = S.presets.t2i_styles || [];
    if (stylesWrap) {
      stylesWrap.innerHTML = '';
      styles.forEach((st) => {
        stylesWrap.append(
          h('button', {
            class: 'chip' + (activeStyleId === st.id ? ' on' : ''),
            type: 'button',
            onclick: () => {
              activeStyleId = activeStyleId === st.id ? null : st.id;
              renderPresets();
              updateMeta();
            },
          }, st.name),
        );
      });
    }

    const scenes = getScenePresets();
    if (scenesWrap) {
      scenesWrap.innerHTML = '';
      scenes.forEach((sc) => {
        scenesWrap.append(
          h('button', {
            class: 'chip scene-movie-chip' + (activeSceneId === sc.id ? ' on' : ''),
            type: 'button',
            title: sc.prompt,
            onclick: () => {
              activeSceneId = sc.id;
              if (promptEl) {
                promptEl.value = sc.prompt;
                updateChars();
              }
              renderPresets();
              updateMeta();
            },
          }, sc.name),
        );
      });
    }

    const aspects = [...(S.presets.aspect_presets || []), LYRA_ASPECT];
    if (aspectsWrap) {
      aspectsWrap.innerHTML = '';
      aspects.forEach((a) => {
        const maxSide = 16;
        const ratio = a.width / a.height;
        const bw = ratio >= 1 ? maxSide : Math.max(7, Math.round(maxSide * ratio));
        const bh = ratio >= 1 ? Math.max(7, Math.round(maxSide / ratio)) : maxSide;
        aspectsWrap.append(
          h('button', {
            class: 'aspect' + (activeAspect.id === a.id ? ' on' : ''),
            type: 'button',
            onclick: () => {
              activeAspect = a;
              renderPresets();
              updateMeta();
            },
          },
            h('span', { class: 'aspect-box' }, h('i', { style: { width: `${bw}px`, height: `${bh}px` } })),
            h('span', { class: 'aspect-txt' },
              h('b', {}, a.name),
              h('span', {}, `${a.width}×${a.height}`))),
        );
      });
    }
  }

  function syncModels() {
    const list = getImageModels();
    if (!list.some((m) => m.id === selectedModelId) && list.length) {
      selectedModelId = list[0].id;
    }

    if (modelSel) {
      modelSel.innerHTML = '';
      list.forEach((m) => {
        modelSel.append(h('option', { value: m.id }, m.name || m.id));
      });
      modelSel.value = selectedModelId;
    }

    renderModelSelectorCards(modelCardsWrap, list, selectedModelId, (m) => {
      selectImageModel(m.id, { focusPrompt: true, announce: true });
    });

    updateMeta();
  }

  function updateMeta() {
    if (!metaEl) return;
    const m = modelById(selectedModelId) || getImageModels()[0];
    const rig = CINEMA_CAMERA_RIGS.find((r) => r.id === activeCamId) || CINEMA_CAMERA_RIGS[0];
    const count = clamp(Number(countInput?.value) || 1, 1, 8);
    const steps = Number(stepsInput?.value) || 8;
    const st = (S.presets.t2i_styles || []).find((x) => x.id === activeStyleId);
    const parts = [
      `<span>模型 <b>${esc(m?.name || selectedModelId)}</b></span>`,
      `<span>摄影机 <b>${esc(rig.short)}</b></span>`,
      `<span>尺寸 <b>${activeAspect.width}×${activeAspect.height}</b> · <b>${count} 张</b></span>`,
    ];
    if (st) parts.push(`<span>风格 <b>${esc(st.name)}</b></span>`);
    if (!S.connected) {
      parts.push(`<span class="warn">${icon('alert')}提交时如未连接 GPU 将自动引导连接</span>`);
    }
    metaEl.innerHTML = parts.join('');
  }

  async function submitT2i() {
    let rawPrompt = (promptEl?.value || '').trim();
    if (!rawPrompt) {
      toast('请先在步骤 ② 输入一句话画面描述，或点击下方电影片段芯片', 'warn', {
        actionText: '🎲 随机填入并生成',
        onAction: () => {
          dicePromptBtn?.click();
          if (promptEl?.value.trim()) submitT2i();
        },
      });
      promptEl?.focus();
      return;
    }
    if (!S.connected) {
      toast('当前尚未连接 Colab 云端 GPU，请点击左侧「一键启动并连接」', 'warn', {
        actionText: '🚀 立即启动 GPU',
        onAction: () => $('#btnStart')?.click(),
      });
      return;
    }
    const st = (S.presets.t2i_styles || []).find((x) => x.id === activeStyleId);
    const withStyle = st ? `${rawPrompt}${st.suffix}` : rawPrompt;
    const finalPrompt = applyCinemaRigSuffix(withStyle, activeCamId);
    const neg = (negEl?.value || '').trim();
    const count = clamp(Number(countInput?.value) || 1, 1, 8);
    const steps = clamp(Number(stepsInput?.value) || 8, 1, 100);
    const seed = Number(seedInput?.value ?? -1);
    const modelId = selectedModelId || modelSel?.value || 'qwen-image-2.1-turbo';

    await withBusy(runBtn, async () => {
      try {
        await remote('/jobs', {
          body: {
            model_id: modelId,
            task: 't2i',
            params: {
              prompt: finalPrompt,
              negative_prompt: neg || undefined,
              width: activeAspect.width,
              height: activeAspect.height,
              steps,
              seed,
              count,
            },
          },
          errTitle: '提交生图任务失败',
        });
        const m = modelById(modelId);
        toast(`已提交生图任务（${m?.name || modelId}）`, 'success', { timeout: 2000 });
        emit('poll:fast');
        refreshAll();
      } catch {}
    });
  }

  runBtn?.addEventListener('click', submitT2i);

  function renderResults() {
    const t2iJobs = S.jobs.filter((j) => j.task === 't2i');
    if (resultsHint) {
      resultsHint.textContent = t2iJobs.length ? `共 ${t2iJobs.length} 次生成任务` : '生成完成后悬停图片可一键「做成 3D 世界」或「图生视频」';
    }
    renderTaskResults(resultsEl, ['t2i'], {
      emptyIcon: 'sparkles',
      emptyTitle: '还没有生图记录',
      emptySub: '① 选择生图模型 → ② 输入一句话描述 → ③ 点击「⚡ 立即生成图片」即可出图',
    });
  }

  on('presets', renderPresets);
  on('models', syncModels);
  on('state', () => {
    syncModels();
    updateMeta();
  });
  on('jobs', () => {
    syncModels();
    renderResults();
  });
  on('gallery', renderResults);
  on('model:select', (m) => {
    if (!m) return;
    if (m.kind === 't2i' || m.also_t2i) {
      selectImageModel(m.id, { focusPrompt: true });
    }
  });
  on('run:image', submitT2i);

  renderPresets();
  syncModels();
  updateChars();
  renderResults();
}

/* =========================================================
   PANEL 2: VIDEO (T2V / I2V / LYRA) — 3-STEP STREAMLINED WORKFLOW
   ========================================================= */
function initVideoPanel({ refreshAll }) {
  const modelCardsWrap = $('#vidModelCards');
  const toggleAddBtn = $('#vidToggleAdd');
  const addBox = $('#vidAddBox');
  const addInput = $('#vidAddInput');
  const addBtn = $('#vidAddBtn');
  const expandPromptBtn = $('#vidExpandPrompt');
  const dicePromptBtn = $('#vidDicePrompt');
  const cinemaCamWrap = $('#vidCinemaCam');
  const clearBtn = $('#vidClear');
  const charsEl = $('#vidChars');
  const scenesWrap = $('#vidScenes');
  const optRefDetails = $('#vidOptRefDetails');

  const dropEl = $('#vidDrop');
  const promptEl = $('#vidPrompt');
  const negEl = $('#vidNeg');
  const modelSel = $('#vidModel');
  const resSel = $('#vidRes');
  const framesInput = $('#vidFrames');
  const fpsInput = $('#vidFps');
  const stepsInput = $('#vidSteps');
  const guidanceInput = $('#vidGuidance');
  const seedInput = $('#vidSeed');
  const metaEl = $('#vidMeta');
  const runBtn = $('#vidRun');
  const resultsEl = $('#vidResults');

  let vidSource = null;
  let activeVidSceneId = null;
  let activeVidCamId = 'iwai_soft'; // Default: 🌸 岩井俊二·黄金逆光柔焦 (ARRI Alexa 65 + 85mm f/1.2L)
  let selectedModelId = 'minimax-h3-hybrid';

  function getVideoModels() {
    const list = modelsOfKind('t2v', 'i2v', 'lyra', 'tts');
    // Sort so minimax-h3-hybrid is always first
    return list.slice().sort((a, b) => {
      if (a.id === 'minimax-h3-hybrid') return -1;
      if (b.id === 'minimax-h3-hybrid') return 1;
      if (a.featured_hybrid && !b.featured_hybrid) return -1;
      if (!a.featured_hybrid && b.featured_hybrid) return 1;
      return 0;
    });
  }

  function selectVideoModel(mOrId, { focusPrompt = false, announce = false } = {}) {
    const id = typeof mOrId === 'string' ? mOrId : mOrId?.id;
    if (!id) return;
    selectedModelId = id;
    if (modelSel) modelSel.value = id;
    const m = modelById(id);
    if (m?.defaults) {
      if (m.defaults.steps && stepsInput) stepsInput.value = String(m.defaults.steps);
      if (m.defaults.fps && fpsInput) fpsInput.value = String(m.defaults.fps);
      if (m.defaults.num_frames && framesInput) framesInput.value = String(m.defaults.num_frames);
      if (m.defaults.guidance != null && guidanceInput) guidanceInput.value = String(m.defaults.guidance);
    }
    syncModels();
    if (announce && m) {
      toast(`已选择视频模型：${m.name}，输入一句话提示词即可生成视频`, 'info', { timeout: 2200 });
    }
    if (focusPrompt) {
      setTimeout(() => promptEl?.focus(), 60);
    }
  }

  // Toggle inline "+ 添加视频模型" box
  toggleAddBtn?.addEventListener('click', () => {
    if (!addBox) return;
    addBox.hidden = !addBox.hidden;
    if (!addBox.hidden) setTimeout(() => addInput?.focus(), 50);
  });

  async function handleAddVideoModel(rawVal) {
    const val = (rawVal ?? addInput?.value ?? '').trim();
    const added = await addCustomHfModel(val, 't2v', { refreshAll });
    if (added) {
      if (addInput) addInput.value = '';
      if (addBox) addBox.hidden = true;
      selectVideoModel(added.id, { focusPrompt: true });
    }
  }

  addBtn?.addEventListener('click', () => withBusy(addBtn, () => handleAddVideoModel()));
  addInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      withBusy(addBtn, () => handleAddVideoModel());
    }
  });
  $$('[data-hf-vid]').forEach((chip) => {
    chip.addEventListener('click', () => {
      const repo = chip.dataset.hfVid;
      if (addInput) addInput.value = repo;
      withBusy(chip, () => handleAddVideoModel(repo));
    });
  });

  function updateChars() {
    if (charsEl && promptEl) charsEl.textContent = String(promptEl.value.length);
  }

  promptEl?.addEventListener('input', () => {
    updateChars();
    updateMeta();
  });

  clearBtn?.addEventListener('click', () => {
    if (!promptEl) return;
    promptEl.value = '';
    activeVidSceneId = null;
    renderVideoPresets();
    updateChars();
    updateMeta();
    promptEl.focus();
  });

  // ✨ 电影级扩写 button
  expandPromptBtn?.addEventListener('click', () => {
    if (!promptEl) return;
    const expanded = expandCinemaMasterPrompt(promptEl.value, activeVidCamId, true);
    promptEl.value = expanded;
    updateChars();
    updateMeta();
    const rig = CINEMA_CAMERA_RIGS.find((r) => r.id === activeVidCamId) || CINEMA_CAMERA_RIGS[0];
    toast(`✨ 已为您扩写为「${rig.short}」大师级电影运镜提示词`, 'success', { timeout: 2200 });
    promptEl.focus();
  });

  dicePromptBtn?.addEventListener('click', () => {
    const presets = VIDEO_PROMPT_PRESETS || [];
    if (!presets.length || !promptEl) return;
    const pick = presets[Math.floor(Math.random() * presets.length)];
    activeVidSceneId = pick.id;
    promptEl.value = pick.prompt;
    updateChars();
    renderVideoPresets();
    updateMeta();
    toast(`🎬 已填入电影级片段：${pick.name}`, 'info', { timeout: 1800 });
    promptEl.focus();
  });

  function renderVideoPresets() {
    renderCinemaCamBar(cinemaCamWrap, activeVidCamId, (rig) => {
      activeVidCamId = rig.id;
      renderVideoPresets();
      updateMeta();
      toast(`🎥 已切换电影摄影机：${rig.name}`, 'info', { timeout: 1800 });
    });

    if (!scenesWrap) return;
    scenesWrap.innerHTML = '';
    (VIDEO_PROMPT_PRESETS || []).forEach((sc) => {
      scenesWrap.append(
        h('button', {
          class: 'chip scene-movie-chip' + (activeVidSceneId === sc.id ? ' on' : ''),
          type: 'button',
          title: sc.prompt,
          onclick: () => {
            activeVidSceneId = sc.id;
            if (promptEl) {
              promptEl.value = sc.prompt;
              updateChars();
            }
            renderVideoPresets();
            updateMeta();
          },
        }, sc.name),
      );
    });
  }

  const dz = dropEl ? bindDropzone(dropEl, {
    onChange: (src) => {
      vidSource = src;
      if (src && optRefDetails) optRefDetails.open = true;
      syncModels();
      updateMeta();
    },
  }) : null;

  on('use:video', (src) => {
    if (optRefDetails) optRefDetails.open = true;
    dz?.set(src);
    if (src?.meta?.prompt && promptEl && !promptEl.value.trim()) {
      promptEl.value = src.meta.prompt;
      updateChars();
    }
  });

  if (resSel) {
    resSel.innerHTML = '';
    VIDEO_RESOLUTIONS.forEach((r) => {
      resSel.append(h('option', { value: r.id }, r.name));
    });
  }

  modelSel?.addEventListener('change', () => {
    selectVideoModel(modelSel.value);
  });

  function syncModels() {
    const list = getVideoModels();
    if (!list.some((m) => m.id === selectedModelId) && list.length) {
      selectedModelId = list[0].id;
    }

    if (modelSel) {
      modelSel.innerHTML = '';
      list.forEach((m) => {
        modelSel.append(h('option', { value: m.id }, `${m.name || m.id} (${m.kind.toUpperCase()})`));
      });
      modelSel.value = selectedModelId;
    }

    renderModelSelectorCards(modelCardsWrap, list, selectedModelId, (m) => {
      selectVideoModel(m.id, { focusPrompt: true, announce: true });
    });

    updateMeta();
  }

  function updateMeta() {
    if (!metaEl) return;
    const m = modelById(selectedModelId) || getVideoModels()[0];
    const rig = CINEMA_CAMERA_RIGS.find((r) => r.id === activeVidCamId) || CINEMA_CAMERA_RIGS[0];
    const resObj = VIDEO_RESOLUTIONS.find((r) => r.id === resSel?.value) || VIDEO_RESOLUTIONS[0];
    const frames = Number(framesInput?.value) || 81;
    const fps = Number(fpsInput?.value) || 24;
    const isTts = m?.kind === 'tts' || m?.id === 'breeze-tts-2';
    const dur = m?.kind === 'lyra' ? '30.1' : (frames / Math.max(1, fps)).toFixed(1);
    const modeTxt = isTts
      ? 'Breeze-TTS-2 语音合成 (0显存 · 云盘常驻)'
      : (m?.kind === 'lyra'
          ? 'Lyra 2.0 3D 长片直出'
          : (vidSource ? '图生视频 (I2V)' : '一句话文生视频 (T2V)'));
    const parts = [
      `<span>模型 <b>${esc(m?.name || selectedModelId)}</b></span>`,
      isTts ? `<span>模式 <b>${modeTxt}</b></span>` : `<span>摄影机 <b>${esc(rig.short)}</b></span>`,
      isTts
        ? `<span>引擎 <b>Google Drive 云盘常驻 · 0 GPU 显存占用</b></span>`
        : `<span>规格 <b>${resObj.width}×${resObj.height} · ~${dur}s</b></span>`,
    ];
    if (!S.connected) {
      parts.push(`<span class="warn">${icon('alert')}提交时如未连接 GPU 将自动引导连接</span>`);
    }
    metaEl.innerHTML = parts.join('');
  }

  [resSel, framesInput, fpsInput, stepsInput, guidanceInput].forEach((el) => {
    el?.addEventListener('input', updateMeta);
    el?.addEventListener('change', updateMeta);
  });

  async function submitVideo() {
    const prompt = (promptEl?.value || '').trim();
    if (!prompt && !vidSource) {
      toast('请先在步骤 ② 输入一句话视频提示词，或点击下方快速芯片', 'warn', {
        actionText: '🎲 随机填入并生成',
        onAction: () => {
          dicePromptBtn?.click();
          if (promptEl?.value.trim()) submitVideo();
        },
      });
      promptEl?.focus();
      return;
    }
    if (!S.connected) {
      toast('当前尚未连接 Colab 云端 GPU，请点击左侧「一键启动并连接」', 'warn', {
        actionText: '🚀 立即启动 GPU',
        onAction: () => $('#btnStart')?.click(),
      });
      return;
    }
    const modelId = selectedModelId || modelSel?.value || 'minimax-h3-hybrid';
    const resObj = VIDEO_RESOLUTIONS.find((r) => r.id === resSel?.value) || VIDEO_RESOLUTIONS[0];
    const numFrames = clamp(Number(framesInput?.value) || 81, 9, 721);
    const fps = clamp(Number(fpsInput?.value) || 24, 8, 60);
    const steps = clamp(Number(stepsInput?.value) || 8, 1, 100);
    const guidance = Number(guidanceInput?.value ?? 1.0);
    const seed = Number(seedInput?.value ?? -1);
    const neg = (negEl?.value || '').trim();

    await withBusy(runBtn, async () => {
      try {
        let imagePath;
        if (vidSource) {
          imagePath = await resolveRemote(vidSource);
        }
        const m = modelById(modelId);
        const finalVideoPrompt = applyCinemaRigSuffix(prompt, activeVidCamId);
        if (m?.kind === 'tts' || modelId === 'breeze-tts-2') {
          await remote('/jobs', {
            body: {
              model_id: modelId || 'breeze-tts-2',
              task: 'tts',
              params: {
                prompt,
                text: prompt,
                seed: seed < 0 ? 42 : seed,
              },
            },
            errTitle: '提交 Breeze-TTS-2 语音生成任务失败',
          });
          toast('已提交 Breeze-TTS-2 语音合成任务（0显存 · 云盘常驻）', 'success', { timeout: 2000 });
        } else if (m?.kind === 'lyra' || modelId === 'lyra-2') {
          await remote('/jobs', {
            body: {
              model_id: 'lyra-2',
              task: 'lyra',
              params: {
                scene: finalVideoPrompt,
                prompt: finalVideoPrompt,
                image_path: imagePath,
                mode: 'flythrough',
                frames: 481,
                zoom_out_frames: 241,
                zoom_in_frames: 241,
                steps: 4,
                dmd: true,
                seed: seed < 0 ? 42 : seed,
              },
            },
            errTitle: '提交 Lyra 2.0 3D 视频任务失败',
          });
          toast('已提交 Lyra 2.0 3D 长片视频任务', 'success', { timeout: 2000 });
        } else {
          const task = vidSource ? 'i2v' : 't2v';
          await remote('/jobs', {
            body: {
              model_id: modelId,
              task,
              params: {
                prompt: finalVideoPrompt,
                negative_prompt: neg || undefined,
                width: resObj.width,
                height: resObj.height,
                num_frames: numFrames,
                fps,
                steps,
                guidance,
                seed,
                image_path: imagePath,
              },
            },
            errTitle: '提交视频任务失败',
          });
          toast(`已提交视频生成任务（${m?.name || modelId}）`, 'success', { timeout: 2000 });
        }
        emit('poll:fast');
        refreshAll();
      } catch {}
    });
  }

  runBtn?.addEventListener('click', submitVideo);

  function renderResults() {
    renderTaskResults(resultsEl, ['t2v', 'i2v', 'lyra', 'tts'], {
      emptyIcon: 'film',
      emptyTitle: '还没有视频/语音生成记录',
      emptySub: '① 选择模型 → ② 输入一句话提示词或台词 → ③ 点击「🎬 立即生成视频」即可直出',
    });
  }

  on('models', syncModels);
  on('state', () => {
    syncModels();
    updateMeta();
  });
  on('jobs', () => {
    syncModels();
    renderResults();
  });
  on('gallery', renderResults);
  on('model:select', (m) => {
    if (!m) return;
    if (m.kind === 't2v' || m.kind === 'i2v' || m.kind === 'lyra' || m.kind === 'tts' || m.id === 'breeze-tts-2') {
      selectVideoModel(m.id, { focusPrompt: true });
    }
  });
  on('run:video', submitVideo);

  renderVideoPresets();
  syncModels();
  updateChars();
  renderResults();
}

/* =========================================================
   PANEL 3: 3D WORLD (LYRA 2.0)
   ========================================================= */
function initWorldPanel({ refreshAll }) {
  const statusBadge = $('#lyraStatus');
  const dropEl = $('#worldDrop');
  const sceneEl = $('#worldScene');
  const scenesWrap = $('#worldScenes');
  const capStateEl = $('#worldCapState');
  const capPreviewEl = $('#worldCapPreview');
  const capEditToggle = $('#worldCapEdit');
  const capTextarea = $('#worldCaption');
  const modeHintEl = $('#worldModeHint');
  const modesWrap = $('#worldModes');
  const paramBody = $('#worldParamBody');
  const dmdToggle = $('#worldDmd');
  const stepsInput = $('#worldSteps');
  const guidanceInput = $('#worldGuidance');
  const shiftInput = $('#worldShift');
  const seedInput = $('#worldSeed');
  const upwardInput = $('#worldUpward');
  const groundToggle = $('#worldGround');
  const estTimeEl = $('#estTime');
  const estCostEl = $('#estCost');
  const estRowsEl = $('#estRows');
  const runBtn = $('#worldRun');
  const resultsEl = $('#worldResults');

  let worldSource = null;
  let activeScenePresetId = null;

  const st = {
    mode: 'flythrough',           // 'flythrough' | 'single'
    trajectory: 'horizontal_zoom',
    direction: 'right',
    strength: 1.0,
    frames: 481,
    zoom_out_frames: 241,
    zoom_out_strength: 1.5,
    zoom_in_frames: 241,
    zoom_in_strength: 3.0,
  };

  const dz = dropEl ? bindDropzone(dropEl, {
    onChange: (src) => {
      worldSource = src;
      if (src?.meta && sceneEl && !sceneEl.value.trim()) {
        const hint = src.meta.scene || src.meta.prompt || '';
        if (hint) {
          sceneEl.value = hint;
          updateCaptionPreview();
        }
      }
      updateEstimate();
    },
  }) : null;

  on('use:world', (src) => {
    dz?.set(src);
    if (src?.meta && sceneEl) {
      const matched = (S.presets.scene_presets || []).find((s) => src.meta.prompt && src.meta.prompt.includes(s.prompt.slice(0, 10)));
      if (matched) {
        sceneEl.value = matched.lyra_scene;
        activeScenePresetId = matched.id;
        renderSceneChips();
      } else if (src.meta.prompt && !sceneEl.value.trim()) {
        sceneEl.value = src.meta.prompt;
      }
      updateCaptionPreview();
    }
  });

  function buildTemplatedCaption(sceneRaw) {
    const tpl = S.presets.caption_template ||
      'A cinematic drone shot glides smoothly forward through {scene}. The entire world is frozen in time like a still tableau: no people, no animals, no wind, nothing moves. Rich parallax and depth, consistent lighting, highly detailed — only the camera travels.';
    const clean = (sceneRaw || '').trim() || 'a vast cinematic world with deep perspective';
    return tpl.replace('{scene}', clean);
  }

  function updateCaptionPreview() {
    const raw = (sceneEl?.value || '').trim();
    const tpl = S.presets.caption_template ||
      'A cinematic drone shot glides smoothly forward through {scene}. The entire world is frozen in time like a still tableau: no people, no animals, no wind, nothing moves. Rich parallax and depth, consistent lighting, highly detailed — only the camera travels.';
    const sceneTxt = raw || 'a vast cinematic world with deep perspective';
    if (capPreviewEl) {
      const parts = tpl.split('{scene}');
      if (parts.length === 2) {
        capPreviewEl.innerHTML = `${esc(parts[0])}<mark>${esc(sceneTxt)}</mark>${esc(parts[1])}`;
      } else {
        capPreviewEl.textContent = buildTemplatedCaption(raw);
      }
    }
    if (capEditToggle && !capEditToggle.checked && capTextarea) {
      capTextarea.value = buildTemplatedCaption(raw);
    }
  }

  sceneEl?.addEventListener('input', () => {
    activeScenePresetId = null;
    renderSceneChips();
    updateCaptionPreview();
  });

  capEditToggle?.addEventListener('change', () => {
    const manual = !!capEditToggle.checked;
    if (capTextarea) {
      capTextarea.hidden = !manual;
      if (manual && !capTextarea.value.trim()) {
        capTextarea.value = buildTemplatedCaption(sceneEl?.value || '');
      }
    }
    if (capStateEl) {
      capStateEl.textContent = manual ? '手动编辑完整提示词' : '自动套用官方 frozen-tableau 模板';
    }
  });

  function renderSceneChips() {
    if (!scenesWrap) return;
    const list = S.presets.scene_presets || [];
    scenesWrap.innerHTML = '';
    list.forEach((sc) => {
      scenesWrap.append(
        h('button', {
          class: 'chip' + (activeScenePresetId === sc.id ? ' on' : ''),
          type: 'button',
          onclick: () => {
            activeScenePresetId = sc.id;
            if (sceneEl) sceneEl.value = sc.lyra_scene;
            renderSceneChips();
            updateCaptionPreview();
          },
        }, sc.name),
      );
    });
  }

  function renderModes() {
    if (!modesWrap) return;
    const trajs = S.presets.lyra_trajectories || [];
    modesWrap.innerHTML = '';

    // Hero mode: flythrough
    const isFly = st.mode === 'flythrough';
    modesWrap.append(
      h('button', {
        class: 'mode hero-mode' + (isFly ? ' on' : ''),
        type: 'button',
        onclick: () => {
          st.mode = 'flythrough';
          renderModes();
          renderParams();
          updateEstimate();
        },
      },
        h('div', { html: trajDiagram('flythrough') }),
        h('b', {}, '一路穿梭', h('span', { class: 'rec' }, '官方同款')),
        h('span', {}, '先倒放后退拉远展示全景，再一路向前深入穿梭，还原 Lyra 2 标志性的长镜头世界漫游')),
    );

    trajs.forEach((t) => {
      const onCard = st.mode === 'single' && st.trajectory === t.id;
      modesWrap.append(
        h('button', {
          class: 'mode' + (onCard ? ' on' : ''),
          type: 'button',
          onclick: () => {
            st.mode = 'single';
            st.trajectory = t.id;
            if (t.directions && t.directions.length && !t.directions.includes(st.direction)) {
              st.direction = t.directions[0];
            }
            if (t.strength?.default != null) {
              st.strength = clamp(st.strength, t.strength.min ?? 0.1, t.strength.max ?? 5);
            }
            renderModes();
            renderParams();
            updateEstimate();
          },
        },
          h('div', { html: trajDiagram(t.id) }),
          h('b', {}, t.name),
          h('span', {}, t.desc || '')),
      );
    });

    if (modeHintEl) {
      if (isFly) {
        modeHintEl.textContent = '已选：官方两段式一路穿梭（后退拉远 + 持续前推）';
      } else {
        const cur = trajs.find((x) => x.id === st.trajectory);
        modeHintEl.textContent = cur ? `已选单一轨迹：${cur.name} — ${cur.desc}` : '';
      }
    }
  }

  function renderParams() {
    if (!paramBody) return;
    paramBody.innerHTML = '';

    // Duration Presets Bar (30s Official / 45s Epic / 15s Quick Preview)
    const durRow = h('div', { class: 'dur-presets-wrap' },
      h('div', { class: 'dur-presets-head' },
        h('span', { class: 'label' }, htmlIconLabel('film', '一键镜头时长规格 (@NVIDIAAI 官方长片同款)')),
        h('span', { class: 'muted mono' }, st.mode === 'flythrough'
          ? `当前共 ${st.zoom_out_frames + st.zoom_in_frames - 1} 帧 (~${((st.zoom_out_frames + st.zoom_in_frames - 1) / LYRA_FPS).toFixed(1)}s)`
          : `当前共 ${st.frames} 帧 (~${(st.frames / LYRA_FPS).toFixed(1)}s)`)),
      h('div', { class: 'dur-presets' },
        LYRA_DURATION_PRESETS.map((dp) => {
          const isMatch = st.mode === 'flythrough'
            ? (st.zoom_out_frames === dp.zoom_out_frames && st.zoom_in_frames === dp.zoom_in_frames)
            : (st.frames === dp.frames);
          return h('button', {
            type: 'button',
            class: 'dur-pill' + (isMatch ? ' on' : '') + (dp.recommended ? ' rec' : ''),
            onclick: () => {
              st.zoom_out_frames = dp.zoom_out_frames;
              st.zoom_in_frames = dp.zoom_in_frames;
              st.frames = dp.frames;
              renderParams();
              updateEstimate();
              toast(`已切换至「${dp.label}」(${dp.sub})`, 'info', { timeout: 1600 });
            },
          },
            h('b', {}, dp.label),
            h('span', {}, dp.sub));
        })));
    paramBody.append(durRow);

    if (st.mode === 'flythrough') {
      paramBody.append(
        h('div', { class: 'param-title', html: icon('cube') + '<span>一路穿梭 · 两段式轨迹参数</span>' }),
        h('div', { class: 'param-sub' }, '帧数自动对齐 1 + 80k（每 80 帧为 1 个自回归推理段，16 fps）'),
        // Segment 1: zoom_out
        buildFlyGroup({
          title: '第 1 段 · 倒放后退拉远 (zoom_out)',
          dotColor: '#a78bfa',
          framesVal: st.zoom_out_frames,
          framesMin: 81,
          framesMax: 481,
          onFrames: (v) => { st.zoom_out_frames = snapFrames(v); updateEstimate(); },
          strVal: st.zoom_out_strength,
          strMin: 0.2,
          strMax: 3.5,
          onStr: (v) => { st.zoom_out_strength = v; updateEstimate(); },
        }),
        // Segment 2: zoom_in
        buildFlyGroup({
          title: '第 2 段 · 向前深入穿梭 (zoom_in)',
          dotColor: '#22d3ee',
          framesVal: st.zoom_in_frames,
          framesMin: 81,
          framesMax: 961,
          onFrames: (v) => { st.zoom_in_frames = snapFrames(v); updateEstimate(); },
          strVal: st.zoom_in_strength,
          strMin: 0.5,
          strMax: 5.0,
          onStr: (v) => { st.zoom_in_strength = v; updateEstimate(); },
        }),
      );
    } else {
      const trajs = S.presets.lyra_trajectories || [];
      const cur = trajs.find((x) => x.id === st.trajectory) || trajs[0] || {
        id: 'horizontal_zoom',
        name: '直线推进',
        directions: [],
        strength: { min: 0.1, max: 5, default: 1.0 },
      };
      const dirs = cur.directions || [];
      const sMin = cur.strength?.min ?? 0.1;
      const sMax = cur.strength?.max ?? 5.0;

      const framesLabel = h('b', {}, `${st.frames} 帧`, h('em', {}, `(${(st.frames / LYRA_FPS).toFixed(1)}s · ${(st.frames - 1) / 80} 段)`));
      const framesInput = h('input', {
        type: 'range',
        min: 81,
        max: 961,
        step: 80,
        value: st.frames,
        oninput: (e) => {
          st.frames = snapFrames(Number(e.target.value));
          framesLabel.innerHTML = `${st.frames} 帧<em>(${(st.frames / LYRA_FPS).toFixed(1)}s · ${(st.frames - 1) / 80} 段)</em>`;
          updateEstimate();
        },
      });

      const strLabel = h('b', {}, fmtNum(st.strength, 1));
      const strInput = h('input', {
        type: 'range',
        min: sMin,
        max: sMax,
        step: 0.1,
        value: st.strength,
        oninput: (e) => {
          st.strength = Number(e.target.value);
          strLabel.textContent = fmtNum(st.strength, 1);
          updateEstimate();
        },
      });

      let dirBlock = null;
      if (dirs.length) {
        const seg = h('div', { class: 'seg seg-xs' });
        dirs.forEach((d) => {
          seg.append(
            h('button', {
              type: 'button',
              class: st.direction === d ? 'on' : '',
              onclick: () => {
                st.direction = d;
                renderParams();
              },
            }, DIRECTION_LABEL[d] || d),
          );
        });
        dirBlock = h('div', { class: 'field', style: { gridColumn: '1 / -1' } },
          h('span', { class: 'label' }, '运动方向'),
          seg);
      }

      paramBody.append(
        h('div', { class: 'param-title', html: icon('camera') + `<span>${esc(cur.name)} · 轨迹参数</span>` }),
        h('div', { class: 'param-group' },
          dirBlock,
          h('div', { class: 'slider' },
            h('div', { class: 'slider-head' }, h('span', {}, '生成总帧数'), framesLabel),
            framesInput,
            h('div', { class: 'slider-ticks' }, h('span', {}, '81 (5s)'), h('span', {}, '481 (30s)'), h('span', {}, '961 (60s)'))),
          h('div', { class: 'slider' },
            h('div', { class: 'slider-head' }, h('span', {}, '运动幅度 (Strength)'), strLabel),
            strInput,
            h('div', { class: 'slider-ticks' }, h('span', {}, String(sMin)), h('span', {}, String(sMax))))),
      );
    }

    bindRanges(paramBody);
  }

  function htmlIconLabel(icName, txt) {
    const s = h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: '6px' } });
    s.innerHTML = `${icon(icName)}<span>${esc(txt)}</span>`;
    return s;
  }

  function buildFlyGroup({ title, dotColor, framesVal, framesMin, framesMax, onFrames, strVal, strMin, strMax, onStr }) {
    const fLabel = h('b', {}, `${framesVal} 帧`, h('em', {}, `(${(framesVal / LYRA_FPS).toFixed(1)}s)`));
    const fRange = h('input', {
      type: 'range',
      min: framesMin,
      max: framesMax,
      step: 80,
      value: framesVal,
      oninput: (e) => {
        const v = snapFrames(Number(e.target.value));
        fLabel.innerHTML = `${v} 帧<em>(${(v / LYRA_FPS).toFixed(1)}s)</em>`;
        onFrames(v);
      },
    });

    const sLabel = h('b', {}, fmtNum(strVal, 1));
    const sRange = h('input', {
      type: 'range',
      min: strMin,
      max: strMax,
      step: 0.1,
      value: strVal,
      oninput: (e) => {
        const v = Number(e.target.value);
        sLabel.textContent = fmtNum(v, 1);
        onStr(v);
      },
    });

    return h('div', { class: 'param-group' },
      h('div', { class: 'param-group-title' },
        h('i', { style: { background: dotColor } }),
        h('span', {}, title)),
      h('div', { class: 'slider' },
        h('div', { class: 'slider-head' }, h('span', {}, '帧数'), fLabel),
        fRange,
        h('div', { class: 'slider-ticks' }, h('span', {}, `${framesMin}`), h('span', {}, `${framesMax}`))),
      h('div', { class: 'slider' },
        h('div', { class: 'slider-head' }, h('span', {}, '推进幅度'), sLabel),
        sRange,
        h('div', { class: 'slider-ticks' }, h('span', {}, `${strMin}`), h('span', {}, `${strMax}`))));
  }

  function updateEstimate() {
    const isFly = st.mode === 'flythrough';
    const outFrames = isFly ? st.zoom_out_frames : 0;
    const inFrames = isFly ? st.zoom_in_frames : st.frames;
    const totalFrames = isFly ? (outFrames + inFrames - 1) : st.frames;
    const chunksOut = isFly ? Math.round((outFrames - 1) / 80) : 0;
    const chunksIn = Math.round((inFrames - 1) / 80);
    const totalChunks = chunksOut + chunksIn;

    const dmd = dmdToggle ? dmdToggle.checked : true;
    const steps = clamp(Number(stepsInput?.value) || 50, 1, 100);
    const secPerChunk = dmd ? 22 : Math.round(22 * (steps / 4) * 0.72);
    const estSec = 15 + totalChunks * secPerChunk;
    const rate = colab().rate || 10.05;
    const estCu = (estSec / 3600) * rate;

    const rawSec = totalFrames / LYRA_FPS;
    const fast8xSec = rawSec / 8;

    setText(estTimeEl, fmtDur(estSec));
    if (estCostEl) {
      estCostEl.innerHTML = `${fmtNum(estCu, 2)}<small>CU</small>`;
    }

    if (estRowsEl) {
      const w = workerOf('lyra-2');
      const lyraMod = modelById('lyra-2');
      if (statusBadge) {
        if (w?.state === 'on_gpu') {
          statusBadge.textContent = 'Lyra 2.0 · GPU 常驻';
          statusBadge.dataset.tone = 'green';
        } else if (lyraMod?.status === 'downloaded' || lyraMod?.status === 'loaded') {
          statusBadge.textContent = 'Lyra 2.0 · 已就绪';
          statusBadge.dataset.tone = 'cyan';
        } else {
          statusBadge.textContent = 'Lyra 2.0';
          statusBadge.dataset.tone = 'violet';
        }
      }

      const outPct = isFly ? Math.round((chunksOut / Math.max(1, totalChunks)) * 100) : 0;
      const inPct = 100 - outPct;

      estRowsEl.innerHTML = `
        <div class="est-bar" title="分段占比">
          ${isFly ? `<i style="width:${outPct}%;background:#a78bfa"></i>` : ''}
          <i style="width:${inPct}%;background:#22d3ee"></i>
        </div>
        <div class="est-row"><span>总帧数 / 自回归段</span><b>${totalFrames} 帧 · ${totalChunks} 段</b></div>
        <div class="est-row"><span>原始视频时长 (16fps)</span><b>${rawSec.toFixed(1)} 秒</b></div>
        <div class="est-row"><span>后期 8× 穿梭时长</span><b>${fast8xSec.toFixed(1)} 秒</b></div>
        <div class="est-row"><span>推理模式</span><b>${dmd ? 'DMD 4步蒸馏加速' : `标准 ${steps} 步`}</b></div>
      `;
    }
  }

  [dmdToggle, stepsInput, guidanceInput, shiftInput, upwardInput, groundToggle].forEach((el) => {
    el?.addEventListener('change', updateEstimate);
    el?.addEventListener('input', updateEstimate);
  });

  async function submitWorld() {
    if (!worldSource) {
      const g = await pickFromGallery({ kind: 'image', title: '选择一张图片生成 3D 世界' });
      if (!g) {
        toast('请先拖入或从作品库选择一张起始图片', 'warn');
        return;
      }
      dz?.set(srcFromGallery(g));
    }
    if (!S.connected) {
      toast('请先在左侧启动并连接云端 GPU', 'warn');
      return;
    }

    const scene = (sceneEl?.value || '').trim();
    const manualCap = capEditToggle?.checked ? (capTextarea?.value || '').trim() : '';
    const dmd = !!dmdToggle?.checked;
    const steps = clamp(Number(stepsInput?.value) || 50, 1, 100);
    const guidance = Number(guidanceInput?.value ?? 5.0);
    const shift = Number(shiftInput?.value ?? 5.0);
    const seed = Number(seedInput?.value ?? 1);
    const upward = Number(upwardInput?.value ?? 0.15);
    const ground = !!groundToggle?.checked;

    await withBusy(runBtn, async () => {
      try {
        const imagePath = await resolveRemote(worldSource);
        const params = {
          image_path: imagePath,
          scene: scene || 'a cinematic 3D world with deep perspective',
          caption: manualCap || undefined,
          mode: st.mode,
          trajectory: st.trajectory,
          direction: st.direction,
          strength: st.strength,
          frames: st.frames,
          zoom_in_frames: st.zoom_in_frames,
          zoom_in_strength: st.zoom_in_strength,
          zoom_out_frames: st.zoom_out_frames,
          zoom_out_strength: st.zoom_out_strength,
          dmd,
          steps,
          guidance,
          shift,
          seed,
          ground_align: ground,
          upward_ratio: upward,
        };
        await remote('/jobs', {
          body: { model_id: 'lyra-2', task: 'lyra', params },
          errTitle: '提交 3D 世界任务失败',
        });
        toast('已提交 Lyra 2.0 3D 世界生成任务', 'success');
        emit('poll:fast');
        refreshAll();
      } catch {}
    });
  }

  runBtn?.addEventListener('click', submitWorld);

  function renderResults() {
    renderTaskResults(resultsEl, ['lyra'], {
      emptyIcon: 'cube',
      emptyTitle: '还没有 3D 世界记录',
      emptySub: '上传一张纵深感强的场景图（或从生图结果一键送入），即可生成相机漫游视频',
    });
  }

  on('presets', () => {
    renderSceneChips();
    renderModes();
    renderParams();
    updateCaptionPreview();
    updateEstimate();
  });
  on('state', updateEstimate);
  on('metrics', updateEstimate);
  on('models', updateEstimate);
  on('jobs', renderResults);
  on('gallery', renderResults);
  on('run:world', submitWorld);

  renderSceneChips();
  renderModes();
  renderParams();
  updateCaptionPreview();
  updateEstimate();
  renderResults();
}

/* =========================================================
   PANEL 4: POST-PROCESSING (LOCAL MAC FFMPEG / RIFE)
   ========================================================= */
function initPostPanel({ refreshGallery, refreshAll }) {
  const pickBtn = $('#postPick');
  const playerWrap = $('#postPlayer');
  const srcMetaEl = $('#postSrcMeta');
  const speedSeg = $('#postSpeed');
  const interpSeg = $('#postInterp');
  const trimStartIn = $('#postTrimStart');
  const setStartBtn = $('#postSetStart');
  const trimEndIn = $('#postTrimEnd');
  const setEndBtn = $('#postSetEnd');
  const scaleSeg = $('#postScale');
  const holdWrap = $('#postHold');
  const holdPickBtn = $('#postHoldPick');
  const estEl = $('#postEst');
  const runBtn = $('#postRun');
  const resultsEl = $('#postResults');

  let srcGallery = null;
  let videoEl = null;
  let videoDur = 0;
  let holdGallery = null;

  const opts = {
    speed: 8,
    interp: 2,
    scale: '1080p',
  };

  function syncSeg(segEl, val) {
    if (!segEl) return;
    $$('button', segEl).forEach((b) => b.classList.toggle('on', b.dataset.v === String(val)));
  }

  $$('#postSpeed button').forEach((b) => {
    b.addEventListener('click', () => {
      opts.speed = Number(b.dataset.v) || 1;
      syncSeg(speedSeg, opts.speed);
      if (videoEl) videoEl.playbackRate = clamp(opts.speed, 0.25, 4);
      updatePostEst();
    });
  });

  $$('#postInterp button').forEach((b) => {
    b.addEventListener('click', () => {
      opts.interp = Number(b.dataset.v) || 1;
      syncSeg(interpSeg, opts.interp);
      updatePostEst();
    });
  });

  $$('#postScale button').forEach((b) => {
    b.addEventListener('click', () => {
      opts.scale = b.dataset.v || '1080p';
      syncSeg(scaleSeg, opts.scale);
      updatePostEst();
    });
  });

  function setSourceVideo(g) {
    srcGallery = g || null;
    videoDur = 0;
    if (!playerWrap) return;
    playerWrap.innerHTML = '';
    if (!srcGallery) {
      const empty = h('div', {
        class: 'empty',
        onclick: pickVideo,
        html: `${icon('film')}<b>选择一个视频开始后期</b><span>加速、补帧、裁剪、导出 1080p</span>`,
      });
      playerWrap.append(empty);
      if (srcMetaEl) srcMetaEl.innerHTML = '';
      updatePostEst();
      return;
    }

    videoEl = h('video', {
      src: srcGallery.url,
      controls: true,
      loop: true,
      playsinline: true,
    });
    videoEl.addEventListener('loadedmetadata', () => {
      videoDur = videoEl.duration || 0;
      if (trimEndIn && !trimEndIn.value) {
        trimEndIn.placeholder = videoDur ? videoDur.toFixed(1) : '结尾';
      }
      if (srcMetaEl) {
        srcMetaEl.innerHTML = `
          <span>文件 <b>${esc(srcGallery.name)}</b></span>
          <span>分辨率 <b>${videoEl.videoWidth}×${videoEl.videoHeight}</b></span>
          <span>原始时长 <b>${videoDur.toFixed(2)}s</b></span>
        `;
      }
      updatePostEst();
    });
    playerWrap.append(videoEl);
    if (srcMetaEl) {
      srcMetaEl.innerHTML = `<span>文件 <b>${esc(srcGallery.name)}</b></span>`;
    }
    updatePostEst();
  }

  async function pickVideo() {
    const g = await pickFromGallery({ kind: 'video', title: '选择要处理的源视频' });
    if (g) setSourceVideo(g);
  }

  pickBtn?.addEventListener('click', pickVideo);
  playerWrap?.querySelector('.empty')?.addEventListener('click', pickVideo);
  on('use:post', (g) => setSourceVideo(g));

  setStartBtn?.addEventListener('click', () => {
    if (!videoEl || !trimStartIn) return;
    trimStartIn.value = videoEl.currentTime.toFixed(1);
    updatePostEst();
  });

  setEndBtn?.addEventListener('click', () => {
    if (!videoEl || !trimEndIn) return;
    trimEndIn.value = videoEl.currentTime.toFixed(1);
    updatePostEst();
  });

  [trimStartIn, trimEndIn].forEach((el) => el?.addEventListener('input', updatePostEst));

  function renderHold() {
    if (!holdWrap) return;
    holdWrap.innerHTML = '';
    if (holdGallery) {
      holdWrap.append(
        h('div', { class: 'hold-prev' },
          h('img', { src: holdGallery.thumb || holdGallery.url, alt: '' }),
          h('span', { title: holdGallery.name }, holdGallery.name),
          h('button', {
            class: 'icon-btn sm',
            type: 'button',
            title: '移除定格图',
            html: icon('x'),
            onclick: () => {
              holdGallery = null;
              renderHold();
              updatePostEst();
            },
          })),
      );
    }
    holdWrap.append(
      h('button', {
        class: 'btn btn-sm',
        type: 'button',
        html: icon('plus') + `<span>${holdGallery ? '更换图片' : '选择图片'}</span>`,
        onclick: async () => {
          const g = await pickFromGallery({ kind: 'image', title: '选择结尾定格图片' });
          if (g) {
            holdGallery = g;
            renderHold();
            updatePostEst();
          }
        },
      }),
    );
  }

  function updatePostEst() {
    if (!estEl) return;
    const t0 = Math.max(0, Number(trimStartIn?.value) || 0);
    const rawEnd = trimEndIn?.value ? Number(trimEndIn.value) : videoDur;
    const segDur = rawEnd > t0 ? rawEnd - t0 : videoDur;
    const outDur = segDur > 0 ? (segDur / opts.speed + (holdGallery ? 2.4 : 0)).toFixed(1) : '—';
    const scaleLabel = opts.scale === 'original' ? '原始分辨率' : opts.scale;
    const rifeOk = S.local?.local?.rife;
    const rifeNote = opts.interp > 1
      ? (rifeOk ? `RIFE 补帧 <b>${opts.interp}×</b>` : `RIFE 补帧 <b>${opts.interp}×</b>（首次自动下载 RIFE）`)
      : '不补帧';

    estEl.innerHTML = `
      <div>管线：播放加速 <b>${opts.speed}×</b> · ${rifeNote} · 输出 <b>${scaleLabel}</b>${holdGallery ? ' · <b>含尾帧定格</b>' : ''}</div>
      <div>${srcGallery ? `预计输出时长：<b>~${outDur} 秒</b>（Mac 本地处理，不消耗 Colab CU）` : '请先在左侧选择一个源视频'}</div>
    `;
  }

  async function submitPost() {
    if (!srcGallery) {
      await pickVideo();
      if (!srcGallery) return;
    }
    const trimStart = Math.max(0, Number(trimStartIn?.value) || 0);
    const trimEndRaw = trimEndIn?.value ? Number(trimEndIn.value) : null;
    if (trimEndRaw != null && trimEndRaw <= trimStart) {
      toast('裁剪结尾时间必须大于开始时间', 'warn');
      return;
    }
    const apiScale = opts.scale === 'original' ? 'orig' : opts.scale;

    await withBusy(runBtn, async () => {
      try {
        await local('/post', {
          body: {
            gallery_id: srcGallery.id,
            speed: opts.speed,
            interp: opts.interp,
            trim_start: trimStart,
            trim_end: trimEndRaw,
            scale: apiScale,
            end_hold_image: holdGallery ? holdGallery.id : null,
          },
          errTitle: '启动后期处理失败',
        });
        toast('已启动本地后期处理任务', 'success');
        emit('poll:fast');
        refreshAll();
      } catch {}
    });
  }

  runBtn?.addEventListener('click', submitPost);

  function renderPostResults() {
    if (!resultsEl) return;
    const postTasks = S.tasks.filter((t) => t.type === 'post');
    const postGallery = S.gallery.filter((g) => g.meta && g.meta.post);

    if (!postTasks.length && !postGallery.length) {
      resultsEl.innerHTML = '';
      resultsEl.append(
        h('div', {
          class: 'empty',
          html: `${icon('wand')}<b>还没有后期处理结果</b><span>将 Lyra 原始漫游视频进行 8× 加速 + RIFE 2× 补帧，即可获得丝滑的演示级成片</span>`,
        }),
      );
      return;
    }

    const blocks = [];
    const activeTasks = postTasks.filter((t) => t.status === 'running' || t.status === 'error');
    if (activeTasks.length) {
      const tilesWrap = h('div', { class: 'tiles video' });
      activeTasks.forEach((t) => {
        if (t.status === 'running') {
          const pct = Math.round((t.progress || 0) * 100);
          tilesWrap.append(
            h('div', { class: 'tile pending shimmer', style: { '--ar': '16 / 9' } },
              h('div', { class: 'pend' },
                h('b', {}, `${pct}%`),
                h('div', { class: 'progress' }, h('i', { style: { width: `${pct}%` } })),
                h('span', {}, t.log_tail || t.title))),
          );
        } else {
          tilesWrap.append(
            h('div', { class: 'tile failed', style: { '--ar': '16 / 9' } },
              h('div', {},
                h('div', { html: icon('alert') }),
                h('b', {}, `${t.title} 失败`),
                t.error ? h('div', { class: 'muted', style: { marginTop: '4px', fontSize: '11px' } }, t.error) : null)),
          );
        }
      });
      blocks.push(h('div', { class: 'job-block' }, tilesWrap));
    }

    if (postGallery.length) {
      const items = postGallery.map((g) => A.mediaFromGallery(g));
      const tilesWrap = h('div', { class: 'tiles video' });
      items.forEach((it, idx) => {
        tilesWrap.append(renderMediaTile(it, items, idx, { ar: '16 / 9', showDelete: true }));
      });
      blocks.push(h('div', { class: 'job-block' }, tilesWrap));
    }

    resultsEl.innerHTML = '';
    resultsEl.append(...blocks);
  }

  on('tasks', renderPostResults);
  on('gallery', () => {
    renderPostResults();
    // Auto-select latest video if none selected yet
    if (!srcGallery) {
      const firstVid = S.gallery.find((g) => g.kind === 'video');
      if (firstVid) setSourceVideo(firstVid);
    }
  });
  on('state', updatePostEst);
  on('run:post', submitPost);

  syncSeg(speedSeg, opts.speed);
  syncSeg(interpSeg, opts.interp);
  syncSeg(scaleSeg, opts.scale);
  renderHold();
  updatePostEst();
  renderPostResults();
}

/* =========================================================
   PANEL 5: GALLERY
   ========================================================= */
function initGalleryPanel({ refreshGallery }) {
  const sortSel = $('#galSort');
  const searchIn = $('#galSearch');
  const statEl = $('#galStat');
  const refreshBtn = $('#galRefresh');
  const abBtn = $('#galABBtn');
  const cinemaBtn = $('#btnCinemaShowcase');
  const gridEl = $('#galGrid');
  const tabCountEl = $('#galleryCount');

  let filter = 'all';
  let sortBy = 'newest';
  let query = '';
  let currentRenderedItems = [];

  const filterLabels = {
    all: '全部',
    world3d: '3D 世界穿梭',
    enhanced: '1080p60 增强',
    image2k: '2K 场景原画',
    video: '视频',
    image: '图片',
    fav: '★ 收藏',
  };

  $$('#galFilter button').forEach((b) => {
    b.addEventListener('click', () => {
      filter = b.dataset.v || 'all';
      $$('#galFilter button').forEach((x) => x.classList.toggle('on', x.dataset.v === filter));
      renderGallery();
    });
  });

  sortSel?.addEventListener('change', () => {
    sortBy = sortSel.value || 'newest';
    renderGallery();
  });

  searchIn?.addEventListener('input', () => {
    query = (searchIn.value || '').trim().toLowerCase();
    renderGallery();
  });

  refreshBtn?.addEventListener('click', (e) => {
    withBusy(e.currentTarget, () => refreshGallery(true));
  });

  abBtn?.addEventListener('click', () => {
    const firstEnh = currentRenderedItems.find((it) => it.kind === 'video' && (it.category === 'enhanced' || it.raw_media_url || it.enhanced_media_url))
      || currentRenderedItems.find((it) => it.kind === 'video')
      || null;
    openABCompare(firstEnh);
  });

  cinemaBtn?.addEventListener('click', () => {
    const vids = currentRenderedItems.filter((it) => it.kind === 'video');
    openCinemaShowcase(vids.length ? vids : null, 0);
  });

  function updateFilterCounts() {
    $$('#galFilter button').forEach((btn) => {
      const f = btn.dataset.v || 'all';
      const baseLabel = filterLabels[f] || btn.textContent;
      const n = S.gallery.filter((g) => A.matchesGalleryFilter(g, f)).length;
      btn.innerHTML = `${esc(baseLabel)}<em class="seg-count">${n}</em>`;
    });
  }

  function sortItems(list) {
    return [...list].sort((a, b) => {
      if (sortBy === 'fav_first') {
        const fa = A.isGalleryFavorite(a) ? 1 : 0;
        const fb = A.isGalleryFavorite(b) ? 1 : 0;
        if (fb !== fa) return fb - fa;
      }
      if (sortBy === 'resolution') {
        const pa = (Number(a.width ?? a.info?.width ?? a.meta?.width ?? 0) * Number(a.height ?? a.info?.height ?? a.meta?.height ?? 0));
        const pb = (Number(b.width ?? b.info?.width ?? b.meta?.width ?? 0) * Number(b.height ?? b.info?.height ?? b.meta?.height ?? 0));
        if (pb !== pa) return pb - pa;
      }
      if (sortBy === 'duration') {
        const da = Number(a.duration ?? a.info?.duration ?? a.meta?.duration ?? 0);
        const db = Number(b.duration ?? b.info?.duration ?? b.meta?.duration ?? 0);
        if (db !== da) return db - da;
      }
      return (b.created || 0) - (a.created || 0);
    });
  }

  function renderGallery() {
    if (tabCountEl) {
      tabCountEl.textContent = S.gallery.length ? String(S.gallery.length) : '';
    }
    updateFilterCounts();
    if (!gridEl) return;

    const filtered = sortItems(
      S.gallery.filter((g) => {
        if (!A.matchesGalleryFilter(g, filter)) return false;
        if (!query) return true;
        const m = g.meta || {};
        const tags = Array.isArray(g.tags) ? g.tags.join(' ') : '';
        const hay = [g.name, g.title, m.title, m.prompt, m.scene, m.caption, m.model_id, m.task, tags]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return hay.includes(query);
      }),
    );

    if (statEl) {
      const totalVids = S.gallery.filter((g) => (g.kind || g.type) === 'video').length;
      const totalImgs = S.gallery.length - totalVids;
      const totalEnh = S.gallery.filter((g) => A.matchesGalleryFilter(g, 'enhanced')).length;
      const totalBytes = S.gallery.reduce((acc, g) => acc + (Number(g.size ?? g.info?.size ?? 0) || 0), 0);
      const sizeTxt = totalBytes > 1024 * 1024 * 1024
        ? `${(totalBytes / (1024 ** 3)).toFixed(2)} GB`
        : totalBytes > 0
          ? `${Math.round(totalBytes / (1024 * 1024))} MB`
          : '';
      if (query || filter !== 'all') {
        statEl.textContent = `显示 ${filtered.length} / ${S.gallery.length} 件 · ${totalEnh} 部 1080p60${sizeTxt ? ` · ${sizeTxt}` : ''}`;
      } else {
        statEl.textContent = `共 ${S.gallery.length} 件 (${totalVids} 视频 / ${totalImgs} 原画 · ${totalEnh} 部 1080p60${sizeTxt ? ` · ${sizeTxt}` : ''})`;
      }
    }

    if (!filtered.length) {
      currentRenderedItems = [];
      gridEl.innerHTML = '';
      gridEl.append(
        h('div', {
          class: 'empty',
          style: { gridColumn: '1 / -1' },
          html: `${icon('grid')}<b>${query || filter !== 'all' ? '没有找到匹配当前筛选的作品' : '作品库还是空的'}</b><span>生成的 2K 原画、Lyra 3D 世界穿梭与 1080p60 RIFE 增强成片会自动归档在此</span>`,
        }),
      );
      return;
    }

    const items = filtered.map((g) => A.mediaFromGallery(g));
    currentRenderedItems = items;
    gridEl.innerHTML = '';
    const frag = document.createDocumentFragment();
    items.forEach((it, idx) => {
      frag.append(renderMediaTile(it, items, idx, { ar: '16 / 9', showDelete: true, showCaption: true }));
    });
    gridEl.append(frag);
  }

  $$('#galFilter button').forEach((x) => x.classList.toggle('on', x.dataset.v === filter));
  on('gallery', renderGallery);
  on('gallery:fav', () => {
    updateFilterCounts();
    if (filter === 'fav' || sortBy === 'fav_first') renderGallery();
  });
  renderGallery();
}
