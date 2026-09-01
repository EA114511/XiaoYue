<template>
  <canvas ref="canvasRef" class="night-sky" aria-hidden="true"></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref(null)
let ctx = null
let animationId = null
let stars = []
let moon = null
let prefersReducedMotion = false

// 检查用户是否偏好减少动画
if (window.matchMedia) {
  prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function init() {
  const canvas = canvasRef.value
  if (!canvas) return

  ctx = canvas.getContext('2d')
  resize()
  createStars()
  createMoon()
  animate()
}

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return

  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = window.innerWidth * dpr
  canvas.height = window.innerHeight * dpr
  ctx.scale(dpr, dpr)
}

function createStars() {
  stars = []
  const count = 50 // 移动端减少星星数量

  for (let i = 0; i < count; i++) {
    stars.push({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight * 0.55,
      size: Math.random() * 1.2 + 0.4,
      brightness: Math.random() * 0.4 + 0.25,
      twinkleSpeed: Math.random() * 0.015 + 0.004,
      phase: Math.random() * Math.PI * 2
    })
  }
}

function createMoon() {
  moon = {
    x: window.innerWidth * 0.82,
    y: window.innerHeight * 0.12,
    radius: 22,
    phase: 0.72
  }
}

function animate() {
  if (!ctx) return

  const width = window.innerWidth
  const height = window.innerHeight

  // 清除画布 - 使用墨蓝底色
  ctx.fillStyle = '#090C14'
  ctx.fillRect(0, 0, width, height)

  // 绘制星空
  stars.forEach(star => {
    if (!prefersReducedMotion) {
      star.phase += star.twinkleSpeed
    }
    const alpha = star.brightness * (0.55 + Math.sin(star.phase) * 0.45)

    // 星星颜色：偏暖白
    ctx.fillStyle = `rgba(239, 231, 211, ${alpha})`
    ctx.beginPath()
    ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2)
    ctx.fill()
  })

  // 绘制月亮
  if (moon) {
    // 月亮光晕
    const glowGradient = ctx.createRadialGradient(
      moon.x, moon.y, 0,
      moon.x, moon.y, moon.radius * 2.5
    )
    glowGradient.addColorStop(0, 'rgba(239, 231, 211, 0.12)')
    glowGradient.addColorStop(0.5, 'rgba(239, 231, 211, 0.05)')
    glowGradient.addColorStop(1, 'rgba(239, 231, 211, 0)')

    ctx.fillStyle = glowGradient
    ctx.beginPath()
    ctx.arc(moon.x, moon.y, moon.radius * 2.5, 0, Math.PI * 2)
    ctx.fill()

    // 月亮本体
    ctx.fillStyle = 'rgba(239, 231, 211, 0.22)'
    ctx.beginPath()
    ctx.arc(moon.x, moon.y, moon.radius, 0, Math.PI * 2)
    ctx.fill()

    // 月相阴影
    ctx.fillStyle = 'rgba(9, 12, 20, 0.35)'
    ctx.beginPath()
    ctx.arc(moon.x - moon.radius * 0.28, moon.y, moon.radius * 0.88, 0, Math.PI * 2)
    ctx.fill()
  }

  // 绘制极光渐变（底部）
  const auroraGradient = ctx.createLinearGradient(0, height * 0.75, 0, height)
  auroraGradient.addColorStop(0, 'rgba(159, 212, 203, 0)')
  auroraGradient.addColorStop(0.4, 'rgba(159, 212, 203, 0.025)')
  auroraGradient.addColorStop(0.8, 'rgba(228, 181, 106, 0.015)')
  auroraGradient.addColorStop(1, 'rgba(228, 181, 106, 0.01)')

  ctx.fillStyle = auroraGradient
  ctx.fillRect(0, height * 0.75, width, height * 0.25)

  if (!prefersReducedMotion) {
    animationId = requestAnimationFrame(animate)
  }
}

onMounted(() => {
  init()
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  cancelAnimationFrame(animationId)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
.night-sky {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: -1;
  pointer-events: none;
}

/* 减少动画模式 */
@media (prefers-reduced-motion: reduce) {
  .night-sky {
    /* 静态背景，无动画 */
  }
}
</style>
