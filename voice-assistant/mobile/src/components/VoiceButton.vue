<template>
  <div class="voice-button" :class="{ recording: recording, processing: processing }">
    <button
      class="btn"
      @touchstart="handleTouchStart"
      @touchend="handleTouchEnd"
      @mousedown="handleTouchStart"
      @mouseup="handleTouchEnd"
      :disabled="disabled"
    >
      <van-icon v-if="processing" name="more" class="icon loading" />
      <van-icon v-else-if="recording" name="stop" class="icon" />
      <van-icon v-else name="volume" class="icon" />
    </button>
    <p class="label">{{ label }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  recording: Boolean,
  processing: Boolean,
  disabled: Boolean
})

const emit = defineEmits(['touchstart', 'touchend'])

const label = computed(() => {
  if (props.processing) return '正在处理...'
  if (props.recording) return '松开结束'
  return '按住说话'
})

function handleTouchStart(e) {
  e.preventDefault()
  emit('touchstart')
}

function handleTouchEnd(e) {
  e.preventDefault()
  emit('touchend')
}
</script>

<style scoped>
.voice-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.btn {
  width: var(--button-size, 72px);
  height: var(--button-size, 72px);
  border-radius: 50%;
  border: 2px solid var(--hair-warm);
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.2), rgba(228, 181, 106, 0.05));
  color: var(--gold);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
  touch-action: none;
  -webkit-tap-highlight-color: transparent;
}

.btn:active {
  transform: scale(0.95);
  background: var(--gold);
  color: var(--ink-0);
}

.btn:disabled {
  opacity: 0.5;
}

.voice-button.recording .btn {
  background: var(--celadon);
  border-color: var(--celadon);
  color: var(--ink-0);
  animation: pulse 1.5s ease-in-out infinite;
}

.voice-button.processing .btn {
  background: var(--mist);
  border-color: var(--mist);
}

.icon {
  font-size: 28px;
}

.icon.loading {
  animation: spin 1s linear infinite;
}

@keyframes pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(159, 212, 203, 0.4);
  }
  50% {
    box-shadow: 0 0 0 12px rgba(159, 212, 203, 0);
  }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.label {
  font-size: 14px;
  color: var(--mist);
  letter-spacing: 0.05em;
}
</style>
