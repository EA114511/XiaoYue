/**
 * useVAD — 前端语音活动检测（Voice Activity Detection）
 *
 * 基于 Web Audio API 的能量阈值检测，无需额外模型文件：
 * - 检测到音量超过阈值视为开始说话
 * - 连续静音 silenceTimeoutMs 后触发 onSpeechEnd，实现自动断句
 * - 支持最小说话时长保护，避免短促噪声误触发
 */

export class VADProcessor {
  /**
   * @param {object} options
   * @param {() => void} [options.onSpeechStart] - 检测到开始说话
   * @param {() => void} [options.onSpeechEnd] - 检测到说话结束（连续静音）
   * @param {number} [options.silenceTimeoutMs=800] - 判定说话结束的连续静音时长
   * @param {number} [options.speechThreshold=0.018] - 语音能量阈值（RMS）
   * @param {number} [options.minSpeechDurationMs=300] - 触发 speechEnd 前至少需要说多久
   * @param {number} [options.sampleRate=16000] - 采样率，仅用于日志/调试
   */
  constructor({
    onSpeechStart,
    onSpeechEnd,
    silenceTimeoutMs = 800,
    speechThreshold = 0.018,
    minSpeechDurationMs = 300,
    sampleRate = 16000
  } = {}) {
    this.onSpeechStart = onSpeechStart
    this.onSpeechEnd = onSpeechEnd
    this.silenceTimeoutMs = silenceTimeoutMs
    this.speechThreshold = speechThreshold
    this.minSpeechDurationMs = minSpeechDurationMs
    this.sampleRate = sampleRate

    this.isSpeech = false
    this.speechStartTime = 0
    /** @type {number|null} */
    this.silenceTimer = null
  }

  /**
   * 处理一帧音频数据
   * @param {Float32Array} audioData - 时间域采样，[-1, 1]
   */
  process(audioData) {
    const rms = Math.sqrt(
      audioData.reduce((sum, x) => sum + x * x, 0) / audioData.length
    )

    if (rms > this.speechThreshold) {
      if (!this.isSpeech) {
        this.isSpeech = true
        this.speechStartTime = performance.now()
        this.onSpeechStart?.()
      }
      if (this.silenceTimer !== null) {
        clearTimeout(this.silenceTimer)
        this.silenceTimer = null
      }
    } else if (this.isSpeech && this.silenceTimer === null) {
      const speechDuration = performance.now() - this.speechStartTime
      // 若说话时间不足最小值，则延长静音等待期，避免噪声误结束
      const extraDelay = Math.max(0, this.minSpeechDurationMs - speechDuration)
      const delay = this.silenceTimeoutMs + extraDelay

      this.silenceTimer = window.setTimeout(() => {
        this.isSpeech = false
        this.silenceTimer = null
        this.onSpeechEnd?.()
      }, delay)
    }
  }

  /**
   * 主动重置状态，通常用于录音停止后
   */
  reset() {
    if (this.silenceTimer !== null) {
      clearTimeout(this.silenceTimer)
      this.silenceTimer = null
    }
    this.isSpeech = false
    this.speechStartTime = 0
  }

  /**
   * 释放资源
   */
  destroy() {
    this.reset()
    this.onSpeechStart = null
    this.onSpeechEnd = null
  }
}

/**
 * 创建基于 AnalyserNode 的 VAD 分析循环
 *
 * @param {MediaStream} stream - 麦克风流
 * @param {VADProcessor} vadProcessor - VAD 处理器实例
 * @param {object} [options]
 * @param {number} [options.sampleRate=16000]
 * @param {number} [options.fftSize=2048]
 * @param {number} [options.intervalMs=50]
 * @returns {{ context: AudioContext, analyser: AnalyserNode, source: MediaStreamAudioSourceNode, stop: () => void }}
 */
export function createVADAnalyser(stream, vadProcessor, options = {}) {
  const sampleRate = options.sampleRate || 16000
  const fftSize = options.fftSize || 2048
  const intervalMs = options.intervalMs || 50

  const context = new (window.AudioContext || window.webkitAudioContext)({
    sampleRate
  })
  const source = context.createMediaStreamSource(stream)
  const analyser = context.createAnalyser()
  analyser.fftSize = fftSize
  analyser.smoothingTimeConstant = 0.75
  source.connect(analyser)

  const buffer = new Float32Array(analyser.fftSize)
  /** @type {number|null} */
  let timer = null

  function analyze() {
    if (!analyser || !vadProcessor) return
    analyser.getFloatTimeDomainData(buffer)
    vadProcessor.process(buffer)
  }

  timer = window.setInterval(analyze, intervalMs)

  function stop() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
    try {
      source.disconnect()
    } catch {}
    try {
      analyser.disconnect()
    } catch {}
    if (context && context.state !== 'closed') {
      context.close().catch(() => {})
    }
  }

  return { context, analyser, source, stop }
}
