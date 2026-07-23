# -*- coding: utf-8 -*-
"""ConstraintUpdater 和 ConstraintStore 的行为测试。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpensp1"))

from agent.constraint_store import ConstraintStore
from agent.constraint_updater import ConstraintUpdater
from agent.knowledge_store import KnowledgeStore
from agent.memory import MemoryStore
from agent.types import KnowledgeRecord


def _make_updater(tmp_path):
    """构造使用独立持久化文件的约束更新器和知识库。"""
    knowledge = KnowledgeStore(str(tmp_path / "knowledge.json"))
    memory = MemoryStore(str(tmp_path / "memory.json"))
    constraints = ConstraintStore(str(tmp_path / "constraints.json"))
    return ConstraintUpdater(constraints, knowledge, memory), knowledge, memory, constraints


def _add_blueprint(knowledge):
    """写入含设备范围和命令序列的测试蓝图。"""
    return knowledge.add(KnowledgeRecord(
        category="template",
        title="配置蓝图: WLAN",
        content={
            "command_sequence": [
                {"command": "wlan ap-group name office", "expected_view": "system-view"},
                {"command": "ip address 10.0.0.1 255.255.255.0", "expected_view": "interface-view"},
            ],
            "applicable_devices": ["AR2220", "AR3260"],
            "preconditions": [],
        },
    ))


def test_device_not_supported_stores_constraint_and_removes_model(tmp_path):
    """设备不支持命令时应原子存约束并收窄蓝图设备范围。"""
    updater, knowledge, _, constraints = _make_updater(tmp_path)
    record_id = _add_blueprint(knowledge)

    result = updater.update_from_error({
        "error_type": "device_not_supported",
        "constraint": {
            "command_pattern": "wlan ap-group name office",
            "alternative": "改用支持 WLAN 的设备。",
        },
        "device_info": {"model": "AR2220"},
        "task_id": "task-wlan-1",
    })

    assert result == {
        "error_type": "device_not_supported",
        "constraint_recorded": True,
        "blueprints_updated": 1,
        "memory_recorded": False,
    }
    stored_constraint = constraints.list()[0]
    assert stored_constraint["task_id"] == "task-wlan-1"
    assert stored_constraint["device_model"] == "AR2220"
    assert stored_constraint["recorded_at"]
    assert not list(tmp_path.glob("*.tmp"))
    with open(tmp_path / "constraints.json", encoding="utf-8") as file:
        assert json.load(file)["constraints"][0]["command_pattern"] == "wlan ap-group name office"
    blueprint = knowledge._records[record_id]
    assert blueprint.content["applicable_devices"] == ["AR3260"]


def test_context_error_adds_precondition_and_missing_view_entry(tmp_path):
    """视图错误应仅修正命中命令所在蓝图的前置步骤。"""
    updater, knowledge, _, _ = _make_updater(tmp_path)
    record_id = _add_blueprint(knowledge)

    result = updater.update_from_error({
        "error_type": "context_error",
        "failed_command": "ip address 10.0.0.1 255.255.255.0",
        "required_view": "interface GigabitEthernet0/0/1",
        "task_id": "task-interface-1",
    })

    assert result["blueprints_updated"] == 1
    blueprint = knowledge._records[record_id].content
    assert blueprint["preconditions"] == [
        "requires view: interface GigabitEthernet0/0/1"
    ]
    assert blueprint["command_sequence"][1] == {
        "command": "interface GigabitEthernet0/0/1",
        "expected_view": "system-view",
    }


def test_other_error_types_are_recorded_in_memory(tmp_path):
    """非能力和视图类错误只记录统计记忆，不修改蓝图。"""
    updater, _, memory, constraints = _make_updater(tmp_path)

    result = updater.update_from_error({
        "error_type": "syntax_error",
        "suggestion": "核对参数。",
        "raw_output_summary": "Error: Wrong parameter",
        "task_id": "task-syntax-1",
        "device_model": "AR2220",
    })

    assert result["memory_recorded"] is True
    assert constraints.list() == []
    entries = memory.get_error_patterns()
    assert len(entries) == 1
    assert entries[0].context["task_id"] == "task-syntax-1"
    assert entries[0].context["recorded_at"]
