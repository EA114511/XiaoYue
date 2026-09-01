<template>
  <div class="settings-view">
    <!-- 顶栏 -->
    <van-nav-bar
      title="设置"
      left-arrow
      fixed
      placeholder
      @click-left="goBack"
    />

    <div class="settings-content">
      <!-- NAS 配置 -->
      <van-cell-group inset title="服务器配置">
        <van-field
          v-model="nasUrl"
          label="NAS 地址"
          placeholder="http://192.168.5.5:8000"
          :error-message="nasUrlError"
        />
        <van-cell title="连接状态" :value="isConnected ? '已连接' : '未连接'" />
      </van-cell-group>

      <!-- 语音配置 -->
      <van-cell-group inset title="语音设置">
        <van-cell title="唤醒词" value="小玥小玥" />
        <van-cell title="语音打断" center>
          <template #right-icon>
            <van-switch v-model="bargeInEnabled" size="22" />
          </template>
        </van-cell>
        <van-cell title="VAD 自动断句" center>
          <template #right-icon>
            <van-switch v-model="vadEnabled" size="22" />
          </template>
        </van-cell>
      </van-cell-group>

      <!-- 关于 -->
      <van-cell-group inset title="关于">
        <van-cell title="版本" value="1.0.0" />
        <van-cell title="设计主题" value="月夜 · 明珠" />
      </van-cell-group>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores'
import { STORAGE_KEYS } from '@/utils/constants'

const router = useRouter()
const store = useAppStore()

const nasUrl = ref('')
const nasUrlError = ref('')
const bargeInEnabled = ref(true)
const vadEnabled = ref(true)

const isConnected = ref(false)

function goBack() {
  router.back()
}

function validateAndSave() {
  if (!nasUrl.value.startsWith('http')) {
    nasUrlError.value = '请输入正确的 URL，以 http:// 或 https:// 开头'
    return
  }
  nasUrlError.value = ''
  store.setNasUrl(nasUrl.value)
}

onMounted(() => {
  nasUrl.value = store.nasUrl
})
</script>

<style scoped>
.settings-view {
  min-height: 100vh;
  background: var(--ink-0);
}

.settings-content {
  padding: 16px 0;
}

:deep(.van-cell-group--inset) {
  margin: 16px;
  border-radius: 12px;
  background: var(--ink-1);
  border: 1px solid var(--hair-cool);
  overflow: hidden;
}

:deep(.van-cell) {
  background: transparent;
  color: var(--pearl);
}

:deep(.van-cell::after) {
  border-bottom-color: var(--hair-cool);
}

:deep(.van-cell__title) {
  color: var(--pearl);
}

:deep(.van-cell__value) {
  color: var(--mist);
}

:deep(.van-field__label) {
  color: var(--pearl);
}

:deep(.van-field__control) {
  color: var(--pearl);
}
</style>
