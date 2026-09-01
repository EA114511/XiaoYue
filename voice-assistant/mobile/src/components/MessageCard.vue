<template>
  <div class="message-card" :class="message.role">
    <div class="avatar" v-if="message.role !== 'user'">
      <span class="seal">{{ message.role === 'assistant' ? '玥' : '小' }}</span>
    </div>
    <div class="content">
      <p class="text">{{ message.content }}</p>
      <span class="time">{{ message.time }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  message: {
    type: Object,
    required: true
  }
})
</script>

<style scoped>
.message-card {
  display: flex;
  gap: 10px;
  margin: 10px 0;
  padding: 12px 14px;
  border-radius: 14px;
  max-width: 88%;
  animation: msg-in 0.4s ease both;
}

@keyframes msg-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-card.user {
  margin-left: auto;
  flex-direction: row-reverse;
  background: linear-gradient(160deg, rgba(159, 212, 203, 0.18), rgba(159, 212, 203, 0.06));
  border: 1px solid rgba(159, 212, 203, 0.22);
}

.message-card.assistant {
  margin-right: auto;
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.14), rgba(228, 181, 106, 0.05));
  border: 1px solid rgba(228, 181, 106, 0.18);
}

.avatar {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
}

.seal {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 13px;
  font-weight: 600;
  color: var(--gold-2);
  border: 1px solid var(--hair-warm);
  border-radius: 8px;
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.1), rgba(228, 181, 106, 0.02));
}

.message-card.user .seal {
  color: var(--celadon);
  border-color: rgba(159, 212, 203, 0.25);
  background: linear-gradient(160deg, rgba(159, 212, 203, 0.1), rgba(159, 212, 203, 0.02));
}

.content {
  min-width: 0;
}

.text {
  font-size: 14px;
  line-height: 1.65;
  color: var(--pearl);
  margin: 0;
  word-break: break-word;
}

.message-card.user .text {
  color: var(--celadon);
}

.time {
  display: block;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--faint);
  margin-top: 6px;
}

.message-card.user .time {
  text-align: right;
}
</style>
