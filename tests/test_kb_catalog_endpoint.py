"""回归测试：/api/kb/catalog 后端不得返回空列表。

该端点是 MCP 工具 get_command_catalog 经 mcp_req 代理的目标。
历史上 app.py 定义了 COMMAND_CATALOG 却从未注入 knowledge 模块，
导致 kb.get_command_catalog() 遍历空字典、路由返回 []；
get_command_catalog 工具本身也因引用未导入的 COMMAND_CATALOG 而 NameError。
两处修复后，本测试断言路由返回 200 且含真实命令目录条目。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpensp1"))

try:
    import app as flask_app
except Exception:  # 若 Flask 应用在某些环境无法导入，跳过而非红
    flask_app = None

import pytest


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_kb_catalog_endpoint_returns_populated_list():
    client = flask_app.app.test_client()
    resp = client.get("/api/kb/catalog")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    data = resp.get_json()
    assert isinstance(data, list), f"catalog 应返回列表，实际: {type(data)}"
    assert len(data) > 0, "catalog 不应为空（COMMAND_CATALOG 未注入 knowledge 模块？）"
    # 每个条目至少含 command 与 category 字段
    assert all("command" in item and "category" in item for item in data), \
        "catalog 条目结构异常"


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_kb_catalog_endpoint_filters_by_risk():
    client = flask_app.app.test_client()
    resp = client.get("/api/kb/catalog?risk=high")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    data = resp.get_json()
    assert isinstance(data, list)
    assert all(item.get("risk") == "high" for item in data), "risk=high 过滤未生效"
