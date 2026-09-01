"""
技能系统 (Skill System) 单元测试

测试覆盖:
  - SkillRegistry — 注册/注销/查询/重复注册
  - 预置技能注册 — 全部 8 个技能注册与信息验证
  - 计算器 Skill — 基本运算/中文表达式/错误处理
  - 日期时间 Skill — 多种查询类型
  - 讲笑话 Skill — 数量/主题过滤
  - MCP 持久化 — 配置保存/加载/API Key 保护
  - MCPRegistry — 注册/移除/工具发现
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from app.skills import SkillDefinition, SkillFunction, SkillRegistry, skill_registry
from app.skills.mcp_bridge import MCPRegistry, MCPServerConfig, MCP_SERVERS_FILE


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def fresh_registry():
    """创建一个干净的空注册表"""
    reg = SkillRegistry()
    return reg


@pytest.fixture
def sample_skill():
    """一个简单的测试技能"""
    async def _hello_handler(params):
        name = params.get("name", "World")
        return f"Hello, {name}!"

    return SkillDefinition(
        name="test_greeting",
        display_name="问候测试",
        description="一个用于测试的问候技能",
        category="测试",
        functions=[
            SkillFunction(
                name="say_hello",
                description="打招呼",
                handler=_hello_handler,
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "姓名",
                        }
                    },
                },
            ),
        ],
    )


@pytest.fixture(autouse=True)
def backup_and_restore_mcp_file():
    """
    自动备份并恢复 MCP 持久化文件
    确保测试不会互相污染
    """
    original_exists = os.path.exists(MCP_SERVERS_FILE)
    original_content = None
    if original_exists:
        with open(MCP_SERVERS_FILE, "r", encoding="utf-8") as f:
            original_content = f.read()
    yield
    # 恢复原状
    if original_content is not None:
        with open(MCP_SERVERS_FILE, "w", encoding="utf-8") as f:
            f.write(original_content)
    elif os.path.exists(MCP_SERVERS_FILE):
        os.remove(MCP_SERVERS_FILE)


# ============================================================
# SkillRegistry 基础操作测试
# ============================================================

class TestSkillRegistry:
    """SkillRegistry 核心功能测试"""

    async def test_register_and_get_skill(self, fresh_registry, sample_skill):
        """注册技能并通过名称获取"""
        result = fresh_registry.register(sample_skill)
        assert result is True
        retrieved = fresh_registry.get_skill("test_greeting")
        assert retrieved is not None
        assert retrieved.name == "test_greeting"
        assert retrieved.display_name == "问候测试"
        assert retrieved.category == "测试"

    async def test_register_duplicate_overwrites(self, fresh_registry, sample_skill):
        """重复注册同一技能应覆盖并返回 True"""
        fresh_registry.register(sample_skill)
        result = fresh_registry.register(sample_skill)
        assert result is True  # 覆盖也返回 True

    async def test_skill_exists(self, fresh_registry, sample_skill):
        """检查技能是否存在"""
        assert fresh_registry.skill_exists("test_greeting") is False
        fresh_registry.register(sample_skill)
        assert fresh_registry.skill_exists("test_greeting") is True

    async def test_unregister_existing(self, fresh_registry, sample_skill):
        """注销已存在的技能"""
        fresh_registry.register(sample_skill)
        result = fresh_registry.unregister("test_greeting")
        assert result is True
        assert fresh_registry.skill_exists("test_greeting") is False

    async def test_unregister_nonexistent(self, fresh_registry):
        """注销不存在的技能应返回 False"""
        result = fresh_registry.unregister("nonexistent")
        assert result is False

    async def test_get_all_skills_returns_copy(self, fresh_registry, sample_skill):
        """get_all_skills 应返回副本，修改不影响原注册表"""
        fresh_registry.register(sample_skill)
        all_skills = fresh_registry.get_all_skills()
        all_skills["injected"] = sample_skill
        assert fresh_registry.skill_exists("injected") is False

    async def test_get_skills_by_category(self, fresh_registry, sample_skill):
        """按分类获取技能"""
        fresh_registry.register(sample_skill)
        # 创建一个同类技能
        another = SkillDefinition(
            name="test_echo",
            display_name="回显",
            description="回显测试",
            category="测试",
            functions=[],
        )
        fresh_registry.register(another)
        # 创建一个其他分类的技能
        other = SkillDefinition(
            name="other_tool",
            display_name="其他",
            description="其他分类",
            category="工具",
            functions=[],
        )
        fresh_registry.register(other)

        test_skills = fresh_registry.get_skills_by_category("测试")
        assert len(test_skills) == 2
        assert "test_greeting" in test_skills
        assert "test_echo" in test_skills

    async def test_get_enabled_skills(self, fresh_registry, sample_skill):
        """只返回启用的技能"""
        fresh_registry.register(sample_skill)
        disabled = SkillDefinition(
            name="disabled_skill",
            display_name="已禁用",
            description="禁用测试",
            category="测试",
            functions=[],
            enabled=False,
        )
        fresh_registry.register(disabled)
        enabled = fresh_registry.get_enabled_skills()
        assert "test_greeting" in enabled
        assert "disabled_skill" not in enabled

    async def test_call_skill_function(self, fresh_registry, sample_skill):
        """通过注册表调用技能函数"""
        fresh_registry.register(sample_skill)
        result = await fresh_registry.call_skill_function(
            "test_greeting", "say_hello", {"name": "测试"}
        )
        assert result == "Hello, 测试!"

    async def test_call_skill_function_default_params(self, fresh_registry, sample_skill):
        """调用函数时不传可选参数"""
        fresh_registry.register(sample_skill)
        result = await fresh_registry.call_skill_function(
            "test_greeting", "say_hello", {}
        )
        assert result == "Hello, World!"

    async def test_call_nonexistent_skill(self, fresh_registry):
        """调用不存在的技能应抛出 ValueError"""
        with pytest.raises(ValueError, match="不存在"):
            await fresh_registry.call_skill_function("ghost", "fn", {})

    async def test_call_nonexistent_function(self, fresh_registry, sample_skill):
        """调用技能中不存在的函数应抛出 ValueError"""
        fresh_registry.register(sample_skill)
        with pytest.raises(ValueError, match="不存在函数"):
            await fresh_registry.call_skill_function("test_greeting", "ghost_fn", {})


# ============================================================
# 预置技能注册测试
# ============================================================

class TestBuiltinSkills:
    """系统预置技能注册与完整性测试"""

    async def test_all_builtin_skills_registered(self):
        """确认所有 8 个预置技能都已注册到全局注册表"""
        from app.skills.builtin import register_builtin_skills
        register_builtin_skills()
        all_skills = skill_registry.get_all_skills()
        expected_names = {
            "weather", "device_control", "schedule", "music_play",
            "web_search", "calculator", "time_date", "joke",
        }
        actual_names = set(all_skills.keys())
        assert expected_names.issubset(actual_names), (
            f"缺少技能: {expected_names - actual_names}"
        )

    async def test_each_skill_has_required_fields(self):
        """每个技能都有必要的字段值"""
        from app.skills.builtin import register_builtin_skills
        register_builtin_skills()
        for name, skill in skill_registry.get_all_skills().items():
            assert skill.display_name, f"技能 {name} 缺少 display_name"
            assert skill.description, f"技能 {name} 缺少 description"
            assert skill.category, f"技能 {name} 缺少 category"
            assert len(skill.functions) > 0, f"技能 {name} 没有函数"

    async def test_calculator_skill_metadata(self):
        """计算器技能的元数据正确"""
        from app.skills.builtin import register_builtin_skills
        register_builtin_skills()
        skill = skill_registry.get_skill("calculator")
        assert skill is not None
        assert skill.name == "calculator"
        assert skill.display_name == "计算器"
        assert skill.category == "工具"
        assert skill.has_function("calculate")

    async def test_time_date_skill_metadata(self):
        """日期时间技能的元数据正确"""
        from app.skills.builtin import register_builtin_skills
        register_builtin_skills()
        skill = skill_registry.get_skill("time_date")
        assert skill is not None
        assert skill.name == "time_date"
        assert skill.display_name == "日期时间"
        assert skill.category == "效率"
        assert skill.has_function("get_datetime")

    async def test_joke_skill_metadata(self):
        """讲笑话技能的元数据正确"""
        from app.skills.builtin import register_builtin_skills
        register_builtin_skills()
        skill = skill_registry.get_skill("joke")
        assert skill is not None
        assert skill.name == "joke"
        assert skill.display_name == "讲笑话"
        assert skill.category == "娱乐"
        assert skill.has_function("tell_joke")

    async def test_web_search_skill_metadata(self):
        """联网搜索技能的元数据正确"""
        from app.skills.builtin import register_builtin_skills
        register_builtin_skills()
        skill = skill_registry.get_skill("web_search")
        assert skill is not None
        assert skill.name == "web_search"
        assert skill.display_name == "联网搜索"
        assert skill.category == "工具"
        assert skill.has_function("search_web")


# ============================================================
# 计算器 Skill 测试
# ============================================================

class TestCalculatorSkill:
    """计算器技能功能测试"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.skills.builtin import register_builtin_skills
        register_builtin_skills()

    async def test_basic_arithmetic(self):
        """基本四则运算"""
        result = await skill_registry.call_skill_function(
            "calculator", "calculate", {"expression": "2 + 3 * 4"}
        )
        assert "14" in result

    async def test_power_operation(self):
        """幂运算"""
        result = await skill_registry.call_skill_function(
            "calculator", "calculate", {"expression": "2^10"}
        )
        assert "1024" in result

    async def test_parentheses(self):
        """括号运算"""
        result = await skill_registry.call_skill_function(
            "calculator", "calculate", {"expression": "(1 + 2) * 3"}
        )
        assert "9" in result

    async def test_division(self):
        """除法运算"""
        result = await skill_registry.call_skill_function(
            "calculator", "calculate", {"expression": "10 / 3"}
        )
        assert "3.333" in result

    async def test_chinese_expression_x(self):
        """中文符号 '×' 替换"""
        result = await skill_registry.call_skill_function(
            "calculator", "calculate", {"expression": "3×4"}
        )
        assert "12" in result

    async def test_chinese_expression_divide(self):
        """中文符号 '÷' 替换"""
        result = await skill_registry.call_skill_function(
            "calculator", "calculate", {"expression": "8÷2"}
        )
        assert "4" in result

    async def test_pi_constant(self):
        """圆周率 π"""
        result = await skill_registry.call_skill_function(
            "calculator", "calculate", {"expression": "π"}
        )
        assert "3.1416" in result

    async def test_empty_expression(self):
        """空表达式提示"""
        result = await skill_registry.call_skill_function(
            "calculator", "calculate", {"expression": ""}
        )
        assert "请告诉我" in result

    async def test_invalid_expression(self):
        """非法表达式优雅处理"""
        result = await skill_registry.call_skill_function(
            "calculator", "calculate", {"expression": "hello world"}
        )
        assert "抱歉" in result or "无法计算" in result


# ============================================================
# 日期时间 Skill 测试
# ============================================================

class TestDateTimeSkill:
    """日期时间技能功能测试"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.skills.builtin import register_builtin_skills
        register_builtin_skills()

    async def test_get_time(self):
        """查询当前时间"""
        result = await skill_registry.call_skill_function(
            "time_date", "get_datetime", {"type": "time"}
        )
        assert "现在是" in result

    async def test_get_date(self):
        """查询当前日期"""
        result = await skill_registry.call_skill_function(
            "time_date", "get_datetime", {"type": "date"}
        )
        assert "今天是" in result
        assert "星期" in result

    async def test_get_datetime_full(self):
        """查询完整日期时间"""
        result = await skill_registry.call_skill_function(
            "time_date", "get_datetime", {"type": "full"}
        )
        assert "现在是" in result
        assert ":" in result

    async def test_get_weekday(self):
        """查询星期"""
        result = await skill_registry.call_skill_function(
            "time_date", "get_datetime", {"type": "weekday"}
        )
        assert "星期" in result

    async def test_get_year(self):
        """查询年份"""
        result = await skill_registry.call_skill_function(
            "time_date", "get_datetime", {"type": "year"}
        )
        assert "年" in result

    async def test_get_timestamp(self):
        """查询时间戳"""
        result = await skill_registry.call_skill_function(
            "time_date", "get_datetime", {"type": "timestamp"}
        )
        assert "时间戳" in result
        # 验证是合法的 Unix 时间戳
        ts_str = result.split("：")[-1]
        assert ts_str.isdigit()

    async def test_default_type_is_now(self):
        """不传 type 时默认返回完整时间"""
        result = await skill_registry.call_skill_function(
            "time_date", "get_datetime", {}
        )
        assert ":" in result or "年" in result


# ============================================================
# 讲笑话 Skill 测试
# ============================================================

class TestJokeSkill:
    """讲笑话技能功能测试"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.skills.builtin import register_builtin_skills
        register_builtin_skills()

    async def test_tell_one_joke(self):
        """讲 1 个笑话返回单条文本"""
        result = await skill_registry.call_skill_function(
            "joke", "tell_joke", {"count": 1}
        )
        assert isinstance(result, str)
        assert len(result) > 0
        assert "---" not in result  # 单个笑话不用分隔符

    async def test_tell_multiple_jokes(self):
        """讲多个笑话用分隔符"""
        result = await skill_registry.call_skill_function(
            "joke", "tell_joke", {"count": 2}
        )
        assert "---" in result

    async def test_count_capped_at_three(self):
        """最多讲 3 个笑话"""
        result = await skill_registry.call_skill_function(
            "joke", "tell_joke", {"count": 99}
        )
        assert result.count("---") <= 2  # 3 个笑话最多 2 个分隔符

    async def test_default_count_is_one(self):
        """不传 count 时默认讲 1 个"""
        result = await skill_registry.call_skill_function(
            "joke", "tell_joke", {}
        )
        assert isinstance(result, str)
        assert "---" not in result

    async def test_category_filter(self):
        """按关键词过滤笑话"""
        result = await skill_registry.call_skill_function(
            "joke", "tell_joke", {"count": 1, "category": "程序员"}
        )
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_category_no_match_fallback(self):
        """分类无匹配时返回带 fallback 的提示"""
        result = await skill_registry.call_skill_function(
            "joke", "tell_joke", {"count": 1, "category": "天文物理"}
        )
        assert isinstance(result, str)
        assert len(result) > 0
        # 应包含"抱歉"提示并附上随机笑话
        assert "抱歉" in result


# ============================================================
# MCP 持久化测试
# ============================================================

class TestMCPPersistence:
    """MCP 服务器配置持久化功能测试"""

    def teardown_method(self):
        """每个测试后清理 MCP 注册表"""
        from app.skills.mcp_bridge import mcp_registry
        for server in mcp_registry.list_servers():
            mcp_registry.remove_server(server.name)

    async def test_save_creates_file(self):
        """注册服务器后持久化文件应被创建"""
        from app.skills.mcp_bridge import mcp_registry
        config = MCPServerConfig(
            name="test_save",
            display_name="测试保存",
            url="http://localhost:1111",
        )
        mcp_registry.register_server(config)
        assert os.path.exists(MCP_SERVERS_FILE)

    async def test_save_and_load(self):
        """保存后重新加载应恢复服务器配置"""
        from app.skills.mcp_bridge import mcp_registry, MCPRegistry

        # 保存
        config = MCPServerConfig(
            name="persist_test",
            display_name="持久化测试",
            url="http://localhost:2222",
        )
        mcp_registry.register_server(config)

        # 创建新实例重新加载
        new_registry = MCPRegistry()
        new_registry.load_servers()
        servers = new_registry.list_servers()
        assert len(servers) == 1
        assert servers[0].name == "persist_test"
        assert servers[0].url == "http://localhost:2222"

    async def test_api_key_not_persisted(self):
        """API Key 不应出现在持久化文件中"""
        from app.skills.mcp_bridge import mcp_registry

        config = MCPServerConfig(
            name="secret_test",
            display_name="密钥测试",
            url="http://localhost:3333",
            api_key="sk-super-secret-key-12345",
        )
        mcp_registry.register_server(config)

        with open(MCP_SERVERS_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        assert "sk-super-secret-key-12345" not in content
        assert "super-secret" not in content

    async def test_remove_cleanup(self):
        """移除服务器后持久化文件应同步更新"""
        from app.skills.mcp_bridge import mcp_registry

        config = MCPServerConfig(name="temp", url="http://temp.local")
        mcp_registry.register_server(config)
        mcp_registry.remove_server("temp")

        with open(MCP_SERVERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        names = [item["name"] for item in data]
        assert "temp" not in names

    async def test_load_empty_file_graceful(self):
        """文件为空或不存在时不应报错"""
        from app.skills.mcp_bridge import MCPRegistry

        # 确保文件不存在
        if os.path.exists(MCP_SERVERS_FILE):
            os.remove(MCP_SERVERS_FILE)

        reg = MCPRegistry()
        # 不应抛出异常
        reg.load_servers()
        assert len(reg.list_servers()) == 0

    async def test_load_corrupted_file_graceful(self):
        """文件损坏时不应抛异常，应静默跳过"""
        from app.skills.mcp_bridge import MCPRegistry

        # 写入损坏数据
        with open(MCP_SERVERS_FILE, "w", encoding="utf-8") as f:
            f.write("{invalid json")

        reg = MCPRegistry()
        # 不应抛出异常
        reg.load_servers()

    async def test_tools_cached_and_reloaded(self):
        """缓存的工具列表随配置一起持久化，加载后自动注册为 Skill"""
        from app.skills.mcp_bridge import mcp_registry, MCPRegistry
        from app.skills import skill_registry

        # 先清理可能残留的技能
        skill_registry.unregister("mcp_cached_test")

        # 注册带工具缓存的服务器
        config = MCPServerConfig(
            name="cached_test",
            display_name="缓存测试",
            url="http://localhost:4444",
            tools=[
                {"name": "cached_tool", "description": "缓存的工具", "inputSchema": {"type": "object"}},
            ],
        )
        mcp_registry.register_server(config)
        # register_server 只保存配置，不会自动注册 skill

        # 创建新注册表重新加载，应自动注册 skill
        new_reg = MCPRegistry()
        new_reg.load_servers()
        skill = skill_registry.get_skill("mcp_cached_test")
        assert skill is not None, "加载后应自动注册 mcp_cached_test 技能"
        assert len(skill.functions) == 1
        assert skill.functions[0].name == "cached_tool"

        # 清理
        new_reg.remove_server("cached_test")


# ============================================================
# MCPRegistry 基础功能测试
# ============================================================

class TestMCPRegistry:
    """MCPRegistry 核心功能测试"""

    def setup_method(self):
        self.reg = MCPRegistry()

    def teardown_method(self):
        for server in self.reg.list_servers():
            self.reg.remove_server(server.name)

    async def test_register_and_get_server(self):
        """注册并获取 MCP 服务器"""
        config = MCPServerConfig(name="my_server", url="http://localhost:8080")
        self.reg.register_server(config)
        retrieved = self.reg.get_server("my_server")
        assert retrieved is not None
        assert retrieved.name == "my_server"
        assert retrieved.url == "http://localhost:8080"

    async def test_register_server_sets_display_name_default(self):
        """未设置 display_name 时默认使用 name"""
        config = MCPServerConfig(name="my_server", url="http://localhost:8080")
        assert config.display_name == "my_server"

    async def test_register_server_sets_auth_header(self):
        """设置 api_key 时自动添加 Authorization header"""
        config = MCPServerConfig(name="secure", api_key="sk-test-key")
        assert config._headers.get("Authorization") == "Bearer sk-test-key"

    async def test_remove_server(self):
        """移除服务器"""
        config = MCPServerConfig(name="temp_server", url="http://temp")
        self.reg.register_server(config)
        self.reg.remove_server("temp_server")
        assert self.reg.get_server("temp_server") is None

    async def test_list_servers(self):
        """列出所有服务器"""
        self.reg.register_server(MCPServerConfig(name="s1"))
        self.reg.register_server(MCPServerConfig(name="s2"))
        servers = self.reg.list_servers()
        assert len(servers) == 2
        names = {s.name for s in servers}
        assert names == {"s1", "s2"}

    async def test_get_nonexistent_server(self):
        """获取不存在的服务器返回 None"""
        assert self.reg.get_server("ghost") is None

    @patch("aiohttp.ClientSession")
    async def test_discover_tools_network_error(self, mock_session):
        """网络错误时 discover_tools 应抛出异常"""
        mock_session.side_effect = Exception("Network error")
        config = MCPServerConfig(name="broken", url="http://broken")
        self.reg.register_server(config)
        with pytest.raises(Exception):
            await self.reg.discover_tools("broken")
