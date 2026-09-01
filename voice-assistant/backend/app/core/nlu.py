"""
自然语言理解模块 (NLU — Natural Language Understanding)
意图识别 + 实体抽取，采用混合策略：
  1. 规则引擎（正则表达式）快速匹配，返回高置信度结果
  2. 匹配失败时调用大模型 API（OpenAI 兼容接口）进行意图识别

支持意图:
  - weather_query   : 天气查询
  - device_control  : 智能家居控制
  - schedule        : 日程管理
  - music_play      : 音乐播放
  - general_chat    : 通用聊天（兜底）

返回格式:
  Intent(name="weather_query", confidence=0.85, entities={"city": "北京", "date": "明天"})
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

import httpx

from app.core.config import settings, runtime_config
from app.core.http_client import get_http_client
from app.core.llm_providers import provider_registry
from app.core.multi_agent import agent_registry

logger = logging.getLogger("voice-assistant.nlu")


# ============================================================
# 意图结果数据结构
# ============================================================
class Intent:
    """意图识别结果"""

    def __init__(
        self,
        name: str,
        confidence: float,
        entities: Optional[Dict[str, Any]] = None,
    ):
        self.name = name                       # 意图名称
        self.confidence = confidence           # 置信度 (0.0 ~ 1.0)
        self.entities = entities or {}          # 抽取的实体键值对

    def __repr__(self) -> str:
        return (
            f"Intent(name={self.name}, "
            f"confidence={self.confidence:.2f}, "
            f"entities={self.entities})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（与对话管理器交互使用）"""
        return {
            "intent": self.name,
            "confidence": self.confidence,
            "entities": self.entities,
        }


# ============================================================
# 规则引擎：正则意图模式 + 实体抽取
# ============================================================
class RuleEngine:
    """
    基于正则表达式的规则引擎

    每个意图包含多组匹配模式，命中模式数量越多 → 置信度越高。
    实体抽取从文本中提取时间、地点、设备名、数字等关键信息。
    """

    # ============================================================
    # 意图匹配规则
    # 每组规则是一个列表，命中越多置信度越高
    # ============================================================
    INTENT_PATTERNS: Dict[str, List[str]] = {
        # ---------- 天气查询 ----------
        "weather_query": [
            # 核心关键词
            r"天气", r"气温", r"温度", r"多少度",
            r"下雨", r"下雪", r"刮风", r"台风", r"雾霾",
            r"晴天", r"阴天", r"多云", r"暴雨",
            # 带地点的查询
            r"冷不冷", r"热不热", r"暖和吗",
            r"天气预报", r"一周天气", r"明天天气",
            r"穿什么", r"带伞",
        ],

        # ---------- 智能家居控制 ----------
        "device_control": [
            # 动作动词
            r"打开", r"关闭", r"开关", r"调节", r"调整", r"设置",
            r"开(一下|灯|空调|电视)?$",
            r"关(一下|灯|空调|电视)?$",
            # 设备名
            r"灯", r"空调", r"电视", r"窗帘", r"风扇",
            r"音响", r"投影仪", r"加湿器", r"净化器",
            r"热水器", r"电饭煲", r"扫地机",
            # 场景
            r"亮度", r"音量", r"温度.*调", r"模式",
            r"开灯", r"关灯", r"把.*打开", r"把.*关闭",
        ],

        # ---------- 日程管理 ----------
        "schedule": [
            # 日程创建
            r"提醒[我我]?", r"记[录得]?", r"设置.*提醒",
            r"创建.*日程", r"添加.*事件", r"安排.*会议",
            r"定个.*闹钟", r"设个.*提醒",
            # 日程查询
            r"今天.*安排", r"明天.*日程",
            r"查看.*日历", r"看看.*行程",
            r"有什么.*安排", r"待办",
            # 日程删除
            r"取消.*日程", r"删除.*提醒", r"移除.*事件",
            # 时间相关
            r"明天.*几点", r"后天.*会议",
            r"这周五", r"下周一",
            r"提醒我.*(点|分|钟)",
        ],

        # ---------- 音乐播放 ----------
        "music_play": [
            # 播放动作
            r"播放", r"暂停", r"下一首", r"上一首",
            r"听一下", r"放(个|首)?",
            r"唱(个|首)?", r"来(首|个|点)?",
            r"关掉音乐", r"停止播放",
            # 歌手/歌曲/类型
            r"歌", r"音乐", r"歌曲", r"旋律", r"曲子",
            r"周杰伦", r"林俊杰", r"邓紫棋", r"陈奕迅",
            r"流行", r"古典", r"摇滚", r"轻音乐",
            # 歌名关键词
            r"听.*的歌", r"放.*的歌",
            r"音量.*(大|小|调)",
        ],

        # ---------- 通用聊天（兜底意图，仅最低匹配） ----------
        "general_chat": [
            # 问候类
            r"你好", r"您好", r"嗨", r"hi", r"hello",
            r"早上好", r"下午好", r"晚上好",
            # 近况/闲聊
            r"你叫什么", r"你是谁", r"你多大了",
            r"你会什么", r"你能做什么",
            r"你好吗", r"怎么样",
            r"帮个忙", r"问你个问题",
            # 感谢/肯定
            r"谢谢", r"好的", r"明白了", r"知道了",
            r"可以", r"不错", r"厉害",
        ],
    }

    # ============================================================
    # 实体抽取规则
    # ============================================================
    ENTITY_PATTERNS: Dict[str, str] = {
        # 城市/地点
        "city": (
            r"北京|上海|广州|深圳|杭州|成都|武汉|"
            r"南京|天津|重庆|苏州|西安|长沙|青岛|"
            r"大连|厦门|宁波|福州|合肥|郑州|"
            r"哈尔滨|沈阳|昆明|贵阳|海口|拉萨|兰州|"
            r"香港|澳门|台北"
        ),
        # 日期：今天/明天/后天/周X/星期X/日期数字
        "date": (
            r"今天|明天|后天|昨天|"
            r"周一|周二|周三|周四|周五|周六|周日|"
            r"星期一|星期二|星期三|星期四|星期五|星期六|星期日|星期天|"
            r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?"
        ),
        # 时间：几点几分（含"下午3点"这类带时段前缀的完整表达）
        # 修复说明：原正则含捕获组，导致 re.findall 返回元组而非字符串；
        # 现改用非捕获组，并让时段前缀与数字整体匹配（"下午3点" 不再被拆成 "下午" + "3点"）
        "time": (
            r"\d{1,2}[:：]\d{2}|"
            r"(?:凌晨|早上|上午|中午|下午|傍晚|晚上|深夜)?\d{1,2}点(?:\d{1,2}分)?(?:半)?|"
            r"凌晨|早上|上午|中午|下午|傍晚|晚上|深夜"
        ),
        # 设备名
        "device": (
            r"灯[光]?|空调|电视[机]?|窗帘|风扇|"
            r"音响|投影仪|加湿器|空气净化器|[净化器]|"
            r"热水器|电饭煲|扫地机[器人]?|洗衣机|冰箱|"
            r"门锁|摄像头|传感器"
        ),
        # 动作/操作
        "action": r"打开|关闭|开|关|调节|调整|设置|开启|启动|停止|暂停",
        # 数字（整数、小数、百分比）
        # 修复说明：原捕获组 (\.\d+)? 会让 re.findall 返回空串而非数字，改用非捕获组
        "number": r"\d+(?:\.\d+)?[%％]?",
        # 温度单位
        "temperature_unit": r"度|摄氏度|华氏度",
        # 歌手/音乐人
        "artist": r"周杰伦|林俊杰|邓紫棋|陈奕迅|王菲|李荣浩|张学友|刘德华|许嵩|毛不易",
        # 音乐类型
        "genre": r"流行|古典|摇滚|轻音乐|爵士|民谣|R&B|电子|说唱|纯音乐",
    }

    # ============================================================
    # 意图与意图关键词的置信度映射
    # ============================================================
    # 每命中一条规则增加的置信度基数
    CONFIDENCE_PER_MATCH = {
        "weather_query": 0.20,
        "device_control": 0.20,
        "schedule": 0.18,
        "music_play": 0.18,
        "general_chat": 0.15,
    }
    # 基础置信度（首次命中时）
    BASE_CONFIDENCE = {
        "weather_query": 0.40,
        "device_control": 0.45,
        "schedule": 0.35,
        "music_play": 0.35,
        "general_chat": 0.25,
    }

    def classify(self, text: str) -> Tuple[str, float]:
        """
        基于正则匹配识别意图

        策略:
          - 对每个意图统计命中的正则数量
          - 按命中率 = 命中数 / 总规则数 计算置信度
          - 取置信度最高的意图

        返回:
          (intent_name, confidence)
        """
        best_intent = "general_chat"
        best_confidence = 0.0

        for intent_name, patterns in self.INTENT_PATTERNS.items():
            matches = 0
            for pattern in patterns:
                if re.search(pattern, text):
                    matches += 1

            if matches == 0:
                continue

            # 置信度 = 基础值 + 命中数 × 单条增量
            increment = self.CONFIDENCE_PER_MATCH.get(intent_name, 0.15)
            base = self.BASE_CONFIDENCE.get(intent_name, 0.30)
            confidence = min(base + matches * increment, 0.98)

            if confidence > best_confidence:
                best_confidence = confidence
                best_intent = intent_name

        return best_intent, best_confidence

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        从文本中抽取实体

        对每种实体类型执行正则匹配，找到第一个非空结果。
        日期和时间实体做额外格式化。
        """
        entities: Dict[str, Any] = {}

        for entity_type, pattern in self.ENTITY_PATTERNS.items():
            matches = re.findall(pattern, text)
            if matches:
                # 取第一个匹配作为实体的值
                value = matches[0] if isinstance(matches, list) else matches
                entities[entity_type] = value

        # ---- 日期标准化 ----
        date_str = entities.get("date", "")
        if date_str:
            entities["date"] = self._normalize_date(date_str)

        # ---- 时间标准化 ----
        time_str = entities.get("time", "")
        if time_str:
            entities["time"] = self._normalize_time(time_str)

        return entities

    # ============================================================
    # 实体标准化
    # ============================================================

    @staticmethod
    def _normalize_date(date_text: str) -> str:
        """
        将相对日期（"今天"/"明天"）转为绝对日期 "YYYY-MM-DD"
        """
        today = datetime.now()
        # 修复：使用 timedelta 计算相对日期，避免月末（如 8/31）day+1 越界抛 ValueError
        date_map = {
            "今天": today.strftime("%Y-%m-%d"),
            "明天": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
            "后天": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
            "昨天": (today + timedelta(days=-1)).strftime("%Y-%m-%d"),
        }

        if date_text in date_map:
            return date_map[date_text]

        # 尝试解析 "2024-01-15" 或 "2024年1月15日" 格式
        match = re.match(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日号]?", date_text)
        if match:
            return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"

        return date_text

    @staticmethod
    def _normalize_time(time_text: str) -> str:
        """
        将时间描述标准化为 "HH:MM"

        支持 "3点" / "3点30分" / "3点半" / "下午3点" / "15:30" 等形式。
        修复说明：原正则括号不匹配（会抛 re.error），且时段换算有误
        （"下午3点" 被算成 16:00）；现改为按 PM 时段对 12 小时制 +12 转换。
        """
        # 先处理 "15:30" 冒号格式
        match = re.match(r"(\d{1,2})[:：](\d{2})", time_text)
        if match:
            return f"{match.group(1).zfill(2)}:{match.group(2)}"

        # 下午/晚间（PM）时段：小时小于 12 时需要 +12 转为 24 小时制
        pm_periods = ("中午", "下午", "傍晚", "晚上", "深夜")
        am_periods = ("凌晨", "早上", "上午")

        period = ""
        rest = time_text
        for p in pm_periods + am_periods:
            if time_text.startswith(p):
                period = p
                rest = time_text[len(p):]
                break

        # 解析 "3点" / "3点30分" / "3点半"
        match = re.match(r"(\d{1,2})点(?:(\d{1,2})分)?(半)?", rest)
        if match:
            hour = int(match.group(1))
            if match.group(2):
                minute = int(match.group(2))
            elif match.group(3):  # "半" 表示 30 分
                minute = 30
            else:
                minute = 0

            # PM 时段下转为 24 小时制（"下午3点" -> 15:00）
            if period in pm_periods and hour < 12:
                hour += 12

            return f"{hour:02d}:{minute:02d}"

        return time_text


# ============================================================
# LLM 意图识别（OpenAI 兼容接口）
# ============================================================
class LLMIntentClassifier:
    """
    基于大模型的意图识别（Agent 感知增强版）

    当规则引擎置信度低于阈值时，调用此分类器作为兜底。
    支持 OpenAI 兼容 API（如 OpenAI、Azure OpenAI、本地 LLM 等）。

    增强特性:
      - 动态从 AgentRegistry 获取所有专精智能体的名称和描述
      - 将智能体信息注入 SYSTEM_PROMPT，使 LLM 能识别"写代码/翻译/写诗"等意图
      - 意图类别 = 5个内置意图 + 所有专精智能体名称
    """

    # 基础意图定义（固定不变的部分）
    BASE_INTENTS = [
        ("weather_query", "查询天气、气温、降水、风速等"),
        ("device_control", "控制智能家居设备（灯、空调、电视等）"),
        ("schedule", "日程管理（创建提醒、查询安排、取消事件）"),
        ("music_play", "音乐播放（播放、暂停、切歌、歌名、歌手）"),
        ("general_chat", "通用聊天（问候、寒暄、闲聊、感谢、提问）"),
    ]

    # 基础实体定义
    BASE_ENTITIES_DESC = """需要抽取的实体（entities），没有的字段留空字符串:
- city       : 城市名（如"北京"）
- date       : 日期（如"2024-01-15"、"明天"）
- time       : 时间（如"15:30"、"晚上8点"）
- device     : 设备名（如"空调"）
- action     : 操作（如"打开"）
- number     : 数字（如"26"）
- artist     : 歌手名
- song       : 歌曲名
- genre      : 音乐类型
- event_name : 日程事件名
- agent_request : 是否请求调用专精智能体（true/false），当用户明确要求某个专业领域时设为true
- raw_text   : 用户输入的原文"""

    # JSON 输出格式模板
    OUTPUT_FORMAT = """请严格按以下 JSON 格式返回（不要包含 markdown 代码块标记，纯 JSON）:
{
    "intent": "weather_query",
    "confidence": 0.95,
    "entities": {
        "city": "北京",
        "date": "明天",
        "time": "",
        "device": "",
        "action": "",
        "number": "",
        "artist": "",
        "song": "",
        "genre": "",
        "event_name": "",
        "agent_request": false,
        "raw_text": "北京明天天气怎么样"
    }
}"""

    def _build_system_prompt(self) -> str:
        """
        动态构建 SYSTEM_PROMPT

        从 AgentRegistry 获取所有已启用的专精智能体，
        将其名称和描述注入到意图识别指令中。
        """
        # ---- 动态获取智能体列表 ----
        specialists = agent_registry.get_specialists()
        agent_intents = []
        for name, cfg in specialists.items():
            # 跳过 general_chat（已在基础意图中）
            if name == "general_chat":
                continue
            agent_intents.append(f"- {name}: {cfg.description}")

        # ---- 构建意图列表 ----
        intent_lines = []
        for intent_name, intent_desc in self.BASE_INTENTS:
            intent_lines.append(f"- {intent_name:16s}: {intent_desc}")

        if agent_intents:
            intent_lines.append("")
            intent_lines.append("同时，如果用户请求涉及以下专业领域，请将 intent 设为对应的智能体名称:")
            intent_lines.extend(agent_intents)
            intent_lines.append("")
            intent_lines.append('判断逻辑：当用户明确要求专业服务时（如\u201c翻译这段话\u201d\u2192translator、')
            intent_lines.append('\u201c写一段代码\u201d\u2192code_expert、\u201c写首诗\u201d\u2192creative、\u201c分析数据\u201d\u2192analyst)，')
            intent_lines.append('将 intent 设为对应的智能体名称，并在 entities.agent_request 中设为 true。')
            intent_lines.append('如果模糊不清或属于日常闲聊，保留为 general_chat。')

        intent_list = "\n".join(intent_lines)

        prompt = f"""你是一个智能语音助手的意图识别引擎。请分析用户输入，返回 JSON 格式结果。

可识别的意图（intent）:
{intent_list}

{self.BASE_ENTITIES_DESC}

{self.OUTPUT_FORMAT}"""
        return prompt

    def __init__(self):
        self.max_tokens = settings.OPENAI_MAX_TOKENS
        self.temperature = settings.OPENAI_TEMPERATURE

    @property
    def available(self) -> bool:
        """LLM 是否可用：NLU 配置的 Provider 存在且有 API Key 配置"""
        provider_name = runtime_config.nlu_provider_name
        provider = provider_registry.get(provider_name) or provider_registry.get_default()
        if not provider:
            return False
        return bool(provider.api_key)

    async def classify(self, text: str) -> Tuple[str, float, Dict[str, Any]]:
        """
        调用 LLM 进行意图识别

        参数:
            text: 用户输入文本

        返回:
            (intent_name, confidence, entities_dict)

        异常时:
            返回 ("general_chat", 0.3, {"raw_text": text})
        """
        if not self.available:
            logger.warning("[NLU-LLM] LLM 不可用，跳过 LLM 分类")
            return "general_chat", 0.3, {"raw_text": text}

        # 每次调用前从 NLU 配置的 Provider 获取最新配置（支持运行时热更新）
        provider_name = runtime_config.nlu_provider_name
        provider = provider_registry.get(provider_name) or provider_registry.get_default()
        if not provider:
            logger.warning("[NLU-LLM] 无可用 Provider，跳过 LLM 分类")
            return "general_chat", 0.3, {"raw_text": text}

        api_base = provider.api_base
        model = provider.model or "gpt-3.5-turbo"
        has_key = bool(provider.api_key)

        logger.debug(f"[NLU-LLM] 正在调用 LLM 识别: \"{text[:50]}...\" (provider={provider.name}, model={model})")

        try:
            # 有 API Key 时添加 Authorization 头
            headers = {"Content-Type": "application/json"}
            if has_key:
                headers["Authorization"] = f"Bearer {provider.api_key}"

            # ---- 每次调用时动态构建提示词（Agent 感知） ----
            system_prompt = self._build_system_prompt()

            client = get_http_client()
            response = await client.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text},
                    ],
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                },
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()

        except httpx.TimeoutException:
            logger.warning("[NLU-LLM] API 请求超时")
            return "general_chat", 0.3, {"raw_text": text}

        except httpx.HTTPStatusError as e:
            logger.warning(f"[NLU-LLM] API HTTP 错误: {e.response.status_code}")
            return "general_chat", 0.3, {"raw_text": text}

        except Exception as e:
            logger.warning(f"[NLU-LLM] API 调用异常: {e}")
            return "general_chat", 0.3, {"raw_text": text}

        # ---- 解析 LLM 返回 ----
        try:
            content = data["choices"][0]["message"]["content"].strip()
            # 去除可能的 markdown 代码块标记
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
            result = json.loads(content)

            intent_name = result.get("intent", "general_chat")
            confidence = float(result.get("confidence", 0.5))
            entities = result.get("entities", {})

            # 确保 raw_text 存在
            if "raw_text" not in entities:
                entities["raw_text"] = text

            # 限制置信度范围
            confidence = max(0.3, min(confidence, 0.99))

            logger.info(
                f"[NLU-LLM] 识别结果: intent={intent_name}, "
                f"confidence={confidence:.2f}, "
                f"entities={entities}"
            )

            return intent_name, confidence, entities

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning(f"[NLU-LLM] 解析 LLM 响应失败: {e}")
            return "general_chat", 0.3, {"raw_text": text}


# ============================================================
# NLU 服务（唯一对外接口）
# ============================================================
class NLUService:
    """
    自然语言理解服务

    混合策略:
      1. 规则引擎（正则）快速匹配
         - 置信度 ≥ 0.60 → 直接采用规则结果
         - 置信度 < 0.60 → 降级到 LLM
      2. LLM 兜底（OpenAI 兼容接口）
         - LLM 可用 → 使用 LLM 结果
         - LLM 不可用 → 使用规则结果（即使置信度低）

    用法:
        nlu = NLUService()
        intent = await nlu.parse("北京明天天气怎么样")
        # → Intent(name="weather_query", confidence=0.85, entities={"city":"北京", "date":"明天"})
    """

    # 规则引擎置信度阈值：低于此值时尝试 LLM 兜底
    RULE_CONFIDENCE_THRESHOLD = 0.60

    def __init__(self):
        self.rule_engine = RuleEngine()
        self.llm_classifier = LLMIntentClassifier()

    async def parse(self, text: str) -> Intent:
        """
        解析用户输入，返回结构化意图

        流程:
          1. 规则引擎正则匹配 → 得到 (intent, confidence, entities)
          2. 若 confidence ≥ 阈值，直接返回
          3. 否则调用 LLM 兜底
          4. LLM 失败或不可用时，返回规则引擎结果

        参数:
            text: 用户输入的文本

        返回:
            Intent 对象
        """
        text = text.strip()
        if not text:
            return Intent(name="general_chat", confidence=0.0, entities={})

        # ---- 步骤 1: 规则引擎 ----
        intent_name, confidence = self.rule_engine.classify(text)
        entities = self.rule_engine.extract_entities(text)
        entities["raw_text"] = text

        logger.debug(
            f"[NLU-规则] intent={intent_name}, "
            f"confidence={confidence:.2f}, "
            f"entities={entities}"
        )

        # 规则引擎置信度足够，直接返回
        if confidence >= self.RULE_CONFIDENCE_THRESHOLD:
            return Intent(
                name=intent_name,
                confidence=confidence,
                entities=entities,
            )

        # ---- 步骤 2: LLM 兜底 ----
        logger.info(
            f"[NLU] 规则置信度不足 ({confidence:.2f} < {self.RULE_CONFIDENCE_THRESHOLD}), "
            f"降级到 LLM"
        )

        llm_intent, llm_confidence, llm_entities = await self.llm_classifier.classify(text)

        # 合并实体：LLM 的实体覆盖规则引擎的同名字段，保留规则引擎特有的字段
        merged_entities = {**entities, **llm_entities}

        return Intent(
            name=llm_intent,
            confidence=llm_confidence,
            entities=merged_entities,
        )
