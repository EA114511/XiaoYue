<template>
  <div class="voice-orb" :class="state">
    <canvas ref="canvasRef"></canvas>
    <div class="orb-core"></div>
    <div class="orb-glow"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  state: {
    type: String,
    default: 'idle'
  }
})

const canvasRef = ref(null)
let ctx = null
let animationId = null
let time = 0

const params = {
  radius: 0,
  particles: [],
  ripples: []
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

  params.radius = rect.width * 0.32
}

function initParticles() {
  params.particles = []
  const count = 16

  for (let i = 0; i < count; i++) {
    params.particles.push({
      angle: (i / count) * Math.PI * 2,
      baseRadius: params.radius * 1.3,
      speed: 0.015 + Math.random() * 0.01,
      size: 1.5 + Math.random() * 2,
      alpha: 0.4 + Math.random() * 0.4,
      offset: Math.random() * Math.PI * 2
    })
  }
}

function animate() {
  if (!ctx) return

  const canvas = canvasRef.value
  const rect = canvas.getBoundingClientRect()
  const width = rect.width
  const height = rect.height
  const centerX = width / 2
  const centerY = height / 2

  ctx.clearRect(0, 0, width, height)
  time += 0.016

  // 状态配置
  const config = {
    idle: { pulseSpeed: 1, particleSpeed: 1, glowIntensity: 0.25 },
    listening: { pulseSpeed: 2, particleSpeed: 2.5, glowIntensity: 0.4 },
    thinking: { pulseSpeed: 3, particleSpeed: 4, glowIntensity: 0.35 },
    speaking: { pulseSpeed: 2.5, particleSpeed: 3, glowIntensity: 0.5 }
  }[props.state] || { pulseSpeed: 1, particleSpeed: 1, glowIntensity: 0.25 }

  // 呼吸脉冲
  const pulse = 1 + Math.sin(time * 2 * config.pulseSpeed) * 0.03

  // 绘制粒子轨道
  ctx.save()
  ctx.translate(centerX, centerY)

  params.particles.forEach((p, i) => {
    p.angle += p.speed * config.particleSpeed

    const wobble = Math.sin(time * 2 + p.offset) * 0.1
    const radius = p.baseRadius * (1 + wobble) * pulse
    const x = Math.cos(p.angle) * radius
    const y = Math.sin(p.angle) * radius

    // 状态相关透明度
    let alpha = p.alpha
    if (props.state === 'thinking') {
      alpha = 0.4 + Math.sin(time * 4 + i) * 0.3
    } else if (props.state === 'speaking') {
      alpha = 0.5 + Math.sin(time * 6 + i) * 0.4
    } else if (props.state === 'listening') {
      alpha = 0.5 + Math.sin(time * 3 + i) * 0.3
    }

    ctx.fillStyle = `rgba(228, 181, 106, ${alpha})`
    ctx.beginPath()
    ctx.arc(x, y, p.size, 0, Math.PI * 2)
    ctx.fill()
  })

  ctx.restore()

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
.voice-orb {
  position: relative;
  width: 180px;
  height: 180px;
}

.voice-orb canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.orb-core {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 60%;
  height: 60%;
  border-radius: 50%;
  background: radial-gradient(
    circle at 35% 35%,
    #F3D9A4 0%,
    #E4B56A 40%,
    rgba(228, 181, 106, 0.9) 100%
  );
  box-shadow:
    0 0 20px rgba(228, 181, 106, 0.4),
    0 0 40px rgba(228, 181, 106, 0.2),
    inset 0 0 20px rgba(255, 255, 255, 0.1);
  animation: core-breathe 4s ease-in-out infinite;
}

.voice-orb.listening .orb-core {
  background: radial-gradient(
    circle at 35% 35%,
    #B8E4DC 0%,
    #9FD4CB 40%,
    rgba(159, 212, 203, 0.9) 100%
  );
  box-shadow:
    0 0 20px rgba(159, 212, 203, 0.4),
    0 0 40px rgba(159, 212, 203, 0.2),
    inset 0 0 20px rgba(255, 255, 255, 0.1);
  animation-duration: 2s;
}

.voice-orb.speaking .orb-core {
  animation-duration: 1.5s;
}

.voice-orb.thinking .orb-core {
  animation-duration: 3s;
}

@keyframes core-breathe {
  0%, 100% {
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    transform: translate(-50%, -50%) scale(1.05);
  }
}

.orb-glow {
  position: absolute;
  inset: -25%;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    rgba(228, 181, 106, 0.25) 0%,
    rgba(228, 181, 106, 0.1) 40%,
    transparent 70%
  );
  pointer-events: none;
  animation: glow-pulse 4s ease-in-out infinite;
}

.voice-orb.listening .orb-glow {
  background: radial-gradient(
    circle,
    rgba(159, 212, 203, 0.3) 0%,
    rgba(159, 212, 203, 0.12) 40%,
    transparent 70%
  );
  animation-duration: 2s;
}

.voice-orb.speaking .orb-glow {
  animation-duration: 1.5s;
}

@keyframes glow-pulse {
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.08);
  }
}
</style>
