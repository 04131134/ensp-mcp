"""回归测试：实验路由不再返回假数据 / 静默丢失。

- 创建实验后必须可在全局 experiments 中查到（原逻辑正常模式下会丢弃）。
- /api/experiments/<id>/plan 委托 AgentRuntime.get_plan 返回真实计划；
  缺 goal 返回 400，未找到返回 404。
- /api/experiments/dependency-graph 诚实返回 501。
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
def test_create_then_plan_returns_real_plan():
    client = flask_app.app.test_client()
    name = "regression_test_exp_%s" % os.getpid()
    create = client.post("/api/experiments", json={"name": name, "goal": "配置 VLAN 10 并测试连通性"})
    assert create.status_code == 200, create.get_data(as_text=True)[:200]
    exp_id = create.get_json()["experiment_id"]

    # 创建后实验应可在全局 experiments 中查到（不再静默丢失）
    get_resp = client.get("/api/experiments/%s" % exp_id)
    assert get_resp.status_code == 200
    assert get_resp.get_json().get("goal")

    plan = client.post("/api/experiments/%s/plan" % exp_id, json={})
    assert plan.status_code == 200, plan.get_data(as_text=True)[:300]
    data = plan.get_json()
    assert data["success"] is True
    assert "plan" in data


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_plan_missing_goal_returns_400():
    client = flask_app.app.test_client()
    name = "no_goal_exp_%s" % os.getpid()
    create = client.post("/api/experiments", json={"name": name, "goal": ""})
    assert create.status_code == 200
    exp_id = create.get_json()["experiment_id"]
    plan = client.post("/api/experiments/%s/plan" % exp_id, json={})
    assert plan.status_code == 400, plan.get_data(as_text=True)[:200]


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_plan_unknown_experiment_returns_404():
    client = flask_app.app.test_client()
    plan = client.post("/api/experiments/does_not_exist/plan", json={})
    assert plan.status_code == 404


@pytest.mark.skipif(flask_app is None, reason="Flask app 无法导入")
def test_dependency_graph_returns_501():
    client = flask_app.app.test_client()
    resp = client.get("/api/experiments/dependency-graph")
    assert resp.status_code == 501
    assert resp.get_json().get("implemented") is False
