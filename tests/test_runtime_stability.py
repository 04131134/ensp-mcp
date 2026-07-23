# -*- coding: utf-8 -*-
"""第四阶段 Step5: runtime 接入 plan_reviewer 稳定性测试

验证：
1. plan_reviewer 注入成功（孤岛模块接入）
2. _review_plan 方法正常工作（不阻塞、不破坏）
3. 开关关闭 / reviewer 未注入 / 异常 → 容错跳过
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from agent.runtime import AgentRuntime
from agent.types import ExecutionPlan, PlanNode, NodeType, TaskGoal


def _make_runtime(tmp_path):
    """构造测试用 AgentRuntime（mock executor，临时数据目录）。"""
    def mock_exec(path, cmd):
        return {'success': True, 'output': '', 'cmd_success': True}
    return AgentRuntime(data_dir=str(tmp_path), command_executor=mock_exec)


def _make_simple_plan():
    """构造简单 ExecutionPlan（含一个 config 节点）。"""
    plan = ExecutionPlan(goal=TaskGoal(
        description='configure VLAN', raw_request='vlan', experiment_type='vlan',
    ))
    node = PlanNode(
        node_id='vlan', label='VLAN Config',
        node_type=NodeType.CONFIG, commands=['vlan 10', 'quit'],
    )
    plan.add_node(node)
    return plan


def test_runtime_plan_reviewer_injected(tmp_path):
    """__init__ 后 plan_reviewer 注入成功（孤岛模块接入）。"""
    runtime = _make_runtime(tmp_path)
    assert runtime._plan_reviewer is not None
    assert runtime.review_plan is True


def test_review_plan_runs_without_error(tmp_path, caplog):
    """_review_plan 正常执行，不抛异常，产生审核日志。"""
    runtime = _make_runtime(tmp_path)
    plan = _make_simple_plan()
    with caplog.at_level(logging.INFO, logger='mcpensp1.agent.runtime'):
        runtime._review_plan(plan, 'test_exp')
    review_logs = [r for r in caplog.records if '阶段4.5' in r.getMessage()]
    assert len(review_logs) > 0, '应产生计划审核日志'


def test_review_plan_disabled(tmp_path, caplog):
    """review_plan=False 时跳过审核（无日志）。"""
    runtime = _make_runtime(tmp_path)
    runtime.review_plan = False
    plan = _make_simple_plan()
    with caplog.at_level(logging.INFO, logger='mcpensp1.agent.runtime'):
        runtime._review_plan(plan, 'test_exp')
    review_logs = [r for r in caplog.records if '阶段4.5' in r.getMessage()]
    assert len(review_logs) == 0, '开关关闭时不应有审核日志'


def test_review_plan_no_reviewer_skips(tmp_path, caplog):
    """_plan_reviewer=None 时跳过（向后兼容）。"""
    runtime = _make_runtime(tmp_path)
    runtime._plan_reviewer = None
    plan = _make_simple_plan()
    with caplog.at_level(logging.INFO, logger='mcpensp1.agent.runtime'):
        runtime._review_plan(plan, 'test_exp')  # 不应抛异常
    review_logs = [r for r in caplog.records if '阶段4.5' in r.getMessage()]
    assert len(review_logs) == 0


def test_review_plan_exception_handled(tmp_path, caplog):
    """reviewer.review 异常时不破坏流程（log warning 跳过）。"""
    runtime = _make_runtime(tmp_path)

    class BadReviewer:
        def review(self, *args, **kwargs):
            raise RuntimeError('mock review failure')

    runtime._plan_reviewer = BadReviewer()
    plan = _make_simple_plan()
    with caplog.at_level(logging.WARNING, logger='mcpensp1.agent.runtime'):
        runtime._review_plan(plan, 'test_exp')  # 不应抛异常
    warning_logs = [r for r in caplog.records if '审核异常' in r.getMessage()]
    assert len(warning_logs) > 0, '异常时应 log warning'


def test_review_plan_empty_plan(tmp_path, caplog):
    """空 plan 不破坏审核（边界情况）。"""
    runtime = _make_runtime(tmp_path)
    plan = ExecutionPlan()
    with caplog.at_level(logging.INFO, logger='mcpensp1.agent.runtime'):
        runtime._review_plan(plan, 'test_exp')  # 不应抛异常


def test_runtime_default_flags(tmp_path):
    """runtime 默认开关正确。"""
    runtime = _make_runtime(tmp_path)
    assert runtime.review_plan is True
    # 第二阶段的开关也应保留
    assert runtime.planner.use_experience is True
    assert runtime.planner.check_capability is True
    assert runtime.reflection.causal_reflection is True
