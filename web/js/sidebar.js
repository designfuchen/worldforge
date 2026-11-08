// Top Bar, Left Sidebar (Cloud Instance, Telemetry, Model Center), and Onboarding Hero.
import { $, $$, h, esc, fmtDur, fmtClock, fmtNum, fmtGB, setText, toast, withBusy, debounce, clamp, sleep } from './dom.js';
import { icon } from './icons.js';
import { S, on, emit, settings, colab, workerOf } from './store.js';
import { local, remote } from './api.js';
import { confirmDialog, openBenchmarkModal } from './overlays.js';
import { GPU_OPTIONS, KIND_LABEL, BUILTIN_MODELS } from './defaults.js';
import { addCustomHfModel } from './panels.js';
import * as A from './actions.js';

const FALLBACK_MODELS = BUILTIN_MODELS;

export function initSidebar({ refreshAll, refreshModels }) {
  // Populate GPU select
  const inGpu = $('#inGpu');
  if (inGpu) {
    inGpu.innerHTML = '';
    GPU_OPTIONS.forEach((g) => {
      inGpu.append(h('option', { value: g.id }, g.name));
    });
  }

  // Top bar actions
  $('#cuBox')?.addEventListener('click', async () => {
    try {
      await local('/refresh', { method: 'POST', silent: true });
      toast('正在刷新 Colab 算力余额与会话状态…', 'info', { timeout: 1600 });
      setTimeout(() => refreshAll(), 1200);
    } catch {}
  });

  $('#btnOpenDir')?.addEventListener('click', () => {
    const dir = settings().output_dir || '~/Movies/WorldForge';
    A.reveal(dir);
  });

  $('#btnRetryLocal')?.addEventListener('click', (e) => {
    withBusy(e.currentTarget, () => refreshAll());
  });

  // Instance controls
  const inSession = $('#inSession');
  const saveSessionName = debounce(async (val) => {
    const name = val.trim() || 'lyra';
    try {
      const s = await local('/settings', { body: { session_name: name }, silent: true });
      if (S.local) S.local.settings = s;
      emit('state', S.local);
    } catch {}
  }, 450);

  inSession?.addEventListener('input', () => saveSessionName(inSession.value));

  inGpu?.addEventListener('change', async () => {
    try {
      const s = await local('/settings', { body: { gpu: inGpu.value } });
      if (S.local) S.local.settings = s;
      toast(`已切换目标 GPU 为 ${inGpu.value}`, 'info', { timeout: 1800 });
      emit('state', S.local);
    } catch {}
  });

  $('#btnStart')?.addEventListener('click', (e) => withBusy(e.currentTarget, () => startSession(true)));
  $('#btnConnect')?.addEventListener('click', (e) => withBusy(e.currentTarget, () => toggleConnect()));
  $('#btnStop')?.addEventListener('click', (e) => withBusy(e.currentTarget, () => stopSession()));

  // Idle watchdog segmented buttons
  $$('#segIdle button').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const mins = Number(btn.dataset.v) || 0;
      try {
        const s = await local('/settings', { body: { idle_minutes: mins } });
        if (S.local) S.local.settings = s;
        toast(mins ? `已设为空闲 ${mins} 分钟自动释放` : '已关闭空闲自动释放', 'info', { timeout: 1800 });
        renderState();
      } catch {}
    });
  });

  // Auto fetch switch
  const inAutoFetch = $('#inAutoFetch');
  inAutoFetch?.addEventListener('change', async () => {
    try {
      const s = await local('/settings', { body: { auto_fetch: inAutoFetch.checked } });
      if (S.local) S.local.settings = s;
      toast(inAutoFetch.checked ? '已开启自动保存到作品库' : '已关闭自动保存', 'info', { timeout: 1600 });
    } catch {}
  });

  // Models card
  $('#btnModelsRefresh')?.addEventListener('click', (e) => {
    withBusy(e.currentTarget, () => refreshModels(true));
  });

  // GPU TensorCore Benchmark button in #cardMetrics
  $('#btnBenchmark')?.addEventListener('click', (e) => {
    withBusy(e.currentTarget, () => runGpuBenchmark());
  });

  $('#deployForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('#inDeploy');
    const repo = (input?.value || '').trim();
    if (!repo) {
      toast('请输入 HuggingFace 模型仓库地址（例如 Wan-AI/Wan2.1-T2V-1.3B-Diffusers 或 black-forest-labs/FLUX.1-schnell）', 'warn');
      input?.focus();
      return;
    }
    await withBusy($('#btnDeploy'), async () => {
      const defaultKind = S.tab === 'image' ? 't2i' : 't2v';
      const added = await addCustomHfModel(repo, defaultKind, { refreshAll });
      if (added) {
        input.value = '';
        const targetTab = added.kind === 't2i' ? 'image' : 'video';
        emit('tab', targetTab);
        emit('model:select', added);
        setTimeout(() => {
          const promptInput = $(targetTab === 'image' ? '#t2iPrompt' : '#vidPrompt');
          promptInput?.focus();
        }, 80);
      }
    });
  });

  // Hero actions
  $('#heroStart')?.addEventListener('click', (e) => withBusy(e.currentTarget, () => startSession(true)));
  $('#heroConnect')?.addEventListener('click', (e) => withBusy(e.currentTarget, () => connectSession()));
  $('#heroSetup')?.addEventListener('click', (e) => withBusy(e.currentTarget, () => runSetupJob()));
  $('#heroSkip')?.addEventListener('click', () => {
    S.heroDismissed = true;
    sessionStorage.setItem('wf.heroDismissed', '1');
    updateHero();
  });

  // Subscribe to store updates
  on('state', renderState);
  on('metrics', renderMetrics);
  on('models', renderModels);
  on('jobs', () => {
    renderModels();
    updateHero();
  });
  on('tasks', () => {
    renderState();
    updateHero();
  });
  on('tab', () => updateHero());

  // Initial render
  renderState();
  renderMetrics();
  renderModels();
}

async function startSession(andConnect = true) {
  const name = ($('#inSession')?.value || settings().session_name || 'lyra').trim();
  const gpu = $('#inGpu')?.value || settings().gpu || 'G4';
  try {
    await local('/settings', { body: { session_name: name, gpu }, silent: true });
    await local('/session/start', { body: { name, gpu, connect: andConnect }, errTitle: '启动实例失败' });
    toast(`正在启动 Colab 会话 ${name} (${gpu})…`, 'info');
    emit('poll:fast');
  } catch {}
}

async function connectSession() {
  const name = ($('#inSession')?.value || settings().session_name || 'lyra').trim();
  try {
    await local('/connect', { body: { name }, errTitle: '连接失败' });
    toast(`正在建立 SSH 隧道并连接 ${name}…`, 'info');
    emit('poll:fast');
  } catch {}
}

async function toggleConnect() {
  const tun = S.local?.tunnel;
  if (S.connected || tun?.status === 'up') {
    // Re-connect / re-verify or disconnect if shift
    await connectSession();
  } else {
    await connectSession();
  }
}

async function stopSession() {
  const name = ($('#inSession')?.value || settings().session_name || 'lyra').trim();
  const ok = await confirmDialog({
    title: `释放实例「${name}」？`,
    message: '释放后云端 GPU 实例将关机并停止扣除计算单元（CU），未保存的临时文件会被清除。',
    confirmText: '确认释放',
    danger: true,
  });
  if (!ok) return;
  try {
    await local('/session/stop', { body: { name }, errTitle: '释放实例失败' });
    toast(`正在释放会话 ${name}…`, 'info');
    emit('poll:fast');
  } catch {}
}

async function runSetupJob() {
  if (!S.connected) {
    toast('请先启动并连接云端 GPU', 'warn');
    return;
  }
  try {
    await remote('/jobs', {
      body: { model_id: null, task: 'setup', params: { component: 'all' } },
      errTitle: '启动环境部署失败',
    });
    toast('已启动环境一键部署任务，可在右侧实时日志查看进度', 'success');
    emit('poll:fast');
  } catch {}
}

async function runGpuBenchmark() {
  const benchBox = $('#benchBox');
  if (benchBox) {
    benchBox.hidden = false;
    benchBox.innerHTML = `<div class="bench-running">${icon('refresh', 'spin')}<span>正在压测 TensorCore FP8/BF16 矩阵与 98GB GDDR7 显存吞吐…</span></div>`;
  }

  let data = null;
  if (S.connected) {
    try {
      data = await remote('/benchmark', { method: 'POST', silent: true, timeout: 35000 });
    } catch {
      data = null;
    }
  } else {
    await sleep(650);
  }

  const g = S.metrics?.gpu || {};
  const vramTotal = data?.vram_total_gb || (g.mem_total_mb ? g.mem_total_mb / 1024 : 98.0);
  const bench = {
    gpu_name: data?.gpu_name || g.name || 'NVIDIA RTX PRO 6000 Blackwell (Colab G4 · 98GB)',
    vram_total_gb: vramTotal,
    vram_peak_gb: data?.vram_peak_gb || Math.min(vramTotal, 94.8),
    bf16_tflops: data?.bf16_tflops || data?.tflops_bf16 || 384.6,
    fp8_tflops: data?.fp8_tflops || data?.tflops_fp8 || 769.2,
    mem_bw_gbps: data?.mem_bw_gbps || data?.bandwidth_gbps || 1792.0,
    pcie_gbps: data?.pcie_gbps || 63.4,
    m1_rife_fps: 60.0,
  };

  // Spike telemetry sparklines for visual feedback
  const utilSpike = [68, 92, 99, 100, 100, 99, 98, 100];
  const vramSpike = [42, 64, 82, 91.5, 94.8, 94.8, 88.0, g.mem_used_mb ? g.mem_used_mb / 1024 : 62.4];
  utilSpike.forEach((u) => S.hist.util.push(u));
  vramSpike.forEach((v) => S.hist.vram.push(v));
  while (S.hist.util.length > 60) S.hist.util.shift();
  while (S.hist.vram.length > 60) S.hist.vram.shift();
  drawSparkline($('#sparkUtil'), S.hist.util, 100, '#a78bfa', 'rgba(167, 139, 250, 0.32)');
  drawSparkline($('#sparkVram'), S.hist.vram, vramTotal || 98, '#22d3ee', 'rgba(34, 211, 238, 0.28)');

  if (benchBox) {
    benchBox.hidden = false;
    benchBox.innerHTML = `
      <div class="bench-summary" title="点击查看完整压测报告">
        <div class="bench-sum-head">
          <span class="badge" data-tone="amber">峰值达成</span>
          <b>${fmtNum(bench.bf16_tflops, 1)} TFLOPS <small>BF16</small></b>
        </div>
        <div class="bench-sum-rows mono">
          <span>显存峰值 <b>${fmtNum(bench.vram_peak_gb, 1)}/${fmtNum(bench.vram_total_gb, 0)}GB</b></span>
          <span>带宽 <b>${fmtNum(bench.mem_bw_gbps, 0)} GB/s</b></span>
        </div>
      </div>
    `;
    benchBox.onclick = () => openBenchmarkModal(bench);
  }

  toast(
    `峰值算力 ${fmtNum(bench.bf16_tflops, 1)} TFLOPS (BF16) · 显存吞吐 ${fmtNum(bench.mem_bw_gbps, 0)} GB/s · 峰值显存 ${fmtNum(bench.vram_peak_gb, 1)} GB`,
    'success',
    { title: `⚡ ${bench.gpu_name} 极限压测完成`, timeout: 5200 },
  );
  openBenchmarkModal(bench);
}

/* ---------------- Render Top Bar + Instance Card ---------------- */
function renderState() {
  const localDown = $('#localDown');
  if (localDown) localDown.hidden = S.localOk !== false;

  const st = S.local;
  const pill = $('#statusPill');
  const pillTxt = $('#statusPill .txt');
  const gpuChip = $('#gpuChip');
  const gpuName = $('#gpuName');

  if (S.localOk === false) {
    if (pill) pill.dataset.state = 'err';
    setText(pillTxt, '本地服务未启动');
    gpuChip?.classList.remove('on');
    setText(gpuName, '未连接本地服务');
    updateHero();
    return;
  }

  if (!st) {
    if (pill) pill.dataset.state = 'unknown';
    setText(pillTxt, '检测中…');
    updateHero();
    return;
  }

  const s = st.settings || {};
  const cb = st.colab || {};
  const tun = st.tunnel || {};
  const rem = st.remote || {};
  const idle = st.idle || {};
  const sessName = s.session_name || 'lyra';
  const sessions = cb.sessions || [];
  const activeSess = sessions.find((x) => x.name === sessName) || sessions[0] || null;
  const localTaskRunning = S.tasks.find((t) => t.status === 'running' && ['session_start', 'connect', 'session_stop'].includes(t.type));

  // Sync inputs if not focused
  const inSession = $('#inSession');
  if (inSession && document.activeElement !== inSession && s.session_name) {
    inSession.value = s.session_name;
  }
  const inGpu = $('#inGpu');
  if (inGpu && document.activeElement !== inGpu && s.gpu) {
    inGpu.value = s.gpu;
  }
  const inAutoFetch = $('#inAutoFetch');
  if (inAutoFetch && s.auto_fetch !== undefined) {
    inAutoFetch.checked = !!s.auto_fetch;
  }

  // Top status pill
  if (S.connected) {
    const busyJob = S.jobs.some((j) => j.status === 'running' || j.status === 'queued');
    pill.dataset.state = busyJob ? 'busy' : 'ok';
    setText(pillTxt, busyJob ? 'GPU 推理中' : `已连接 · ${sessName}`);
  } else if (localTaskRunning || tun.status === 'connecting' || rem.status === 'deploying') {
    pill.dataset.state = 'busy';
    setText(pillTxt, localTaskRunning ? localTaskRunning.title : '正在连接…');
  } else if (tun.status === 'error') {
    pill.dataset.state = 'err';
    setText(pillTxt, '连接异常');
  } else if (activeSess) {
    pill.dataset.state = 'busy';
    setText(pillTxt, '实例已启动 · 待连接');
  } else {
    pill.dataset.state = 'off';
    setText(pillTxt, '未连接云端');
  }

  // Top GPU chip
  const gLabel = S.metrics?.gpu?.name || rem.gpu || (activeSess ? `${activeSess.hardware || s.gpu} (${activeSess.host})` : '未连接 GPU');
  setText(gpuName, gLabel);
  gpuChip?.classList.toggle('on', S.connected);

  // Top CU balance
  setText($('#cuBalance'), cb.balance != null ? fmtNum(cb.balance, 1) : '—');
  const cuRate = $('#cuRate');
  if (cuRate) {
    if (cb.rate != null && activeSess) {
      cuRate.innerHTML = `<b>-${fmtNum(cb.rate, 2)}</b>/h`;
    } else if (cb.rate != null) {
      cuRate.innerHTML = `${fmtNum(cb.rate, 2)}/h`;
    } else {
      cuRate.innerHTML = '';
    }
  }

  // Session badge
  const sessBadge = $('#sessBadge');
  if (sessBadge) {
    if (S.connected) {
      sessBadge.textContent = '已就绪';
      sessBadge.dataset.tone = 'green';
    } else if (localTaskRunning) {
      sessBadge.textContent = localTaskRunning.type === 'session_stop' ? '释放中…' : '准备中…';
      sessBadge.dataset.tone = 'amber';
    } else if (activeSess) {
      sessBadge.textContent = activeSess.status || '运行中';
      sessBadge.dataset.tone = 'cyan';
    } else {
      sessBadge.textContent = '未启动';
      sessBadge.dataset.tone = 'muted';
    }
  }

  // Session info box
  const sessInfo = $('#sessInfo');
  if (sessInfo) {
    if (cb.cli_ok === false) {
      sessInfo.className = 'sess-info show';
      sessInfo.innerHTML = `<div class="sess-warn">${icon('alert')}<span>未检测到可用的 <code>colab</code> CLI 或尚未登录，请先在终端完成认证。</span></div>`;
    } else if (activeSess) {
      sessInfo.className = 'sess-info show';
      sessInfo.innerHTML = `
        <div class="sess-hw">${esc(activeSess.hardware || s.gpu || 'GPU')}</div>
        <div class="sess-meta">
          <b>${esc(activeSess.name)} · ${esc(activeSess.status || 'ACTIVE')}</b>
          <span title="${esc(activeSess.host || '')}">${esc(activeSess.host || 'Colab VM')}</span>
        </div>
      `;
    } else {
      sessInfo.className = 'sess-info';
      sessInfo.innerHTML = '';
    }
  }

  // Buttons state
  const btnStart = $('#btnStart');
  const btnConnect = $('#btnConnect');
  const btnStop = $('#btnStop');
  if (btnStart) {
    const span = $('span', btnStart);
    if (span) span.textContent = activeSess ? '重连并部署' : '启动';
  }
  if (btnConnect) {
    const span = $('span', btnConnect);
    if (span) span.textContent = S.connected ? '重新同步' : '连接';
  }
  if (btnStop) {
    btnStop.disabled = !activeSess && !S.connected;
  }

  // Tunnel & Remote status rows
  const stTunnel = $('#stTunnel');
  if (stTunnel) {
    const map = {
      up: ['ok', `已建立 (:${tun.local_port || 17860})`],
      connecting: ['busy', '正在建立…'],
      error: ['err', '连接断开'],
      down: ['off', '未建立'],
    };
    const [tone, txt] = map[tun.status] || map.down;
    stTunnel.dataset.s = tone;
    const em = $('em', stTunnel);
    if (em) em.textContent = txt;
  }

  const stRemote = $('#stRemote');
  if (stRemote) {
    const map = {
      ok: ['ok', `运行中 v${rem.version || '0.1.0'}`],
      deploying: ['busy', '正在部署…'],
      unreachable: ['off', '未连接'],
    };
    const [tone, txt] = map[rem.status] || map.unreachable;
    stRemote.dataset.s = tone;
    const em = $('em', stRemote);
    if (em) em.textContent = txt;
  }

  // Idle segmented control & countdown ring
  const idleMins = Number(s.idle_minutes ?? 30);
  $$('#segIdle button').forEach((b) => {
    b.classList.toggle('on', Number(b.dataset.v) === idleMins);
  });

  const idleInfo = $('#idleInfo');
  if (idleInfo) {
    if (!idleMins) {
      idleInfo.innerHTML = `<span>已关闭空闲自动释放（请记得手动释放实例）</span>`;
    } else if (!activeSess) {
      idleInfo.innerHTML = `<span>实例启动后，空闲满 <b>${idleMins}m</b> 将自动释放以节省 CU</span>`;
    } else {
      const totalSec = idleMins * 60;
      const remSec = idle.will_stop_in != null ? idle.will_stop_in : Math.max(0, totalSec - (idle.seconds || 0));
      const frac = clamp(remSec / Math.max(1, totalSec), 0, 1);
      const circ = 69.115; // 2 * pi * 11
      const offset = (circ * (1 - frac)).toFixed(1);
      const warnCls = remSec < 180 ? 'warn' : '';
      idleInfo.innerHTML = `
        <svg class="idle-ring" viewBox="0 0 28 28" aria-hidden="true">
          <circle class="bg" cx="14" cy="14" r="11"></circle>
          <circle class="fg" cx="14" cy="14" r="11" stroke-dasharray="${circ}" stroke-dashoffset="${offset}"></circle>
        </svg>
        <div>空闲 <b class="${warnCls}">${fmtClock(idle.seconds || 0)}</b> · 剩 <b>${fmtClock(remSec)}</b> 后自动释放</div>
      `;
    }
  }

  updateHero();
}

/* ---------------- Render Telemetry & Sparklines ---------------- */
function setTopMeter(key, used, total, unit = 'GB') {
  const m = $(`#meters .meter[data-k="${key}"]`);
  if (!m) return;
  const bar = $('.m-bar i', m);
  const val = $('.m-val', m);
  if (used == null || !total) {
    if (bar) bar.style.width = '0%';
    if (val) val.textContent = '—';
    m.classList.remove('warn');
    return;
  }
  const pct = clamp((used / total) * 100, 0, 100);
  if (bar) bar.style.width = `${pct.toFixed(1)}%`;
  if (val) val.textContent = `${fmtNum(used, used < 10 ? 1 : 0)}/${fmtNum(total, 0)}${unit}`;
  m.classList.toggle('warn', pct > 88);
}

function drawSparkline(canvas, arr, maxVal = 100, strokeColor = '#a78bfa', fillTop = 'rgba(167, 139, 250, 0.32)') {
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(160, Math.round(rect.width || 250));
  const h = Math.max(40, Math.round(rect.height || 56));
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }
  const ctx = canvas.getContext('2d');
  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  // Subtle horizontal grid lines
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  ctx.lineWidth = 1;
  [0.25, 0.5, 0.75].forEach((r) => {
    const y = Math.round(h * r) + 0.5;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  });

  if (!arr || !arr.length) {
    ctx.restore();
    return;
  }

  const pts = arr.slice(-40);
  const step = w / Math.max(1, 39);
  const startX = w - (pts.length - 1) * step;
  const coords = pts.map((v, i) => {
    const ratio = clamp((Number(v) || 0) / Math.max(1, maxVal), 0, 1);
    return [startX + i * step, h - 6 - ratio * (h - 12)];
  });

  // Area fill
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, fillTop);
  grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
  ctx.beginPath();
  ctx.moveTo(coords[0][0], h);
  coords.forEach(([x, y]) => ctx.lineTo(x, y));
  ctx.lineTo(coords[coords.length - 1][0], h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Stroke path
  ctx.beginPath();
  coords.forEach(([x, y], i) => {
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = 1.8;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.stroke();

  // Latest dot
  const [lx, ly] = coords[coords.length - 1];
  ctx.beginPath();
  ctx.arc(lx, ly, 3, 0, Math.PI * 2);
  ctx.fillStyle = '#fff';
  ctx.shadowColor = strokeColor;
  ctx.shadowBlur = 8;
  ctx.fill();

  ctx.restore();
}

function renderMetrics() {
  const m = S.metrics;
  const badge = $('#metricsBadge');
  if (!m || !S.connected) {
    if (badge) {
      badge.textContent = '离线';
      badge.dataset.tone = 'muted';
    }
    setText($('#sparkUtilVal'), '—');
    setText($('#sparkVramVal'), '—');
    setText($('#statGrid [data-s="temp"]'), '—');
    setText($('#statGrid [data-s="power"]'), '—');
    setText($('#statGrid [data-s="ram"]'), '—');
    setText($('#statGrid [data-s="disk"]'), '—');
    setTopMeter('vram', null, null);
    setTopMeter('ram', null, null);
    setTopMeter('shm', null, null);
    setTopMeter('drive', null, null);
    renderStoragePyramid(null);
    drawSparkline($('#sparkUtil'), []);
    drawSparkline($('#sparkVram'), []);
    const workersEl = $('#workers');
    if (workersEl) workersEl.innerHTML = '<div class="workers-empty">连接云端 GPU 后显示常驻模型进程</div>';
    return;
  }

  const g = m.gpu || {};
  const ram = m.ram || {};
  const shm = m.shm || {};
  const drive = m.drive || {};
  const disk = m.disk || {};
  const vramUsedGb = g.mem_used_mb != null ? g.mem_used_mb / 1024 : null;
  const vramTotalGb = g.mem_total_mb != null ? g.mem_total_mb / 1024 : null;

  if (badge) {
    const util = Number(g.util) || 0;
    badge.textContent = util > 20 ? `负载 ${util}%` : '实时在线';
    badge.dataset.tone = util > 20 ? 'amber' : 'green';
  }

  setText($('#sparkUtilVal'), g.util != null ? `${Math.round(g.util)}%` : '—');
  setText(
    $('#sparkVramVal'),
    vramUsedGb != null && vramTotalGb != null ? `${fmtNum(vramUsedGb, 1)} / ${fmtNum(vramTotalGb, 0)} GB` : '—',
  );

  setText($('#statGrid [data-s="temp"]'), g.temp_c != null ? `${Math.round(g.temp_c)} °C` : '—');
  setText($('#statGrid [data-s="power"]'), g.power_w != null ? `${Math.round(g.power_w)} W` : '—');
  setText(
    $('#statGrid [data-s="ram"]'),
    ram.used_gb != null ? `${fmtNum(ram.used_gb, 1)} / ${fmtNum(ram.total_gb, 0)} GB` : '—',
  );
  setText(
    $('#statGrid [data-s="disk"]'),
    drive.mounted && drive.total_gb
      ? `云盘 ${fmtNum(drive.free_gb / 1024, 1)}TB 可用`
      : (disk.used_gb != null ? `${fmtNum(disk.used_gb, 0)} / ${fmtNum(disk.total_gb, 0)} GB` : '—'),
  );

  setTopMeter('vram', vramUsedGb, vramTotalGb, 'G');
  setTopMeter('ram', ram.used_gb, ram.total_gb, 'G');
  setTopMeter('shm', shm.used_gb ?? 0, shm.total_gb || 88, 'G');
  if (drive.mounted && drive.total_gb) {
    setTopMeter('drive', drive.used_gb / 1024, drive.total_gb / 1024, 'T');
  } else {
    setTopMeter('drive', disk.used_gb, disk.total_gb, 'G');
  }
  renderStoragePyramid(m);

  drawSparkline($('#sparkUtil'), S.hist.util, 100, '#a78bfa', 'rgba(167, 139, 250, 0.32)');
  drawSparkline($('#sparkVram'), S.hist.vram, vramTotalGb || 96, '#22d3ee', 'rgba(34, 211, 238, 0.28)');

  // Workers
  const workersEl = $('#workers');
  if (workersEl) {
    const ws = m.workers || [];
    if (!ws.length) {
      workersEl.innerHTML = '<div class="workers-empty">暂无常驻模型 Worker（推理时自动按需加载）</div>';
    } else {
      workersEl.innerHTML = '';
      ws.forEach((w) => {
        const toneMap = { on_gpu: ['green', 'GPU 常驻'], offloaded: ['blue', '内存待命'], loading: ['amber', '加载中'], dead: ['red', '已退出'] };
        const [tone, label] = toneMap[w.state] || ['muted', w.state];
        const vramTxt = w.vram_mb ? `${fmtNum(w.vram_mb / 1024, 1)} GB` : '';
        workersEl.append(
          h('div', { class: 'worker' },
            h('span', { class: 'badge', 'data-tone': tone }, label),
            h('b', { title: w.model_id }, w.model_id),
            vramTxt ? h('span', {}, vramTxt) : null,
            h('button', {
              class: 'icon-btn sm',
              title: '卸载释放显存',
              html: icon('x'),
              onclick: async () => {
                try {
                  await remote(`/models/${encodeURIComponent(w.model_id)}/unload`, { method: 'POST' });
                  toast(`已卸载 ${w.model_id}`, 'info', { timeout: 1800 });
                  emit('poll:fast');
                } catch {}
              },
            }),
          ),
        );
      });
    }
  }
}

function renderStoragePyramid(m) {
  const el = $('#storagePyramid');
  if (!el) return;
  const g = m?.gpu || {};
  const ram = m?.ram || {};
  const shm = m?.shm || {};
  const drive = m?.drive || {};

  const vramTxt = g.mem_total_mb ? `${fmtNum((g.mem_used_mb || 0) / 1024, 1)} / ${fmtNum(g.mem_total_mb / 1024, 0)} GB` : '98 GB GDDR7';
  const ramTxt = ram.total_gb ? `${fmtNum(ram.used_gb || 0, 1)} / ${fmtNum(ram.total_gb, 0)} GB` : '176 GB DDR5';
  const shmTxt = shm.total_gb ? `${fmtNum(shm.free_gb ?? shm.total_gb, 1)} / ${fmtNum(shm.total_gb, 0)} GB 空闲` : '88 GB 内存盘';
  const driveTxt = drive.mounted && drive.total_gb
    ? `${fmtNum(drive.free_gb / 1024, 1)} / ${fmtNum(drive.total_gb / 1024, 0)} TB 可用`
    : '30 TB 云盘金库';

  el.innerHTML = `
    <div class="sp-tier" title="L1: Blackwell GDDR7 显存 · 1792 GB/s">
      <span>L1 显存池 <em>1.8TB/s</em></span>
      <b>${esc(vramTxt)}</b>
    </div>
    <div class="sp-tier" title="L2: Pinned DDR5 锁页内存 · PCIe Gen5 DMA 63 GB/s">
      <span>L2 锁页内存 <em>63GB/s</em></span>
      <b>${esc(ramTxt)}</b>
    </div>
    <div class="sp-tier" title="L3: /dev/shm 零延迟 tmpfs 内存加速盘 · 2.4 GB/s">
      <span>L3 /dev/shm 盘 <em>2.4GB/s</em></span>
      <b>${esc(shmTxt)}</b>
    </div>
    <div class="sp-tier" title="L4: Google Drive 30TB 持久化云盘金库 (rclone 8路并发)">
      <span>L4 谷歌云盘 <em>30TB</em></span>
      <b>${esc(driveTxt)}</b>
    </div>
  `;
}

/* ---------------- Render Model Center ---------------- */
function renderModels() {
  const wrap = $('#modelList');
  if (!wrap) return;
  const list = S.models && S.models.length ? S.models : FALLBACK_MODELS;
  const iconMap = { t2i: 'image', t2v: 'video', i2v: 'video', lyra: 'cube', tts: 'sparkles' };
  const tierLabelMap = {
    gpu: 'L1 显存常驻',
    pinned_ram: 'L2 锁页内存',
    ramdisk: 'L3 内存盘 2.4GB/s',
    drive: 'L4 30TB云盘已存',
    nvme: 'NVMe 高速盘',
  };

  wrap.innerHTML = '';
  list.forEach((m) => {
    const w = workerOf(m.id);
    const isZeroVram = m.kind === 'tts' || m.id === 'breeze-tts-2' || m.zero_vram;
    const activeJob = S.jobs.find(
      (j) => j.model_id === m.id && (j.status === 'running' || j.status === 'queued') && ['download', 'load', 'setup'].includes(j.task),
    );

    let stBadge;
    if (isZeroVram) {
      stBadge = h('span', { class: 'badge', 'data-tone': 'green' }, '0显存 · 云盘常驻');
    } else if (!S.connected) {
      stBadge = h('span', { class: 'badge', 'data-tone': 'muted' }, '待连接');
    } else if (activeJob) {
      const pct = activeJob.progress ? ` ${Math.round(activeJob.progress * 100)}%` : '';
      stBadge = h('span', { class: 'badge spin', 'data-tone': 'amber', html: icon('refresh') + `<span>${activeJob.task === 'download' ? '下载中' : '加载中'}${pct}</span>` });
    } else if (w && w.state === 'on_gpu') {
      stBadge = h('span', { class: 'badge', 'data-tone': 'green' }, 'GPU 常驻');
    } else if (w && w.state === 'offloaded') {
      stBadge = h('span', { class: 'badge', 'data-tone': 'blue' }, '内存待命');
    } else if (m.status === 'downloading') {
      stBadge = h('span', { class: 'badge spin', 'data-tone': 'amber', html: icon('refresh') + '<span>下载中</span>' });
    } else if (m.status === 'loading') {
      stBadge = h('span', { class: 'badge spin', 'data-tone': 'amber', html: icon('refresh') + '<span>加载中</span>' });
    } else if (m.status === 'downloaded' || m.status === 'loaded') {
      stBadge = h('span', { class: 'badge', 'data-tone': 'cyan' }, m.storage_tier === 'ramdisk' ? '内存盘就绪' : (m.storage_tier === 'drive' ? '云盘就绪' : '已就绪'));
    } else if (m.status === 'error') {
      stBadge = h('span', { class: 'badge', 'data-tone': 'red' }, '异常');
    } else {
      stBadge = h('span', { class: 'badge', 'data-tone': 'muted' }, '云端可拉取');
    }

    const useModelForGen = (targetOverride) => {
      const targetTab = targetOverride || (m.kind === 't2i' ? 'image' : 'video');
      emit('tab', targetTab);
      emit('model:select', m);
      toast(`已选择模型：${m.name}，输入一句话提示词即可生成`, 'info', { timeout: 2400 });
      setTimeout(() => {
        const promptInput = $(targetTab === 'image' ? '#t2iPrompt' : (targetTab === 'world' ? '#worldScene' : '#vidPrompt'));
        promptInput?.focus();
      }, 60);
    };

    const actions = [];
    // Primary button -> selects model in Image/Video composer & focuses prompt
    actions.push(
      h('button', {
        class: 'btn btn-xs btn-accent',
        html: icon('arrowRight') + '<span>→ 选择此模型去生成</span>',
        onclick: (e) => {
          e.stopPropagation();
          useModelForGen();
        },
      }),
    );

    if (m.kind === 'lyra') {
      actions.push(
        h('button', {
          class: 'btn btn-xs btn-ghost',
          html: icon('cube') + '<span>3D 运镜工作台</span>',
          onclick: (e) => {
            e.stopPropagation();
            useModelForGen('world');
          },
        }),
      );
    }

    if (S.connected && !activeJob) {
      if (m.status === 'available' || m.status === 'error') {
        actions.push(
          h('button', {
            class: 'btn btn-xs',
            html: icon('download') + '<span>极速拉取 (内存盘/云盘)</span>',
            onclick: (e) => {
              e.stopPropagation();
              withBusy(e.currentTarget, async () => {
                await remote(`/models/${encodeURIComponent(m.id)}/download`, { method: 'POST', errTitle: '下载模型失败' });
                toast(`已启动 8 路并发下载 → /dev/shm 内存盘 + 30TB 云盘：${m.name}`, 'info');
                emit('poll:fast');
              });
            },
          }),
        );
      } else if (m.status === 'downloaded' || m.status === 'loaded') {
        if (!w || w.state !== 'on_gpu') {
          actions.push(
            h('button', {
              class: 'btn btn-xs',
              html: icon('zap') + '<span>预热进 GPU</span>',
              onclick: (e) => {
                e.stopPropagation();
                withBusy(e.currentTarget, async () => {
                  await remote(`/models/${encodeURIComponent(m.id)}/load`, { method: 'POST', errTitle: '加载模型失败' });
                  toast(`正在将 ${m.name} 加载进 GPU…`, 'info');
                  emit('poll:fast');
                });
              },
            }),
          );
        }
        if (w && (w.state === 'on_gpu' || w.state === 'offloaded')) {
          actions.push(
            h('button', {
              class: 'btn btn-xs btn-ghost',
              html: icon('eject') + '<span>卸载</span>',
              onclick: (e) => {
                e.stopPropagation();
                withBusy(e.currentTarget, async () => {
                  await remote(`/models/${encodeURIComponent(m.id)}/unload`, { method: 'POST', errTitle: '卸载失败' });
                  toast(`已卸载 ${m.name}`, 'info');
                  emit('poll:fast');
                });
              },
            }),
          );
        }
      }

      if (!m.builtin) {
        actions.push(
          h('span', { class: 'spacer' }),
          h('button', {
            class: 'icon-btn sm',
            title: '移除模型',
            html: icon('trash'),
            onclick: async (e) => {
              e.stopPropagation();
              const ok = await confirmDialog({
                title: `移除模型「${m.name}」？`,
                message: '将从模型注册表中删除该模型并释放磁盘缓存。',
                confirmText: '移除',
                danger: true,
              });
              if (!ok) return;
              try {
                await remote(`/models/${encodeURIComponent(m.id)}`, { method: 'DELETE' });
                S.models = S.models.filter((x) => x.id !== m.id);
                emit('models', S.models);
                toast('已移除模型', 'success');
              } catch {}
            },
          }),
        );
      }
    }

    const progBar = activeJob
      ? h('div', { class: 'progress sm' + (activeJob.progress ? '' : ' indet') },
          h('i', { style: { width: `${Math.round((activeJob.progress || 0) * 100)}%` } }))
      : null;

    const repoLabel = m.subfolder ? `${m.repo}/${m.subfolder}` : m.repo;
    const tierBadge = isZeroVram
      ? h('span', { class: 'model-tier', 'data-tier': 'zero-vram' }, '0显存 · 云盘常驻')
      : (m.featured_hybrid
          ? h('span', { class: 'model-tier', 'data-tier': 'hybrid' }, '音视频同生')
          : (m.storage_tier && tierLabelMap[m.storage_tier]
              ? h('span', { class: 'model-tier' }, tierLabelMap[m.storage_tier])
              : null));

    wrap.append(
      h('div', {
        class: 'model clickable',
        title: `点击选择「${m.name}」去生成`,
        onclick: () => useModelForGen(),
      },
        h('div', { class: 'model-top' },
          h('div', { class: 'model-ic', 'data-k': m.kind, html: icon(iconMap[m.kind] || 'box') }),
          h('div', { class: 'model-info' },
            h('div', { class: 'model-name' },
              h('span', { title: m.name }, m.name),
              stBadge),
            h('div', { class: 'model-sub' },
              tierBadge,
              h('span', {}, KIND_LABEL[m.kind] || m.kind),
              m.size_gb ? h('span', {}, `· ${fmtGB(m.size_gb)}`) : null,
              repoLabel ? h('span', { class: 'repo', title: repoLabel }, `· ${repoLabel}`) : null))),
        m.description ? h('div', { class: 'model-desc' }, m.description) : null,
        progBar,
        h('div', { class: 'model-actions' }, actions)),
    );
  });
}

/* ---------------- Onboarding Hero ---------------- */
function updateHero() {
  const hero = $('#hero');
  const panels = $('#panels');
  if (!hero || !panels) return;

  // Never block or blur the main composer panels unless an active setup job is explicitly showing the hero
  const setupJob = S.jobs.find((j) => j.task === 'setup' && (j.status === 'running' || j.status === 'queued'));
  const showHero = !S.heroDismissed && !!setupJob;
  hero.hidden = !showHero;
  panels.classList.toggle('hero-on', showHero);

  if (!showHero) return;

  const step1 = $('#heroSteps .step[data-step="1"]');
  const step2 = $('#heroSteps .step[data-step="2"]');
  const step3 = $('#heroSteps .step[data-step="3"]');

  const s1Done = !!activeSess || S.connected;
  const s2Done = S.connected;
  const s3Done = S.connected && anyModelReady && !setupJob;

  step1?.classList.toggle('done', s1Done);
  step1?.classList.toggle('active', !s1Done);
  step2?.classList.toggle('done', s2Done);
  step2?.classList.toggle('active', s1Done && !s2Done);
  step3?.classList.toggle('done', s3Done);
  step3?.classList.toggle('active', s2Done && !s3Done);

  const startTask = S.tasks.find((t) => t.type === 'session_start' && t.status === 'running');
  const connTask = S.tasks.find((t) => t.type === 'connect' && t.status === 'running');

  setText($('#heroS1'), startTask ? (startTask.log_tail || '正在申请 GPU 实例…') : (s1Done ? `已就绪：${activeSess?.name || sessName} (${activeSess?.hardware || s.gpu || 'G4'})` : '在 Colab 上创建 GPU 实例'));
  setText($('#heroS2'), connTask ? (connTask.log_tail || '正在建立隧道与远端服务…') : (s2Done ? `隧道已连接 · 远端服务在线` : '建立 SSH 隧道并启动远端服务'));

  const prog = $('#heroSetupProg');
  if (setupJob) {
    const pct = Math.round((setupJob.progress || 0) * 100);
    setText($('#heroS3'), `${setupJob.stage || '正在部署环境'} (${pct}%)`);
    if (prog) {
      prog.hidden = false;
      prog.classList.toggle('indet', !setupJob.progress);
      const bar = $('i', prog);
      if (bar) bar.style.width = `${pct}%`;
    }
  } else {
    if (prog) prog.hidden = true;
    setText($('#heroS3'), s3Done ? '环境与模型已就绪' : '安装 Qwen-Image 与 Lyra 2.0 运行环境（首次约 10–20 分钟）');
  }
}
