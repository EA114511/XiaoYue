"""
大模型接口 Provider 注册表

===== 核心概念 =====

替代旧的"远程模型 vs 本地模型"二元切换逻辑：
  每个 Provider 是一个独立的大模型接口配置（名称、地址、Key、模型），
  不同功能（对话、路由、各智能体）直接引用 Provider，不再有自动切换。

===== 使用方式 =====

  from app.core.llm_providers import provider_registry

  # 获取默认 Provider
  provider = provider_registry.get_default()
  # provider.api_base, provider.api_key, provider.model

  # 获取指定 Provider
  provider = provider_registry.get("deepseek")
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, List

from app.core.config import settings
from app.core.crypto_utils import encrypt_value, decrypt_value

logger = logging.getLogger("voice-assistant.llm_providers")

# 持久化文件路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
PROVIDERS_FILE = os.path.join(DATA_DIR, "llm_providers.json")


@dataclass
class LlmProvider:
    """
    大模型接口提供者配置

    每个 Provider 代表一个独立的大模型 API 端点：
      - name:        唯一标识名（如 "default"、"deepseek"、"local-ollama"）
      - api_base:    API 基础地址（如 "https://api.openai.com/v1"）
      - api_key:     API 密钥（空字符串表示无需密钥，如本地 Ollama）
      - model:       模型名称（如 "gpt-4"、"deepseek-chat"、"qwen2.5:7b"）
      - max_tokens:  最大生成 token 数
      - temperature: 生成温度
    """
    name: str
    api_base: str
    api_key: str = ""
    model: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7


class ProviderRegistry:
    """
    LLM 接口 Provider 注册表

    职责:
      1. 管理多个 LLM Provider 的增删改查
      2. 从 Settings 初始化默认 Provider
      3. 持久化到 JSON 文件，重启后保留配置

    默认 Provider:
      - name 固定为 "default"
      - 初始值来自 Settings（OPENAI_API_KEY / OPENAI_API_BASE / OPENAI_MODEL）
      - 可通过 upsert 更新
      - 不可删除
    """

    def __init__(self):
        self._providers: Dict[str, LlmProvider] = {}
        self._init_default()
        self._load()
        logger.info(
            f"[ProviderRegistry] 已加载 {len(self._providers)} 个 Provider: "
            f"{list(self._providers.keys())}"
        )

    def _init_default(self):
        """从 Settings 初始化默认 Provider"""
        default_api_base = (
            os.environ.get("OPENAI_API_BASE") or "https://api.openai.com/v1"
        )
        # 使用 settings 中的值（来自 .env）
        api_key = settings.OPENAI_API_KEY or ""
        # 如果是占位值，视为未配置
        if api_key == "sk-your-openai-api-key-here":
            api_key = ""

        self._providers["default"] = LlmProvider(
            name="default",
            api_base=default_api_base,
            api_key=api_key,
            model=settings.OPENAI_MODEL or "gpt-3.5-turbo",
            max_tokens=settings.OPENAI_MAX_TOKENS or 2048,
            temperature=settings.OPENAI_TEMPERATURE or 0.7,
        )

    # ---------------------------------------------------------------
    # 持久化
    # ---------------------------------------------------------------

    def _load(self):
        """从 JSON 文件加载 Provider 配置并合并到内存"""
        try:
            if not os.path.exists(PROVIDERS_FILE):
                return
            with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                name = item.get("name")
                if not name:
                    continue
                provider = LlmProvider(**{k: item[k] for k in LlmProvider.__dataclass_fields__ if k in item})
                if name == "default":
                    # 默认 Provider 保留 api_key 的运行时更新值
                    provider.api_key = provider.api_key or self._providers["default"].api_key
                # 解密持久化的 API Key
                if provider.api_key:
                    decrypted = decrypt_value(provider.api_key)
                    if decrypted is not None:
                        provider.api_key = decrypted
                self._providers[name] = provider
            logger.info(f"[ProviderRegistry] 从 {PROVIDERS_FILE} 加载 {len(data)} 个 Provider")
        except Exception as e:
            logger.warning(f"[ProviderRegistry] 加载 Provider 配置失败: {e}")

    def save(self):
        """持久化所有 Provider 到 JSON 文件，API Key 加密存储"""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = []
            for p in self._providers.values():
                item = asdict(p)
                # 加密 API Key 后再写入文件
                if item.get("api_key"):
                    item["api_key"] = encrypt_value(item["api_key"])
                data.append(item)
            with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[ProviderRegistry] 保存 Provider 配置失败: {e}")

    # ---------------------------------------------------------------
    # 查询
    # ---------------------------------------------------------------

    def get_default(self) -> LlmProvider:
        """获取默认 Provider（各功能的回退选项）"""
        return self._providers.get("default")

    def get(self, name: str) -> Optional[LlmProvider]:
        """获取指定名称的 Provider，不存在返回 None"""
        return self._providers.get(name)

    def get_all(self) -> List[LlmProvider]:
        """获取所有 Provider 列表"""
        return list(self._providers.values())

    # ---------------------------------------------------------------
    # 管理
    # ---------------------------------------------------------------

    def upsert(self, name: str, provider: LlmProvider) -> LlmProvider:
        """
        创建或更新 Provider

        - name="default" 时更新默认 Provider
        - 其他名称创建新的 Provider 或更新已有的
        """
        provider.name = name
        if name == "default":
            # 更新默认 Provider：保留 api_key 如果新值不为空
            existing = self._providers.get("default")
            if existing and not provider.api_key:
                provider.api_key = existing.api_key
        self._providers[name] = provider
        self.save()
        logger.info(f"[ProviderRegistry] 已{'更新' if name in self._providers else '创建'} Provider: {name}")
        return provider

    def delete(self, name: str) -> bool:
        """删除 Provider（不允许删除 default）"""
        if name == "default":
            logger.warning("[ProviderRegistry] 不允许删除默认 Provider")
            return False
        if name not in self._providers:
            return False
        del self._providers[name]
        self.save()
        logger.info(f"[ProviderRegistry] 已删除 Provider: {name}")
        return True


# ---------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------

provider_registry = ProviderRegistry()
