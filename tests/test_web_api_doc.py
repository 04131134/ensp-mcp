"""文档覆盖测试：docs/modules/web_api.md 必须覆盖所有运行时 HTTP 路由与 SocketIO 事件。

以 Flask app.url_map（含 init_agent_runtime 在导入时注册的 agent 路由）与
app.py 的 @socketio.on 声明为唯一事实源，防止文档再次漂移。
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpensp1"))

try:
    import app as flask_app
except Exception:
    flask_app = None

import pytest

DOC_PATH = "docs/modules/web_api.md"

# 框架/传输层路由，不属于对外 API，文档无需覆盖
_EXCLUDE_PREFIXES = ("/static/", "/socket.io")


def _norm(s):
    # 将 <var> 占位符统一替换为单个字符，避免路由变量位于路径中段时
    # 被替换为空产生双斜杠（如 /api/experiments/<exp_id>/plan -> //）。
    return re.sub(r"<[^>]+>", "_", s)


def _runtime_http_paths():
    paths = set()
    for rule in flask_app.app.url_map.iter_rules():
        if rule.rule.startswith(_EXCLUDE_PREFIXES):
            continue
        paths.add(_norm(rule.rule))
    return paths


def _socketio_events():
    src = open("mcpensp1/web/socketio_handlers.py", encoding="utf-8").read()
    # 事件名可能是单引号或双引号，且带 namespace 关键字参数
    return set(re.findall(r"@socketio\.on\(\s*['\"]([^'\"]+)['\"]", src))


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_all_http_routes_documented():
    doc = _norm(open(DOC_PATH, encoding="utf-8").read())
    missing = sorted(p for p in _runtime_http_paths() if p not in doc)
    assert not missing, f"未文档化的 HTTP 路由: {missing}"


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_all_socketio_events_documented():
    doc = _norm(open(DOC_PATH, encoding="utf-8").read())
    missing = sorted(e for e in _socketio_events() if e not in doc)
    assert not missing, f"未文档化的 SocketIO 事件: {missing}"
