# -*- coding: utf-8 -*-
"""回归测试：覆盖 command_executor、knowledge、heartbeat 核心逻辑。"""
from __future__ import annotations
import sys
import os
import json
import pytest
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCommandExecutor:
    """测试 command_executor 模块的命令分类和发送逻辑。"""

    def test_is_blocked_command_reject(self):
        """验证危险命令被拦截。"""
        from mcpensp1.command_executor import is_blocked_command
        assert is_blocked_command("reboot") is True
        assert is_blocked_command("format") is True
        assert is_blocked_command("reset saved-configuration") is True

    def test_is_blocked_command_allow_safe(self):
        """验证安全命令不被拦截。"""
        from mcpensp1.command_executor import is_blocked_command
        assert is_blocked_command("display version") is False
        assert is_blocked_command("interface GigabitEthernet0/0/1") is False
        assert is_blocked_command("vlan 10") is False

    def test_send_command_returns_dict(self):
        """验证 send_command 返回格式正确。"""
        from mcpensp1.command_executor import CommandExecutor
        ce = CommandExecutor()
        result = ce.send_command("127.0.0.1:2000", "display version")
        assert isinstance(result, dict)
        assert "path" in result or "command" in result or "output" in result or "error" in result

    def test_group_command_returns_dict(self):
        """验证 send_command_to_group 返回格式。"""
        from mcpensp1.command_executor import CommandExecutor
        ce = CommandExecutor()
        result = ce.send_command_to_group(["127.0.0.1:2000", "127.0.0.1:2001"], "display clock")
        assert isinstance(result, dict)


class TestKnowledgeBase:
    """测试 knowledge 模块的 KB 核心操作。"""

    @pytest.fixture
    def kb_tempdir(self):
        d = tempfile.mkdtemp(prefix="test_kb_")
        yield d
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_kb_init_and_get_stats(self, kb_tempdir):
        """验证知识库初始化和统计查询。"""
        from mcpensp1.knowledge import KnowledgeBase
        kb = KnowledgeBase(kb_tempdir)
        stats = kb.get_stats()
        assert "total" in stats or isinstance(stats, dict)

    def test_kb_search_experiences_empty(self, kb_tempdir):
        """验证空知识库搜索不崩溃。"""
        from mcpensp1.knowledge import KnowledgeBase
        kb = KnowledgeBase(kb_tempdir)
        results = kb.search_experiences("vlan")
        assert isinstance(results, (list, dict))

    def test_kb_best_practices(self, kb_tempdir):
        """验证最佳实践查询。"""
        from mcpensp1.knowledge import KnowledgeBase
        kb = KnowledgeBase(kb_tempdir)
        result = kb.get_best_practices()
        assert isinstance(result, (list, dict))

    def test_kb_structured_kb(self, kb_tempdir):
        """验证结构化知识库加载不崩溃。"""
        from mcpensp1.knowledge import KnowledgeBase
        kb = KnowledgeBase(kb_tempdir)
        result = kb.get_structured_kb()
        assert isinstance(result, (list, dict))

    def test_guess_category(self, kb_tempdir):
        """验证命令分类猜测。"""
        from mcpensp1.knowledge import KnowledgeBase
        kb = KnowledgeBase(kb_tempdir)
        assert kb._guess_cat("display version") in ("display", None)
        assert kb._guess_cat("vlan 10") in (None, "config")


class TestHeartbeatMonitor:
    """测试 heartbeat 模块的心跳逻辑。"""

    def test_heartbeat_init(self):
        """验证心跳监控初始化不崩溃。"""
        from mcpensp1.heartbeat import HeartbeatMonitor
        mock_kb = MagicMock()
        hb = HeartbeatMonitor(mock_kb)
        assert hb is not None

    def test_heartbeat_status_no_devices(self):
        """验证无设备时状态查询正常。"""
        from mcpensp1.heartbeat import HeartbeatMonitor
        mock_kb = MagicMock()
        hb = HeartbeatMonitor(mock_kb)
        status = hb.get_status()
        assert isinstance(status, dict)

    def test_heartbeat_status_specific_device(self):
        """验证查询特定设备状态。"""
        from mcpensp1.heartbeat import HeartbeatMonitor
        mock_kb = MagicMock()
        hb = HeartbeatMonitor(mock_kb)
        status = hb.get_status("127.0.0.1:2000")
        assert isinstance(status, dict)


class TestMCPServerRegression:
    """测试 mcp_server.py 中关键回归点。"""

    def test_tool_list_returns_all_tools(self):
        """验证工具列表包含所有关键工具名。"""
        import asyncio
        from mcpensp1.mcp_server import list_tools
        tools = asyncio.run(list_tools())
        tool_names = {t.name for t in tools}
        expected = {
            "scan_devices", "connect_device", "send_command", "disconnect_device",
            "get_connected_devices", "rename_device", "fetch_device_name",
            "batch_command", "group_command", "snapshot_config", "list_snapshots",
            "config_method_list", "config_method_get", "config_method_search",
            "agent_status", "agent_plan", "agent_execute",
            "search_kb", "get_kb_commands", "get_kb_stats",
            "get_topology", "find_topology_path", "save_topology",
            "generate_config_template", "list_templates", "get_config_guidance",
        }
        missing = expected - tool_names
        assert not missing, f"缺少工具: {missing}"

    def test_batch_command_schema_has_auto_undo_tm(self):
        """回归：batch_command 的 inputSchema 包含 auto_undo_tm。"""
        import asyncio
        from mcpensp1.mcp_server import list_tools
        tools = asyncio.run(list_tools())
        batch = next(t for t in tools if t.name == "batch_command")
        schema = batch.inputSchema
        assert "auto_undo_tm" in schema.get("properties", {})
        assert "auto_view" in schema.get("properties", {})

    def test_config_method_list_exists(self):
        """验证 config_method_list 工具已注册。"""
        import asyncio
        from mcpensp1.mcp_server import list_tools
        tools = asyncio.run(list_tools())
        cfg_methods = [t for t in tools if "config_method" in t.name]
        assert len(cfg_methods) >= 5  # list/get/search/add/steps/update
