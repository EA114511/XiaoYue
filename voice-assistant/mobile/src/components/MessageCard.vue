<template>
  <div class="message-card" :class="message.role">
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
  margin: 8px 0;
  padding: 12px 16px;
  border-radius: 12px;
  max-width: 85%;
}

.message-card.user {
  margin-left: auto;
  background: linear-gradient(160deg, rgba(159, 212, 203, 0.15), rgba(159, 212, 203, 0.05));
  border: 1px solid rgba(159, 212, 203, 0.2);
}

.message-card.assistant {
  margin-right: auto;
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.12), rgba(228, 181, 106, 0.04));
  border: 1px solid rgba(228, 181, 106, 0.15);
}

.text {
  font-size: 15px;
  line-height: 1.6;
  color: var(--pearl);
  margin: 0;
}

.time {
  display: block;
  font-size: 11px;
  color: var(--mist);
  margin-top: 6px;
  text-align: right;
}
</style>
