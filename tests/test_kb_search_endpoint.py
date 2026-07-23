"""回归测试：/api/kb/search 后端不得崩溃（曾因 troubleshooting 条目为 list 而 500）。

该端点是 MCP 工具 search_kb 经 mcp_req 代理的目标，若后端 500 则整个工具失效。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpensp1"))

try:
    import app as flask_app
except Exception as _e:  # 若 Flask 应用在某些环境无法导入，跳过而非红
    flask_app = None

import pytest


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_kb_search_endpoint_returns_200():
    client = flask_app.app.test_client()
    resp = client.get("/api/kb/search?q=vlan")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_kb_search_includes_markdown_reference():
    client = flask_app.app.test_client()
    resp = client.get("/api/kb/search?q=ospf")

    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    assert any(item.get('type') == 'markdown_reference' for item in resp.get_json())
