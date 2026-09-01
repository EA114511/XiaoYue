/* ══════════════════════════════════════════════════════════════
   小玥 · 界面重设计 — 交互与渲染
   玥珠光球 / 星野 / 状态机 / 语音条 / 设计标注
   ══════════════════════════════════════════════════════════════ */
'use strict';

/* ───────────────────────── 状态机 ───────────────────────── */

const STATES = {
  idle: {
    verb: '待机', sub: 'STANDBY',
    caption: '轻触麦克风，或按住空格开始说话',
    ripple: 0.5, core: 0.68, ring: 0.14, particles: 0, tint: 0,
  },
  listening: {
    verb: '聆听', sub: 'LISTENING',
    caption: '我在听，请讲……',
    ripple: 1.2, core: 0.9, ring: 0.45, particles: 0, tint: 1,
  },
  thinking: {
    verb: '思索', sub: 'THINKING',
    caption: '稍候，正在为你组织回答……',
    ripple: 0.65, core: 0.75, ring: 1.7, particles: 1, tint: 0,
  },
  speaking: {
    verb: '应答', sub: 'SPEAKING',
    caption: '「北京今天晴，气温 18 到 26 度，傍晚转凉，记得带件薄外套。」',
    ripple: 1.35, core: 1.0, ring: 0.55, particles: 0, tint: 0,
  },
};

let currentState = 'idle';
const params = { ...STATES.idle }; // 平滑插值后的实时参数

function setState(s) {
  if (!STATES[s]) return;
  currentState = s;
  document.body.dataset.state = s;

  // 演示按钮
  document.querySelectorAll('.demo-bar button').forEach(b =>
    b.classList.toggle('on', b.dataset.s === s));

  // 动词淡入淡出
  const verb = document.getElementById('stateVerb');
  const sub = document.getElementById('stateSub');
  const caption = document.getElementById('caption');
  [verb, caption].forEach(el => { el.style.opacity = 0; });
  setTimeout(() => {
    verb.textContent = STATES[s].verb;
    sub.textContent = STATES[s].sub;
    caption.textContent = STATES[s].caption;
    [verb, caption].forEach(el => { el.style.opacity = 1; });
  }, 240);
}

document.querySelectorAll('.demo-bar button').forEach(b =>
  b.addEventListener('click', () => setState(b.dataset.s)));

document.getElementById('micBtn').addEventListener('click', () =>
  setState(currentState === 'listening' ? 'idle' : 'listening'));

/* ───────────────────────── 振幅模拟 ───────────────────────── */

let amp = 0.06, ampTarget = 0.06, lastPick = 0;

function pickAmplitude(t, dt) {
  switch (currentState) {
    case 'idle':
      ampTarget = 0.05 + 0.035 * Math.sin(t * 0.6);
      break;
    case 'listening':
      // 模拟人声：随机游走，偶发峰值与停顿
      if (t - lastPick > 0.09) {
        lastPick = t;
        const r = Math.random();
        ampTarget = r < 0.18 ? 0.05 + Math.random() * 0.08
                  : r < 0.75 ? 0.25 + Math.random() * 0.4
                  : 0.7 + Math.random() * 0.3;
      }
      break;
    case 'thinking':
      ampTarget = 0.1 + 0.05 * Math.sin(t * 1.9);
      break;
    case 'speaking': {
      // 音节式包络：快慢两层正弦叠加
      const gate = Math.sin(t * 6.4) > -0.35 ? 1 : 0.25;
      ampTarget = gate * (0.3 + 0.5 * Math.abs(Math.sin(t * 2.7))) * (0.75 + 0.25 * Math.sin(t * 0.9));
      break;
    }
  }
  amp += (ampTarget - amp) * Math.min(1, dt * (currentState === 'listening' ? 14 : 7));
}

/* ───────────────────────── 玥珠渲染 ───────────────────────── */

const GOLD = [228, 181, 106], GOLD2 = [243, 217, 164], CELA = [159, 212, 203];
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const mix = (a, b, k) => a.map((v, i) => Math.round(v + (b[i] - v) * k));

const orbCanvas = document.getElementById('orb');
const octx = orbCanvas.getContext('2d');
let OW = 0, ODPR = 1;

function sizeOrb() {
  ODPR = Math.min(window.devicePixelRatio || 1, 2);
  const r = orbCanvas.getBoundingClientRect();
  OW = r.width;
  orbCanvas.width = OW * ODPR;
  orbCanvas.height = OW * ODPR;
}

// 思索粒子
const particles = Array.from({ length: 16 }, (_, i) => ({
  a0: (i / 16) * Math.PI * 2,
  r: 1.1 + Math.random() * 0.14,
  s: 0.9 + Math.random() * 0.9,
  w: 0.7 + Math.random() * 0.6,
}));

let rot = 0, pRot = 0;

function drawOrb(t, dt) {
  if (!OW) sizeOrb();
  const ctx = octx;
  ctx.setTransform(ODPR, 0, 0, ODPR, 0, 0);
  ctx.clearRect(0, 0, OW, OW);

  const c = OW / 2;
  const R = OW * 0.3;                     // 核心半径
  const p = params;

  // 参数平滑
  for (const k of ['ripple', 'core', 'ring', 'particles', 'tint']) {
    p[k] += (STATES[currentState][k] - p[k]) * Math.min(1, dt * 3.2);
  }
  rot += dt * (0.12 + p.ring * 0.9);
  pRot += dt * (0.25 + p.ring * 1.1);

  const breath = 1 + 0.05 * Math.sin(t * 0.7) + amp * 0.1;
  const rippleCol = mix(GOLD, CELA, p.tint);

  ctx.globalCompositeOperation = 'lighter';

  // —— 结构环（常显细边，珍珠的轮廓） ——
  ctx.beginPath();
  ctx.arc(c, c, R * 1.02, 0, Math.PI * 2);
  ctx.strokeStyle = rgba(GOLD, 0.1 + p.core * 0.06);
  ctx.lineWidth = 1;
  ctx.stroke();

  // —— 涟漪三环 ——
  for (let i = 0; i < 3; i++) {
    const wob = Math.sin(t * (1.4 + i * 0.5) + i * 2.1) * 0.5 + 0.5;
    const rr = R * (1.18 + i * 0.24) * (1 + amp * 0.34 * (0.4 + 0.6 * wob));
    const alpha = (0.34 - i * 0.09) * p.ripple * (0.35 + amp * 0.9);
    if (alpha <= 0.004) continue;
    ctx.beginPath();
    ctx.arc(c, c, rr, 0, Math.PI * 2);
    ctx.strokeStyle = rgba(i === 2 ? rippleCol : mix(GOLD2, rippleCol, i * 0.4), alpha);
    ctx.lineWidth = 1.1;
    ctx.stroke();
  }

  // —— 外环弧光（旋转高光） ——
  const ringR = R * 1.04;
  for (const [off, len, a] of [[0, 1.9, 0.5], [Math.PI, 1.1, 0.28]]) {
    const g = ctx.createConicGradient
      ? ctx.createConicGradient(rot + off, c, c)
      : null;
    ctx.beginPath();
    ctx.arc(c, c, ringR, rot + off, rot + off + len);
    ctx.strokeStyle = rgba(GOLD2, a * (0.4 + p.core * 0.6));
    ctx.lineWidth = 1.4;
    ctx.lineCap = 'round';
    ctx.stroke();
  }

  // —— 核心光球 ——
  const coreR = R * breath;
  const gCore = ctx.createRadialGradient(c, c, 0, c, c, coreR);
  gCore.addColorStop(0, rgba(GOLD2, 0.92 * p.core));
  gCore.addColorStop(0.28, rgba(GOLD, 0.5 * p.core));
  gCore.addColorStop(0.72, rgba(GOLD, 0.1 * p.core));
  gCore.addColorStop(1, rgba(GOLD, 0));
  ctx.beginPath();
  ctx.arc(c, c, coreR, 0, Math.PI * 2);
  ctx.fillStyle = gCore;
  ctx.fill();

  // —— 内亮珠 ——
  const innerR = coreR * (0.34 + amp * 0.1);
  const gIn = ctx.createRadialGradient(c, c, 0, c, c, innerR);
  gIn.addColorStop(0, rgba([255, 244, 220], 0.95 * p.core));
  gIn.addColorStop(0.6, rgba(GOLD2, 0.4 * p.core));
  gIn.addColorStop(1, rgba(GOLD2, 0));
  ctx.beginPath();
  ctx.arc(c, c, innerR, 0, Math.PI * 2);
  ctx.fillStyle = gIn;
  ctx.fill();

  // —— 应答时内核声纹 ——
  if (currentState === 'speaking') {
    const bars = 24, base = R * 0.52;
    for (let i = 0; i < bars; i++) {
      const a = (i / bars) * Math.PI * 2 + pRot * 0.4;
      const h = (0.3 + 0.7 * Math.abs(Math.sin(t * 5 + i * 1.7))) * amp * R * 0.3;
      ctx.beginPath();
      ctx.moveTo(c + Math.cos(a) * base, c + Math.sin(a) * base);
      ctx.lineTo(c + Math.cos(a) * (base + h), c + Math.sin(a) * (base + h));
      ctx.strokeStyle = rgba(GOLD2, 0.4);
      ctx.lineWidth = 1.3;
      ctx.lineCap = 'round';
      ctx.stroke();
    }
  }

  // —— 思索粒子轨 ——
  if (p.particles > 0.02) {
    for (const pt of particles) {
      const a = pt.a0 + pRot * pt.w;
      const rr = R * pt.r * (1 + 0.04 * Math.sin(t * 2 + pt.a0 * 3));
      const x = c + Math.cos(a) * rr;
      const y = c + Math.sin(a) * rr * 0.98;
      const tw = 0.45 + 0.55 * Math.sin(t * 2.4 * pt.s + pt.a0);
      ctx.beginPath();
      ctx.arc(x, y, 1.15, 0, Math.PI * 2);
      ctx.fillStyle = rgba(GOLD2, 0.75 * tw * p.particles);
      ctx.fill();
    }
  }

  ctx.globalCompositeOperation = 'source-over';
}

/* ───────────────────────── 星野渲染 ───────────────────────── */

const sky = document.getElementById('sky');
const sctx = sky.getContext('2d');
let stars = [];

function sizeSky() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  sky.width = innerWidth * dpr;
  sky.height = innerHeight * dpr;
  sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  stars = Array.from({ length: Math.floor(innerWidth * innerHeight / 11000) }, () => ({
    x: Math.random() * innerWidth,
    y: Math.random() * innerHeight,
    r: 0.4 + Math.random() * 0.9,
    p: Math.random() * Math.PI * 2,
    s: 0.4 + Math.random() * 1.2,
    warm: Math.random() < 0.3,
  }));
}

function drawSky(t) {
  sctx.clearRect(0, 0, innerWidth, innerHeight);

  // 远处月轮
  const mx = innerWidth * 0.84, my = innerHeight * 0.15, mr = 120;
  const gm = sctx.createRadialGradient(mx, my, 0, mx, my, mr);
  gm.addColorStop(0, 'rgba(243,217,164,0.05)');
  gm.addColorStop(0.45, 'rgba(243,217,164,0.02)');
  gm.addColorStop(1, 'rgba(243,217,164,0)');
  sctx.beginPath();
  sctx.arc(mx, my, mr, 0, Math.PI * 2);
  sctx.fillStyle = gm;
  sctx.fill();

  // 星
  for (const st of stars) {
    const a = 0.14 + 0.3 * (0.5 + 0.5 * Math.sin(t * st.s + st.p));
    sctx.beginPath();
    sctx.arc(st.x, st.y, st.r, 0, Math.PI * 2);
    sctx.fillStyle = st.warm ? `rgba(243,217,164,${a})` : `rgba(190,205,228,${a})`;
    sctx.fill();
  }
}

/* ───────────────────────── 主循环 ───────────────────────── */

let lastT = performance.now();
function frame(now) {
  const t = now / 1000;
  const dt = Math.min(0.05, (now - lastT) / 1000);
  lastT = now;
  pickAmplitude(t, dt);
  drawSky(t);
  drawOrb(t, dt);
  requestAnimationFrame(frame);
}

window.addEventListener('resize', () => { sizeSky(); sizeOrb(); });
sizeSky();
requestAnimationFrame(frame);

/* ───────────────────────── 语音条 ───────────────────────── */

document.querySelectorAll('.voice-pill').forEach(pill => {
  pill.addEventListener('click', () => {
    const was = pill.classList.contains('playing');
    document.querySelectorAll('.voice-pill.playing').forEach(p => p.classList.remove('playing'));
    if (!was) pill.classList.add('playing');
  });
});

/* ───────────────────────── 设计标注 ───────────────────────── */

const ANNOTATIONS = [
  { n: 1, title: '品牌字标', text: '宋体「小玥」与「玥」印章并置，建立人格与东方感；替代原方案的通用无衬线标题。' },
  { n: 2, title: '模型芯片', text: '青瓷绿 = 本地模型，暖金 = 远程模型；颜色即状态，无需阅读文字。' },
  { n: 3, title: '玥珠 · 语音主角', text: '光球即助手之「身」。呼吸为待机，涟漪随人声起伏为聆听，粒子轨道为思索，内核声纹为应答。' },
  { n: 4, title: '状态动词', text: '一词知状态：待机 / 聆听 / 思索 / 应答。衬线大字取代原方案的圆点加英文标签。' },
  { n: 5, title: '实况字幕', text: '当前识别文本与流式回复在此呈现，说完即沉入右侧对话流。' },
  { n: 6, title: '输入坞', text: '语音键置于最左并加大，文本输入退居其次——顺序即优先级。录音时金环扩散。' },
  { n: 7, title: '对话流 · 双声部', text: '取消气泡，以颜色分声部：暖金为小玥，青瓷为用户；印章头像标记智能体。' },
];

const annoLayer = document.getElementById('annoLayer');
const annoList = document.getElementById('annoList');
const annoToggle = document.getElementById('annoToggle');

ANNOTATIONS.forEach(a => {
  const li = document.createElement('li');
  li.innerHTML = `<span class="n">${a.n}</span><span><b>${a.title}</b> — ${a.text}</span>`;
  annoList.appendChild(li);
});

function placeAnnoDots() {
  annoLayer.innerHTML = '';
  ANNOTATIONS.forEach(a => {
    const el = document.querySelector(`[data-anno="${a.n}"]`);
    if (!el) return;
    const r = el.getBoundingClientRect();
    const dot = document.createElement('span');
    dot.className = 'anno-dot';
    dot.textContent = a.n;
    // 放在元素左上角外侧
    dot.style.left = `${r.left - 6}px`;
    dot.style.top = `${r.top - 6}px`;
    annoLayer.appendChild(dot);
  });
}

annoToggle.addEventListener('click', () => {
  const on = document.body.classList.toggle('show-anno');
  annoToggle.setAttribute('aria-pressed', String(on));
  if (on) placeAnnoDots();
});
window.addEventListener('resize', () => {
  if (document.body.classList.contains('show-anno')) placeAnnoDots();
});

/* ───────────────────────── 入场编排 ───────────────────────── */

// 解析时立即初始化状态（脚本位于 body 末尾，DOM 已就绪）
const _qs = new URLSearchParams(location.search);
const _initState = _qs.get('state');
setState(_initState && STATES[_initState] ? _initState : 'idle');

window.addEventListener('load', () => {
  // ?anno=1 直接展开设计标注（等待字体与布局稳定后放置标注点）
  if (_qs.get('anno') === '1') {
    document.body.classList.add('show-anno');
    annoToggle.setAttribute('aria-pressed', 'true');
    placeAnnoDots();
  }
});
