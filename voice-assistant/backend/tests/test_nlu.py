"""
意图识别模块 (NLU) 单元测试

测试覆盖:
  - RuleEngine — 各意图类别的正则匹配和置信度计算
  - RuleEngine — 实体抽取（城市、日期、时间、设备、动作等）
  - NLUService.parse() — 混合策略（规则 ≥ 0.60 直接返回）
  - NLUService.parse() — LLM 兜底分支
  - LLMIntentClassifier — API 调用与响应解析
  - Intent 数据结构 — 创建/序列化
  - 边缘情况 — 空文本、特殊字符、多意图文本
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.nlu import (
    NLUService,
    RuleEngine,
    LLMIntentClassifier,
    Intent,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def rule_engine():
    """创建规则引擎实例"""
    return RuleEngine()


@pytest.fixture
def nlu_service():
    """创建 NLU 服务实例"""
    return NLUService()


@pytest.fixture
def llm_classifier():
    """创建 LLM 分类器实例"""
    return LLMIntentClassifier()


# ============================================================
# Intent 数据结构测试
# ============================================================

class TestIntent:
    """意图数据结构测试"""

    def test_create_intent(self):
        """测试创建基本意图"""
        intent = Intent(name="weather_query", confidence=0.85)
        assert intent.name == "weather_query"
        assert intent.confidence == 0.85
        assert intent.entities == {}

    def test_create_with_entities(self):
        """测试带实体创建意图"""
        intent = Intent(
            name="weather_query",
            confidence=0.92,
            entities={"city": "北京", "date": "明天"},
        )
        assert intent.entities["city"] == "北京"
        assert intent.entities["date"] == "明天"

    def test_to_dict(self):
        """测试序列化为字典"""
        intent = Intent(
            name="device_control",
            confidence=0.88,
            entities={"device": "灯", "action": "打开"},
        )
        d = intent.to_dict()
        assert d["intent"] == "device_control"
        assert d["confidence"] == 0.88
        assert d["entities"]["device"] == "灯"

    def test_empty_intent(self):
        """测试空意图"""
        intent = Intent(name="general_chat", confidence=0.0)
        assert intent.confidence == 0.0
        assert intent.entities == {}


# ============================================================
# 规则引擎 — 意图分类测试
# ============================================================

class TestRuleEngineClassification:
    """规则引擎意图分类测试"""

    def test_classify_weather_query(self, rule_engine):
        """测试天气查询意图识别"""
        intent_name, confidence = rule_engine.classify("北京明天天气怎么样")
        assert intent_name == "weather_query"
        assert confidence >= 0.60  # 置信度应超过阈值

    def test_classify_weather_simple(self, rule_engine):
        """测试简单天气查询"""
        intent_name, confidence = rule_engine.classify("今天多少度")
        assert intent_name == "weather_query"
        assert confidence >= 0.40

    def test_classify_weather_rain(self, rule_engine):
        """测试下雨查询"""
        intent_name, confidence = rule_engine.classify("上海会下雨吗")
        assert intent_name == "weather_query"

    def test_classify_device_control_on(self, rule_engine):
        """测试设备控制（打开）"""
        intent_name, confidence = rule_engine.classify("打开客厅的灯")
        assert intent_name == "device_control"
        assert confidence >= 0.60

    def test_classify_device_control_off(self, rule_engine):
        """测试设备控制（关闭）"""
        intent_name, confidence = rule_engine.classify("关闭电视")
        assert intent_name == "device_control"
        assert confidence >= 0.60

    def test_classify_device_control_ac(self, rule_engine):
        """测试空调控制"""
        intent_name, confidence = rule_engine.classify("把空调调到26度")
        assert intent_name == "device_control"

    def test_classify_schedule_reminder(self, rule_engine):
        """测试日程管理（提醒）"""
        intent_name, confidence = rule_engine.classify("提醒我明天早上8点开会")
        assert intent_name == "schedule"
        assert confidence >= 0.50

    def test_classify_schedule_query(self, rule_engine):
        """测试日程查询"""
        intent_name, confidence = rule_engine.classify("今天有什么安排")
        assert intent_name == "schedule"

    def test_classify_music_play(self, rule_engine):
        """测试音乐播放"""
        intent_name, confidence = rule_engine.classify("播放周杰伦的歌")
        assert intent_name == "music_play"
        assert confidence >= 0.50

    def test_classify_music_play_simple(self, rule_engine):
        """测试简单音乐播放"""
        intent_name, confidence = rule_engine.classify("来一首流行音乐")
        assert intent_name == "music_play"

    def test_classify_general_chat_greeting(self, rule_engine):
        """测试问候语"""
        intent_name, confidence = rule_engine.classify("你好")
        assert intent_name == "general_chat"

    def test_classify_general_chat_whoami(self, rule_engine):
        """测试身份询问"""
        intent_name, confidence = rule_engine.classify("你是谁")
        assert intent_name == "general_chat"

    def test_classify_general_chat_thanks(self, rule_engine):
        """测试感谢"""
        intent_name, confidence = rule_engine.classify("谢谢")
        assert intent_name == "general_chat"

    def test_classify_empty_text(self, rule_engine):
        """测试空文本（应返回 general_chat）"""
        intent_name, confidence = rule_engine.classify("")
        assert intent_name == "general_chat"
        assert confidence == 0.0

    def test_classify_ambiguous_text(self, rule_engine):
        """测试模糊文本"""
        intent_name, confidence = rule_engine.classify("这个东西怎么用")
        # 没有任何关键词命中，应返回 general_chat
        assert intent_name == "general_chat"
        assert confidence < 0.60


# ============================================================
# 规则引擎 — 实体抽取测试
# ============================================================

class TestRuleEngineEntityExtraction:
    """实体抽取测试"""

    def test_extract_city(self, rule_engine):
        """测试城市名抽取"""
        entities = rule_engine.extract_entities("北京明天天气怎么样")
        assert entities.get("city") == "北京"

    def test_extract_city_multiple(self, rule_engine):
        """测试多城市名抽取（取第一个）"""
        entities = rule_engine.extract_entities("北京和上海哪个更冷")
        assert entities.get("city") in ("北京", "上海")

    def test_extract_date_today(self, rule_engine):
        """测试日期抽取（今天）"""
        entities = rule_engine.extract_entities("今天天气怎么样")
        assert entities.get("date") is not None
        # 相对日期应转为绝对日期 YYYY-MM-DD 格式
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}", entities.get("date", ""))

    def test_extract_date_tomorrow(self, rule_engine):
        """测试日期抽取（明天）"""
        entities = rule_engine.extract_entities("明天会下雨吗")
        assert entities.get("date") is not None

    def test_extract_time(self, rule_engine):
        """测试时间抽取"""
        entities = rule_engine.extract_entities("提醒我明天早上8点开会")
        time_val = entities.get("time", "")
        assert "08:00" in time_val or "早上" in time_val or "8" in time_val

    def test_extract_device_light(self, rule_engine):
        """测试设备名抽取（灯）"""
        entities = rule_engine.extract_entities("请打开灯")
        assert entities.get("device") == "灯"

    def test_extract_device_ac(self, rule_engine):
        """测试设备名抽取（空调）"""
        entities = rule_engine.extract_entities("关闭空调")
        assert entities.get("device") == "空调"

    def test_extract_device_tv(self, rule_engine):
        """测试设备名抽取（电视）"""
        entities = rule_engine.extract_entities("打开电视")
        assert entities.get("device") == "电视"

    def test_extract_action_open(self, rule_engine):
        """测试动作抽取（打开）"""
        entities = rule_engine.extract_entities("打开灯")
        assert entities.get("action") == "打开"

    def test_extract_action_close(self, rule_engine):
        """测试动作抽取（关闭）"""
        entities = rule_engine.extract_entities("关闭空调")
        assert entities.get("action") == "关闭"

    def test_extract_artist(self, rule_engine):
        """测试歌手名抽取"""
        entities = rule_engine.extract_entities("播放周杰伦的歌")
        assert entities.get("artist") == "周杰伦"

    def test_extract_genre(self, rule_engine):
        """测试音乐类型抽取"""
        entities = rule_engine.extract_entities("播放流行音乐")
        assert entities.get("genre") == "流行"

    def test_extract_no_entities(self, rule_engine):
        """测试无实体文本"""
        entities = rule_engine.extract_entities("你好")
        assert entities == {}

    def test_extract_special_characters(self, rule_engine):
        """测试特殊字符处理"""
        entities = rule_engine.extract_entities("北京！天气！")
        assert entities.get("city") == "北京"

    def test_date_normalization(self, rule_engine):
        """测试日期标准化"""
        normalized = rule_engine._normalize_date("明天")
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}", normalized)

    def test_time_normalization(self, rule_engine):
        """测试时间标准化"""
        normalized = rule_engine._normalize_time("15:30")
        assert normalized == "15:30"


# ============================================================
# NLUService 混合策略测试
# ============================================================

class TestNLUServiceParse:
    """NLU 服务 parse() 方法测试"""

    @pytest.mark.asyncio
    async def test_parse_weather_high_confidence(self, nlu_service):
        """测试高置信度天气查询（走规则引擎，无需 LLM）"""
        intent = await nlu_service.parse("北京明天天气怎么样")
        assert intent.name == "weather_query"
        assert intent.confidence >= 0.60
        assert intent.entities.get("city") == "北京"

    @pytest.mark.asyncio
    async def test_parse_device_control_high_confidence(self, nlu_service):
        """测试高置信度设备控制"""
        intent = await nlu_service.parse("打开客厅的灯")
        assert intent.name == "device_control"
        assert intent.confidence >= 0.60

    @pytest.mark.asyncio
    async def test_parse_empty_text(self, nlu_service):
        """测试空文本"""
        intent = await nlu_service.parse("")
        assert intent.name == "general_chat"
        assert intent.confidence == 0.0

    @pytest.mark.asyncio
    async def test_parse_whitespace_text(self, nlu_service):
        """测试空白文本"""
        intent = await nlu_service.parse("   ")
        assert intent.name == "general_chat"
        assert intent.confidence == 0.0

    @pytest.mark.asyncio
    async def test_parse_low_confidence_without_llm(self, nlu_service):
        """
        测试低置信度文本但 LLM 不可用
        应回退使用规则引擎结果
        """
        # 覆盖 settings 使 LLM 不可用
        with patch("app.core.nlu.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            intent = await nlu_service.parse("这个东西怎么用")
            # 规则引擎返回 general_chat，置信度低
            assert intent.name == "general_chat"
            assert intent.confidence < 0.60

    @pytest.mark.asyncio
    async def test_parse_low_confidence_with_llm(self, nlu_service):
        """
        测试低置信度文本且 LLM 可用
        应降级到 LLM 兜底
        """
        with patch("app.core.nlu.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-test-key"

            # Mock LLM 分类器返回结果
            nlu_service.llm_classifier.available = True
            nlu_service.llm_classifier.classify = AsyncMock(
                return_value=("weather_query", 0.85, {
                    "city": "北京", "date": "", "raw_text": "北京天气",
                })
            )

            intent = await nlu_service.parse("北京天气")
            assert intent.name == "weather_query"
            assert intent.confidence == 0.85
            # 验证 LLM 分类器被调用
            nlu_service.llm_classifier.classify.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_raw_text_in_entities(self, nlu_service):
        """测试 parse 结果中包含原始文本"""
        intent = await nlu_service.parse("北京明天天气怎么样")
        assert intent.entities.get("raw_text") == "北京明天天气怎么样"

    @pytest.mark.asyncio
    async def test_parse_general_chat_greeting(self, nlu_service):
        """测试问候语"""
        intent = await nlu_service.parse("你好")
        assert intent.name == "general_chat"

    @pytest.mark.asyncio
    async def test_parse_schedule(self, nlu_service):
        """测试日程管理"""
        intent = await nlu_service.parse("提醒我明天早上8点开会")
        assert intent.name == "schedule"

    @pytest.mark.asyncio
    async def test_parse_music_play(self, nlu_service):
        """测试音乐播放"""
        intent = await nlu_service.parse("播放周杰伦的歌")
        assert intent.name == "music_play"


# ============================================================
# LLM 分类器测试
# ============================================================

class TestLLMIntentClassifier:
    """LLM 意图分类器测试"""

    @pytest.mark.asyncio
    async def test_classifier_available_with_key(self, llm_classifier):
        """测试 API Key 配置检查（已配置）"""
        with patch("app.core.nlu.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-real-key-12345"
            assert llm_classifier.available is True

    @pytest.mark.asyncio
    async def test_classifier_not_available_without_key(self, llm_classifier):
        """测试 API Key 配置检查（未配置）"""
        with patch("app.core.nlu.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            assert llm_classifier.available is False

    @pytest.mark.asyncio
    async def test_classifier_not_available_default_key(self, llm_classifier):
        """测试默认占位 Key 被识别为未配置"""
        with patch("app.core.nlu.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-your-openai-api-key-here"
            assert llm_classifier.available is False

    @pytest.mark.asyncio
    async def test_classify_success(self, llm_classifier):
        """测试 LLM 分类成功路径"""
        with patch("app.core.nlu.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-test-key"

            # Mock httpx 异步请求
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "intent": "weather_query",
                                "confidence": 0.95,
                                "entities": {
                                    "city": "北京",
                                    "date": "明天",
                                    "time": "",
                                    "raw_text": "北京明天天气怎么样",
                                },
                            }),
                        }
                    }
                ]
            }

            with patch("httpx.AsyncClient") as MockClient:
                mock_client = MagicMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.post.return_value = mock_response
                MockClient.return_value = mock_client

                intent_name, confidence, entities = await llm_classifier.classify(
                    "北京明天天气怎么样"
                )

                assert intent_name == "weather_query"
                assert confidence == 0.95
                assert entities["city"] == "北京"
                assert entities["date"] == "明天"

    @pytest.mark.asyncio
    async def test_classify_timeout(self, llm_classifier):
        """测试 LLM 请求超时"""
        from httpx import TimeoutException

        with patch("app.core.nlu.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-test-key"

            with patch("httpx.AsyncClient") as MockClient:
                mock_client = MagicMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.post.side_effect = TimeoutException("Timeout")
                MockClient.return_value = mock_client

                intent_name, confidence, entities = await llm_classifier.classify("测试")
                assert intent_name == "general_chat"
                assert confidence == 0.3
                assert entities["raw_text"] == "测试"

    @pytest.mark.asyncio
    async def test_classify_http_error(self, llm_classifier):
        """测试 LLM HTTP 错误"""
        from httpx import HTTPStatusError, Request

        with patch("app.core.nlu.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-test-key"

            with patch("httpx.AsyncClient") as MockClient:
                mock_client = MagicMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.post.side_effect = HTTPStatusError(
                    "401 Unauthorized", request=MagicMock(), response=MagicMock(),
                )
                MockClient.return_value = mock_client

                intent_name, confidence, entities = await llm_classifier.classify("测试")
                assert intent_name == "general_chat"

    @pytest.mark.asyncio
    async def test_classify_invalid_json_response(self, llm_classifier):
        """测试 LLM 返回无效 JSON"""
        with patch("app.core.nlu.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-test-key"

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": "这不是JSON格式的响应",
                        }
                    }
                ]
            }

            with patch("httpx.AsyncClient") as MockClient:
                mock_client = MagicMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.post.return_value = mock_response
                MockClient.return_value = mock_client

                intent_name, confidence, entities = await llm_classifier.classify("测试")
                assert intent_name == "general_chat"


# ============================================================
# 多意图与复杂场景测试
# ============================================================

class TestComplexScenarios:
    """复杂场景测试"""

    def test_multiple_intents_weather_dominant(self, rule_engine):
        """测试多意图文本中天气占主导"""
        intent_name, confidence = rule_engine.classify(
            "你好，请问明天北京的天气怎么样？谢谢"
        )
        assert intent_name == "weather_query"
        # 虽然包含问候和感谢，但天气关键词更多
        assert confidence >= 0.40

    def test_multiple_intents_device_dominant(self, rule_engine):
        """测试多意图文本中设备控制占主导"""
        intent_name, confidence = rule_engine.classify(
            "帮我打开客厅的灯和空调，谢谢"
        )
        assert intent_name == "device_control"

    def test_confidence_upper_bound(self, rule_engine):
        """测试置信度上限不超过 0.98"""
        text = "天气气温温度多少度下雨下雪刮风台风雾霾晴天阴天多云暴雨冷不冷热不热"
        intent_name, confidence = rule_engine.classify(text)
        assert intent_name == "weather_query"
        assert confidence <= 0.98

    def test_entities_in_weather_text(self, rule_engine):
        """测试天气文本的实体完整性"""
        entities = rule_engine.extract_entities("深圳后天天气怎么样")
        assert entities.get("city") == "深圳"
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}", entities.get("date", ""))
