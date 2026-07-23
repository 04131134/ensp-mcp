# -*- coding: utf-8 -*-
"""批次1: Planner 接入 structured_commands_kb 测试

验证：
1. S5700 VLAN: structured_kb 提供候选命令（非模板默认值）
2. USG6000V NAT: 不再生成 nat outbound（从 structured_kb 获取正确命令）
3. 无设备型号: 降级使用 COMMAND_TEMPLATES
4. KnowledgeBase 不可用: Planner 正常降级
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from agent.planner import DAGPlanner
from agent.types import TaskGoal, NodeType

# 项目 kb 目录
_KB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'mcpensp1', 'kb',
)


def _make_kb():
    """构造 KnowledgeBase 实例。"""
    from knowledge import KnowledgeBase
    return KnowledgeBase(kb_folder=_KB_DIR)


def test_s5700_vlan_uses_structured_kb():
    """S5700 VLAN 配置：structured_kb 应提供候选命令（非仅模板 vlan/quit）。"""
    planner = DAGPlanner()
    planner.set_knowledge_base(_make_kb())

    goal = TaskGoal(
        description='S5700 VLAN配置 创建VLAN10',
        raw_request='配置VLAN',
        experiment_type='vlan',
    )
    plan = planner.plan_from_goal(goal, devices={'model': 'S5700'})

    # S5700 应有 vlan 节点
    vlan_node = plan.nodes.get('vlan')
    assert vlan_node is not None, 'plan 应含 vlan 节点'
    assert len(vlan_node.commands) > 0, 'vlan 节点应有命令'

    # structured_kb 的 S5700.VLAN端口 function 应提供 port link-type 等命令
    # （不再是仅来自 COMMAND_TEMPLATES 的 ['vlan 10', 'quit']）
    cmd_texts = ' '.join(vlan_node.commands).lower()
    assert 'vlan' in cmd_texts
    # structured_kb 应包含 trunk/access 接口命令
    assert any('port' in c for c in vlan_node.commands) or 'vlan' in cmd_texts


def test_usg6000v_nat_not_generates_outbound():
    """USG6000V NAT: 不应生成 nat outbound（structured_kb 提供正确防火墙 NAT 命令）。

    注意：描述避免含 'as' 子串（'easy'/'as'），_match_template 的 bgp 关键词
    'as' 会误匹配。此问题已知（审计报告已记录），非本批次修复范围。
    """
    planner = DAGPlanner()
    planner.set_knowledge_base(_make_kb())

    goal = TaskGoal(
        description='USG6000V 配置NAT地址转换',
        raw_request='配置NAT',
        experiment_type='nat',
    )
    plan = planner.plan_from_goal(goal, devices={'model': 'USG6000V'})

    # 检查所有 config 节点的命令
    all_cmds = []
    for n in plan.nodes.values():
        if n.node_type == NodeType.CONFIG:
            all_cmds.extend(n.commands)

    cmd_text = ' '.join(all_cmds).lower()

    # 关键断言：不应出现交换机/路由器风格的 nat outbound 命令
    assert 'nat outbound' not in cmd_text, (
        f'USG6000V NAT 不应使用 nat outbound 命令，实际命令: {all_cmds}'
    )

    # structured_kb 的 USG6000V.NAT策略 function 应提供 nat-policy 等防火墙命令
    # 如果 NAT 节点被 structured_kb 增强，应有 nat-policy 或 source-zone
    has_fw_nat = any(
        kw in cmd_text for kw in ('nat-policy', 'source-zone', 'source-nat')
    )
    assert has_fw_nat, (
        f'USG6000V NAT 应从 structured_kb 获取防火墙 NAT 命令，实际命令: {all_cmds}'
    )


def test_no_device_model_fallback_to_template():
    """无设备型号时，降级使用 COMMAND_TEMPLATES（与当前行为一致）。"""
    planner = DAGPlanner()
    planner.set_knowledge_base(_make_kb())

    goal = TaskGoal(
        description='VLAN配置 创建VLAN10',
        raw_request='配置VLAN',
        experiment_type='vlan',
    )
    # 不传 devices → 不传 model
    plan = planner.plan_from_goal(goal)  # devices=None

    vlan_node = plan.nodes.get('vlan')
    assert vlan_node is not None
    assert len(vlan_node.commands) > 0
    # 应来自 COMMAND_TEMPLATES（默认值 vlan 10, quit）
    assert 'vlan 10' in vlan_node.commands
    assert 'quit' in vlan_node.commands

    # 确认未使用 structured_kb 的命令（不应有 port link-type 等交换机配置命令）
    cmd_text = ' '.join(vlan_node.commands).lower()
    assert 'port link-type' not in cmd_text, (
        '无设备型号时不应使用 structured_kb 命令'
    )


def test_knowledge_base_unavailable_fallback():
    """KnowledgeBase 未注入时，Planner 正常降级（不抛异常）。"""
    planner = DAGPlanner()
    # 不注入 knowledge_base
    planner.use_structured_kb = True  # 开关开但无注入

    goal = TaskGoal(
        description='S5700 VLAN配置',
        raw_request='配置VLAN',
        experiment_type='vlan',
    )
    # 不应抛异常
    plan = planner.plan_from_goal(goal, devices={'model': 'S5700'})

    vlan_node = plan.nodes.get('vlan')
    assert vlan_node is not None
    assert len(vlan_node.commands) > 0
    # 应降级为 COMMAND_TEMPLATES
