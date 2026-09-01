<template>
  <canvas ref="skyRef" class="night-sky" aria-hidden="true"></canvas>
</template>

<script setup>
/**
 * NightSky.vue — 星野背景
 *
 * 移植自设计稿 app.js 的星野渲染：
 * 全屏 fixed canvas，星星闪烁 + 远处月轮，resize 自适应，DPR 处理。
 */
import { ref, onMounted, onUnmounted } from 'vue'

const skyRef = ref(null)

let ctx = null
let stars = []
let rafId = null
let lastT = 0

function sizeSky() {
  const sky = skyRef.value
  if (!sky) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  sky.width = innerWidth * dpr
  sky.height = innerHeight * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  stars = Array.from({ length: Math.floor((innerWidth * innerHeight) / 11000) }, () => ({
    x: Math.random() * innerWidth,
    y: Math.random() * innerHeight,
    r: 0.4 + Math.random() * 0.9,
    p: Math.random() * Math.PI * 2,
    s: 0.4 + Math.random() * 1.2,
    warm: Math.random() < 0.3
  }))
}

function drawSky(t) {
  ctx.clearRect(0, 0, innerWidth, innerHeight)

  // 远处月轮
  const mx = innerWidth * 0.84
  const my = innerHeight * 0.15
  const mr = 120
  const gm = ctx.createRadialGradient(mx, my, 0, mx, my, mr)
  gm.addColorStop(0, 'rgba(243,217,164,0.05)')
  gm.addColorStop(0.45, 'rgba(243,217,164,0.02)')
  gm.addColorStop(1, 'rgba(243,217,164,0)')
  ctx.beginPath()
  ctx.arc(mx, my, mr, 0, Math.PI * 2)
  ctx.fillStyle = gm
  ctx.fill()

  // 星
  for (const st of stars) {
    const a = 0.14 + 0.3 * (0.5 + 0.5 * Math.sin(t * st.s + st.p))
    ctx.beginPath()
    ctx.arc(st.x, st.y, st.r, 0, Math.PI * 2)
    ctx.fillStyle = st.warm ? `rgba(243,217,164,${a})` : `rgba(190,205,228,${a})`
    ctx.fill()
  }
}

function frame(now) {
  const t = now / 1000
  lastT = now
  drawSky(t)
  rafId = requestAnimationFrame(frame)
}

function onResize() {
  sizeSky()
}

onMounted(() => {
  ctx = skyRef.value.getContext('2d')
  sizeSky()
  window.addEventListener('resize', onResize)
  rafId = requestAnimationFrame(frame)
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  window.removeEventListener('resize', onResize)
  stars = []
  lastT = 0
})
</script>

<style scoped>
.night-sky {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none;
}
</style>
