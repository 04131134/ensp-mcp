# -*- coding: utf-8 -*-
"""learning 数据质量修复测试

验证：
1. device_type 不再硬编码 'huawei'，改为 _infer_device_type 推断（默认仍 huawei，向后兼容）
2. record_verify_method 不再传空 commands，改为 _extract_verify_commands 提取（兜底 check_name）
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from agent.learning import LearningEngine, DEFAULT_DEVICE_TYPE
from agent.memory import MemoryStore
from agent.knowledge_store import KnowledgeStore
from agent.types import (
    ExperimentResult, ExecutionPlan, PlanNode, NodeType, TaskGoal,
    VerificationResult, ReflectionEntry,
)


def _make_engine(tmp_path):
    """构造 LearningEngine（独立临时存储）。"""
    memory = MemoryStore(str(tmp_path / 'memory.json'))
    knowledge = KnowledgeStore(str(tmp_path / 'knowledge.json'))
    return LearningEngine(memory, knowledge)


def test_learning_default_device_type_constant():
    """DEFAULT_DEVICE_TYPE 常量为 'huawei'（eNSP 平台默认）。"""
    assert DEFAULT_DEVICE_TYPE == 'huawei'


def test_learning_infer_device_type_default(tmp_path):
    """_infer_device_type 默认返回 huawei（向后兼容）。"""
    engine = _make_engine(tmp_path)
    result = ExperimentResult(experiment_id='test', success=True)
    assert engine._infer_device_type(result) == DEFAULT_DEVICE_TYPE


def test_learning_verify_method_non_empty_commands(tmp_path):
    """record_verify_method 不再传空 commands，evidence 有命令时用命令。"""
    engine = _make_engine(tmp_path)

    # 构造成功实验 + 含命令的验证结果
    plan = ExecutionPlan(goal=TaskGoal(
        description='configure OSPF', raw_request='configure OSPF', experiment_type='ospf',
    ))
    node = PlanNode(
        node_id='ospf', label='OSPF Config',
        node_type=NodeType.CONFIG, commands=['ospf 1'],
    )
    node.status = 'success'
    plan.add_node(node)

    vr = VerificationResult(
        check_name='ospf_peer',
        passed=True,
        detail='OSPF 邻居已建立',
        evidence={'command': 'display ospf peer brief'},
    )

    result = ExperimentResult(experiment_id='test_exp', success=True, plan=plan)
    result.verification_results.append(vr)

    reflection = ReflectionEntry(experiment_id='test_exp', summary='ok')

    stats = engine.learn_from_experiment(result, reflection)
    assert stats['knowledge_created'] > 0, '应产生知识记录'

    # 验证 verify_method 记录的 commands 非空
    records = engine._knowledge.search(category='verify_method')
    assert records, '应有 verify_method 记录'
    for r in records:
        cmds = r.content.get('commands') if isinstance(r.content, dict) else None
        assert cmds and len(cmds) > 0, 'verify_method commands 不应为空'
        assert 'display ospf peer brief' in cmds


def test_learning_extract_verify_commands_fallback_to_check_name(tmp_path):
    """evidence 无命令时，用 check_name 兜底（不再是空列表）。"""
    engine = _make_engine(tmp_path)
    vr = VerificationResult(check_name='vlan_check', passed=True, detail='ok')
    cmds = engine._extract_verify_commands(vr)
    assert cmds == ['vlan_check'], 'evidence 无命令时应兜底为 check_name'


def test_learning_extract_verify_commands_from_evidence_list(tmp_path):
    """evidence 含 commands 列表时，提取列表。"""
    engine = _make_engine(tmp_path)
    vr = VerificationResult(
        check_name='routing',
        passed=True,
        detail='ok',
        evidence={'commands': ['display ip routing-table', 'display ospf peer']},
    )
    cmds = engine._extract_verify_commands(vr)
    assert cmds == ['display ip routing-table', 'display ospf peer']


def test_learning_success_uses_inferred_device_type(tmp_path):
    """成功案例记录使用 _infer_device_type 而非硬编码（间接验证：不抛异常 + 记录存在）。"""
    engine = _make_engine(tmp_path)

    plan = ExecutionPlan(goal=TaskGoal(
        description='configure VLAN', raw_request='configure VLAN', experiment_type='vlan',
    ))
    node = PlanNode(
        node_id='vlan', label='VLAN Config',
        node_type=NodeType.CONFIG, commands=['vlan 10', 'quit'],
    )
    node.status = 'success'
    plan.add_node(node)

    result = ExperimentResult(experiment_id='test_exp', success=True, plan=plan)
    reflection = ReflectionEntry(experiment_id='test_exp', summary='ok')

    stats = engine.learn_from_experiment(result, reflection)
    assert stats['knowledge_created'] > 0

    # 验证 success_case 记录的 device_type 是推断的（默认 huawei）
    records = engine._knowledge.search(category='success_case')
    assert records
    assert records[0].device_type == DEFAULT_DEVICE_TYPE
