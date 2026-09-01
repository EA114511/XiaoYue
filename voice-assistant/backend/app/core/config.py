"""
应用配置模块
包含所有环境变量和应用配置
"""

import logging

from pydantic_settings import BaseSettings
from typing import List, Optional
import os

logger = logging.getLogger("voice-assistant")


class Settings(BaseSettings):
    """应用配置类"""

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # CORS配置（.env 中请用逗号分隔，如: http://a.com,http://b.com）
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # ============================================================
    # 安全配置
    # ============================================================
    # API Token：保护管理类写接口（POST/PATCH/DELETE），为空则不启用鉴权
    API_TOKEN: str = ""
    # 加密密钥：用于加密 data/*.json 中持久化的 API Key（Fernet 派生密码）
    CRYPTO_KEY: str = ""

    # 数据库配置
    DATABASE_URL: str = "sqlite:///./voice_assistant.db"

    # 语音识别配置 (ASR)
    ASR_ENGINE: str = "whisper"                    # whisper, vosk
    VOSK_MODEL_PATH: str = "./models/vosk"
    ASR_DEFAULT_LANGUAGE: str = "zh"               # 默认识别语言: zh, en, ja
    VAD_SENSITIVITY: int = 2                       # WebRTC VAD 灵敏度 0-3

    # ---- 功能开关 ----
    # 是否启用语音对话功能。设为 false 时，WebSocket 连接将被拒绝
    ENABLE_VOICE_DIALOGUE: bool = True

    # OpenAI 配置
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    OPENAI_MAX_TOKENS: int = 2048
    OPENAI_TEMPERATURE: float = 0.7

    # 天气API配置
    WEATHER_API_KEY: str = ""
    WEATHER_API_URL: str = "http://api.openweathermap.org/data/2.5"
    WEATHER_UNITS: str = "metric"

    # WebSocket配置
    WS_TIMEOUT: int = 30

    # ============================================================
    # 性能优化配置
    # ============================================================

    # --- 端到端延迟优化 ---
    # ASR 模型: tiny(最快) < base < small < medium < large(最慢但最准)
    # 追求 < 2s 延迟建议用 "tiny" 或 "base"
    WHISPER_MODEL_SIZE: str = "base"       # tiny/base/small/medium/large
    # 静音超时（秒），值越小响应越快，但可能过早截断
    SILENCE_TIMEOUT: float = 0.5
    # 最小语音长度（毫秒），低于此值忽略
    MIN_SPEECH_MS: int = 200

    # --- 并发处理 ---
    # ASR 并发工作数（同时处理的识别请求数）
    ASR_MAX_CONCURRENCY: int = 2
    # TTS 并发合成数
    TTS_MAX_CONCURRENCY: int = 2
    # LLM API 并发连接池大小
    LLM_MAX_CONNECTIONS: int = 5
    # WebSocket 最大连接数
    WS_MAX_CONNECTIONS: int = 100

    # --- 缓存策略 ---
    # ASR 缓存大小（音频指纹）
    ASR_CACHE_SIZE: int = 128
    # TTS 缓存大小（文本哈希）
    TTS_CACHE_SIZE: int = 256
    # LLM 响应缓存大小（语义哈希）
    LLM_CACHE_SIZE: int = 256
    # LLM 缓存 TTL（秒），相同问题短时间内不重复调用 API
    LLM_CACHE_TTL: int = 300

    # --- 音频传输 ---
    # 是否启用二进制 WebSocket 帧（替代 base64，节省 ~33% 带宽）
    WS_BINARY_MODE: bool = True
    # 音频分块大小（毫秒）
    AUDIO_CHUNK_MS: int = 60
    # 目标采样率（降采样减少传输量）
    TARGET_SAMPLE_RATE: int = 16000

    # --- 错误处理 ---
    # 熔断器阈值（连续失败次数）
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    # 熔断器恢复超时（秒）
    CIRCUIT_BREAKER_RECOVERY: float = 30.0
    # 重试次数
    MAX_RETRIES: int = 2
    # 重试基础延迟（秒）
    RETRY_BASE_DELAY: float = 0.5

    # --- 日志配置 ---
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/voice_assistant.log"
    LOG_MAX_SIZE: int = 10485760   # 10MB
    LOG_BACKUP_COUNT: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # ============================================================
    # 配置检查辅助方法
    # ============================================================

    @property
    def allowed_origins_list(self) -> List[str]:
        """解析 ALLOWED_ORIGINS 字符串为列表（逗号分隔）"""
        if isinstance(self.ALLOWED_ORIGINS, str):
            return [item.strip() for item in self.ALLOWED_ORIGINS.split(",") if item.strip()]
        return self.ALLOWED_ORIGINS  # 兼容旧值

    @property
    def ai_key_configured(self) -> bool:
        """检查 AI API Key 是否已配置（含兼容的非标端点如 DeepSeek）"""
        # 优先检查 OpenAI API Key
        if self.OPENAI_API_KEY and self.OPENAI_API_KEY != "sk-your-openai-api-key-here":
            return True
        # 也检查环境变量中的备用 Key
        if os.environ.get("OPENAI_API_KEY", "").strip():
            return True
        return False


# ============================================================
# 运行时配置（可动态修改，不依赖环境变量）
# 用于前端运行时修改配置（如切换语音对话开关、设置 AI Key）
# ============================================================

class RuntimeConfig:
    """运行时配置 — 存储运行时功能开关和各功能使用的 Provider 名称

    LLM Provider 配置移入 ProviderRegistry（见 llm_providers.py），
    每个 Provider 独立管理 api_base / api_key / model。

    各功能（NLU 语义识别、Dialog 对话、Coordinator 路由等）可以
    独立选择使用哪个 Provider，只需设置对应的 provider_name。

    注意：TTS 仅使用 AI 语音大模型 API（已移除本地 edge-tts），
    未配置 AI 语音 Provider 时自动禁用语音对话功能。
    """

    def __init__(self):
        # 功能开关（默认使用 Settings 的值）
        self._enable_voice_dialogue: bool = settings.ENABLE_VOICE_DIALOGUE
        # ============================================================
        # Provider 绑定：各功能独立选择使用的 LLM Provider
        # 值为 ProviderRegistry 中的名称，"default" 表示使用默认 Provider
        # ============================================================
        # NLU 语义识别（意图分类）使用的 Provider 名称
        self._nlu_provider_name: str = "default"
        # 对话生成（聊天回复）使用的 Provider 名称
        self._dialog_provider_name: str = "default"
        # ============================================================
        # 全局 AI 性格配置 — 用户可自定义，注入到所有智能体的 system_prompt
        # ============================================================
        self._assistant_personality: str = ""
        # ============================================================
        # headroom-ai 上下文压缩开关 — 降低 LLM API Token 消耗
        # 开启后自动压缩发送给 LLM 的消息列表（平均节省 60-95% Token）
        # ============================================================
        self._enable_headroom_compression: bool = True

    # ---- 语音对话开关 ----

    @property
    def enable_voice_dialogue(self) -> bool:
        return self._enable_voice_dialogue

    @enable_voice_dialogue.setter
    def enable_voice_dialogue(self, value: bool):
        self._enable_voice_dialogue = value

    # ---- Provider 绑定：NLU 语义识别用的 Provider ----

    @property
    def nlu_provider_name(self) -> str:
        """NLU 语义识别使用的 Provider 名称"""
        return self._nlu_provider_name

    @nlu_provider_name.setter
    def nlu_provider_name(self, value: str):
        if not value:
            value = "default"
        self._nlu_provider_name = value
        logger.info(f"[Config] NLU Provider 切换为: {value}")

    # ---- Provider 绑定：对话生成用的 Provider ----

    @property
    def dialog_provider_name(self) -> str:
        """对话生成使用的 Provider 名称"""
        return self._dialog_provider_name

    @dialog_provider_name.setter
    def dialog_provider_name(self, value: str):
        if not value:
            value = "default"
        self._dialog_provider_name = value
        logger.info(f"[Config] Dialog Provider 切换为: {value}")

    # ---- 全局 AI 性格配置 ----

    @property
    def assistant_personality(self) -> str:
        """全局 AI 性格描述（注入到所有智能体的 system_prompt）"""
        return self._assistant_personality

    @assistant_personality.setter
    def assistant_personality(self, value: str):
        self._assistant_personality = value or ""
        logger.info(f"[Config] 全局 AI 性格已更新")

    # ---- headroom-ai 上下文压缩开关 ----

    @property
    def enable_headroom_compression(self) -> bool:
        """是否启用 headroom-ai 上下文压缩以降低 Token 消耗"""
        return self._enable_headroom_compression

    @enable_headroom_compression.setter
    def enable_headroom_compression(self, value: bool):
        self._enable_headroom_compression = bool(value)
        logger.info(f"[Config] headroom-ai 压缩已{'开启' if value else '关闭'}")

    # ---- 导出当前有效配置 ----

    @property
    def voice_dialogue_ready(self) -> bool:
        """检查语音对话功能是否可用（需要已配置并启用 AI 语音 Provider）"""
        try:
            from app.core.voice_providers import voice_provider_registry
            vp = voice_provider_registry.get_active()
            return vp is not None and bool(vp.api_base) and bool(vp.api_key)
        except Exception:
            return False

    def to_dict(self) -> dict:
        """导出前端可读的配置状态"""
        return {
            "enable_voice_dialogue": self.enable_voice_dialogue,
            "voice_dialogue_ready": self.voice_dialogue_ready,
            "nlu_provider_name": self.nlu_provider_name,
            "dialog_provider_name": self.dialog_provider_name,
            "assistant_personality": self.assistant_personality,
            "enable_headroom_compression": self.enable_headroom_compression,
        }


# 创建全局配置实例
settings = Settings()
# 创建全局运行时配置实例
runtime_config = RuntimeConfig()