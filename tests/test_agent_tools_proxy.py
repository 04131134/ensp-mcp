"""Agent MCP 工具必须直接使用统一服务中的 Agent Runtime。"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

try:
    import mcp_server as srv
except Exception:
    srv = None


@pytest.mark.skipif(srv is None, reason='mcp_server 无法导入')
def test_agent_tools_directly_use_agent_runtime():
    cases = {
        'agent_memory_query': {'query': 'vlan', 'limit': 20},
        'agent_memory_lessons': {},
        'agent_memory_stats': {},
        'agent_knowledge_search': {'query': 'ospf', 'category': 'c', 'device_type': 'huawei', 'limit': 20},
        'agent_knowledge_best_practices': {},
        'agent_knowledge_troubleshooting': {'query': 'flap'},
    }
    for tool, arguments in cases.items():
        result = asyncio.run(srv.call_tool(tool, arguments))
        assert result and hasattr(result[0], 'text'), f'{tool} 无返回'
        assert '"success": true' in result[0].text, result[0].text[:200]


@pytest.mark.skipif(srv is None, reason='mcp_server 无法导入')
def test_mcp_server_has_no_http_proxy():
    source = open(os.path.join(os.path.dirname(__file__), '..', 'mcpensp1', 'mcp_server.py'), encoding='utf-8').read()
    assert 'httpx' not in source
    assert 'AsyncClient' not in source
