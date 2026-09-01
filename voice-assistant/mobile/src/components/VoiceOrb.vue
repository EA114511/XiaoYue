<template>
  <div class="voice-orb" :class="state">
    <canvas ref="canvasRef"></canvas>
    <div class="orb-glow"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  state: {
    type: String,
    default: 'idle' // idle, listening, thinking, speaking
  }
})

const canvasRef = ref(null)
let ctx = null
let animationId = null
let time = 0

// 光球参数
const params = {
  radius: 0,
  glowRadius: 0,
  particles: [],
  pulse: 0
}

function init() {
  const canvas = canvasRef.value
  if (!canvas) return

  ctx = canvas.getContext('2d')
  resize()
  initParticles()
  animate()
}

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return

  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const rect = canvas.getBoundingClientRect()

  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)

  params.radius = rect.width * 0.35
  params.glowRadius = rect.width * 0.45
}

function initParticles() {
  params.particles = []
  const count = 24
  for (let i = 0; i < count; i++) {
    params.particles.push({
      angle: (i / count) * Math.PI * 2,
      radius: params.radius * 1.2,
      speed: 0.02 + Math.random() * 0.02,
      size: 2 + Math.random() * 3,
      alpha: 0.3 + Math.random() * 0.5
    })
  }
}

function animate() {
  if (!ctx) return

  const canvas = canvasRef.value
  const width = canvas.width / (window.devicePixelRatio || 1)
  const height = canvas.height / (window.devicePixelRatio || 1)
  const centerX = width / 2
  const centerY = height / 2

  ctx.clearRect(0, 0, width, height)

  time += 0.016

  // 根据状态调整参数
  const stateConfig = {
    idle: { pulseSpeed: 0.02, particleSpeed: 1, glow: 0.3 },
    listening: { pulseSpeed: 0.05, particleSpeed: 2, glow: 0.5 },
    thinking: { pulseSpeed: 0.08, particleSpeed: 4, glow: 0.4 },
    speaking: { pulseSpeed: 0.06, particleSpeed: 3, glow: 0.6 }
  }

  const config = stateConfig[props.state] || stateConfig.idle

  // 呼吸脉冲
  params.pulse = Math.sin(time * 2) * 0.05 + 1

  // 绘制光晕
  const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, params.glowRadius * params.pulse)
  gradient.addColorStop(0, `rgba(228, 181, 106, ${0.3 * config.glow})`)
  gradient.addColorStop(0.5, `rgba(228, 181, 106, ${0.15 * config.glow})`)
  gradient.addColorStop(1, 'rgba(228, 181, 106, 0)')

  ctx.fillStyle = gradient
  ctx.beginPath()
  ctx.arc(centerX, centerY, params.glowRadius * params.pulse, 0, Math.PI * 2)
  ctx.fill()

  // 绘制粒子轨道
  ctx.save()
  ctx.translate(centerX, centerY)

  params.particles.forEach((p, i) => {
    p.angle += p.speed * config.particleSpeed

    const x = Math.cos(p.angle) * p.radius * params.pulse
    const y = Math.sin(p.angle) * p.radius * params.pulse

    // 根据状态调整粒子透明度
    let alpha = p.alpha
    if (props.state === 'thinking') {
      alpha = 0.5 + Math.sin(time * 3 + i) * 0.3
    } else if (props.state === 'speaking') {
      alpha = 0.6 + Math.sin(time * 5 + i) * 0.4
    }

    ctx.fillStyle = `rgba(228, 181, 106, ${alpha})`
    ctx.beginPath()
    ctx.arc(x, y, p.size, 0, Math.PI * 2)
    ctx.fill()
  })

  ctx.restore()

  // 绘制核心光球
  const coreGradient = ctx.createRadialGradient(
    centerX - params.radius * 0.3,
    centerY - params.radius * 0.3,
    0,
    centerX,
    centerY,
    params.radius * params.pulse
  )
  coreGradient.addColorStop(0, '#F3D9A4')
  coreGradient.addColorStop(0.5, '#E4B56A')
  coreGradient.addColorStop(1, 'rgba(228, 181, 106, 0.8)')

  ctx.fillStyle = coreGradient
  ctx.beginPath()
  ctx.arc(centerX, centerY, params.radius * params.pulse, 0, Math.PI * 2)
  ctx.fill()

  // 高光
  ctx.fillStyle = 'rgba(255, 255, 255, 0.4)'
  ctx.beginPath()
  ctx.arc(
    centerX - params.radius * 0.25,
    centerY - params.radius * 0.25,
    params.radius * 0.2,
    0,
    Math.PI * 2
  )
  ctx.fill()

  animationId = requestAnimationFrame(animate)
}

watch(() => props.state, () => {
  // 状态变化时的过渡动画
})

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
.voice-orb {
  position: relative;
  width: 160px;
  height: 160px;
}

.voice-orb canvas {
  width: 100%;
  height: 100%;
}

.orb-glow {
  position: absolute;
  inset: -30%;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(228, 181, 106, 0.2) 0%, transparent 70%);
  pointer-events: none;
  animation: breathe 4s ease-in-out infinite;
}

.voice-orb.listening .orb-glow {
  animation-duration: 2s;
  background: radial-gradient(circle, rgba(159, 212, 203, 0.3) 0%, transparent 70%);
}

.voice-orb.speaking .orb-glow {
  animation-duration: 1.5s;
}

@keyframes breathe {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.05); }
}
</style>
