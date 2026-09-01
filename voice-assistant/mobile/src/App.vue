<template>
  <router-view />
</template>

<script setup>
import { Capacitor } from '@capacitor/core'

// Capacitor 环境标记
if (Capacitor.isNativePlatform()) {
  document.body.classList.add('capacitor-android')
  console.log('[小玥] 运行在 Android App 中')
}
</script>

<style>
/* 全局样式已在 styles/main.css 中定义 */
</style>
