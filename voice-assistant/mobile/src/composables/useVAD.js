// useVAD — 移动端语音活动检测

export class VADProcessor {
  constructor({
    onSpeechStart,
    onSpeechEnd,
    silenceTimeoutMs = 800,
    speechThreshold = 0.018,
    minSpeechDurationMs = 300
  } = {}) {
    this.onSpeechStart = onSpeechStart
    this.onSpeechEnd = onSpeechEnd
    this.silenceTimeoutMs = silenceTimeoutMs
    this.speechThreshold = speechThreshold
    this.minSpeechDurationMs = minSpeechDurationMs
    this.isSpeech = false
    this.speechStartTime = 0
    this.silenceTimer = null
  }

  process(audioData) {
    const rms = Math.sqrt(audioData.reduce((sum, x) => sum + x * x, 0) / audioData.length)

    if (rms > this.speechThreshold) {
      if (!this.isSpeech) {
        this.isSpeech = true
        this.speechStartTime = performance.now()
        this.onSpeechStart?.()
      }
      clearTimeout(this.silenceTimer)
      this.silenceTimer = null
    } else if (this.isSpeech && this.silenceTimer === null) {
      const speechDuration = performance.now() - this.speechStartTime
      const extraDelay = Math.max(0, this.minSpeechDurationMs - speechDuration)
      this.silenceTimer = setTimeout(() => {
        this.isSpeech = false
        this.silenceTimer = null
        this.onSpeechEnd?.()
      }, this.silenceTimeoutMs + extraDelay)
    }
  }

  destroy() {
    clearTimeout(this.silenceTimer)
    this.onSpeechStart = null
    this.onSpeechEnd = null
  }
}

export function createVADAnalyser(stream, processor, options = {}) {
  const sampleRate = options.sampleRate || 16000
  const fftSize = options.fftSize || 2048
  const intervalMs = options.intervalMs || 50

  const context = new (window.AudioContext || window.webkitAudioContext)({ sampleRate })
  const source = context.createMediaStreamSource(stream)
  const analyser = context.createAnalyser()
  analyser.fftSize = fftSize
  analyser.smoothingTimeConstant = 0.75
  source.connect(analyser)

  const buffer = new Float32Array(analyser.fftSize)
  let timer = null

  function analyze() {
    if (!analyser || !processor) return
    analyser.getFloatTimeDomainData(buffer)
    processor.process(buffer)
  }

  timer = setInterval(analyze, intervalMs)

  function stop() {
    clearInterval(timer)
    source.disconnect()
    analyser.disconnect()
    context.close()
  }

  return { context, analyser, source, stop }
}
