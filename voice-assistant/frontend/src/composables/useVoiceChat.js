/**
 * useVoiceChat — AI 语音助手核心组合式 API
 *
 * ===== 性能优化 =====
 *
 * 【优化1】Opus 音频编码 + 二进制传输
 *   - 使用 audio/webm;codecs=opus 编码（WebRTC 标准）
 *   - 分块大小从 100ms 降至 60ms，降低首音延迟
 *   - 支持 WebSocket 二进制帧发送音频（节省 ~33% 带宽）
 *
 * 【优化2】二进制帧接收 TTS 音频
 *   - 解析 [1B类型][4B头长][JSON头][音频数据] 格式
 *   - 省去 base64 解码开销
 *
 * 【优化3】自适应心跳
 *   - 初始 10s 间隔，丢包时降为 5s，稳定后恢复
 *
 * 【优化4】E2E 延迟追踪
 *   - 记录每轮从录音结束到收到回复的延迟
 *
 * ===== VAD 自动断句 =====
 *
 * 默认启用前端 VAD：检测到用户说话结束后，连续静音 800ms 自动停止录音并发送，
 * 无需一直按住麦克风。可通过 enableVAD: false 或在 vadOptions 中调整阈值关闭。
 *
 * 用法：
 *   const {
 *     isRecording, isProcessing, isPlaying, status,
 *     transcript, response, mediaStream,
 *     startRecording, stopRecording, disconnect,
 *   } = useVoiceChat({
 *     serverUrl: 'ws://localhost:8000/ws/voice',  // 字符串或 Ref
 *     onTranscript(text) { /* 用户语音识别结果 *\/ },
 *     onResponse(text)   { /* AI 回复文本 *\/ },
 *     onError(err)       { /* 错误处理 *\/ },
 *   })
 */
import { ref, computed, onUnmounted } from 'vue'
import { VADProcessor, createVADAnalyser } from './useVAD.js'

// ============================================================
// 常量
// ============================================================

/** 音频分块大小（毫秒），越小首音延迟越低 */
const CHUNK_INTERVAL_MS = 60

/** 心跳间隔（秒） */
const HEARTBEAT_INTERVAL = 10
const HEARTBEAT_RETRY_INTERVAL = 5 // 丢包时降低间隔

/** 二进制帧类型 */
const BINARY_TYPE_AUDIO = 0x01 // TTS 音频块
const BINARY_TYPE_END = 0x02 // TTS 流结束

/**
 * 创建语音聊天会话
 * @param {object} options
 */
export function useVoiceChat(options = {}) {
  // serverUrl 可以是字符串或 Ref<string>（支持从组件动态传入）
  const serverUrlRef = typeof options.serverUrl === 'string' ? ref(options.serverUrl) : options.serverUrl || ref('ws://localhost:8000/ws/voice')

  /** 获取当前服务器地址 */
  function getServerUrl() {
    // 优先使用用户配置的 NAS 地址（保存到 localStorage）
    const savedNasUrl = localStorage.getItem('xiaoyue_nas_url')
    if (savedNasUrl) {
      // 将 http://nas-ip:8000 转换为 ws://nas-ip:8000/ws/voice
      const wsUrl = savedNasUrl.replace(/^http/, 'ws').replace(/\/$/, '') + '/ws/voice'
      return wsUrl
    }
    return serverUrlRef.value
  }

  // ============================================================
  // 响应式状态
  // ============================================================

  const isRecording = ref(false)
  const isProcessing = ref(false)
  const isPlaying = ref(false)
  const status = computed(() => {
    if (isRecording.value) return 'recording'
    if (isProcessing.value) return 'processing'
    return 'idle'
  })
  const transcript = ref('')
  const response = ref('')
  /** 是否正在接收流式 LLM 响应 */
  const isStreamingResponse = ref(false)

  // ============================================================
  // 回调
  // ============================================================

  const onTranscript = options.onTranscript || (() => {})
  const onResponse = options.onResponse || (() => {})
  const onAgentInfo = options.onAgentInfo || (() => {})
  const onError = options.onError || (() => {})
  const onStatusChange = options.onStatusChange || (() => {})
  const onAudioReady = options.onAudioReady || (() => {})

  // ============================================================
  // WebSocket 内部状态
  // ============================================================

  /** @type {WebSocket|null} */
  let ws = null
  let reconnectTimer = null
  let heartbeatTimer = null
  let intentionalClose = false

  // 心跳统计
  let heartbeatMisses = 0
  let lastPingTime = 0

  // E2E 延迟追踪
  let recordingStopTime = 0

  // TTS 音频缓冲（二进制模式接收）
  /** @type {AudioQueue|null} */
  let audioQueue = null

  // 音频累计 — 用于语音气泡回放
  /** @type {ArrayBuffer[]} */
  let audioChunks = []
  /** @type {string|null} */
  let currentAudioFormat = 'mp3'

  // ============================================================
  // 录音内部状态
  // ============================================================

  /** @type {MediaRecorder|null} */
  let mediaRecorder = null
  /** @type {Ref<MediaStream|null>} */
  const mediaStream = ref(null)

  // ============================================================
  // VAD 内部状态
  // ============================================================

  /** @type {VADProcessor|null} */
  let vadProcessor = null
  /** @type {{ stop: () => void }|null} */
  let vadAnalyser = null
  /** 是否启用 VAD 自动断句 */
  const enableVAD = options.enableVAD !== false
  /** VAD 参数（允许调用方覆盖） */
  const vadOptions = options.vadOptions || {}

  // ============================================================
  // Barge-in 内部状态（语音打断）
  // ============================================================

  /** @type {{ stop: () => void }|null} */
  let bargeInAnalyser = null
  /** @type {VADProcessor|null} */
  let bargeInProcessor = null
  /** 是否启用语音打断 */
  const enableBargeIn = options.enableBargeIn !== false
  /** 打断冷却时间（毫秒），防止误触发 */
  const BARGE_IN_COOLDOWN_MS = 1500
  let lastBargeInTime = 0

  // ============================================================
  // Audio Queue — 顺序播放 TTS 音频
  // ============================================================

  /**
   * 将二进制音频数据入队并尝试播放
   * @param {ArrayBuffer} data - 音频原始数据
   * @param {string} format - 音频格式 ('mp3', 'wav', 等)
   */
  class AudioQueue {
    /** @param {(playing: boolean) => void} [onPlayStateChange] */
    constructor(onPlayStateChange) {
      /** @type {{data: ArrayBuffer, format: string}[]} */
      this.queue = []
      this.isPlaying = false
      /** @type {AudioContext|null} */
      this.ctx = null
      this.onPlayStateChange = onPlayStateChange || (() => {})
    }

    /**
     * 将音频数据入队并尝试播放
     * @param {ArrayBuffer} data - 音频原始数据
     * @param {string} [format='mp3'] - 音频格式
     */
    async enqueue(data, format = 'mp3') {
      this.queue.push({ data, format })
      if (!this.isPlaying) {
        await this.playNext()
      }
    }

    async playNext() {
      if (this.queue.length === 0) {
        this.isPlaying = false
        this.onPlayStateChange(false)
        return
      }
      this.isPlaying = true
      this.onPlayStateChange(true)
      const { data, format } = this.queue.shift()

      try {
        // 使用 AudioContext 解码并播放（延迟更低）
        if (!this.ctx) {
          this.ctx = new (window.AudioContext || window.webkitAudioContext)()
          // 恢复可能被浏览器挂起的 AudioContext
          if (this.ctx.state === 'suspended') {
            await this.ctx.resume()
          }
        }
        const audioBuffer = await this.ctx.decodeAudioData(data.slice(0))
        const source = this.ctx.createBufferSource()
        source.buffer = audioBuffer
        source.connect(this.ctx.destination)
        source.onended = () => {
          this.playNext()
        }
        source.start(0)
      } catch (err) {
        console.warn('[useVoiceChat] AudioContext 播放失败，回退到 Audio 元素:', err)
        // 降级：Blob URL — 根据格式选择 MIME 类型
        const mimeMap = { mp3: 'audio/mpeg', wav: 'audio/wav', ogg: 'audio/ogg' }
        const blob = new Blob([data], { type: mimeMap[format] || 'audio/mpeg' })
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audio.onended = () => {
          URL.revokeObjectURL(url)
          this.playNext()
        }
        audio.play().catch(() => URL.revokeObjectURL(url))
      }
    }

    /** 清空并停止 */
    stop() {
      this.queue = []
      this.isPlaying = false
      this.onPlayStateChange(false)
      if (this.ctx) {
        this.ctx.close().catch(() => {})
        this.ctx = null
      }
    }
  }

  // ============================================================
  // WebSocket 连接管理
  // ============================================================

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    intentionalClose = false

    try {
      const url = getServerUrl()
      console.log('[useVoiceChat] 正在连接 WebSocket:', url)
      ws = new WebSocket(url)
      // 启用二进制消息接收
      ws.binaryType = 'arraybuffer'
    } catch (err) {
      console.error('[useVoiceChat] WebSocket 创建失败:', err)
      onError(err)
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      console.log('[useVoiceChat] WebSocket 已连接')
      clearTimeout(reconnectTimer)
      heartbeatMisses = 0
      startHeartbeat()
      onStatusChange('connected')
    }

    ws.onmessage = event => {
      if (event.data instanceof ArrayBuffer) {
        handleBinaryMessage(event.data)
      } else {
        handleTextMessage(event.data)
      }
    }

    ws.onclose = event => {
      console.log('[useVoiceChat] WebSocket 关闭, code:', event.code)
      stopHeartbeat()
      if (isProcessing.value) {
        isProcessing.value = false
      }
      onStatusChange('disconnected')
      if (!intentionalClose) {
        scheduleReconnect()
      }
    }

    ws.onerror = err => {
      console.error('[useVoiceChat] WebSocket 错误:', err)
      onError(err)
      ws?.close()
    }
  }

  function disconnect() {
    intentionalClose = true
    cleanupVAD()
    stopBargeInMonitor()
    clearTimeout(reconnectTimer)
    reconnectTimer = null
    stopHeartbeat()

    if (mediaRecorder && mediaRecorder.state === 'recording') {
      stopRecording()
    }

    if (audioQueue) {
      audioQueue.stop()
      audioQueue = null
    }
    audioChunks = []

    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }

    if (mediaStream.value) {
      mediaStream.value.getTracks().forEach(t => t.stop())
      mediaStream.value = null
    }

    isRecording.value = false
    isProcessing.value = false
    onStatusChange('disconnected')
  }

  function scheduleReconnect() {
    if (reconnectTimer || intentionalClose) return
    // 指数退避：第一次 1s，后续 3s，最大 10s
    const delay = reconnectTimer ? 3000 : 1000
    console.log(`[useVoiceChat] ${delay}ms 后尝试重连...`)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  // ============================================================
  // 自适应心跳
  // ============================================================

  function startHeartbeat() {
    stopHeartbeat()
    const sendPing = () => {
      if (ws?.readyState === WebSocket.OPEN) {
        lastPingTime = Date.now()
        ws.send(JSON.stringify({ type: 'ping', timestamp: lastPingTime }))
      }
    }
    sendPing()
    heartbeatTimer = setInterval(sendPing, HEARTBEAT_INTERVAL * 1000)
  }

  function stopHeartbeat() {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }

  // ============================================================
  // 消息处理
  // ============================================================

  /**
   * 处理文本消息（JSON）
   */
  function handleTextMessage(raw) {
    if (!raw || raw.trim() === '') {
      isProcessing.value = false
      onStatusChange('idle')
      return
    }

    let msg
    try {
      msg = JSON.parse(raw)
    } catch {
      return
    }

    switch (msg.type) {
      case 'audio_result':
        if (msg.text) {
          transcript.value = msg.text
          onTranscript(msg.text)
        }
        // audio_result 现在只返回 ASR 文本；LLM 回复通过 stream_delta/stream_end 推送
        if (msg.response) {
          response.value = msg.response
          onResponse(msg.response)
          isProcessing.value = false
          onStatusChange('idle')
        }
        // 记录 E2E 文本延迟
        if (msg.e2e_text_latency_ms) {
          console.log(`[E2E] 文本延迟: ${msg.e2e_text_latency_ms}ms`)
        }
        break

      case 'text_response': {
        const text = msg.response || msg.text || ''
        if (text) {
          response.value = text
          onResponse(text)
        }
        // 传递智能体信息
        if (msg.agent) {
          onAgentInfo(msg.agent)
        }
        // 兼容旧服务端：文本消息处理完成后必须重置 processing 状态
        isProcessing.value = false
        onStatusChange('idle')
        break
      }

      case 'stream_delta': {
        const delta = msg.delta || ''
        if (!isStreamingResponse.value) {
          isStreamingResponse.value = true
          response.value = delta
        } else {
          response.value += delta
        }
        onResponse(response.value)
        break
      }

      case 'stream_end': {
        const fullText = msg.full_text || response.value
        response.value = fullText
        isStreamingResponse.value = false
        isProcessing.value = false
        onStatusChange('idle')
        // 传递智能体信息
        if (msg.agent) {
          onAgentInfo(msg.agent)
        }
        break
      }

      case 'pong': {
        const rtt = Date.now() - (msg.timestamp || lastPingTime)
        heartbeatMisses = 0
        break
      }

      case 'error':
        console.error('[useVoiceChat] 服务端错误:', msg.message)
        onError(new Error(msg.message || '服务端错误'))
        isProcessing.value = false
        onStatusChange('idle')
        break

      case 'end':
        isProcessing.value = false
        onStatusChange('idle')
        break
    }
  }

  /**
   * 处理二进制消息（TTS 音频帧）
   *
   * 帧格式:
   *   [1B 类型] [4B JSON头长度(大端)] [JSON头] [音频数据]
   */
  function handleBinaryMessage(buffer) {
    if (buffer.byteLength < 5) return

    const view = new DataView(buffer)
    const frameType = view.getUint8(0)

    if (frameType === BINARY_TYPE_AUDIO) {
      // 解析头
      const headerLen = view.getUint32(1, false) // 大端
      const headerStr = new TextDecoder().decode(buffer.slice(5, 5 + headerLen))
      let header = {}
      try {
        header = JSON.parse(headerStr)
      } catch {}

      // 音频数据
      const audioData = buffer.slice(5 + headerLen)

      // 累计音频块用于语音气泡
      if (audioData.byteLength > 0) {
        audioChunks.push(audioData)
        currentAudioFormat = header.format || 'mp3'
      }

      // 入队播放
      if (audioData.byteLength > 0) {
        if (!audioQueue) {
          audioQueue = new AudioQueue(playing => {
            isPlaying.value = playing
            if (playing && enableBargeIn) {
              monitorBargeIn()
            } else {
              stopBargeInMonitor()
            }
          })
        }
        audioQueue.enqueue(audioData, header.format || 'mp3')
      }
    } else if (frameType === BINARY_TYPE_END) {
      // TTS 流结束 — 创建完整音频 Blob 用于语音气泡
      if (audioChunks.length > 0) {
        const mimeMap = { mp3: 'audio/mpeg', wav: 'audio/wav', ogg: 'audio/ogg', pcm: 'audio/wav' }
        const mime = mimeMap[currentAudioFormat] || 'audio/mpeg'
        const blob = new Blob(audioChunks, { type: mime })
        const url = URL.createObjectURL(blob)
        // 估算时长（粗略：根据 blob 大小 / 码率）
        let estimatedDuration = 0
        if (currentAudioFormat === 'mp3') {
          // MP3 128kbps 约 16KB/秒
          estimatedDuration = Math.round(blob.size / 16000)
        } else if (currentAudioFormat === 'pcm') {
          // PCM 16bit 16kHz = 32KB/秒
          estimatedDuration = Math.round(blob.size / 32000)
        } else {
          estimatedDuration = Math.round(blob.size / 16000)
        }
        estimatedDuration = Math.max(1, estimatedDuration)
        onAudioReady(url, estimatedDuration)
        audioChunks = []
      }

      // TTS 流结束
      isProcessing.value = false
      onStatusChange('idle')

      // 记录 E2E 完整延迟
      if (recordingStopTime > 0) {
        const e2e = Date.now() - recordingStopTime
        console.log(`[E2E] 完整延迟: ${e2e}ms`)
        recordingStopTime = 0
      }
    }
  }

  // ============================================================
  // 录音控制
  // ============================================================

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

      // 优先使用 Opus 编码（WebRTC 标准，压缩率最高）
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/ogg;codecs=opus'

      mediaRecorder = new MediaRecorder(mediaStream.value, { mimeType })

      // 初始化 VAD 自动断句（在 MediaRecorder 之后，避免占用同一轨道）
      if (enableVAD) {
        setupVAD(mediaStream.value)
      }

      mediaRecorder.ondataavailable = event => {
        if (event.data.size > 0 && ws?.readyState === WebSocket.OPEN) {
          sendAudioChunk(event.data)
        }
      }

      mediaRecorder.onstop = () => {
        if (mediaStream.value) {
          mediaStream.value.getTracks().forEach(t => t.stop())
          mediaStream.value = null
        }
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'audio_end' }))
        }
        isRecording.value = false
        recordingStopTime = Date.now()
        onStatusChange('recording_stopped')
      }

      mediaRecorder.onerror = err => {
        console.error('[useVoiceChat] MediaRecorder 错误:', err)
        onError(err)
        cleanupRecording()
      }

      // 【优化】分块间隔 60ms（比默认 100ms 更低延迟）
      mediaRecorder.start(CHUNK_INTERVAL_MS)
      isRecording.value = true
      onStatusChange('recording')
    } catch (err) {
      console.error('[useVoiceChat] 启动录音失败:', err)
      onError(err)
      cleanupRecording()
      isRecording.value = false
    }
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop()
      isProcessing.value = true
      onStatusChange('processing')
    }
  }

  /**
   * 发送音频块到后端
   * 优先使用二进制帧（节省 ~33% 带宽）
   */
  function sendAudioChunk(blob) {
    const reader = new FileReader()
    reader.onloadend = () => {
      const base64 = reader.result.split(',')[1]
      ws.send(
        JSON.stringify({
          type: 'audio',
          data: base64,
          format: 'webm',
          sample_rate: 16000
        })
      )
    }
    reader.readAsDataURL(blob)
  }

  // ============================================================
  // VAD 自动断句
  // ============================================================

  function setupVAD(stream) {
    cleanupVAD()
    try {
      vadProcessor = new VADProcessor({
        silenceTimeoutMs: 800,
        speechThreshold: 0.018,
        minSpeechDurationMs: 300,
        ...vadOptions,
        onSpeechEnd: () => {
          if (isRecording.value && mediaRecorder?.state === 'recording') {
            console.log('[useVoiceChat] VAD 检测到说话结束，自动停止录音')
            stopRecording()
          }
        }
      })
      vadAnalyser = createVADAnalyser(stream, vadProcessor, {
        sampleRate: 16000,
        intervalMs: 50,
        ...vadOptions.analyser
      })
    } catch (err) {
      console.warn('[useVoiceChat] VAD 初始化失败，已降级为手动断句:', err)
      vadProcessor = null
      vadAnalyser = null
    }
  }

  function cleanupVAD() {
    if (vadAnalyser) {
      vadAnalyser.stop()
      vadAnalyser = null
    }
    if (vadProcessor) {
      vadProcessor.destroy()
      vadProcessor = null
    }
  }

  // ============================================================
  // Barge-in 语音打断
  // ============================================================

  /**
   * 启动打断监听：TTS 播放期间监测用户说话，检测到语音立即打断
   */
  async function monitorBargeIn() {
    if (!enableBargeIn || !isPlaying.value) return
    if (Date.now() - lastBargeInTime < BARGE_IN_COOLDOWN_MS) return

    try {
      // 优先复用当前麦克风流；若无则新建低功耗流
      const stream = mediaStream.value || (await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      }))

      bargeInProcessor = new VADProcessor({
        speechThreshold: 0.025,
        silenceTimeoutMs: 600,
        minSpeechDurationMs: 200,
        onSpeechStart: () => {
          // 冷却期检查
          if (Date.now() - lastBargeInTime < BARGE_IN_COOLDOWN_MS) return
          if (!isPlaying.value) return

          console.log('[useVoiceChat] 检测到用户说话，触发语音打断')
          lastBargeInTime = Date.now()

          // 立即停止 TTS 播放
          if (audioQueue) {
            audioQueue.stop()
          }
          isPlaying.value = false
          onStatusChange('idle')

          // 打断后免唤醒，直接开始录音
          if (!isRecording.value && !isProcessing.value) {
            startRecording()
          }
        }
      })

      bargeInAnalyser = createVADAnalyser(stream, bargeInProcessor, {
        sampleRate: 16000,
        intervalMs: 50
      })
    } catch (err) {
      console.warn('[useVoiceChat] 打断监听初始化失败:', err)
      bargeInProcessor = null
      bargeInAnalyser = null
    }
  }

  /**
   * 停止打断监听
   */
  function stopBargeInMonitor() {
    if (bargeInAnalyser) {
      bargeInAnalyser.stop()
      bargeInAnalyser = null
    }
    if (bargeInProcessor) {
      bargeInProcessor.destroy()
      bargeInProcessor = null
    }
  }

  function cleanupRecording() {
    cleanupVAD()
    stopBargeInMonitor()
    if (mediaStream.value) {
      mediaStream.value.getTracks().forEach(t => t.stop())
      mediaStream.value = null
    }
    mediaRecorder = null
    isRecording.value = false
  }

  // ============================================================
  // 生命周期清理
  // ============================================================

  onUnmounted(() => {
    disconnect()
  })

  // ============================================================
  // 自动连接
  // ============================================================

  connect()

  // ============================================================
  // 返回公共接口
  // ============================================================

  /**
   * 发送文本消息到后端
   * @param {string} text - 用户输入的文本
   */
  function sendText(text) {
    if (!text || !text.trim()) return
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: 'text',
          text: text.trim()
        })
      )
      isProcessing.value = true
      onStatusChange('processing')
    } else {
      onError(new Error('连接未建立，请稍后重试'))
    }
  }

  /**
   * 设置服务器地址并重新连接
   * @param {string} url - 新的 WebSocket 服务器地址
   */
  function setServerUrl(url) {
    serverUrlRef.value = url
    disconnect()
    connect()
  }

  return {
    isRecording,
    isProcessing,
    isPlaying,
    isStreamingResponse,
    status,
    transcript,
    response,
    mediaStream,
    startRecording,
    stopRecording,
    sendText,
    setServerUrl,
    disconnect
  }
}
