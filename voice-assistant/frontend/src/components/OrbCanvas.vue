<template>
  <canvas ref="orbRef" class="orb-canvas"></canvas>
</template>

<script setup>
/**
 * OrbCanvas.vue — 玥珠（呼吸光球）
 *
 * 移植自设计稿 app.js 的玥珠渲染：
 * 核心光球、结构环、旋转弧光、涟漪三环、思索粒子轨、
 * 应答内核声纹、振幅模拟与参数平滑。
 *
 * props.state: 'idle' | 'listening' | 'thinking' | 'speaking'
 * requestAnimationFrame 自循环，onUnmounted 清理；
 * 尺寸跟随 CSS 容器（100% 宽高，ResizeObserver）。
 */
import { ref, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  state: { type: String, default: 'idle' }
})

const STATES = {
  idle:      { ripple: 0.5,  core: 0.68, ring: 0.14, particles: 0, tint: 0 },
  listening: { ripple: 1.2,  core: 0.9,  ring: 0.45, particles: 0, tint: 1 },
  thinking:  { ripple: 0.65, core: 0.75, ring: 1.7,  particles: 1, tint: 0 },
  speaking:  { ripple: 1.35, core: 1.0,  ring: 0.55, particles: 0, tint: 0 }
}

const orbRef = ref(null)

let octx = null
let OW = 0
let ODPR = 1
let rafId = null
let resizeObserver = null

let currentState = STATES[props.state] ? props.state : 'idle'
const params = { ...STATES.idle } // 平滑插值后的实时参数

watch(
  () => props.state,
  s => {
    if (STATES[s]) currentState = s
  }
)

/* ───────────────────────── 振幅模拟 ───────────────────────── */

let amp = 0.06
let ampTarget = 0.06
let lastPick = 0

function pickAmplitude(t, dt) {
  switch (currentState) {
    case 'idle':
      ampTarget = 0.05 + 0.035 * Math.sin(t * 0.6)
      break
    case 'listening':
      // 模拟人声：随机游走，偶发峰值与停顿
      if (t - lastPick > 0.09) {
        lastPick = t
        const r = Math.random()
        ampTarget =
          r < 0.18 ? 0.05 + Math.random() * 0.08 : r < 0.75 ? 0.25 + Math.random() * 0.4 : 0.7 + Math.random() * 0.3
      }
      break
    case 'thinking':
      ampTarget = 0.1 + 0.05 * Math.sin(t * 1.9)
      break
    case 'speaking': {
      // 音节式包络：快慢两层正弦叠加
      const gate = Math.sin(t * 6.4) > -0.35 ? 1 : 0.25
      ampTarget = gate * (0.3 + 0.5 * Math.abs(Math.sin(t * 2.7))) * (0.75 + 0.25 * Math.sin(t * 0.9))
      break
    }
  }
  amp += (ampTarget - amp) * Math.min(1, dt * (currentState === 'listening' ? 14 : 7))
}

/* ───────────────────────── 玥珠渲染 ───────────────────────── */

const GOLD = [228, 181, 106]
const GOLD2 = [243, 217, 164]
const CELA = [159, 212, 203]
const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`
const mix = (a, b, k) => a.map((v, i) => Math.round(v + (b[i] - v) * k))

function sizeOrb() {
  const canvas = orbRef.value
  if (!canvas) return
  ODPR = Math.min(window.devicePixelRatio || 1, 2)
  const r = canvas.getBoundingClientRect()
  OW = r.width
  if (OW <= 0) return
  const w = Math.round(OW * ODPR)
  const h = Math.round(OW * ODPR)
  // 重设 width/height 会清空画布：尺寸未变则跳过，变化时补绘一帧
  if (canvas.width === w && canvas.height === h) return
  canvas.width = w
  canvas.height = h
  if (octx) drawOrb(lastFrameT, 0.016)
}

// 思索粒子
const particles = Array.from({ length: 16 }, (_, i) => ({
  a0: (i / 16) * Math.PI * 2,
  r: 1.1 + Math.random() * 0.14,
  s: 0.9 + Math.random() * 0.9,
  w: 0.7 + Math.random() * 0.6
}))

let rot = 0
let pRot = 0

function drawOrb(t, dt) {
  if (!OW) sizeOrb()
  if (!OW) return
  const ctx = octx
  ctx.setTransform(ODPR, 0, 0, ODPR, 0, 0)
  ctx.clearRect(0, 0, OW, OW)

  const c = OW / 2
  const R = OW * 0.3 // 核心半径
  const p = params

  // 参数平滑
  for (const k of ['ripple', 'core', 'ring', 'particles', 'tint']) {
    p[k] += (STATES[currentState][k] - p[k]) * Math.min(1, dt * 3.2)
  }
  rot += dt * (0.12 + p.ring * 0.9)
  pRot += dt * (0.25 + p.ring * 1.1)

  const breath = 1 + 0.05 * Math.sin(t * 0.7) + amp * 0.1
  const rippleCol = mix(GOLD, CELA, p.tint)

  ctx.globalCompositeOperation = 'lighter'

  // —— 结构环（常显细边，珍珠的轮廓） ——
  ctx.beginPath()
  ctx.arc(c, c, R * 1.02, 0, Math.PI * 2)
  ctx.strokeStyle = rgba(GOLD, 0.1 + p.core * 0.06)
  ctx.lineWidth = 1
  ctx.stroke()

  // —— 涟漪三环 ——
  for (let i = 0; i < 3; i++) {
    const wob = Math.sin(t * (1.4 + i * 0.5) + i * 2.1) * 0.5 + 0.5
    const rr = R * (1.18 + i * 0.24) * (1 + amp * 0.34 * (0.4 + 0.6 * wob))
    const alpha = (0.34 - i * 0.09) * p.ripple * (0.35 + amp * 0.9)
    if (alpha <= 0.004) continue
    ctx.beginPath()
    ctx.arc(c, c, rr, 0, Math.PI * 2)
    ctx.strokeStyle = rgba(i === 2 ? rippleCol : mix(GOLD2, rippleCol, i * 0.4), alpha)
    ctx.lineWidth = 1.1
    ctx.stroke()
  }

  // —— 外环弧光（旋转高光） ——
  const ringR = R * 1.04
  for (const [off, len, a] of [
    [0, 1.9, 0.5],
    [Math.PI, 1.1, 0.28]
  ]) {
    ctx.beginPath()
    ctx.arc(c, c, ringR, rot + off, rot + off + len)
    ctx.strokeStyle = rgba(GOLD2, a * (0.4 + p.core * 0.6))
    ctx.lineWidth = 1.4
    ctx.lineCap = 'round'
    ctx.stroke()
  }

  // —— 核心光球 ——
  const coreR = R * breath
  const gCore = ctx.createRadialGradient(c, c, 0, c, c, coreR)
  gCore.addColorStop(0, rgba(GOLD2, 0.92 * p.core))
  gCore.addColorStop(0.28, rgba(GOLD, 0.5 * p.core))
  gCore.addColorStop(0.72, rgba(GOLD, 0.1 * p.core))
  gCore.addColorStop(1, rgba(GOLD, 0))
  ctx.beginPath()
  ctx.arc(c, c, coreR, 0, Math.PI * 2)
  ctx.fillStyle = gCore
  ctx.fill()

  // —— 内亮珠 ——
  const innerR = coreR * (0.34 + amp * 0.1)
  const gIn = ctx.createRadialGradient(c, c, 0, c, c, innerR)
  gIn.addColorStop(0, rgba([255, 244, 220], 0.95 * p.core))
  gIn.addColorStop(0.6, rgba(GOLD2, 0.4 * p.core))
  gIn.addColorStop(1, rgba(GOLD2, 0))
  ctx.beginPath()
  ctx.arc(c, c, innerR, 0, Math.PI * 2)
  ctx.fillStyle = gIn
  ctx.fill()

  // —— 应答时内核声纹 ——
  if (currentState === 'speaking') {
    const bars = 24
    const base = R * 0.52
    for (let i = 0; i < bars; i++) {
      const a = (i / bars) * Math.PI * 2 + pRot * 0.4
      const h = (0.3 + 0.7 * Math.abs(Math.sin(t * 5 + i * 1.7))) * amp * R * 0.3
      ctx.beginPath()
      ctx.moveTo(c + Math.cos(a) * base, c + Math.sin(a) * base)
      ctx.lineTo(c + Math.cos(a) * (base + h), c + Math.sin(a) * (base + h))
      ctx.strokeStyle = rgba(GOLD2, 0.4)
      ctx.lineWidth = 1.3
      ctx.lineCap = 'round'
      ctx.stroke()
    }
  }

  // —— 思索粒子轨 ——
  if (p.particles > 0.02) {
    for (const pt of particles) {
      const a = pt.a0 + pRot * pt.w
      const rr = R * pt.r * (1 + 0.04 * Math.sin(t * 2 + pt.a0 * 3))
      const x = c + Math.cos(a) * rr
      const y = c + Math.sin(a) * rr * 0.98
      const tw = 0.45 + 0.55 * Math.sin(t * 2.4 * pt.s + pt.a0)
      ctx.beginPath()
      ctx.arc(x, y, 1.15, 0, Math.PI * 2)
      ctx.fillStyle = rgba(GOLD2, 0.75 * tw * p.particles)
      ctx.fill()
    }
  }

  ctx.globalCompositeOperation = 'source-over'
}

/* ───────────────────────── 主循环 ───────────────────────── */

let lastT = 0
let lastFrameT = 0

function frame(now) {
  const t = now / 1000
  const dt = Math.min(0.05, (now - lastT) / 1000)
  lastT = now
  lastFrameT = t
  pickAmplitude(t, dt)
  drawOrb(t, dt)
  rafId = requestAnimationFrame(frame)
}

onMounted(() => {
  octx = orbRef.value.getContext('2d')
  sizeOrb()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => sizeOrb())
    resizeObserver.observe(orbRef.value)
  } else {
    window.addEventListener('resize', sizeOrb)
  }
  lastT = performance.now()
  rafId = requestAnimationFrame(frame)
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  } else {
    window.removeEventListener('resize', sizeOrb)
  }
})
</script>

<style scoped>
.orb-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
