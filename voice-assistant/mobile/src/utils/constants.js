// 常量配置

// API 配置
export const API_CONFIG = {
  // 默认 NAS 地址，可在设置中修改
  DEFAULT_NAS_URL: 'http://192.168.5.5:8000',
  WS_PATH: '/ws/voice',
  API_PATH: '/api/v1'
}

// 唤醒词
export const WAKE_WORDS = ['小玥小玥', '小月小月', '小悦小悦']

// 存储键名
export const STORAGE_KEYS = {
  NAS_URL: 'xiaoyue_nas_url',
  API_TOKEN: 'xiaoyue_api_token',
  USER_ID: 'xiaoyue_user_id'
}

// 状态文本
export const STATE_TEXT = {
  idle: { verb: '待机', sub: 'STANDBY' },
  listening: { verb: '聆听', sub: 'LISTENING' },
  thinking: { verb: '思索', sub: 'THINKING' },
  speaking: { verb: '应答', sub: 'SPEAKING' }
}

// 提示文字
export const HINTS = {
  IDLE: '说「小玥小玥」唤醒我',
  LISTENING: '我在听，请讲……',
  THINKING: '正在思考……',
  SPEAKING: '正在为你朗读……',
  ERROR: '连接失败，请检查网络'
}
