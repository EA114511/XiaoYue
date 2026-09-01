<template>
  <div class="chat-wrapper">
    <!-- 对话历史侧边栏 -->
    <ConversationHistory :is-open="showHistory" :api-base="httpBaseUrl" @close="showHistory = false" @load-conversation="loadConversation" />

    <!-- 主区域：左舞台 · 右对话流 -->
    <main class="layout">
      <!-- 舞台：玥珠 -->
      <section class="stage">
        <div class="orb-wrap" :data-state="orbState">
          <OrbCanvas :state="orbState" />
          <div class="orb-halo" aria-hidden="true"></div>
        </div>

        <div class="state-line">
          <span class="state-verb">{{ stateVerb }}</span>
          <span class="state-rule" aria-hidden="true"></span>
          <span class="state-sub">{{ stateSub }}</span>
        </div>

        <p class="caption">{{ captionText }}</p>

        <div class="dock">
          <button class="mic" :class="{ listening: orbState === 'listening' }" :disabled="status === 'processing'" @mousedown="onMicDown" @mouseup="onMicUp" @mouseleave="onMicUp" @touchstart.prevent="onMicDown" @touchend.prevent="onMicUp" aria-label="按住说话" title="长按录音">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="22" />
            </svg>
            <span class="mic-ring" aria-hidden="true"></span>
          </button>
          <textarea ref="inputRef" v-model="inputText" class="dock-input" rows="1" placeholder="说点什么，或输入文字…" aria-label="输入消息" @keydown.enter.exact.prevent="onSendText" @input="autoResize"></textarea>
          <button class="send" :class="{ active: inputText.trim() }" :disabled="!inputText.trim() || status === 'processing'" @click="onSendText" aria-label="发送" title="发送">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="13 6 19 12 13 18" />
            </svg>
          </button>
        </div>
        <p class="dock-hint">按住 <kbd>空格</kbd> 说话&ensp;·&ensp;<kbd>Enter</kbd> 发送</p>
      </section>

      <!-- 对话流 -->
      <aside class="stream">
        <div class="stream-head">
          <h2>对话</h2>
          <span class="stream-meta">{{ todayLabel }}</span>
          <button class="icon-btn" title="对话历史" aria-label="对话历史" @click="showHistory = !showHistory">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="9" />
              <polyline points="12 7 12 12 15.5 14" />
            </svg>
          </button>
          <button class="text-btn" @click="clearMessages" title="清空对话">清空</button>
        </div>

        <div class="stream-scroll" ref="messageListRef">
          <!-- 空状态：舞台即空状态，此处仅一行淡字 -->
          <p v-if="messages.length === 0 && !showTypingIndicator" class="stream-empty">尚无对话 —— 由左侧玥珠开始</p>

          <article v-for="(msg, idx) in messages" :key="idx" class="msg" :class="msg.role">
            <!-- 印章头像：助手「玥」，智能体取首字，用户无头像 -->
            <div v-if="msg.role !== 'user'" class="msg-avatar">
              <span class="seal" :class="{ agent: isAgentMsg(msg) }">{{ agentSeal(msg) }}</span>
            </div>
            <div class="msg-body">
              <!-- 智能体标识 -->
              <span v-if="isAgentMsg(msg)" class="agent-tag">{{ msg.agent.display_name }}</span>

              <!-- 语音 pill -->
              <button v-if="msg.audio" class="voice-pill" :class="{ playing: msg.audio.isPlaying }" :aria-label="`播放语音 ${formatDuration(msg.audio.duration)} 秒`" @click="toggleVoicePlay(msg)">
                <svg class="vp-play" viewBox="0 0 24 24" fill="currentColor">
                  <polygon v-if="!msg.audio.isPlaying" points="9,6 19,12 9,18" />
                  <g v-else>
                    <rect x="7" y="6" width="3.4" height="12" rx="1" />
                    <rect x="13.6" y="6" width="3.4" height="12" rx="1" />
                  </g>
                </svg>
                <span class="vp-wave"><i v-for="n in 12" :key="n"></i></span>
                <span class="vp-dur">{{ formatDuration(msg.audio.duration) }}″</span>
              </button>

              <p class="msg-text">{{ msg.content }}</p>
              <span class="msg-time">{{ msg.time }}</span>
            </div>
          </article>

          <!-- AI 正在输入：流式光标 -->
          <article v-if="showTypingIndicator" class="msg assistant streaming">
            <div class="msg-avatar"><span class="seal">玥</span></div>
            <div class="msg-body">
              <p class="msg-text"><span class="caret"></span></p>
            </div>
          </article>
        </div>

        <div class="stream-fade top" aria-hidden="true"></div>
        <div class="stream-fade bottom" aria-hidden="true"></div>
      </aside>
    </main>
  </div>
</template>

<script setup>
/**
 * VoiceAssistant.vue — AI 语音助手主聊天组件（「月夜 · 明珠」版）
 *
 * 功能：
 * - 文本对话 + 语音输入双模式
 * - 左舞台：玥珠光球 + 状态动词 + 实况字幕 + 输入坞
 * - 右对话流：无气泡双声部消息、印章头像、语音 pill、流式光标
 * - AI 语音回答后显示语音 pill，支持点击播放/暂停
 * - 底部输入框自动伸缩
 */
import { ref, computed, nextTick, watch, onUnmounted } from 'vue'
import { useVoiceChat } from '@/composables/useVoiceChat'
import OrbCanvas from '@/components/OrbCanvas.vue'
import ConversationHistory from '@/components/ConversationHistory.vue'

// ============================================================
// 设置（从 localStorage 持久化）
// ============================================================

const storedUrl = localStorage.getItem('voice_assistant_server_url')
const defaultUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/voice'
const serverUrl = ref(storedUrl && storedUrl.startsWith('ws') ? storedUrl : defaultUrl)

const audioFormat = ref(localStorage.getItem('voice_assistant_audio_format') || 'audio/webm')

watch(serverUrl, val => localStorage.setItem('voice_assistant_server_url', val))
watch(audioFormat, val => localStorage.setItem('voice_assistant_audio_format', val))

// ============================================================
// 组合式 API
// ============================================================

const emit = defineEmits(['open-settings'])

const { isRecording, isProcessing, isPlaying, status, transcript, response, mediaStream, startRecording, stopRecording, sendText, disconnect } = useVoiceChat({
  serverUrl,
  onTranscript(text) {
    addMessage('user', text)
  },
  onResponse(text) {
    addMessage('assistant', text, pendingAgent.value || null)
    pendingAgent.value = null
  },
  onAgentInfo(agent) {
    pendingAgent.value = agent
  },
  onAudioReady(url, duration) {
    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg && lastMsg.role === 'assistant') {
      lastMsg.audio = { url, duration, isPlaying: false }
    }
  },
  onError(err) {
    console.error('[VoiceAssistant] 错误:', err)
    addMessage('assistant', `⚠️ ${err.message || '发生错误，请重试'}`)
  }
})

// ============================================================
// 对话消息管理
// ============================================================

const messages = ref([])
const messageListRef = ref(null)
const inputText = ref('')
const inputRef = ref(null)
const pendingAgent = ref(null)
const showHistory = ref(false)

const httpBaseUrl = computed(() => {
  return serverUrl.value.replace(/^ws/, 'http').replace(/\/ws\/.*$/, '')
})

let isPressing = false

const showTypingIndicator = computed(() => {
  if (status.value !== 'processing') return false
  const last = messages.value[messages.value.length - 1]
  return !last || last.role !== 'assistant'
})

function addMessage(role, content, agent = null) {
  if (!content) return
  const now = new Date()
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  messages.value.push({ role, content, time, agent })
  nextTick(() => scrollToBottom())
}

function scrollToBottom() {
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

function clearMessages() {
  messages.value = []
}

/** 加载历史对话到聊天区 */
function loadConversation(data) {
  if (!data || !data.messages || data.messages.length === 0) return
  messages.value = data.messages.map(msg => {
    const now = new Date()
    return {
      role: msg.role,
      content: msg.content,
      time: `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`,
      agent: msg.agent || null
    }
  })
  nextTick(() => scrollToBottom())
}

function onSendText() {
  const text = inputText.value.trim()
  if (!text || status.value === 'processing') return
  addMessage('user', text)
  sendText(text)
  inputText.value = ''
  autoResize()
}

function autoResize() {
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
      const newHeight = Math.min(inputRef.value.scrollHeight, 100)
      inputRef.value.style.height = newHeight + 'px'
    }
  })
}

function onMicDown() {
  if (isPressing) return
  isPressing = true
  startRecording()
}

function onMicUp() {
  if (!isPressing) return
  isPressing = false
  stopRecording()
}

// ============================================================
// 语音气泡播放控制
// ============================================================

let currentVoiceAudio = null

function toggleVoicePlay(msg) {
  const audio = msg.audio
  if (!audio || !audio.url) return
  if (audio.isPlaying) {
    if (currentVoiceAudio) currentVoiceAudio.pause()
    audio.isPlaying = false
  } else {
    stopAllVoicePlay()
    const player = new Audio(audio.url)
    player.onended = () => {
      audio.isPlaying = false
      currentVoiceAudio = null
    }
    player.onerror = () => {
      audio.isPlaying = false
      currentVoiceAudio = null
    }
    player.play().catch(() => {
      audio.isPlaying = false
    })
    audio.isPlaying = true
    currentVoiceAudio = player
  }
}

function stopAllVoicePlay() {
  if (currentVoiceAudio) {
    currentVoiceAudio.pause()
    currentVoiceAudio = null
  }
  messages.value.forEach(msg => {
    if (msg.audio) msg.audio.isPlaying = false
  })
}

function formatDuration(seconds) {
  return seconds || 0
}

// ============================================================
// 展示层状态（月夜 · 明珠）
// ============================================================

/** 玥珠状态：录音→聆听，思考→思索，播报→应答，否则待机 */
const orbState = computed(() => {
  if (status.value === 'recording') return 'listening'
  if (status.value === 'processing') return 'thinking'
  if (isPlaying.value) return 'speaking'
  return 'idle'
})

const STATE_TEXT = {
  idle: { verb: '待机', sub: 'STANDBY' },
  listening: { verb: '聆听', sub: 'LISTENING' },
  thinking: { verb: '思索', sub: 'THINKING' },
  speaking: { verb: '应答', sub: 'SPEAKING' }
}

const stateVerb = computed(() => STATE_TEXT[orbState.value].verb)
const stateSub = computed(() => STATE_TEXT[orbState.value].sub)

/** 实况字幕 */
const captionText = computed(() => {
  switch (orbState.value) {
    case 'listening':
      return transcript.value || '我在听，请讲……'
    case 'thinking':
      return response.value || '稍候，正在为你组织回答……'
    case 'speaking':
      return response.value || '正在为你朗读回答……'
    default:
      return '轻触麦克风，或按住空格开始说话'
  }
})

/** 对话流头部时间标签 */
const _now = new Date()
const todayLabel = `今天 · ${String(_now.getHours()).padStart(2, '0')}:${String(_now.getMinutes()).padStart(2, '0')}`

/** 是否为智能体消息（非小玥本体） */
function isAgentMsg(msg) {
  return !!(msg.agent && msg.agent.display_name && msg.agent.display_name !== '小玥')
}

/** 印章首字：助手「玥」，智能体取 display_name 首字 */
function agentSeal(msg) {
  if (isAgentMsg(msg)) return msg.agent.display_name.charAt(0)
  return '玥'
}

// ============================================================
// 生命周期
// ============================================================

onUnmounted(() => {
  stopAllVoicePlay()
  disconnect()
})
defineExpose({ clearMessages })
</script>

<style scoped>
/* ============================================================
   VoiceAssistant — 「月夜 · 明珠」双栏布局
   左舞台（玥珠）· 右对话流
   ============================================================ */

.chat-wrapper {
  position: relative;
  width: 100%;
  flex: 1;
  display: flex;
  min-height: 0;
}

/* ---------- 主布局 ---------- */
.layout {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(360px, 0.88fr);
}

/* ═══════════ 舞台 ═══════════ */
.stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12px 48px 40px;
  min-width: 0;
}

.orb-wrap {
  position: relative;
  width: min(44vh, 420px);
  aspect-ratio: 1;
}

.orb-halo {
  position: absolute;
  inset: -22%;
  border-radius: 50%;
  pointer-events: none;
  background: radial-gradient(circle, var(--gold-glow) 0%, transparent 62%);
  opacity: 0.16;
  filter: blur(18px);
  animation: halo-breathe 7s ease-in-out infinite;
  transition: opacity 1.2s var(--ease);
}

.orb-wrap[data-state='listening'] .orb-halo {
  opacity: 0.3;
}
.orb-wrap[data-state='speaking'] .orb-halo {
  opacity: 0.34;
  animation-duration: 3.2s;
}
.orb-wrap[data-state='thinking'] .orb-halo {
  opacity: 0.22;
}

@keyframes halo-breathe {
  0%,
  100% {
    transform: scale(0.96);
  }
  50% {
    transform: scale(1.05);
  }
}

/* 状态动词 */
.state-line {
  margin-top: 26px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.state-verb {
  font-family: var(--serif);
  font-size: 34px;
  font-weight: 500;
  letter-spacing: 0.3em;
  text-indent: 0.3em; /* 视觉居中补偿 */
  color: var(--pearl);
  transition: opacity 0.5s var(--ease);
}

.state-rule {
  width: 42px;
  height: 1px;
  background: linear-gradient(90deg, var(--hair-warm), transparent);
}

.state-sub {
  font-size: 10px;
  letter-spacing: 0.42em;
  color: var(--faint);
}

.caption {
  margin-top: 16px;
  max-width: 34em;
  min-height: 3.4em;
  text-align: center;
  font-size: 14.5px;
  line-height: 1.85;
  color: var(--pearl-dim);
  transition: opacity 0.4s var(--ease);
}

/* ---------- 输入坞 ---------- */
.dock {
  margin-top: 26px;
  width: min(520px, 100%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px;
  border: 1px solid var(--hair-cool);
  border-radius: 999px;
  background: var(--glass);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  transition:
    border-color 0.4s var(--ease),
    box-shadow 0.4s var(--ease);
}

.dock:focus-within {
  border-color: var(--hair-warm);
  box-shadow:
    0 0 0 1px rgba(228, 181, 106, 0.08),
    0 12px 40px rgba(0, 0, 0, 0.35);
}

.mic {
  position: relative;
  flex-shrink: 0;
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  color: var(--gold-2);
  border-radius: 50%;
  border: 1px solid var(--hair-warm);
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.14), rgba(228, 181, 106, 0.03));
  transition:
    transform 0.2s var(--ease),
    box-shadow 0.3s var(--ease);
}

.mic svg {
  width: 17px;
  height: 17px;
}

.mic:hover {
  box-shadow: 0 0 18px rgba(228, 181, 106, 0.22);
}

.mic:active {
  transform: scale(0.93);
}

.mic:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.mic-ring {
  position: absolute;
  inset: -1px;
  border-radius: 50%;
  border: 1px solid var(--gold);
  opacity: 0;
  pointer-events: none;
}

.mic.listening .mic-ring {
  animation: mic-ping 1.6s var(--ease) infinite;
}

@keyframes mic-ping {
  0% {
    transform: scale(1);
    opacity: 0.7;
  }
  100% {
    transform: scale(1.65);
    opacity: 0;
  }
}

.dock-input {
  flex: 1;
  min-width: 0;
  padding: 0 10px;
  font-size: 14px;
  line-height: 28px;
  max-height: 100px;
  color: var(--pearl);
  resize: none;
  overflow-y: auto;
  align-self: center;
}

.dock-input::placeholder {
  color: var(--faint);
}

.send {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  color: var(--mist);
  border-radius: 50%;
  transition:
    color 0.25s var(--ease),
    background 0.25s var(--ease);
}

.send svg {
  width: 16px;
  height: 16px;
}

.send:hover:not(:disabled),
.send.active {
  color: var(--ink-0);
  background: var(--gold-2);
}

.send:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.dock-hint {
  margin-top: 13px;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--faint);
}

.dock-hint kbd {
  font-family: inherit;
  padding: 1px 6px;
  border: 1px solid var(--hair-cool);
  border-radius: 5px;
  color: var(--mist);
}

/* ═══════════ 对话流 ═══════════ */
.stream {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-left: 1px solid var(--hair-cool);
  background: linear-gradient(180deg, rgba(13, 18, 32, 0.35), rgba(13, 18, 32, 0.12));
}

.stream-head {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 22px 30px 16px;
}

.stream-head h2 {
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.22em;
  color: var(--pearl);
}

.stream-meta {
  flex: 1;
  font-size: 10.5px;
  letter-spacing: 0.18em;
  color: var(--faint);
}

.icon-btn {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  align-self: center;
  color: var(--mist);
  border: 1px solid transparent;
  border-radius: 10px;
  transition:
    color 0.25s var(--ease),
    border-color 0.25s var(--ease),
    background 0.25s var(--ease);
}

.icon-btn svg {
  width: 15px;
  height: 15px;
}

.icon-btn:hover {
  color: var(--gold-2);
  border-color: var(--hair-warm);
  background: rgba(228, 181, 106, 0.05);
}

.text-btn {
  font-size: 11.5px;
  letter-spacing: 0.1em;
  color: var(--mist);
  padding: 4px 10px;
  border-radius: 7px;
  transition:
    color 0.25s,
    background 0.25s;
}

.text-btn:hover {
  color: var(--gold-2);
  background: rgba(228, 181, 106, 0.06);
}

.stream-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 30px 40px;
  scrollbar-width: thin;
  scrollbar-color: var(--ink-3) transparent;
}

.stream-scroll::-webkit-scrollbar {
  width: 4px;
}
.stream-scroll::-webkit-scrollbar-thumb {
  background: var(--ink-3);
  border-radius: 2px;
}

.stream-empty {
  padding: 12px 2px;
  font-size: 12px;
  letter-spacing: 0.12em;
  color: var(--faint);
}

.stream-fade {
  position: absolute;
  left: 0;
  right: 0;
  height: 46px;
  pointer-events: none;
  z-index: 2;
}

.stream-fade.top {
  top: 58px;
  background: linear-gradient(180deg, rgba(11, 15, 26, 0.9), transparent);
}
.stream-fade.bottom {
  bottom: 0;
  background: linear-gradient(0deg, rgba(10, 13, 23, 0.95), transparent);
}

/* ---------- 消息 ---------- */
.msg {
  display: flex;
  gap: 13px;
  margin: 26px 0;
  animation: msg-in 0.6s var(--ease) both;
}

@keyframes msg-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.msg-avatar {
  flex-shrink: 0;
  padding-top: 2px;
}

.seal {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  font-family: var(--serif);
  font-size: 14.5px;
  font-weight: 600;
  color: var(--gold-2);
  border: 1px solid var(--hair-warm);
  border-radius: 8px;
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.1), rgba(228, 181, 106, 0.02));
}

.seal.agent {
  color: var(--celadon);
  border-color: rgba(159, 212, 203, 0.28);
  background: linear-gradient(160deg, rgba(159, 212, 203, 0.1), rgba(159, 212, 203, 0.02));
}

.msg-body {
  min-width: 0;
  max-width: 30em;
}

.msg.user {
  justify-content: flex-end;
}

.msg.user .msg-body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  text-align: right;
}

.msg-text {
  font-size: 14px;
  line-height: 1.95;
  color: var(--pearl);
  word-break: break-word;
  white-space: pre-wrap;
}

.msg.user .msg-text {
  color: var(--celadon);
}

.msg.user .msg-text,
.msg.user .voice-pill {
  opacity: 0.92;
}

.msg-time {
  display: block;
  margin-top: 7px;
  font-size: 10px;
  letter-spacing: 0.16em;
  color: var(--faint);
}

.agent-tag {
  display: inline-block;
  margin-bottom: 7px;
  font-family: var(--serif);
  font-size: 11px;
  letter-spacing: 0.24em;
  color: var(--celadon);
  opacity: 0.85;
}

/* 流式光标 */
.caret {
  display: inline-block;
  width: 2px;
  height: 1.05em;
  margin-left: 3px;
  vertical-align: -0.15em;
  background: var(--gold);
  animation: caret-blink 1s steps(2) infinite;
}

@keyframes caret-blink {
  50% {
    opacity: 0;
  }
}

/* ---------- 语音 pill ---------- */
.voice-pill {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 9px;
  padding: 9px 15px;
  border-radius: 999px;
  border: 1px solid var(--hair-warm);
  background: var(--glass-2);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  transition:
    border-color 0.3s var(--ease),
    box-shadow 0.3s var(--ease);
}

.msg.user .voice-pill {
  border-color: rgba(159, 212, 203, 0.26);
  flex-direction: row-reverse;
}

.voice-pill:hover {
  box-shadow: 0 0 16px rgba(228, 181, 106, 0.14);
}
.msg.user .voice-pill:hover {
  box-shadow: 0 0 16px rgba(159, 212, 203, 0.14);
}

.vp-play {
  width: 13px;
  height: 13px;
  color: var(--gold-2);
  flex-shrink: 0;
}

.msg.user .vp-play {
  color: var(--celadon);
}

.vp-wave {
  display: flex;
  align-items: center;
  gap: 2.5px;
  height: 16px;
}

.vp-wave i {
  width: 2px;
  border-radius: 1px;
  background: var(--gold);
  opacity: 0.65;
  transform-origin: center;
}

.msg.user .vp-wave i {
  background: var(--celadon);
}

/* 静态波形：固定高度节奏 */
.vp-wave i:nth-child(1) {
  height: 26%;
}
.vp-wave i:nth-child(2) {
  height: 52%;
}
.vp-wave i:nth-child(3) {
  height: 82%;
}
.vp-wave i:nth-child(4) {
  height: 58%;
}
.vp-wave i:nth-child(5) {
  height: 94%;
}
.vp-wave i:nth-child(6) {
  height: 66%;
}
.vp-wave i:nth-child(7) {
  height: 100%;
}
.vp-wave i:nth-child(8) {
  height: 48%;
}
.vp-wave i:nth-child(9) {
  height: 74%;
}
.vp-wave i:nth-child(10) {
  height: 40%;
}
.vp-wave i:nth-child(11) {
  height: 62%;
}
.vp-wave i:nth-child(12) {
  height: 30%;
}

/* 播放中：律动 */
.voice-pill.playing .vp-wave i {
  animation: vp-dance 0.9s ease-in-out infinite;
}
.voice-pill.playing .vp-wave i:nth-child(2n) {
  animation-delay: 0.12s;
}
.voice-pill.playing .vp-wave i:nth-child(3n) {
  animation-delay: 0.24s;
}
.voice-pill.playing .vp-wave i:nth-child(4n) {
  animation-delay: 0.06s;
}
.voice-pill.playing .vp-wave i:nth-child(5n) {
  animation-delay: 0.3s;
}

@keyframes vp-dance {
  0%,
  100% {
    transform: scaleY(0.45);
    opacity: 0.45;
  }
  50% {
    transform: scaleY(1);
    opacity: 1;
  }
}

.vp-dur {
  font-size: 11px;
  letter-spacing: 0.05em;
  color: var(--pearl-dim);
  font-variant-numeric: tabular-nums;
}

/* ---------- 响应式 ---------- */
@media (max-width: 1024px) {
  .layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(420px, 52vh);
  }

  .stage {
    padding: 24px 24px 36px;
  }

  .orb-wrap {
    width: min(30vh, 240px);
  }

  .state-verb {
    font-size: 26px;
  }

  .stream {
    border-left: none;
    border-top: 1px solid var(--hair-cool);
  }
}
</style>
