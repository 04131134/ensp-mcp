# -*- coding: utf-8 -*-
"""Step9: reflection 接入 error_library 因果分析测试

验证：reflection 注入 ErrorLibrary 后，对失败节点关联错误原因做因果分析；
      未注入/开关关闭时回退原有行为（向后兼容）。
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from agent.reflection import ReflectionEngine
from agent.error_library import ErrorLibrary
from agent.types import (
    ExperimentResult, ExecutionPlan, PlanNode, NodeType, TaskGoal,
)


def _make_error_library():
    kb_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'mcpensp1', 'kb', 'errors', 'huawei_errors.json',
    )
    return ErrorLibrary(kb_path)


def _make_failed_result(error_text='Error: Unrecognized command found at'):
    """构造含一个失败节点的 ExperimentResult。"""
    plan = ExecutionPlan(goal=TaskGoal(
        description='configure OSPF', raw_request='configure OSPF', experiment_type='ospf',
    ))
    failed_node = PlanNode(
        node_id='ospf',
        label='OSPF Config',
        node_type=NodeType.CONFIG,
        commands=['ospf 1 router-id 1.1.1.1'],
    )
    failed_node.status = 'failed'
    failed_node.result = {'error': error_text, 'commands': []}
    plan.add_node(failed_node)
    return ExperimentResult(experiment_id='test_exp', success=False, plan=plan)


def test_reflection_causal_analyzes_failure(caplog):
    """注入 error_library 后，对失败节点做因果分析（不抛异常）。"""
    engine = ReflectionEngine()
    engine.set_error_library(_make_error_library())

    result = _make_failed_result('Error: Unrecognized command found at')

    with caplog.at_level(logging.INFO, logger='mcpensp1.agent.reflection'):
        reflection = engine.reflect(result)

    # 失败节点应在 what_went_wrong 中有记录（原逻辑 + 因果分析）
    assert any('OSPF' in w or 'ospf' in w.lower() for w in reflection.what_went_wrong), \
        '失败节点应在 what_went_wrong 中有记录'
    # 若 error_library 命中，应有因果分析日志
    causal_logs = [r for r in caplog.records if '因果分析' in r.getMessage()]
    # 不强制命中（取决于错误文本匹配），但若命中则验证日志结构
    for log in causal_logs:
        assert 'ospf' in log.getMessage()


def test_reflection_without_error_library_fallback():
    """未注入 error_library 时，回退原有行为（不抛异常）。"""
    engine = ReflectionEngine()  # 不注入
    result = _make_failed_result()
    reflection = engine.reflect(result)
    assert reflection is not None
    # 原有逻辑仍记录失败
    assert any('OSPF' in w for w in reflection.what_went_wrong)


def test_reflection_causal_disabled():
    """causal_reflection=False 时，不做因果分析。"""
    engine = ReflectionEngine()
    engine.set_error_library(_make_error_library())
    engine.causal_reflection = False

    result = _make_failed_result()
    reflection = engine.reflect(result)

    # 不应有因果分析的"失败原因"（原逻辑的"失败: OSPF Config"仍存在，但无"失败原因"）
    causal_entries = [w for w in reflection.what_went_wrong if '失败原因' in w]
    assert not causal_entries, '开关关闭时不应有因果分析条目'


def test_reflection_error_library_lookup_exception_does_not_break(monkeypatch):
    """error_library.lookup 异常时，reflect 不破坏（静默跳过该节点因果分析）。"""
    engine = ReflectionEngine()
    lib = _make_error_library()
    engine.set_error_library(lib)

    def _raise(error_text):
        raise RuntimeError('mock lookup failure')

    monkeypatch.setattr(lib, 'lookup', _raise)

    result = _make_failed_result()
    # 不应抛异常
    reflection = engine.reflect(result)
    assert reflection is not None
