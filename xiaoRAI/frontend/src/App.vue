<template>
  <div class="app-container">
    <!-- 环境层：星野、aurora 渐变、颗粒 -->
    <NightSky />
    <div class="aurora" aria-hidden="true"></div>
    <div class="grain" aria-hidden="true"></div>

    <!-- 顶栏 -->
    <header class="topbar">
      <div class="brand">
        <span class="brand-seal">玥</span>
        <div class="brand-text">
          <h1>小玥</h1>
          <span class="brand-sub">XIAOYUE&nbsp;·&nbsp;VOICE&nbsp;ASSISTANT</span>
        </div>
      </div>

      <div class="top-meta">
        <!-- 模型状态 chip：本地=青瓷色，远程=暖金色 -->
        <span v-if="configLoaded" class="model-chip" :class="usingLocalLLM ? 'local' : 'remote'">
          <i class="chip-dot"></i>
          <span>{{ usingLocalLLM ? `本地 · ${localModelName || 'Ollama'}` : '远程 AI' }}</span>
        </span>
        <button class="icon-btn" title="设置" aria-label="设置" @click="showConfig = !showConfig">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3.2" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </div>
    </header>

    <!-- 聊天主界面 -->
    <main class="chat-main">
      <VoiceAssistant ref="chatRef" @open-settings="showConfig = true" />
    </main>

    <!-- 配置面板 -->
    <Transition name="fade">
      <VoiceConfig v-if="showConfig" @close="showConfig = false" />
    </Transition>
  </div>
</template>

<script setup>
/**
 * App.vue — 应用根组件
 *
 * 顶部导航栏 + 聊天主界面 + 配置面板弹窗。
 * 启动时自动检查后端配置状态，未配置 Key 时自动切换到本地大模型。
 */
import { ref, onMounted, onUnmounted } from 'vue'
import VoiceAssistant from './components/VoiceAssistant.vue'
import VoiceConfig from './components/VoiceConfig.vue'
import NightSky from './components/NightSky.vue'

// ============================================================
// 状态
// ============================================================

const configLoaded = ref(false)
const usingLocalLLM = ref(false)
const localModelName = ref('')
const showConfig = ref(false)
const chatRef = ref(null)

const SETTINGS_API = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/settings`
let pollTimer = null

// ============================================================
// 加载配置
// ============================================================

async function loadConfig() {
  try {
    const resp = await fetch(SETTINGS_API)
    if (resp.ok) {
      const data = await resp.json()
      usingLocalLLM.value = data.using_local_llm === true
      localModelName.value = data.local_llm_model || ''
      configLoaded.value = true
    }
  } catch {
    /* 后端不可用时静默处理 */
  }
}

// ============================================================
// 生命周期
// ============================================================

onMounted(() => {
  loadConfig()
  pollTimer = setInterval(loadConfig, 10000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
/* ============================================================
   App.vue 根组件样式 — 「月夜 · 明珠」
   ============================================================ */

.app-container {
  position: relative;
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--ink-0);
  overflow: hidden;
}

/* ---- 顶栏 ---- */
.topbar {
  position: relative;
  z-index: 5;
  height: 72px;
  flex-shrink: 0;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-seal {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  font-family: var(--serif);
  font-size: 20px;
  font-weight: 600;
  color: var(--gold-2);
  border: 1px solid var(--hair-warm);
  border-radius: 9px;
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.1), rgba(228, 181, 106, 0.02));
  box-shadow: inset 0 0 12px rgba(228, 181, 106, 0.06);
}

.brand-text h1 {
  font-family: var(--serif);
  font-size: 19px;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: var(--pearl);
}

.brand-sub {
  display: block;
  margin-top: 2px;
  font-size: 9.5px;
  letter-spacing: 0.32em;
  color: var(--faint);
}

.top-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ---- 模型状态 chip ---- */
.model-chip {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 13px;
  font-size: 11.5px;
  letter-spacing: 0.06em;
  border-radius: 999px;
  white-space: nowrap;
}

.model-chip.local {
  color: var(--celadon);
  border: 1px solid rgba(159, 212, 203, 0.22);
  background: rgba(159, 212, 203, 0.05);
}

.model-chip.remote {
  color: var(--gold-2);
  border: 1px solid var(--hair-warm);
  background: rgba(228, 181, 106, 0.05);
}

.chip-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 6px currentColor;
  animation: chip-breathe 3s ease-in-out infinite;
}

@keyframes chip-breathe {
  0%,
  100% {
    opacity: 0.45;
  }
  50% {
    opacity: 1;
  }
}

/* ---- 图标按钮 ---- */
.icon-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  color: var(--mist);
  border: 1px solid transparent;
  border-radius: 10px;
  transition:
    color 0.25s var(--ease),
    border-color 0.25s var(--ease),
    background 0.25s var(--ease);
}

.icon-btn svg {
  width: 17px;
  height: 17px;
}

.icon-btn:hover {
  color: var(--gold-2);
  border-color: var(--hair-warm);
  background: rgba(228, 181, 106, 0.05);
}

/* ---- 聊天主体 ---- */
.chat-main {
  position: relative;
  z-index: 4;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* ---- 过渡动画 ---- */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s var(--ease);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ---- 响应式 ---- */
@media (max-width: 1024px) {
  .app-container {
    height: auto;
    min-height: 100vh;
    min-height: 100dvh;
    overflow: visible;
  }

  .topbar {
    padding: 0 20px;
  }
}
</style>
