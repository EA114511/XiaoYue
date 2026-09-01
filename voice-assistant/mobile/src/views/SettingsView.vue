<template>
  <div class="settings-view">
    <!-- 星野背景 -->
    <NightSky />

    <!-- 顶栏 -->
    <header class="top-bar">
      <button class="back-btn" @click="goBack" aria-label="返回">
        <van-icon name="arrow-left" size="20" />
      </button>
      <h1 class="page-title">设置</h1>
      <div class="placeholder"></div>
    </header>

    <div class="settings-content">
      <!-- NAS 配置 -->
      <section class="setting-group">
        <h2 class="group-title">服务器配置</h2>
        <div class="setting-item">
          <label class="item-label">NAS 地址</label>
          <input
            v-model="nasUrl"
            type="text"
            class="item-input"
            placeholder="http://192.168.5.5:8000"
          />
        </div>
        <div class="setting-item">
          <label class="item-label">连接状态</label>
          <span class="status-badge" :class="{ connected: isConnected }">
            {{ isConnected ? '已连接' : '未连接' }}
          </span>
        </div>
      </section>

      <!-- 语音配置 -->
      <section class="setting-group">
        <h2 class="group-title">语音设置</h2>
        <div class="setting-item">
          <label class="item-label">唤醒词</label>
          <span class="item-value">小玥小玥</span>
        </div>
        <div class="setting-item">
          <label class="item-label">语音打断</label>
          <label class="switch">
            <input type="checkbox" v-model="bargeInEnabled" />
            <span class="slider"></span>
          </label>
        </div>
        <div class="setting-item">
          <label class="item-label">VAD 自动断句</label>
          <label class="switch">
            <input type="checkbox" v-model="vadEnabled" />
            <span class="slider"></span>
          </label>
        </div>
      </section>

      <!-- 关于 -->
      <section class="setting-group">
        <h2 class="group-title">关于</h2>
        <div class="setting-item">
          <label class="item-label">版本</label>
          <span class="item-value">1.0.0</span>
        </div>
        <div class="setting-item">
          <label class="item-label">设计主题</label>
          <span class="item-value">月夜 · 明珠</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores'
import NightSky from '@/components/NightSky.vue'

const router = useRouter()
const store = useAppStore()

const nasUrl = ref('')
const bargeInEnabled = ref(true)
const vadEnabled = ref(true)
const isConnected = ref(false)

function goBack() {
  router.back()
}

onMounted(() => {
  nasUrl.value = store.nasUrl
})
</script>

<style scoped>
.settings-view {
  position: relative;
  min-height: 100vh;
  min-height: 100dvh;
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

.back-btn {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  color: var(--mist);
  border-radius: 10px;
  transition: all 0.25s ease;
}

.back-btn:active {
  background: rgba(228, 181, 106, 0.1);
  color: var(--gold-2);
}

.page-title {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.15em;
  color: var(--pearl);
  margin: 0;
}

.placeholder {
  width: 40px;
}

/* ---------- 设置内容 ---------- */
.settings-content {
  padding: 16px 20px;
  padding-bottom: calc(20px + env(safe-area-inset-bottom));
}

.setting-group {
  margin-bottom: 28px;
}

.group-title {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.15em;
  color: var(--mist);
  margin: 0 0 12px 4px;
}

.setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: linear-gradient(160deg, rgba(27, 35, 64, 0.4), rgba(13, 18, 32, 0.3));
  border: 1px solid var(--hair-cool);
  border-radius: 12px;
  margin-bottom: 10px;
}

.item-label {
  font-size: 14px;
  color: var(--pearl);
}

.item-value {
  font-size: 14px;
  color: var(--mist);
}

.item-input {
  flex: 1;
  max-width: 200px;
  padding: 8px 12px;
  font-size: 14px;
  color: var(--pearl);
  background: rgba(9, 12, 20, 0.5);
  border: 1px solid var(--hair-cool);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.25s ease;
}

.item-input:focus {
  border-color: var(--gold);
}

.item-input::placeholder {
  color: var(--faint);
}

/* ---------- 状态徽章 ---------- */
.status-badge {
  padding: 4px 12px;
  font-size: 12px;
  border-radius: 12px;
  background: rgba(126, 142, 166, 0.15);
  color: var(--mist);
}

.status-badge.connected {
  background: rgba(159, 212, 203, 0.15);
  color: var(--celadon);
}

/* ---------- 开关 ---------- */
.switch {
  position: relative;
  width: 44px;
  height: 24px;
  display: inline-block;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(126, 142, 166, 0.3);
  border-radius: 24px;
  transition: 0.3s;
}

.slider::before {
  position: absolute;
  content: '';
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background: var(--pearl);
  border-radius: 50%;
  transition: 0.3s;
}

.switch input:checked + .slider {
  background: var(--gold);
}

.switch input:checked + .slider::before {
  transform: translateX(20px);
  background: var(--ink-0);
}
</style>
