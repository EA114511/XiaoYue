/**
 * useWakeWord — 唤醒词检测（浏览器 SpeechRecognition API 方案）
 *
 * 功能：
 * - 持续监听麦克风，识别预设唤醒词（如「小玥小玥」）
 * - 唤醒成功后触发 onWake 回调
 * - 自动重启监听，支持连续唤醒
 *
 * 说明：
 * - 基于 window.SpeechRecognition / window.webkitSpeechRecognition
 * - 无需额外 npm 依赖
 * - 浏览器支持：Chrome / Edge 较好，Firefox 有限，Safari 部分支持
 * - 注意：部分浏览器会将识别数据上传至厂商服务器，使用时请注意隐私
 */

export function useWakeWord({ onWake, wakeWords = ['小玥小玥', '小月小月'], confidenceThreshold = 0.5 } = {}) {
  let recognition = null
  let isListening = false
  let restartTimer = null
  let enabled = true

  function isSupported() {
    const supported = !!(window.SpeechRecognition || window.webkitSpeechRecognition)
    if (!supported) {
      console.warn('[useWakeWord] 当前环境不支持唤醒词，将降级为按住说话')
      // Android WebView 中 SpeechRecognition 通常不可用
      if (navigator.userAgent.includes('Android')) {
        console.warn('[useWakeWord] Android WebView 环境，唤醒词功能不可用')
      }
    }
    return supported
  }

  function createRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return null

    const rec = new SR()
    rec.continuous = true
    rec.interimResults = true
    rec.lang = 'zh-CN'
    rec.maxAlternatives = 3

    rec.onresult = event => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        const transcript = result[0].transcript.trim()
        const confidence = result[0].confidence || 0

        if (confidence < confidenceThreshold) continue

        const hit = wakeWords.some(w => transcript.includes(w))
        if (hit) {
          rec.stop()
          onWake(transcript)
          return
        }
      }
    }

    rec.onerror = event => {
      console.warn('[useWakeWord] 识别错误:', event.error)
      // 某些错误（如 no-speech / audio-capture）可自动重启
      if (event.error === 'no-speech' || event.error === 'audio-capture') {
        scheduleRestart()
      }
    }

    rec.onend = () => {
      isListening = false
      // 仅在仍启用时自动重启
      if (enabled) {
        scheduleRestart()
      }
    }

    return rec
  }

  function scheduleRestart() {
    clearTimeout(restartTimer)
    restartTimer = setTimeout(() => {
      if (enabled && !isListening) {
        start()
      }
    }, 300)
  }

  function start() {
    if (!isSupported()) {
      console.warn('[useWakeWord] 当前浏览器不支持 SpeechRecognition')
      return false
    }

    if (isListening) return true

    if (!recognition) {
      recognition = createRecognition()
      if (!recognition) return false
    }

    try {
      recognition.start()
      isListening = true
      return true
    } catch (err) {
      console.warn('[useWakeWord] 启动失败:', err)
      return false
    }
  }

  function stop() {
    enabled = false
    clearTimeout(restartTimer)
    if (recognition) {
      try {
        recognition.stop()
      } catch {}
    }
    isListening = false
  }

  function resume() {
    enabled = true
    start()
  }

  function release() {
    stop()
    recognition = null
  }

  return {
    start,
    stop,
    resume,
    release,
    isListening: () => isListening,
    isSupported
  }
}
