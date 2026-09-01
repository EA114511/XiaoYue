"""
API端点模块

连接核心 ASR / TTS / Dialog 服务，提供 REST API 接口。
服务实例通过 FastAPI app.state 注入（参见 main.py 的 inject_to_app）。
"""

import base64
import logging
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel

from app.functions.weather import get_weather as weather_function
from app.functions.device import device_manager
from app.core.config import runtime_config
from app.core.database import database_service
from app.core.llm_providers import provider_registry, LlmProvider
from app.core.multi_agent import agent_registry, AgentConfig
from app.core.voice_providers import voice_provider_registry, VoiceProvider
from app.skills import skill_registry
from app.skills.mcp_bridge import mcp_registry, MCPServerConfig

logger = logging.getLogger("voice-assistant")

# ============================================================
# 路由定义
# ============================================================
health = APIRouter()
voice = APIRouter()
conversation = APIRouter()
functions = APIRouter()
settings_router = APIRouter()


# ============================================================
# 健康检查
# ============================================================
@health.get("/status")
async def get_status(request: Request) -> Dict[str, Any]:
    """获取服务状态"""
    dialog = request.app.state.dialog_manager
    return {
        "status": "healthy",
        "service": "voice-assistant",
        "version": "1.0.0",
        "active_conversations": dialog.active_count,
        "expired_conversations": dialog.expired_count,
    }


# ============================================================
# 语音处理
# ============================================================
@voice.post("/transcribe")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """音频文件转文本"""
    try:
        # 保存上传文件到临时路径
        suffix = file.filename.split(".")[-1] if file.filename else ".wav"
        with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # 调用 ASR 服务
        asr_service = request.app.state.asr_service
        result = await asr_service.recognize_file(
            audio_path=tmp_path,
            language=language or "zh",
            use_vad=True,
            use_cache=True,
        )

        return {
            "text": result.text,
            "confidence": result.confidence,
            "language": result.language,
            "duration_ms": result.duration_ms,
        }
    except Exception as e:
        logger.error(f"语音识别失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@voice.post("/synthesize")
async def synthesize_speech(
    request: Request,
    text: str,
    voice: Optional[str] = None,
    speed: Optional[float] = None,
    provider_name: Optional[str] = None,
) -> Dict[str, Any]:
    """文本转语音（使用 AI 语音大模型 API，已移除本地 edge-tts）"""
    try:
        ai_voice = request.app.state.ai_voice_service
        kwargs = {"text": text}
        if voice:
            kwargs["voice"] = voice
        if speed:
            kwargs["speed"] = speed
        if provider_name:
            kwargs["provider_name"] = provider_name
        audio_data = await ai_voice.synthesize(**kwargs)
        if not audio_data:
            raise HTTPException(status_code=500, detail="语音合成返回空数据")
        return {
            "audio_data": base64.b64encode(audio_data).decode("utf-8"),
            "format": "mp3",
            "text": text,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"语音合成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 对话管理
# ============================================================
@conversation.post("/start")
async def start_conversation(request: Request) -> Dict[str, Any]:
    """开始新对话"""
    dialog = request.app.state.dialog_manager
    conv_id = dialog.create_conversation()
    return {
        "conversation_id": conv_id,
        "message": "对话已开始",
        "status": "active",
    }


@conversation.post("/message")
async def send_message(
    request: Request,
    conversation_id: str,
    message: str,
    message_type: str = "text",
) -> Dict[str, Any]:
    """发送文本消息给对话管理器"""
    try:
        dialog = request.app.state.dialog_manager
        result = await dialog.process_message(
            message=message,
            conversation_id=conversation_id,
        )
        response = {
            "conversation_id": result["conversation_id"],
            "response": result["response"],
            "intent": result["intent"],
            "confidence": result["confidence"],
        }
        # 包含智能体信息（如果有多智能体路由）
        if "agent" in result:
            response["agent"] = result["agent"]
        return response
    except Exception as e:
        logger.error(f"对话处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 对话历史管理
# ============================================================

@conversation.get("/history", summary="获取对话历史列表")
async def list_conversations(
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """获取最近的对话历史列表（分页）"""
    try:
        records = await database_service.list_conversations(limit=limit, offset=offset)
        return {
            "conversations": records,
            "count": len(records),
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        return {"conversations": [], "count": 0, "limit": limit, "offset": offset}


@conversation.get("/history/{conv_id}", summary="获取对话详情")
async def get_conversation_detail(conv_id: str) -> Dict[str, Any]:
    """获取指定对话的详情，包含所有消息"""
    try:
        conversation = await database_service.get_conversation(conv_id)
        if not conversation:
            raise HTTPException(status_code=404, detail=f"对话 '{conv_id}' 不存在")
        messages = await database_service.get_conversation_messages(conv_id)
        conversation["messages"] = messages
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@conversation.delete("/history/{conv_id}", summary="删除对话")
async def delete_conversation(conv_id: str) -> Dict[str, Any]:
    """删除指定对话及其所有消息"""
    try:
        success = await database_service.delete_conversation(conv_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"对话 '{conv_id}' 不存在")
        return {"message": f"对话 '{conv_id}' 已删除", "conversation_id": conv_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除对话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 功能调用
# ============================================================
@functions.get("/weather")
async def get_weather(city: str = "北京") -> Dict[str, Any]:
    """获取天气信息"""
    try:
        result = await weather_function(city)
        return {
            "city": city,
            "temperature": result.get("temperature", ""),
            "weather": result.get("weather", ""),
            "humidity": result.get("humidity", ""),
            "wind": result.get("wind", ""),
        }
    except Exception as e:
        logger.error(f"天气查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@functions.post("/device/control")
async def control_device(
    device_id: str,
    action: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """设备控制"""
    try:
        params = parameters or {}
        if action == "turn_on":
            success = device_manager.turn_on(device_id)
        elif action == "turn_off":
            success = device_manager.turn_off(device_id)
        elif action == "set_value":
            value = params.get("value", 0)
            success = device_manager.set_value(device_id, value)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的动作: {action}")

        if not success:
            raise HTTPException(status_code=404, detail=f"设备 {device_id} 不存在")

        device = device_manager.get_device(device_id)
        return {
            "device_id": device_id,
            "device_name": device["name"] if device else device_id,
            "action": action,
            "status": device["status"] if device else "unknown",
            "message": f"设备 {device_id} 已执行 {action} 操作",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设备控制失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 配置管理（运行时动态配置）
# ============================================================

class SettingsUpdate(BaseModel):
    """配置更新请求体"""
    enable_voice_dialogue: Optional[bool] = None
    nlu_provider_name: Optional[str] = None
    dialog_provider_name: Optional[str] = None
    assistant_personality: Optional[str] = None
    enable_headroom_compression: Optional[bool] = None


@settings_router.get("", summary="获取当前配置状态")
async def get_settings() -> Dict[str, Any]:
    """获取当前运行时配置状态"""
    config = runtime_config.to_dict()
    # 附加默认 Provider 信息
    default_provider = provider_registry.get_default()
    if default_provider:
        config["default_provider"] = {
            "name": default_provider.name,
            "api_base": default_provider.api_base,
            "model": default_provider.model,
            "api_key_configured": bool(default_provider.api_key),
        }
    else:
        config["default_provider"] = None
    # 附加所有 Provider 列表（供前端下拉框选择）
    providers = provider_registry.get_all()
    config["providers"] = [
        {
            "name": p.name,
            "api_base": p.api_base,
            "model": p.model,
            "api_key_configured": bool(p.api_key),
        }
        for p in providers
    ]
    # 附加语音 Provider 信息
    from app.core.voice_providers import voice_provider_registry
    voice_vp = voice_provider_registry.get_active() or voice_provider_registry.get_default()
    config["voice_provider"] = {
        "name": voice_vp.name if voice_vp else "",
        "api_base": voice_vp.api_base if voice_vp else "",
        "model": voice_vp.model if voice_vp else "",
        "voice": voice_vp.voice if voice_vp else "",
        "enabled": voice_vp.enabled if voice_vp else False,
        "response_format": voice_vp.response_format if voice_vp else "pcm",
        "encode_format": voice_vp.encode_format if voice_vp else "base64",
        "speed": voice_vp.speed if voice_vp else 1.0,
        "volume": voice_vp.volume if voice_vp else 1.0,
        "api_key_configured": bool(voice_vp.api_key) if voice_vp else False,
    } if voice_vp else None
    return config


@settings_router.post("", summary="更新配置")
async def update_settings(update: SettingsUpdate) -> Dict[str, Any]:
    """
    更新运行时配置（功能开关 + Provider 绑定）

    LLM Provider 配置请使用 /api/v1/providers 端点管理。
    Voice Provider 配置请使用 /api/v1/voice-providers 端点管理。

    Provider 绑定时，传入的 provider_name 必须存在于 ProviderRegistry 中，
    未设置或不存在时自动回退到 "default" Provider。
    """
    if update.enable_voice_dialogue is not None:
        runtime_config.enable_voice_dialogue = update.enable_voice_dialogue
        logger.info(f"[配置] 语音对话功能已{'开启' if update.enable_voice_dialogue else '关闭'}")

    if update.nlu_provider_name is not None:
        runtime_config.nlu_provider_name = update.nlu_provider_name
        logger.info(f"[配置] NLU Provider 已切换为: {update.nlu_provider_name}")

    if update.dialog_provider_name is not None:
        runtime_config.dialog_provider_name = update.dialog_provider_name
        logger.info(f"[配置] Dialog Provider 已切换为: {update.dialog_provider_name}")

    if update.assistant_personality is not None:
        runtime_config.assistant_personality = update.assistant_personality
        logger.info(f"[配置] 全局 AI 性格已更新")

    if update.enable_headroom_compression is not None:
        runtime_config.enable_headroom_compression = update.enable_headroom_compression
        logger.info(f"[配置] headroom-ai 压缩已{'开启' if update.enable_headroom_compression else '关闭'}")

    return await get_settings()


# ============================================================
# Provider 管理 API
# ============================================================

providers_router = APIRouter()


class ProviderCreate(BaseModel):
    """创建/更新 Provider 请求体"""
    name: str
    api_base: str
    api_key: str = ""
    model: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7


@providers_router.get("", summary="获取所有 Provider")
async def get_providers() -> Dict[str, Any]:
    """获取所有已配置的大模型接口 Provider"""
    providers = provider_registry.get_all()
    return {
        "providers": [
            {
                "name": p.name,
                "api_base": p.api_base,
                "model": p.model,
                "api_key_configured": bool(p.api_key),
                "max_tokens": p.max_tokens,
                "temperature": p.temperature,
            }
            for p in providers
        ],
        "count": len(providers),
    }


@providers_router.get("/{name}", summary="获取单个 Provider")
async def get_provider(name: str) -> Dict[str, Any]:
    """获取指定名称的 Provider 详情"""
    provider = provider_registry.get(name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' 不存在")
    return {
        "name": provider.name,
        "api_base": provider.api_base,
        "model": provider.model,
        "api_key_configured": bool(provider.api_key),
        "max_tokens": provider.max_tokens,
        "temperature": provider.temperature,
    }


@providers_router.post("", summary="创建 Provider", status_code=201)
async def create_provider(data: ProviderCreate) -> Dict[str, Any]:
    """创建新的 LLM Provider"""
    existing = provider_registry.get(data.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Provider '{data.name}' 已存在，请使用 PATCH 更新",
        )

    provider = LlmProvider(
        name=data.name,
        api_base=data.api_base,
        api_key=data.api_key,
        model=data.model,
        max_tokens=data.max_tokens,
        temperature=data.temperature,
    )
    provider_registry.upsert(data.name, provider)
    logger.info(f"[Provider] 已创建: {data.name} ({data.api_base})")

    return {
        "message": f"Provider '{data.name}' 已创建",
        "name": data.name,
        "api_base": data.api_base,
        "model": data.model,
        "api_key_configured": bool(data.api_key),
    }


@providers_router.patch("/{name}", summary="更新 Provider")
async def update_provider(name: str, data: ProviderCreate) -> Dict[str, Any]:
    """更新指定 Provider 的配置"""
    existing = provider_registry.get(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' 不存在")

    provider = LlmProvider(
        name=name,
        api_base=data.api_base or existing.api_base,
        api_key=data.api_key or existing.api_key,
        model=data.model or existing.model,
        max_tokens=data.max_tokens or existing.max_tokens,
        temperature=data.temperature if data.temperature is not None else existing.temperature,
    )
    provider_registry.upsert(name, provider)
    logger.info(f"[Provider] 已更新: {name}")

    return {
        "message": f"Provider '{name}' 已更新",
        "name": name,
        "api_base": provider.api_base,
        "model": provider.model,
        "api_key_configured": bool(provider.api_key),
    }


@providers_router.delete("/{name}", summary="删除 Provider")
async def delete_provider(name: str) -> Dict[str, Any]:
    """删除指定名称的 Provider（不允许删除 default）"""
    if name == "default":
        raise HTTPException(status_code=400, detail="不允许删除默认 Provider")
    if not provider_registry.get(name):
        raise HTTPException(status_code=404, detail=f"Provider '{name}' 不存在")

    provider_registry.delete(name)
    logger.info(f"[Provider] 已删除: {name}")

    return {"message": f"Provider '{name}' 已删除"}


# ============================================================
# 多智能体管理 API
# ============================================================

agents_router = APIRouter()


@agents_router.get("", summary="获取所有智能体列表")
async def get_agents() -> Dict[str, Any]:
    """获取所有已注册的智能体及其配置"""
    agents = agent_registry.get_all()
    return {
        "agents": [
            {
                "name": cfg.name,
                "display_name": cfg.display_name,
                "description": cfg.description,
                "model": cfg.model,
                "api_base": cfg.api_base,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "enabled": cfg.enabled,
                "is_specialist": cfg.is_specialist,
                "system_prompt": cfg.system_prompt,
                "personality": cfg.personality,
                "equipped_skills": cfg.equipped_skills,
            }
            for cfg in agents.values()
        ],
        "count": len(agents),
    }


@agents_router.get("/enabled", summary="获取已启用的专精智能体")
async def get_enabled_agents() -> Dict[str, Any]:
    """获取当前已启用的专精智能体列表"""
    specialists = agent_registry.get_specialists()
    return {
        "agents": [
            {
                "name": cfg.name,
                "display_name": cfg.display_name,
                "description": cfg.description,
            }
            for cfg in specialists.values()
        ],
    }


class AgentUpdate(BaseModel):
    """智能体配置更新"""
    enabled: Optional[bool] = None
    model: Optional[str] = None
    api_base: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    personality: Optional[str] = None
    equipped_skills: Optional[List[str]] = None


@agents_router.patch("/{agent_name}", summary="更新智能体配置")
async def update_agent(agent_name: str, update: AgentUpdate) -> Dict[str, Any]:
    """更新指定智能体的配置"""
    agent = agent_registry.get(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"智能体 '{agent_name}' 不存在")

    # 只取客户端显式发送的字段（排除未发送的 None）
    allowed_fields = {"enabled", "model", "api_base", "temperature", "max_tokens", "system_prompt", "personality", "equipped_skills"}
    updates = {}
    for field in update.model_fields_set:
        if field in allowed_fields:
            value = getattr(update, field)
            # model / api_base 设为 None 或空字符串时，重置为空（使用默认）
            if field in ("model", "api_base") and not value:
                value = ""
            updates[field] = value

    if not updates:
        return {"message": "无更新内容", "agent": agent_name}

    # 校验：启用智能体时必须已配置模型
    if updates.get("enabled") is True:
        # 获取更新后的 model 值（优先取本次更新值，否则取当前值）
        final_model = updates.get("model", agent.model)
        if not final_model:
            raise HTTPException(
                status_code=400,
                detail=f"无法启用 '{agent_name}'：请先为该智能体配置模型（model 不能为空）",
            )

    agent_registry.update_agent(agent_name, updates)
    logger.info(f"[多智能体] 更新 '{agent_name}': {updates}")

    return {
        "message": f"智能体 '{agent_name}' 配置已更新",
        "updates": updates,
    }


# ============================================================
# 语音 Provider 管理 API
# ============================================================

voice_providers_router = APIRouter()


class VoiceProviderCreate(BaseModel):
    """创建/更新语音 Provider 请求体"""
    name: str
    api_base: str
    api_key: str = ""
    model: str = "glm-tts"
    voice: str = "female"
    voice_type: str = "preset"  # "preset" | "clone"
    clone_settings: dict = None  # 声音复刻配置
    enabled: bool = False
    response_format: str = "pcm"
    encode_format: str = "base64"
    speed: float = 1.0
    volume: float = 1.0


def _voice_provider_to_dict(p) -> dict:
    """将 VoiceProvider 序列化为 API 响应字典"""
    return {
        "name": p.name,
        "api_base": p.api_base,
        "model": p.model,
        "voice": p.voice,
        "voice_type": p.voice_type,
        "clone_settings": p.clone_settings or {},
        "enabled": p.enabled,
        "response_format": p.response_format,
        "encode_format": p.encode_format,
        "speed": p.speed,
        "volume": p.volume,
        "api_key_configured": bool(p.api_key),
    }


@voice_providers_router.get("", summary="获取所有语音 Provider")
async def get_voice_providers() -> Dict[str, Any]:
    """获取所有已配置的语音合成 Provider"""
    providers = voice_provider_registry.get_all()
    return {
        "providers": [_voice_provider_to_dict(p) for p in providers],
        "count": len(providers),
    }


@voice_providers_router.patch("/{name}", summary="更新语音 Provider")
async def update_voice_provider(name: str, data: VoiceProviderCreate) -> Dict[str, Any]:
    """更新指定语音 Provider 的配置"""
    existing = voice_provider_registry.get(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"语音 Provider '{name}' 不存在")

    provider = VoiceProvider(
        name=name,
        api_base=data.api_base or existing.api_base,
        api_key=data.api_key or existing.api_key,
        model=data.model or existing.model,
        voice=data.voice or existing.voice,
        voice_type=data.voice_type or existing.voice_type,
        clone_settings=data.clone_settings if data.clone_settings is not None else existing.clone_settings,
        enabled=data.enabled if data.enabled is not None else existing.enabled,
        response_format=data.response_format or existing.response_format,
        encode_format=data.encode_format or existing.encode_format,
        speed=data.speed if data.speed is not None else existing.speed,
        volume=data.volume if data.volume is not None else existing.volume,
    )
    voice_provider_registry.upsert(name, provider)
    logger.info(f"[语音Provider] 已更新: {name} (model={provider.model}, voice={provider.voice}, voice_type={provider.voice_type})")

    return {
        **{"message": f"语音 Provider '{name}' 已更新"},
        **_voice_provider_to_dict(provider),
    }


@voice_providers_router.post("", summary="创建语音 Provider", status_code=201)
async def create_voice_provider(data: VoiceProviderCreate) -> Dict[str, Any]:
    """创建新的语音合成 Provider"""
    existing = voice_provider_registry.get(data.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"语音 Provider '{data.name}' 已存在，请使用 PATCH 更新",
        )

    provider = VoiceProvider(
        name=data.name,
        api_base=data.api_base,
        api_key=data.api_key,
        model=data.model,
        voice=data.voice,
        voice_type=data.voice_type,
        clone_settings=data.clone_settings,
        enabled=data.enabled,
        response_format=data.response_format,
        encode_format=data.encode_format,
        speed=data.speed,
        volume=data.volume,
    )
    voice_provider_registry.upsert(data.name, provider)
    logger.info(f"[语音Provider] 已创建: {data.name} ({data.api_base})")

    return {
        **{"message": f"语音 Provider '{data.name}' 已创建"},
        **_voice_provider_to_dict(provider),
    }


@voice_providers_router.delete("/{name}", summary="删除语音 Provider")
async def delete_voice_provider(name: str) -> Dict[str, Any]:
    """删除指定名称的语音 Provider"""
    if not voice_provider_registry.get(name):
        raise HTTPException(status_code=404, detail=f"语音 Provider '{name}' 不存在")

    voice_provider_registry.delete(name)
    logger.info(f"[语音Provider] 已删除: {name}")

    return {"message": f"语音 Provider '{name}' 已删除"}


# ============================================================
# 技能管理 API
# ============================================================

skills_router = APIRouter()


@skills_router.get("", summary="获取所有可用技能")
async def get_skills() -> Dict[str, Any]:
    """获取所有已注册的技能列表（含每个技能的详细函数信息）"""
    skills = skill_registry.get_all_skills()
    return {
        "skills": [
            {
                "name": sk.name,
                "display_name": sk.display_name,
                "description": sk.description,
                "category": sk.category,
                "enabled": sk.enabled,
                "functions": [
                    {
                        "name": fn.name,
                        "description": fn.description,
                        "parameters": fn.parameters,
                    }
                    for fn in sk.functions
                ],
            }
            for sk in skills.values()
        ],
        "count": len(skills),
    }


@skills_router.get("/enabled", summary="获取已启用的技能")
async def get_enabled_skills() -> Dict[str, Any]:
    """获取当前已启用的技能列表"""
    skills = skill_registry.get_enabled_skills()
    return {
        "skills": [
            {
                "name": sk.name,
                "display_name": sk.display_name,
                "description": sk.description,
                "category": sk.category,
                "functions": [fn.name for fn in sk.functions],
            }
            for sk in skills.values()
        ],
    }


@skills_router.get("/{skill_name}", summary="获取技能详情")
async def get_skill_detail(skill_name: str) -> Dict[str, Any]:
    """获取指定技能的详细信息"""
    skill = skill_registry.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"技能 '{skill_name}' 不存在")

    return {
        "name": skill.name,
        "display_name": skill.display_name,
        "description": skill.description,
        "category": skill.category,
        "enabled": skill.enabled,
        "functions": [
            {
                "name": fn.name,
                "description": fn.description,
                "parameters": fn.parameters,
            }
            for fn in skill.functions
        ],
    }


# ============================================================
# MCP 服务器管理
# ============================================================

@skills_router.get("/mcp/servers", summary="获取所有 MCP 服务器")
async def get_mcp_servers() -> Dict[str, Any]:
    """获取所有已注册的 MCP 服务器列表"""
    servers = mcp_registry.list_servers()
    return {
        "servers": [
            {
                "name": s.name,
                "display_name": s.display_name,
                "url": s.url,
                "enabled": s.enabled,
                "tool_count": len(s.tools),
            }
            for s in servers
        ],
        "count": len(servers),
    }


class MCPServerCreate(BaseModel):
    """创建 MCP 服务器的请求"""
    name: str
    display_name: str = ""
    url: str
    api_key: str = ""


@skills_router.post("/mcp/servers", summary="注册 MCP 服务器")
async def create_mcp_server(data: MCPServerCreate) -> Dict[str, Any]:
    """注册一个新的 MCP 服务器"""
    if mcp_registry.get_server(data.name):
        raise HTTPException(status_code=400, detail=f"MCP 服务器 '{data.name}' 已存在")

    config = MCPServerConfig(
        name=data.name,
        display_name=data.display_name or data.name,
        url=data.url,
        api_key=data.api_key,
    )
    mcp_registry.register_server(config)
    return {"status": "ok", "name": config.name}


@skills_router.delete("/mcp/servers/{server_name}", summary="移除 MCP 服务器")
async def delete_mcp_server(server_name: str) -> Dict[str, Any]:
    """移除 MCP 服务器及其注册的技能"""
    if not mcp_registry.get_server(server_name):
        raise HTTPException(status_code=404, detail=f"MCP 服务器 '{server_name}' 不存在")

    mcp_registry.remove_server(server_name)
    return {"status": "ok", "name": server_name}


@skills_router.post("/mcp/servers/{server_name}/discover", summary="发现 MCP 工具")
async def discover_mcp_tools(server_name: str) -> Dict[str, Any]:
    """从 MCP 服务器发现并注册工具"""
    try:
        tools = await mcp_registry.discover_tools(server_name)
        return {
            "status": "ok",
            "server": server_name,
            "tools": tools,
            "count": len(tools),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MCP 连接失败: {e}")
