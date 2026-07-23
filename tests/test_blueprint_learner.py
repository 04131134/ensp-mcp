# -*- coding: utf-8 -*-
"""BlueprintLearner 的蓝图提炼和去重测试。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpensp1"))

from agent.blueprint_learner import BlueprintLearner
from agent.knowledge_store import KnowledgeStore


DEVICE_INFO = {
    "model": "AR2220",
    "role": "router",
    "software_version": "V200R003",
}
TOPOLOGY = {
    "interfaces": {
        "GE0/0/1": {"ip": "10.0.0.1/24", "link": "R1-R2"},
    },
}
EXECUTION_LOG = [
    {"command": "display version", "output": "VRP", "view": "<R1>"},
    {"command": "interface GE0/0/1", "output": "", "view": "system-view"},
    {"command": "ip address 10.0.0.1 255.255.255.0", "output": "", "view": "[R1-GE0/0/1]"},
    {"command": "ospf 1 router-id 1.1.1.1", "output": "", "view": "system-view"},
    {"command": "area 0", "output": "", "view": "[R1-ospf-1]"},
    {"command": "display ospf brief", "output": "", "view": "[R1-ospf-1]"},
]


def _make_learner(tmp_path):
    """创建使用独立持久化文件的学习器。"""
    return BlueprintLearner(KnowledgeStore(str(tmp_path / "knowledge.json")))


def test_learn_from_success_creates_self_contained_blueprint(tmp_path):
    """成功执行历史应生成参数化、可回滚且可验证的蓝图。"""
    blueprint = _make_learner(tmp_path).learn_from_success(
        "configure ospf backbone", EXECUTION_LOG, DEVICE_INFO, TOPOLOGY
    )

    assert blueprint is not None
    assert blueprint["intent"] == "configure_ospf_backbone"
    assert blueprint["device_requirements"] == ["router", "VRP8+"]
    assert blueprint["command_sequence"][0] == {
        "command": "system-view", "expected_view": "user-view"
    }
    commands = [step["command"] for step in blueprint["command_sequence"]]
    assert "display version" not in commands
    assert "display ospf brief" not in commands
    assert "ip address {ip_interface_GE0/0/1} 255.255.255.0" in commands
    assert "ospf {pid} router-id {rid}" in commands
    assert blueprint["parameter_sources"]["ip_interface_GE0/0/1"] == {
        "value": "10.0.0.1/24", "source": "topology.interfaces.GE0/0/1"
    }
    assert "undo ospf {pid}" in blueprint["rollback_sequence"]
    assert "undo ip address" in blueprint["rollback_sequence"]
    assert blueprint["verification_commands"] == ["display ospf brief"]


def test_purge_commands_filters_queries_and_view_changes(tmp_path):
    """查询命令和纯视图切换命令不得写入配置蓝图。"""
    learner = _make_learner(tmp_path)
    commands = learner._purge_commands([
        {"command": "display ip interface brief", "output": "", "view": "<R1>"},
        {"command": "ping 10.0.0.2", "output": "", "view": "<R1>"},
        {"command": "system-view", "output": "", "view": "<R1>"},
        {"command": "vlan 10", "output": "", "view": "system-view"},
        {"command": "quit", "output": "", "view": "system-view"},
    ])

    assert [entry["command"] for entry in commands] == ["vlan 10"]


def test_duplicate_blueprint_increments_success_and_device_range(tmp_path):
    """相同规范化命令序列应合并成功次数和适用设备范围。"""
    learner = _make_learner(tmp_path)
    first = learner.learn_from_success("configure ospf", EXECUTION_LOG, DEVICE_INFO, TOPOLOGY)
    second_device = dict(DEVICE_INFO, model="AR3260")
    second = learner.learn_from_success("configure ospf", EXECUTION_LOG, second_device, TOPOLOGY)

    assert first is not None and second is not None
    assert second["id"] == first["id"]
    assert second["success_count"] == 2
    assert second["applicable_devices"] == ["AR2220", "AR3260"]


def test_empty_configuration_history_does_not_create_blueprint(tmp_path):
    """只有查询记录时不应创建空模板。"""
    blueprint = _make_learner(tmp_path).learn_from_success(
        "inspect network",
        [{"command": "display version", "output": "", "view": "<R1>"}],
        DEVICE_INFO,
        TOPOLOGY,
    )

    assert blueprint is None
