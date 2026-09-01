"""
语音合成 Provider 注册表

管理 AI 语音大模型的接口配置，支持 OpenAI 兼容的 TTS API 端点。
每个 Provider 可独立配置接口地址、Key、模型和音色。

===== 支持的 API 格式 =====

OpenAI TTS API (兼容格式):
  POST {api_base}/audio/speech
  {
    "model": "{model}",
    "input": "要合成的文本",
    "voice": "{voice}",
    "response_format": "mp3",
    "speed": 1.0
  }
  返回: 音频二进制数据 (MP3)

===== 使用方式 =====

  from app.core.voice_providers import voice_provider_registry

  # 获取默认语音 Provider
  vp = voice_provider_registry.get_default()
  # vp.api_base, vp.api_key, vp.model, vp.voice
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.crypto_utils import encrypt_value, decrypt_value

logger = logging.getLogger("voice-assistant.voice_providers")

# 持久化文件路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
VOICE_PROVIDERS_FILE = os.path.join(DATA_DIR, "voice_providers.json")


@dataclass
class VoiceProvider:
    """
    语音合成提供者配置

    每个 Provider 代表一个 AI 语音大模型的 API 端点：
      - name:             唯一标识名（如 "zhipu-glm"、"openai-tts"）
      - api_base:         API 基础地址（如 "https://open.bigmodel.cn/api/paas/v4"）
      - api_key:          API 密钥
      - model:            语音模型名称（如 "glm-tts"、"tts-1"、"tts-1-hd"）
      - voice:            音色 ID（仅 voice_type=preset 时使用）
      - voice_type:       音色类型："preset"（预设音色）或 "clone"（声音复刻）
      - clone_settings:   声音复刻配置（仅 voice_type=clone 时使用）
                          {"reference_audio_url": "", "reference_text": "", "clone_voice_id": ""}
      - enabled:          是否启用
      - response_format:  音频格式（"pcm"（智谱默认）、"mp3"、"wav"）
      - encode_format:    编码格式（"base64"（智谱流式默认）、"raw"）
      - speed:            语速（0.5 ~ 2.0，默认 1.0）
      - volume:           音量（0.5 ~ 2.0，默认 1.0）
    """
    name: str
    api_base: str = ""
    api_key: str = ""
    model: str = "glm-tts"
    voice: str = "female"
    voice_type: str = "preset"  # "preset" | "clone"
    clone_settings: dict = None  # {"reference_audio_url": "", "reference_text": "", "clone_voice_id": ""}
    enabled: bool = False
    response_format: str = "pcm"
    encode_format: str = "base64"
    speed: float = 1.0
    volume: float = 1.0

    def __post_init__(self):
        """初始化后处理，确保 clone_settings 不为 None"""
        if self.clone_settings is None:
            self.clone_settings = {
                "reference_audio_url": "",
                "reference_text": "",
                "clone_voice_id": "",
                "voice_name": "",
            }


class VoiceProviderRegistry:
    """
    语音合成 Provider 注册表

    管理多个语音 Provider 的增删改查，持久化到 JSON 文件。
    默认 Provider 名称为 "default-voice"。
    """

    def __init__(self):
        self._providers: Dict[str, VoiceProvider] = {}
        self._load()
        logger.info(
            f"[VoiceProviderRegistry] 已加载 {len(self._providers)} 个语音 Provider: "
            f"{list(self._providers.keys())}"
        )

    # ---------------------------------------------------------------
    # 持久化
    # ---------------------------------------------------------------

    def _load(self):
        """从 JSON 文件加载 Provider 配置"""
        try:
            if not os.path.exists(VOICE_PROVIDERS_FILE):
                # 创建默认语音 Provider（智谱 GLM-TTS）
                default_vp = VoiceProvider(
                    name="zhipu-glm",
                    api_base="https://open.bigmodel.cn/api/paas/v4",
                    api_key="",
                    model="glm-tts",
                    voice="female",
                    enabled=False,
                )
                self._providers["zhipu-glm"] = default_vp
                self.save()
                return

            with open(VOICE_PROVIDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                name = item.get("name")
                if not name:
                    continue
                provider = VoiceProvider(
                    **{k: item[k] for k in VoiceProvider.__dataclass_fields__ if k in item}
                )
                # 解密持久化的 API Key
                if provider.api_key:
                    decrypted = decrypt_value(provider.api_key)
                    if decrypted is not None:
                        provider.api_key = decrypted
                self._providers[name] = provider
            logger.info(f"[VoiceProviderRegistry] 从 {VOICE_PROVIDERS_FILE} 加载 {len(data)} 个 Provider")

            # 确保至少有一个默认 Provider
            if "zhipu-glm" not in self._providers:
                self._providers["zhipu-glm"] = VoiceProvider(
                    name="zhipu-glm",
                    api_base="https://open.bigmodel.cn/api/paas/v4",
                    model="glm-tts",
                    voice="female",
                    enabled=False,
                )
        except Exception as e:
            logger.warning(f"[VoiceProviderRegistry] 加载配置失败: {e}")
            # 创建默认
            if "zhipu-glm" not in self._providers:
                self._providers["zhipu-glm"] = VoiceProvider(
                    name="zhipu-glm",
                    api_base="https://open.bigmodel.cn/api/paas/v4",
                    model="glm-tts",
                    voice="female",
                    enabled=False,
                )

    def save(self):
        """持久化所有语音 Provider 到 JSON 文件，API Key 加密存储"""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = []
            for p in self._providers.values():
                item = asdict(p)
                # 加密 API Key 后再写入文件
                if item.get("api_key"):
                    item["api_key"] = encrypt_value(item["api_key"])
                data.append(item)
            with open(VOICE_PROVIDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[VoiceProviderRegistry] 保存配置失败: {e}")

    # ---------------------------------------------------------------
    # 查询
    # ---------------------------------------------------------------

    def get_default(self) -> Optional[VoiceProvider]:
        """获取默认语音 Provider（zhipu-glm）"""
        return self._providers.get("zhipu-glm")

    def get(self, name: str) -> Optional[VoiceProvider]:
        """获取指定名称的 Provider"""
        return self._providers.get(name)

    def get_all(self) -> List[VoiceProvider]:
        """获取所有 Provider 列表"""
        return list(self._providers.values())

    def get_active(self) -> Optional[VoiceProvider]:
        """获取当前启用的语音 Provider（未启用则返回 None）"""
        for p in self._providers.values():
            if p.enabled:
                return p
        return None

    # ---------------------------------------------------------------
    # 管理
    # ---------------------------------------------------------------

    def upsert(self, name: str, provider: VoiceProvider) -> VoiceProvider:
        """创建或更新语音 Provider"""
        provider.name = name
        if name in self._providers:
            # 保留现有的 api_key（如果新值未提供）
            existing = self._providers[name]
            if not provider.api_key and existing.api_key:
                provider.api_key = existing.api_key
        self._providers[name] = provider
        self.save()
        logger.info(f"[VoiceProviderRegistry] 已{'更新' if name in self._providers else '创建'} 语音 Provider: {name}")
        return provider

    def delete(self, name: str) -> bool:
        """删除语音 Provider"""
        if name not in self._providers:
            return False
        del self._providers[name]
        self.save()
        logger.info(f"[VoiceProviderRegistry] 已删除语音 Provider: {name}")
        return True


# ---------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------

voice_provider_registry = VoiceProviderRegistry()
