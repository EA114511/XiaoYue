<template>
  <canvas ref="canvasRef" class="night-sky"></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref(null)
let ctx = null
let animationId = null
let stars = []
let moon = null

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
  const count = 60

  for (let i = 0; i < count; i++) {
    stars.push({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight * 0.6, // 星星主要在上半部
      size: Math.random() * 1.5 + 0.5,
      brightness: Math.random() * 0.5 + 0.3,
      twinkleSpeed: Math.random() * 0.02 + 0.005,
      phase: Math.random() * Math.PI * 2
    })
  }
}

function createMoon() {
  moon = {
    x: window.innerWidth * 0.85,
    y: window.innerHeight * 0.15,
    radius: 25,
    phase: 0.7
  }
}

function animate() {
  if (!ctx) return

  const width = window.innerWidth
  const height = window.innerHeight

  // 清除画布
  ctx.fillStyle = '#090C14'
  ctx.fillRect(0, 0, width, height)

  // 绘制星空
  stars.forEach(star => {
    star.phase += star.twinkleSpeed
    const alpha = star.brightness * (0.5 + Math.sin(star.phase) * 0.5)

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
      moon.x, moon.y, moon.radius * 2
    )
    glowGradient.addColorStop(0, 'rgba(239, 231, 211, 0.15)')
    glowGradient.addColorStop(1, 'rgba(239, 231, 211, 0)')

    ctx.fillStyle = glowGradient
    ctx.beginPath()
    ctx.arc(moon.x, moon.y, moon.radius * 2, 0, Math.PI * 2)
    ctx.fill()

    // 月亮本体
    ctx.fillStyle = 'rgba(239, 231, 211, 0.25)'
    ctx.beginPath()
    ctx.arc(moon.x, moon.y, moon.radius, 0, Math.PI * 2)
    ctx.fill()

    // 月相阴影
    ctx.fillStyle = 'rgba(9, 12, 20, 0.4)'
    ctx.beginPath()
    ctx.arc(moon.x - moon.radius * 0.3, moon.y, moon.radius * 0.85, 0, Math.PI * 2)
    ctx.fill()
  }

  // 绘制极光渐变（底部）
  const auroraGradient = ctx.createLinearGradient(0, height * 0.7, 0, height)
  auroraGradient.addColorStop(0, 'rgba(159, 212, 203, 0)')
  auroraGradient.addColorStop(0.5, 'rgba(159, 212, 203, 0.03)')
  auroraGradient.addColorStop(1, 'rgba(228, 181, 106, 0.02)')

  ctx.fillStyle = auroraGradient
  ctx.fillRect(0, height * 0.7, width, height * 0.3)

  animationId = requestAnimationFrame(animate)
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
</style>
