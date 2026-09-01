<template>
  <div class="home-view">
    <!-- 星野背景 -->
    <NightSky />

    <!-- 顶栏 -->
    <header class="top-bar">
      <div class="seal-logo">玥</div>
      <h1 class="app-title">小玥</h1>
      <button class="icon-btn" @click="goSettings" aria-label="设置">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="settings-icon">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 1v6m0 6v6M5.64 5.64l4.24 4.24m4.24 4.24l4.24 4.24M1 12h6m6 0h6M5.64 18.36l4.24-4.24m4.24-4.24l4.24-4.24" />
        </svg>
      </button>
    </header>

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 光球区域 -->
      <section class="orb-section">
        <div class="orb-container" :class="status">
          <VoiceOrb :state="status" />
          <div class="orb-ring"></div>
        </div>

        <div class="status-area">
          <p class="status-text">{{ statusText }}</p>
          <div class="status-divider"></div>
          <p class="status-sub">{{ statusSub }}</p>
        </div>

        <p class="hint-text">{{ hintText }}</p>
      </section>

      <!-- 最近消息 -->
      <section class="messages-section" v-if="messages.length > 0">
        <div class="section-header">
          <span class="section-title">最近对话</span>
          <button class="text-btn" @click="clearMessages">清空</button>
        </div>
        <div class="messages-list">
          <MessageCard
            v-for="msg in recentMessages"
            :key="msg.id"
            :message="msg"
          />
        </div>
      </section>
    </main>

    <!-- 底部操作区 -->
    <footer class="action-bar safe-area-bottom">
      <button
        class="voice-btn"
        :class="{ recording: isRecording, processing: isProcessing }"
        :disabled="!isConnected"
        @touchstart.prevent="startRecording"
        @touchend.prevent="stopRecording"
        @mousedown.prevent="startRecording"
        @mouseup.prevent="stopRecording"
      >
        <div class="btn-inner">
          <van-icon v-if="isProcessing" name="more" class="btn-icon loading" />
          <van-icon v-else-if="isRecording" name="stop" class="btn-icon" />
          <van-icon v-else name="volume" class="btn-icon" />
        </div>
        <div class="btn-ring"></div>
      </button>

      <p class="btn-label">{{ buttonLabel }}</p>

      <div class="connection-indicator" :class="{ connected: isConnected }">
        <span class="dot"></span>
        <span class="text">{{ isConnected ? '已连接' : '未连接' }}</span>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores'
import { useVoiceChat } from '@/composables/useVoiceChat'
import { STATE_TEXT, HINTS } from '@/utils/constants'
import NightSky from '@/components/NightSky.vue'
import VoiceOrb from '@/components/VoiceOrb.vue'
import MessageCard from '@/components/MessageCard.vue'

const router = useRouter()
const store = useAppStore()

// 语音对话
const {
  isRecording,
  isProcessing,
  isPlaying,
  isConnected,
  status,
  startRecording,
  stopRecording,
  sendText
} = useVoiceChat({
  onTranscript: (text) => {
    store.addMessage('user', text)
  },
  onResponse: (text, isStream, isEnd) => {
    if (isStream) {
      const lastMsg = store.messages[store.messages.length - 1]
      if (lastMsg?.role === 'assistant') {
        lastMsg.content += text
      } else {
        store.addMessage('assistant', text)
      }
    } else {
      store.addMessage('assistant', text)
    }
  },
  onError: (err) => {
    console.error('[Home] 错误:', err)
  },
  onStatusChange: (status) => {
    store.setConnected(status === 'connected')
  }
})

// 计算属性
const messages = computed(() => store.messages)
const recentMessages = computed(() => store.recentMessages)

const statusText = computed(() => STATE_TEXT[status.value]?.verb || '待机')
const statusSub = computed(() => STATE_TEXT[status.value]?.sub || 'STANDBY')

const hintText = computed(() => {
  if (!isConnected.value) return HINTS.ERROR
  return HINTS[status.value.toUpperCase()] || HINTS.IDLE
})

const buttonLabel = computed(() => {
  if (isProcessing.value) return '正在处理...'
  if (isRecording.value) return '松开结束'
  return '按住说话'
})

// 方法
function goSettings() {
  router.push('/settings')
}

function clearMessages() {
  store.clearMessages()
}

onMounted(() => {
  store.loadHistory()
})
</script>

<style scoped>
.home-view {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

/* ---------- 顶栏 ---------- */
.top-bar {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  padding-top: calc(12px + env(safe-area-inset-top));
}

.seal-logo {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 18px;
  font-weight: 600;
  color: var(--gold-2);
  border: 1.5px solid var(--hair-warm);
  border-radius: 10px;
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.12), rgba(228, 181, 106, 0.02));
}

.app-title {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.15em;
  color: var(--pearl);
  margin: 0;
}

.icon-btn {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  color: var(--mist);
  border-radius: 10px;
  border: 1px solid var(--hair-cool);
  background: linear-gradient(160deg, rgba(27, 35, 64, 0.4), rgba(13, 18, 32, 0.3));
  transition: all 0.25s ease;
}

.icon-btn:active {
  background: rgba(228, 181, 106, 0.15);
  border-color: var(--hair-warm);
  color: var(--gold-2);
}

.settings-icon {
  width: 20px;
  height: 20px;
  stroke: currentColor;
}

/* ---------- 主内容区 ---------- */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 0 20px;
}

/* ---------- 光球区域 ---------- */
.orb-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px 0;
}

.orb-container {
  position: relative;
  width: 180px;
  height: 180px;
}

.orb-ring {
  position: absolute;
  inset: -20px;
  border-radius: 50%;
  border: 1px solid var(--hair-warm);
  opacity: 0.5;
  animation: ring-pulse 3s ease-in-out infinite;
}

.orb-container.listening .orb-ring {
  border-color: var(--celadon);
  animation-duration: 1.5s;
}

.orb-container.speaking .orb-ring {
  border-color: var(--gold);
  animation-duration: 2s;
}

@keyframes ring-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.05);
    opacity: 0.8;
  }
}

/* ---------- 状态区域 ---------- */
.status-area {
  margin-top: 32px;
  text-align: center;
}

.status-text {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 28px;
  font-weight: 500;
  letter-spacing: 0.25em;
  text-indent: 0.25em;
  color: var(--pearl);
  margin: 0;
}

.status-divider {
  width: 40px;
  height: 1px;
  margin: 12px auto;
  background: linear-gradient(90deg, transparent, var(--hair-warm), transparent);
}

.status-sub {
  font-size: 11px;
  letter-spacing: 0.35em;
  color: var(--faint);
  margin: 0;
}

.hint-text {
  margin-top: 20px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--mist);
  text-align: center;
  max-width: 280px;
}

/* ---------- 消息区域 ---------- */
.messages-section {
  flex-shrink: 0;
  max-height: 32vh;
  padding-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--hair-cool);
}

.section-title {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.15em;
  color: var(--pearl-dim);
}

.text-btn {
  font-size: 12px;
  color: var(--mist);
  padding: 4px 12px;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.text-btn:active {
  color: var(--gold-2);
  background: rgba(228, 181, 106, 0.1);
}

.messages-list {
  display: flex;
  flex-direction: column;
  padding-top: 8px;
}

/* ---------- 底部操作区 ---------- */
.action-bar {
  position: relative;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 20px;
  padding-bottom: calc(24px + env(safe-area-inset-bottom));
}

.voice-btn {
  position: relative;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: none;
  background: transparent;
  padding: 0;
  touch-action: none;
  -webkit-tap-highlight-color: transparent;
}

.btn-inner {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.25), rgba(228, 181, 106, 0.08));
  border: 2px solid var(--gold);
  color: var(--gold);
  transition: all 0.2s ease;
}

.voice-btn:active .btn-inner,
.voice-btn.recording .btn-inner {
  background: var(--gold);
  color: var(--ink-0);
  transform: scale(0.95);
}

.voice-btn.recording .btn-inner {
  background: var(--celadon);
  border-color: var(--celadon);
}

.voice-btn.processing .btn-inner {
  background: var(--mist);
  border-color: var(--mist);
}

.voice-btn:disabled .btn-inner {
  opacity: 0.4;
}

.btn-icon {
  font-size: 32px;
}

.btn-icon.loading {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.btn-ring {
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 1px solid var(--hair-warm);
  opacity: 0;
  transition: all 0.3s ease;
}

.voice-btn.recording .btn-ring {
  opacity: 1;
  animation: btn-pulse 1.5s ease-in-out infinite;
}

@keyframes btn-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.6;
  }
  50% {
    transform: scale(1.1);
    opacity: 0;
  }
}

.btn-label {
  margin-top: 16px;
  font-size: 13px;
  letter-spacing: 0.1em;
  color: var(--mist);
}

/* ---------- 连接状态 ---------- */
.connection-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  background: rgba(126, 142, 166, 0.1);
}

.connection-indicator .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--faint);
}

.connection-indicator.connected .dot {
  background: var(--celadon);
  box-shadow: 0 0 6px var(--celadon);
}

.connection-indicator .text {
  font-size: 11px;
  color: var(--mist);
}
</style>
