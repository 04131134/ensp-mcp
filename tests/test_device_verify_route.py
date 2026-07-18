"""回归测试：设备/实验验证路由不得崩溃（曾因 SemanticVerifier(devices, state, kb)
构造参数错误 + state 未定义 + result.get('checks') 对 list 无效而必抛异常）。

修复后：SemanticVerifier(send_command)，按 check_type 分发，结果用 r.to_dict() 序列化。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpensp1"))

try:
    import app as flask_app
except Exception:
    flask_app = None

import pytest


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_device_verify_returns_checks_list(monkeypatch):
    def fake_send(path, command):
        return {"success": True, "output": "Interface GE0/0/1 is up\n  IP: 10.0.0.1"}

    monkeypatch.setattr(flask_app, "send_command", fake_send)
    flask_app.devices["127.0.0.1:2001"] = object()  # 仅用于通过“已连接”判断
    client = flask_app.app.test_client()
    resp = client.post("/api/devices/verify", json={"path": "127.0.0.1:2001", "check_type": "all"})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    data = resp.get_json()
    assert data["success"] is True
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) > 0


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_device_verify_connectivity_with_target(monkeypatch):
    def fake_send(path, command):
        return {"success": True, "output": "Reply from 10.0.0.2: bytes=64"}

    monkeypatch.setattr(flask_app, "send_command", fake_send)
    flask_app.devices["127.0.0.1:2002"] = object()
    client = flask_app.app.test_client()
    resp = client.post(
        "/api/devices/verify",
        json={"path": "127.0.0.1:2002", "check_type": "connectivity", "target_ip": "10.0.0.2"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    data = resp.get_json()
    assert data["success"] is True
    assert isinstance(data["checks"], list)


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_experiment_verify_returns_checks_list(monkeypatch):
    def fake_send(path, command):
        return {"success": True, "output": "VLAN 10 exists"}

    monkeypatch.setattr(flask_app, "send_command", fake_send)
    flask_app.devices["127.0.0.1:2003"] = object()
    client = flask_app.app.test_client()
    resp = client.post("/api/experiments/exp1/verify", json={"path": "127.0.0.1:2003"})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    data = resp.get_json()
    assert data["success"] is True
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) > 0
