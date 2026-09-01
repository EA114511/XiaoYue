"""
预置技能 — 将现有 FunctionRegistry 函数包装为 Skill

每个 Skill 对应一个功能领域，包含一个或多个 OpenAI Function Calling 描述
和对应的处理函数。智能体装配后可自主调用。
"""

import logging
from typing import Any, Dict

from app.functions.weather import get_weather as fetch_real_weather
from app.functions.device import control_device as device_control_func
from app.skills import SkillDefinition, SkillFunction, skill_registry

logger = logging.getLogger("voice-assistant.skills.builtin")


# ============================================================
# 1. 天气查询 Skill
# ============================================================

async def _weather_handler(params: Dict[str, Any]) -> str:
    """天气查询处理函数"""
    city = params.get("city", "北京")
    result = await fetch_real_weather(city)
    if result.get("temperature") and result["temperature"] != "N/A":
        return (
            f"{city}当前天气：{result['weather']}，"
            f"温度{result['temperature']}，"
            f"湿度{result['humidity']}，"
            f"风力{result['wind']}。"
        )
    return f"抱歉，暂时无法获取{city}的天气信息。"


weather_skill = SkillDefinition(
    name="weather",
    display_name="天气查询",
    description="查询任意城市的实时天气信息，包括温度、湿度、风力、天气状况等",
    category="工具",
    functions=[
        SkillFunction(
            name="get_weather",
            description="查询指定城市的当前天气信息",
            handler=_weather_handler,
            parameters={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名，如「北京」「上海」「广州」等",
                    }
                },
                "required": ["city"],
            },
        ),
    ],
)


# ============================================================
# 2. 设备控制 Skill
# ============================================================

async def _device_control_handler(params: Dict[str, Any]) -> str:
    """设备控制处理函数"""
    device = params.get("device", "")
    action = params.get("action", "")
    location = params.get("location", "")
    temperature = params.get("temperature")

    extras = {}
    if temperature:
        extras["temperature"] = temperature

    result = await device_control_func(
        device=device,
        action=action,
        location=location or None,
        params=extras or None,
        batch=params.get("batch", False),
    )
    return result.get("message", f"执行{device}{action}失败")


device_skill = SkillDefinition(
    name="device_control",
    display_name="智能家居控制",
    description="控制智能家居设备，支持打开/关闭/调节温度等操作",
    category="工具",
    functions=[
        SkillFunction(
            name="control_device",
            description="控制智能家居设备，支持打开、关闭、调节温度等操作",
            handler=_device_control_handler,
            parameters={
                "type": "object",
                "properties": {
                    "device": {
                        "type": "string",
                        "description": '设备名，如「灯」「空调」「电视」「窗帘」等',
                    },
                    "action": {
                        "type": "string",
                        "description": '要执行的操作，「打开」或「关闭」',
                        "enum": ["打开", "关闭"],
                    },
                    "location": {
                        "type": "string",
                        "description": '设备所在位置，如「客厅」「卧室」「厨房」等',
                    },
                    "temperature": {
                        "type": "number",
                        "description": "调节温度（仅空调适用）",
                    },
                },
                "required": ["device", "action"],
            },
        ),
    ],
)


# ============================================================
# 3. 日程管理 Skill
# ============================================================

async def _schedule_handler(params: Dict[str, Any]) -> str:
    """日程管理处理函数"""
    event = params.get("event_name", "")
    date = params.get("date", "")
    time = params.get("time", "")

    if event and date:
        return f"已为您记录日程：{date} {time} {event}"
    if date:
        return f"正在查询{date}的日程安排..."
    return "请告诉我您想设置什么提醒或查询哪天的日程？"


schedule_skill = SkillDefinition(
    name="schedule",
    display_name="日程管理",
    description="管理日程提醒和事件安排，支持创建和查询日程",
    category="效率",
    functions=[
        SkillFunction(
            name="create_schedule",
            description="创建日程提醒或安排事件",
            handler=_schedule_handler,
            parameters={
                "type": "object",
                "properties": {
                    "event_name": {
                        "type": "string",
                        "description": '日程事件名称，如「会议」「生日」等',
                    },
                    "date": {
                        "type": "string",
                        "description": '日期，格式 YYYY-MM-DD，或「今天」「明天」等',
                    },
                    "time": {
                        "type": "string",
                        "description": '时间，格式 HH:MM，如「14:30」',
                    },
                },
                "required": ["event_name", "date"],
            },
        ),
    ],
)


# ============================================================
# 4. 音乐播放 Skill
# ============================================================

async def _music_handler(params: Dict[str, Any]) -> str:
    """音乐播放处理函数"""
    artist = params.get("artist", "")
    song = params.get("song", "")
    genre = params.get("genre", "")

    if artist and song:
        return f"正在为您播放{artist}的{song}..."
    if artist:
        return f"正在为您播放{artist}的热门歌曲..."
    if genre:
        return f"正在为您播放{genre}音乐..."
    if song:
        return f"正在为您播放{song}..."
    return "正在为您播放音乐..."


music_skill = SkillDefinition(
    name="music_play",
    display_name="音乐播放",
    description="播放音乐，支持按歌手名、歌曲名或音乐类型播放",
    category="娱乐",
    functions=[
        SkillFunction(
            name="play_music",
            description="播放音乐，支持按歌手、歌曲或风格播放",
            handler=_music_handler,
            parameters={
                "type": "object",
                "properties": {
                    "artist": {
                        "type": "string",
                        "description": '歌手名，如「周杰伦」「林俊杰」等',
                    },
                    "song": {
                        "type": "string",
                        "description": "歌曲名",
                    },
                    "genre": {
                        "type": "string",
                        "description": '音乐类型，如「流行」「古典」「摇滚」等',
                    },
                },
            },
        ),
    ],
)


# ============================================================
# 5. 联网搜索 Skill
# ============================================================

async def _web_search_handler(params: Dict[str, Any]) -> str:
    """联网搜索处理函数（基于 DuckDuckGo 的无 API Key 搜索）"""
    query = params.get("query", "")
    if not query:
        return "请告诉我您想搜索什么内容？"

    try:
        import aiohttp
        from urllib.parse import quote

        url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1&skip_disambig=1"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return f"搜索「{query}」时服务暂不可用，请稍后重试。"
                data = await resp.json()
                abstract = data.get("AbstractText", "")
                source = data.get("AbstractSource", "")
                answer = data.get("Answer", "")

                if answer:
                    return f"关于「{query}」的答案是：{answer}"
                if abstract:
                    result = abstract[:300]
                    return f"为您找到关于「{query}」的信息：{result}" + (f"（来源：{source}）" if source else "")
                # 尝试提取相关话题
                related = data.get("RelatedTopics", [])
                if related:
                    titles = []
                    for r in related[:3]:
                        if isinstance(r, dict) and "Text" in r:
                            titles.append(r["Text"][:80])
                    if titles:
                        return f"关于「{query}」的相关结果：{'；'.join(titles)}"
                return f"未找到关于「{query}」的相关信息，请尝试更精确的关键词。"
    except ImportError:
        return "搜索功能需要 aiohttp 库支持。"
    except Exception as e:
        logger.warning(f"[搜索] 查询失败: {e}")
        return f"搜索「{query}」时出现网络错误，请稍后重试。"


web_search_skill = SkillDefinition(
    name="web_search",
    display_name="联网搜索",
    description="通过互联网搜索实时信息，支持新闻、百科、问答等多种内容",
    category="工具",
    functions=[
        SkillFunction(
            name="search_web",
            description="搜索互联网信息，返回相关结果摘要。适合查询实时信息、新闻、百科知识等",
            handler=_web_search_handler,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，如「今天的新闻」「Python 教程」「周杰伦演唱会」等",
                    }
                },
                "required": ["query"],
            },
        ),
    ],
)


# ============================================================
# 6. 计算器 Skill
# ============================================================

import ast
import operator

# 安全表达式求值 - 只允许安全操作
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expr: str) -> float:
    """安全计算数学表达式（仅支持数字和基本运算符）"""
    tree = ast.parse(expr.strip(), mode="eval")
    if not isinstance(tree, ast.Expression):
        raise ValueError("不支持的表达式类型")

    def _eval_node(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不支持的常量类型: {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            op_func = _ALLOWED_OPS.get(type(node.op))
            if not op_func:
                raise ValueError(f"不支持的操作符: {type(node.op).__name__}")
            return op_func(_eval_node(node.left), _eval_node(node.right))
        elif isinstance(node, ast.UnaryOp):
            op_func = _ALLOWED_OPS.get(type(node.op))
            if not op_func:
                raise ValueError(f"不支持的操作符: {type(node.op).__name__}")
            return op_func(_eval_node(node.operand))
        raise ValueError(f"不支持的表达式节点: {type(node).__name__}")

    result = _eval_node(tree.body)
    return result


async def _calculator_handler(params: Dict[str, Any]) -> str:
    """数学计算处理函数"""
    expression = params.get("expression", "")
    if not expression:
        return "请告诉我您想计算什么表达式？例如「2 + 3 * 4」「2 的 10 次方」"

    try:
        # 中文符号替换
        expr_clean = (
            expression.replace("×", "*")
            .replace("÷", "/")
            .replace("x", "*")
            .replace("X", "*")
            .replace("＋", "+")
            .replace("－", "-")
            .replace("（", "(")
            .replace("）", ")")
            .replace("^", "**")
            .replace("的", "**")
            .replace("次方", "**")
            .replace("平方", "**2")
            .replace("立方", "**3")
            .replace("pi", str(3.141592653589793))
            .replace("π", str(3.141592653589793))
            .replace(" ", "")
        )

        result = _safe_eval(expr_clean)

        # 格式化输出
        if isinstance(result, float) and result == int(result):
            result_str = str(int(result))
        elif isinstance(result, float):
            result_str = f"{result:.4f}".rstrip("0").rstrip(".")
        else:
            result_str = str(result)

        return f"计算结果：{expression} = {result_str}"
    except Exception as e:
        logger.debug(f"[计算器] 表达式解析失败: {expression}, error={e}")
        return f"抱歉，无法计算「{expression}」，请确保输入的是合法数学表达式（如 2+3*4）。"


calculator_skill = SkillDefinition(
    name="calculator",
    display_name="计算器",
    description="执行数学计算，支持加减乘除、幂运算、括号等基本算术",
    category="工具",
    functions=[
        SkillFunction(
            name="calculate",
            description="计算数学表达式，支持加减乘除(+-*/)、幂运算(^)、括号等",
            handler=_calculator_handler,
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如「2 + 3 * 4」「2^10」「(1 + 2) * 3」",
                    }
                },
                "required": ["expression"],
            },
        ),
    ],
)


# ============================================================
# 7. 日期时间 Skill
# ============================================================

import datetime


async def _datetime_handler(params: Dict[str, Any]) -> str:
    """日期时间查询处理函数"""
    query_type = params.get("type", "now")

    now = datetime.datetime.now()
    today = datetime.date.today()

    weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_cn = weekdays_cn[today.weekday()]

    if query_type == "now" or query_type == "time":
        return f"现在是 {now.strftime('%H:%M:%S')}"
    elif query_type == "date" or query_type == "today":
        return f"今天是 {today.strftime('%Y年%m月%d日')}，{weekday_cn}"
    elif query_type == "datetime" or query_type == "full":
        return f"现在是 {today.strftime('%Y年%m月%d日')} {now.strftime('%H:%M:%S')}，{weekday_cn}"
    elif query_type == "year":
        return f"今年是 {today.year} 年"
    elif query_type == "month":
        return f"现在是 {today.year} 年 {today.month} 月"
    elif query_type == "weekday":
        return f"今天是 {weekday_cn}"
    elif query_type == "timestamp":
        return f"当前时间戳：{int(now.timestamp())}"
    else:
        return (
            f"当前时间：{today.strftime('%Y年%m月%d日')} "
            f"{now.strftime('%H:%M:%S')}，{weekday_cn}"
        )


datetime_skill = SkillDefinition(
    name="time_date",
    display_name="日期时间",
    description="查询当前日期、时间、星期、时间戳等信息",
    category="效率",
    functions=[
        SkillFunction(
            name="get_datetime",
            description="查询当前日期、时间、星期等信息，支持多种查询类型",
            handler=_datetime_handler,
            parameters={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": '查询类型：now(时间), date(日期), datetime(完整), weekday(星期), year(年份), month(月份), timestamp(时间戳)',
                        "enum": ["now", "date", "datetime", "weekday", "year", "month", "timestamp", "full"],
                    }
                },
            },
        ),
    ],
)


# ============================================================
# 8. 讲笑话 Skill
# ============================================================

_JOKES = [
    "为什么程序员总分不清万圣节和圣诞节？因为 Oct 31 == Dec 25。",
    "有一天，0 遇到了 8，0 说：「咦，你的腰带好酷啊！」8 说：「是啊，我刚学会扎腰带了。」",
    "程序员写代码的三大错觉：1. 这个 bug 很好修；2. 我马上就能写完；3. 上次能编译通过，这次肯定也能。",
    "产品经理对程序员说：「我要一个能根据用户心情自动切换主题的功能。」程序员说：「那我需要先读懂人心。」产品经理说：「这对你很难吗？」",
    "问：为什么 Java 开发者喜欢穿眼镜？答：因为他们看不到 C#。",
    "两个 C 语言程序员在聊天，一个说：「我愿意为你做任何事。」另一个说：「那你帮我写个 GUI 吧。」",
    "AI 的终极形态不是取代人类，而是帮人类写日报，然后人类帮 AI 填验证码。",
    "老板问程序员：「这个需求要多久？」程序员说：「3 天。」老板说：「太久了，给你 1 天。」第二天，系统崩溃了。",
    "什么是面向对象编程？就是把一个能解决的问题，分成无数个小问题，然后忘记它们之间的关系。",
    "Python 是最好的语言，因为它让你可以专注于解决问题，而不是解决语言本身。",
    "递归的定义：递归就是递归。",
    "软件开发的终极定律：需求永远不会冻结，就像熵永远不会减少。",
    "机器学习工程师的日常：70% 的时间在洗数据，20% 的时间在调参数，10% 的时间在跟人说「模型过拟合了」。",
    "前端开发者的三大难题：1. 居中；2. 浏览器兼容；3. 为什么我的页面在别人电脑上显示不一样。",
    "后端开发者的至理名言：只要我不重启服务器，它就永远正常运行。",
]

import random


async def _joke_handler(params: Dict[str, Any]) -> str:
    """讲笑话处理函数"""
    count = params.get("count", 1)
    category = params.get("category", "")

    if count > 3:
        count = 3  # 一次最多讲 3 个

    available = _JOKES
    if category:
        # 简单按关键词筛选
        available = [j for j in _JOKES if category in j]

    if not available:
        return f"抱歉，暂时没有关于「{category}」的笑话，讲个别的吧！\n{random.choice(_JOKES)}"

    selected = random.sample(available, min(count, len(available)))
    if len(selected) == 1:
        return selected[0]
    else:
        return "\n---\n".join(selected)


joke_skill = SkillDefinition(
    name="joke",
    display_name="讲笑话",
    description="讲一个有趣的笑话或冷笑话，支持按数量获取",
    category="娱乐",
    functions=[
        SkillFunction(
            name="tell_joke",
            description="讲一个或多个笑话，让对话更轻松有趣",
            handler=_joke_handler,
            parameters={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "想听的笑话数量（最多 3 个）",
                    },
                    "category": {
                        "type": "string",
                        "description": "笑话主题分类（可选），如「程序员」「生活」「动物」",
                    },
                },
            },
        ),
    ],
)


# ============================================================
# 注册所有预置技能
# ============================================================

def register_builtin_skills():
    """注册所有系统预置技能"""
    skills = [
        weather_skill, device_skill, schedule_skill, music_skill,
        web_search_skill, calculator_skill, datetime_skill, joke_skill,
    ]

    for skill in skills:
        if skill_registry.skill_exists(skill.name):
            logger.debug(f"[预置技能] 技能 '{skill.name}' 已存在，跳过注册")
            continue
        skill_registry.register(skill)
        logger.info(f"[预置技能] 已注册: '{skill.display_name}' ({skill.name})")

    logger.info(
        f"[预置技能] 注册完成: 共 {len(skills)} 个技能, "
        f"函数总数={sum(len(s.functions) for s in skills)}"
    )
