// useVoiceChat — 移动端语音对话核心

import { ref, computed, onUnmounted } from 'vue'
import { VADProcessor, createVADAnalyser } from './useVAD'
import { getWsUrl } from '@/api'

const CHUNK_INTERVAL_MS = 60
const HEARTBEAT_INTERVAL = 10

export function useVoiceChat(options = {}) {
  // 回调
  const onTranscript = options.onTranscript || (() => {})
  const onResponse = options.onResponse || (() => {})
  const onError = options.onError || (() => {})
  const onStatusChange = options.onStatusChange || (() => {})
  const onAudioReady = options.onAudioReady || (() => {})

  // 状态
  const isRecording = ref(false)
  const isProcessing = ref(false)
  const isPlaying = ref(false)
  const isConnected = ref(false)

  const status = computed(() => {
    if (isRecording.value) return 'listening'
    if (isProcessing.value) return 'thinking'
    if (isPlaying.value) return 'speaking'
    return 'idle'
  })

  // WebSocket
  let ws = null
  let reconnectTimer = null
  let heartbeatTimer = null

  // 录音
  let mediaRecorder = null
  let mediaStream = ref(null)

  // VAD
  let vadProcessor = null
  let vadAnalyser = null
  const enableVAD = options.enableVAD !== false

  // 音频播放
  let audioQueue = []
  let audioContext = null

  // 连接 WebSocket
  function connect() {
    if (ws?.readyState === WebSocket.OPEN) return

    try {
      const url = getWsUrl()
      console.log('[VoiceChat] 连接:', url)
      ws = new WebSocket(url)
      ws.binaryType = 'arraybuffer'
    } catch (err) {
      console.error('[VoiceChat] 连接失败:', err)
      onError(err)
      return
    }

    ws.onopen = () => {
      console.log('[VoiceChat] 已连接')
      isConnected.value = true
      startHeartbeat()
      onStatusChange('connected')
    }

    ws.onmessage = handleMessage
    ws.onclose = handleClose
    ws.onerror = handleError
  }

  function disconnect() {
    stopHeartbeat()
    clearTimeout(reconnectTimer)

    if (mediaRecorder?.state === 'recording') {
      stopRecording()
    }

    ws?.close()
    ws = null
    isConnected.value = false
  }

  function handleClose() {
    isConnected.value = false
    stopHeartbeat()
    onStatusChange('disconnected')
    scheduleReconnect()
  }

  function handleError(err) {
    console.error('[VoiceChat] 错误:', err)
    onError(err)
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, 3000)
  }

  // 心跳
  function startHeartbeat() {
    stopHeartbeat()
    heartbeatTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }))
      }
    }, HEARTBEAT_INTERVAL * 1000)
  }

  function stopHeartbeat() {
    clearInterval(heartbeatTimer)
  }

  // 消息处理
  function handleMessage(event) {
    if (event.data instanceof ArrayBuffer) {
      handleBinaryMessage(event.data)
    } else {
      handleTextMessage(event.data)
    }
  }

  function handleTextMessage(raw) {
    try {
      const msg = JSON.parse(raw)

      switch (msg.type) {
        case 'text':
          onResponse(msg.text)
          isProcessing.value = false
          break

        case 'stream_delta':
          onResponse(msg.delta, true)
          break

        case 'stream_end':
          onResponse(msg.full_text, false, true)
          isProcessing.value = false
          break

        case 'error':
          onError(new Error(msg.message))
          isProcessing.value = false
          break

        case 'end':
          isProcessing.value = false
          break
      }
    } catch (e) {
      console.error('[VoiceChat] 消息解析失败:', e)
    }
  }

  function handleBinaryMessage(buffer) {
    // 解析二进制帧
    const view = new DataView(buffer)
    const frameType = view.getUint8(0)

    if (frameType === 0x01) {
      // 音频数据
      const headerLen = view.getUint32(1, false)
      const header = JSON.parse(new TextDecoder().decode(buffer.slice(5, 5 + headerLen)))
      const audioData = buffer.slice(5 + headerLen)

      playAudio(audioData, header.format)
    } else if (frameType === 0x02) {
      // 播放结束
      isPlaying.value = false
    }
  }

  // 音频播放
  async function playAudio(data, format = 'mp3') {
    try {
      if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)()
      }

      const audioBuffer = await audioContext.decodeAudioData(data.slice(0))
      const source = audioContext.createBufferSource()
      source.buffer = audioBuffer
      source.connect(audioContext.destination)
      source.start(0)

      isPlaying.value = true
      source.onended = () => {
        isPlaying.value = false
      }
    } catch (err) {
      console.error('[VoiceChat] 播放失败:', err)
    }
  }

  // 录音
  async function startRecording() {
    if (isRecording.value || isProcessing.value) return

    try {
      mediaStream.value = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      })

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

      mediaRecorder = new MediaRecorder(mediaStream.value, { mimeType })

      // 启动 VAD
      if (enableVAD) {
        setupVAD(mediaStream.value)
      }

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && ws?.readyState === WebSocket.OPEN) {
          sendAudioChunk(event.data)
        }
      }

      mediaRecorder.onstop = () => {
        mediaStream.value?.getTracks().forEach(t => t.stop())
        mediaStream.value = null
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'audio_end' }))
        }
        isRecording.value = false
      }

      mediaRecorder.start(CHUNK_INTERVAL_MS)
      isRecording.value = true
      onStatusChange('recording')
    } catch (err) {
      console.error('[VoiceChat] 录音失败:', err)
      onError(err)
    }
  }

  function stopRecording() {
    if (mediaRecorder?.state === 'recording') {
      mediaRecorder.stop()
      isProcessing.value = true
      onStatusChange('processing')
    }
  }

  function sendAudioChunk(blob) {
    const reader = new FileReader()
    reader.onloadend = () => {
      const base64 = reader.result.split(',')[1]
      ws?.send(JSON.stringify({
        type: 'audio',
        data: base64,
        format: 'webm',
        sample_rate: 16000
      }))
    }
    reader.readAsDataURL(blob)
  }

  // VAD
  function setupVAD(stream) {
    vadProcessor = new VADProcessor({
      silenceTimeoutMs: 800,
      speechThreshold: 0.018,
      onSpeechEnd: () => {
        if (isRecording.value && mediaRecorder?.state === 'recording') {
          console.log('[VoiceChat] VAD 自动断句')
          stopRecording()
        }
      }
    })

    vadAnalyser = createVADAnalyser(stream, vadProcessor, {
      sampleRate: 16000,
      intervalMs: 50
    })
  }

  function cleanupVAD() {
    vadAnalyser?.stop()
    vadAnalyser = null
    vadProcessor?.destroy()
    vadProcessor = null
  }

  // 文本发送
  function sendText(text) {
    if (!text?.trim()) return
    if (ws?.readyState !== WebSocket.OPEN) {
      onError(new Error('连接未建立'))
      return
    }

    ws.send(JSON.stringify({
      type: 'text',
      text: text.trim()
    }))
    isProcessing.value = true
    onStatusChange('processing')
  }

  // 清理
  onUnmounted(() => {
    disconnect()
    cleanupVAD()
  })

  // 自动连接
  connect()

  return {
    // 状态
    isRecording,
    isProcessing,
    isPlaying,
    isConnected,
    status,
    // 方法
    startRecording,
    stopRecording,
    sendText,
    connect,
    disconnect
  }
}
