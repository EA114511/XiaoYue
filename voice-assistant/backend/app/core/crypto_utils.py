"""
API Key 加密工具 — Fernet (AES-128-CBC + HMAC-SHA256)

提供统一的加密/解密接口，用于敏感配置的持久化存储。
密钥从环境变量 CRYPTO_KEY 读取，不存在时自动生成并提示。

用法:
    from app.core.crypto_utils import encrypt_value, decrypt_value

    # 加密后存储
    encrypted = encrypt_value("sk-xxxxxxxxxxxx")
    # 写入文件的是密文

    # 读取时解密
    plain = decrypt_value(encrypted)  # → "sk-xxxxxxxxxxxx"
    # 无法解密时返回 None（如密钥变更）
"""

import base64
import logging
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings

logger = logging.getLogger("voice-assistant.crypto")

# 从环境变量读取密钥：优先系统环境变量，其次 .env 配置（pydantic 不会把 .env 回写到 os.environ）
_ENV_KEY = os.environ.get("CRYPTO_KEY") or settings.CRYPTO_KEY

# 派生密钥用的盐（固定值，生产环境建议独立存储）
_SALT = b"voice-assistant-salt-v1"
# 派生密钥用的迭代次数
_ITERATIONS = 480_000


def _get_fernet() -> Fernet | None:
    """
    获取 Fernet 加密器

    如果 CRYPTO_KEY 环境变量未设置，返回 None（不加密降级运行）。
    在生产环境中必须设置 CRYPTO_KEY，否则加密功能不可用。
    """
    if not _ENV_KEY:
        return None

    try:
        # 使用 PBKDF2 从密码派生 32 字节密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_SALT,
            iterations=_ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(_ENV_KEY.encode("utf-8")))
        return Fernet(key)
    except Exception as e:
        logger.error(f"[Crypto] Fernet 初始化失败: {e}")
        return None


def encrypt_value(plain_text: str) -> str:
    """
    加密明文（API Key）

    参数:
        plain_text: 原始字符串（如 API Key）
    返回:
        加密后的 base64 字符串；无法加密时返回原文（降级）
    """
    if not plain_text:
        return ""

    f = _get_fernet()
    if f is None:
        logger.warning("[Crypto] CRYPTO_KEY 未配置，API Key 将以明文存储！")
        return plain_text

    try:
        # Fernet.encrypt() 返回的 bytes 已经是 urlsafe-base64 编码
        encrypted = f.encrypt(plain_text.encode("utf-8"))
        return encrypted.decode("utf-8")
    except Exception as e:
        logger.error(f"[Crypto] 加密失败: {e}")
        return plain_text


def decrypt_value(encrypted_text: str) -> str | None:
    """
    解密已加密的 API Key

    参数:
        encrypted_text: 加密后的 base64 字符串
    返回:
        解密后的原文；无法解密时返回 None
    """
    if not encrypted_text:
        return None

    # 如果字符串不是 Fernet 格式（不以 gAAAAA 开头），说明是未加密的旧数据
    # 向下兼容处理
    if not encrypted_text.startswith("gAAAA"):
        return encrypted_text

    f = _get_fernet()
    if f is None:
        logger.warning("[Crypto] CRYPTO_KEY 未配置，无法解密已加密的 Key")
        return None

    try:
        # Fernet.decrypt() 可直接接受 urlsafe-base64 编码的字符串 bytes
        plain = f.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
        return plain
    except Exception as e:
        logger.error(f"[Crypto] 解密失败（密钥可能已变更）: {e}")
        return None
