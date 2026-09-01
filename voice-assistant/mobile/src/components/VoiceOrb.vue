<template>
  <div class="voice-orb" :class="state">
    <canvas ref="canvasRef" class="orb-canvas"></canvas>
    <div class="orb-core"></div>
    <div class="orb-ring"></div>
    <div class="orb-glow"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  state: {
    type: String,
    default: 'idle',
    validator: (v) => ['idle', 'listening', 'thinking', 'speaking'].includes(v)
  }
})

const canvasRef = ref(null)
let ctx = null
let animationId = null
let time = 0
let prefersReducedMotion = false

// 检查用户是否偏好减少动画
if (window.matchMedia) {
  prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

const params = {
  radius: 0,
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

  params.radius = rect.width * 0.32
}

function initParticles() {
  params.particles = []
  const count = 16 // 移动端限制粒子数

  for (let i = 0; i < count; i++) {
    params.particles.push({
      angle: (i / count) * Math.PI * 2,
      baseRadius: params.radius * 1.35,
      speed: 0.012 + Math.random() * 0.008,
      size: 1.2 + Math.random() * 1.8,
      alpha: 0.35 + Math.random() * 0.35,
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

  // 减少动画模式下，只绘制静态效果
  if (prefersReducedMotion) {
    drawStatic()
    return
  }

  time += 0.016

  // 状态配置
  const config = {
    idle: { pulseSpeed: 1, particleSpeed: 1, glowIntensity: 0.2 },
    listening: { pulseSpeed: 2, particleSpeed: 2.2, glowIntensity: 0.35 },
    thinking: { pulseSpeed: 3, particleSpeed: 4, glowIntensity: 0.3 },
    speaking: { pulseSpeed: 2.5, particleSpeed: 3.5, glowIntensity: 0.45 }
  }[props.state] || { pulseSpeed: 1, particleSpeed: 1, glowIntensity: 0.2 }

  // 呼吸脉冲
  params.pulse = 1 + Math.sin(time * 2 * config.pulseSpeed) * 0.03

  // 绘制粒子轨道
  ctx.save()
  ctx.translate(centerX, centerY)

  params.particles.forEach((p, i) => {
    p.angle += p.speed * config.particleSpeed

    const wobble = Math.sin(time * 2 + p.offset) * 0.08
    const radius = p.baseRadius * (1 + wobble) * params.pulse
    const x = Math.cos(p.angle) * radius
    const y = Math.sin(p.angle) * radius

    // 状态相关透明度
    let alpha = p.alpha
    if (props.state === 'thinking') {
      alpha = 0.35 + Math.sin(time * 4 + i * 0.5) * 0.3
    } else if (props.state === 'speaking') {
      alpha = 0.45 + Math.sin(time * 6 + i * 0.3) * 0.4
    } else if (props.state === 'listening') {
      alpha = 0.45 + Math.sin(time * 3 + i * 0.4) * 0.3
    }

    // 聆听状态使用青瓷色
    const color = props.state === 'listening' ? '159, 212, 203' : '228, 181, 106'

    ctx.fillStyle = `rgba(${color}, ${alpha})`
    ctx.beginPath()
    ctx.arc(x, y, p.size, 0, Math.PI * 2)
    ctx.fill()
  })

  ctx.restore()

  animationId = requestAnimationFrame(animate)
}

function drawStatic() {
  // 静态模式：只绘制核心光球
  const canvas = canvasRef.value
  const rect = canvas.getBoundingClientRect()
  const centerX = rect.width / 2
  const centerY = rect.height / 2

  // 绘制静态光晕
  const gradient = ctx.createRadialGradient(
    centerX, centerY, 0,
    centerX, centerY, params.radius * 1.5
  )
  gradient.addColorStop(0, 'rgba(228, 181, 106, 0.15)')
  gradient.addColorStop(1, 'rgba(228, 181, 106, 0)')

  ctx.fillStyle = gradient
  ctx.beginPath()
  ctx.arc(centerX, centerY, params.radius * 1.5, 0, Math.PI * 2)
  ctx.fill()
}

watch(() => props.state, (newState, oldState) => {
  // 状态变化时的平滑过渡
  if (oldState !== newState) {
    // 可以在这里添加状态切换动画
  }
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
  width: var(--orb-size, 160px);
  height: var(--orb-size, 160px);
}

.orb-canvas {
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
  width: 58%;
  height: 58%;
  border-radius: 50%;
  background: radial-gradient(
    circle at 32% 32%,
    var(--gold-2) 0%,
    var(--gold) 45%,
    rgba(228, 181, 106, 0.85) 100%
  );
  box-shadow:
    0 0 24px rgba(228, 181, 106, 0.35),
    0 0 48px rgba(228, 181, 106, 0.15),
    inset 0 0 24px rgba(255, 255, 255, 0.08);
  animation: core-breathe 4s ease-in-out infinite;
}

.orb-ring {
  position: absolute;
  inset: -12px;
  border-radius: 50%;
  border: 1px solid var(--hair-warm);
  opacity: 0.4;
  transition: all 0.4s ease;
}

.orb-glow {
  position: absolute;
  inset: -30%;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    rgba(228, 181, 106, 0.22) 0%,
    rgba(228, 181, 106, 0.08) 45%,
    transparent 70%
  );
  pointer-events: none;
  animation: glow-pulse 4s ease-in-out infinite;
}

/* 聆听状态 */
.voice-orb.listening .orb-core {
  background: radial-gradient(
    circle at 32% 32%,
    #B8E4DC 0%,
    var(--celadon) 45%,
    rgba(159, 212, 203, 0.85) 100%
  );
  box-shadow:
    0 0 24px rgba(159, 212, 203, 0.4),
    0 0 48px rgba(159, 212, 203, 0.18),
    inset 0 0 24px rgba(255, 255, 255, 0.08);
  animation-duration: 2s;
}

.voice-orb.listening .orb-ring {
  border-color: var(--celadon);
  opacity: 0.6;
}

.voice-orb.listening .orb-glow {
  background: radial-gradient(
    circle,
    rgba(159, 212, 203, 0.28) 0%,
    rgba(159, 212, 203, 0.1) 45%,
    transparent 70%
  );
  animation-duration: 2s;
}

/* 思索状态 */
.voice-orb.thinking .orb-core {
  animation-duration: 3s;
}

.voice-orb.thinking .orb-glow {
  animation-duration: 3s;
}

/* 应答状态 */
.voice-orb.speaking .orb-core {
  animation-duration: 1.5s;
}

.voice-orb.speaking .orb-glow {
  animation-duration: 1.5s;
  animation-name: glow-pulse-speaking;
}

@keyframes core-breathe {
  0%, 100% {
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    transform: translate(-50%, -50%) scale(1.04);
  }
}

@keyframes glow-pulse {
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.06);
  }
}

@keyframes glow-pulse-speaking {
  0%, 100% {
    opacity: 0.7;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.1);
  }
}

/* 减少动画模式 */
@media (prefers-reduced-motion: reduce) {
  .orb-core,
  .orb-glow,
  .orb-ring {
    animation: none !important;
  }
}
</style>
