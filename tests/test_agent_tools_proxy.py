"""回归测试：6 个 agent_* 记忆/知识工具必须代理到真实 AgentRuntime 后端，
而非调用旧 knowledge.py 的 kb（冒牌 Agent 记忆）。

通过替换 mcp_server._http_client 为记录调用的假客户端，断言每个工具打到正确的 /api/agent/* 端点。
"""
import asyncio
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpensp1"))

try:
    import mcp_server as srv
except Exception:
    srv = None

import pytest


class _FakeResp:
    def __init__(self, text):
        self.status_code = 200
        self._text = text

    @property
    def text(self):
        return self._text

    def json(self):
        return json.loads(self._text)


class _FakeClient:
    def __init__(self):
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append(("GET", url, params))
        return _FakeResp('{"success": true, "data": {}}')

    async def post(self, url, json=None, headers=None):
        self.calls.append(("POST", url, json))
        return _FakeResp('{"success": true, "data": {}}')


def _path_of(url):
    return urlparse(url).path


@pytest.mark.skipif(srv is None, reason="mcp_server 无法导入")
def test_agent_tools_proxy_to_agent_runtime(monkeypatch):
    fc = _FakeClient()
    monkeypatch.setattr(srv, "_http_client", fc)

    cases = {
        "agent_memory_query": ("GET", "/api/agent/memory", {"query": "vlan", "limit": 20}),
        "agent_memory_lessons": ("GET", "/api/agent/memory/lessons", {}),
        "agent_memory_stats": ("GET", "/api/agent/memory/stats", {}),
        "agent_knowledge_search": ("GET", "/api/agent/knowledge/search",
                                   {"query": "ospf", "category": "c", "device_type": "huawei", "limit": 20}),
        "agent_knowledge_best_practices": ("GET", "/api/agent/knowledge/best-practices", {}),
        "agent_knowledge_troubleshooting": ("GET", "/api/agent/knowledge/troubleshooting",
                                            {"query": "flap"}),
    }
    for tool, (method, path, args) in cases.items():
        fc.calls.clear()
        result = asyncio.run(srv.call_tool(tool, args))
        assert result and hasattr(result[0], "text"), f"{tool} 无返回"
        # 不应再返回旧 kb 的 '{'experiences'...' 之类结构；至少应是代理后端响应
        assert '"success": true' in result[0].text, f"{tool} 返回异常: {result[0].text[:200]}"
        assert fc.calls, f"{tool} 未发起 HTTP 代理"
        verb, url, params = fc.calls[0]
        assert verb == method, f"{tool} 方法应为 {method}，实际 {verb}"
        assert _path_of(url) == path, f"{tool} 应代理到 {path}，实际 {_path_of(url)}"
        # 参数透传校验
        if "query" in args:
            assert params and params.get("query") == args["query"], f"{tool} query 未透传"


@pytest.mark.skipif(srv is None, reason="mcp_server 无法导入")
def test_agent_tools_no_longer_reference_old_kb(monkeypatch):
    """静态确认 call_tool 中 6 个 agent 工具不再调用旧 kb.*（冒牌记忆）"""
    src = open(os.path.join(os.path.dirname(__file__), "..", "mcpensp1", "mcp_server.py"), encoding="utf-8").read()
    body_start = src.index("async def call_tool")
    body = src[body_start:body_start + src[body_start:].index("\nasync def run_mcp_server")]
    agent_block = body[body.index('agent_memory_query'):body.index('agent_plan')]
    assert "kb.search_experiences" not in agent_block, "agent_memory_query 仍调用旧 kb"
    assert "kb.get_experiences" not in agent_block, "agent_memory_lessons 仍调用旧 kb"
    assert "kb.get_stats" not in agent_block, "agent_memory_stats 仍调用旧 kb"
    assert "kb.get_best_practices" not in agent_block, "agent_knowledge_best_practices 仍调用旧 kb"
    assert "kb.get_troubleshooting_cases" not in agent_block, "agent_knowledge_troubleshooting 仍调用旧 kb"
