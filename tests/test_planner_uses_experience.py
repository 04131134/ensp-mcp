# -*- coding: utf-8 -*-
"""Step1: planner 接入 knowledge_store 经验检索测试

验证：planner 注入 KnowledgeStore 后，plan_from_goal 优先用成功经验覆盖模板命令；
      未注入或开关关闭时回退模板行为（向后兼容）。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from agent.planner import DAGPlanner
from agent.types import TaskGoal
from agent.knowledge_store import KnowledgeStore


def _make_store_with_experience(tmp_path, experiment_type='ospf', commands=None):
    """构造含成功经验的 KnowledgeStore。"""
    store = KnowledgeStore(str(tmp_path / 'ks.json'))
    store.record_success(
        commands=commands or ['EXPERIENCE_OSPF_OVERRIDE_CMD'],
        device_type='huawei',
        experiment_type=experiment_type,
        context={'plan_id': 'test'},
    )
    return store


def test_planner_uses_experience_to_override_template(tmp_path):
    """注入 knowledge_store 后，命中经验则用经验命令覆盖模板命令。"""
    store = _make_store_with_experience(tmp_path, 'ospf', commands=['EXPERIENCE_OSPF_OVERRIDE_CMD'])
    planner = DAGPlanner()
    planner.set_knowledge_store(store)

    goal = TaskGoal(
        description='configure OSPF routing protocol',
        raw_request='configure OSPF',
        experiment_type='ospf',
    )
    plan = planner.plan_from_goal(goal)

    ospf_node = plan.nodes.get('ospf')
    assert ospf_node is not None, 'plan 应包含 ospf 配置节点'
    assert 'EXPERIENCE_OSPF_OVERRIDE_CMD' in ospf_node.commands, \
        '经验命令应覆盖模板命令'


def test_planner_without_store_uses_template(tmp_path):
    """未注入 knowledge_store 时，回退模板行为（向后兼容）。"""
    planner = DAGPlanner()  # 不注入
    goal = TaskGoal(
        description='configure OSPF routing protocol',
        raw_request='configure OSPF',
        experiment_type='ospf',
    )
    plan = planner.plan_from_goal(goal)

    ospf_node = plan.nodes.get('ospf')
    assert ospf_node is not None
    assert len(ospf_node.commands) > 0, '模板命令应非空'
    assert 'EXPERIENCE_OSPF_OVERRIDE_CMD' not in ospf_node.commands, \
        '未注入 store 时不应出现经验命令'


def test_planner_use_experience_disabled(tmp_path):
    """use_experience=False 时，即使注入 store 也不用经验。"""
    store = _make_store_with_experience(tmp_path, 'ospf', commands=['EXPERIENCE_DISABLED_CMD'])
    planner = DAGPlanner()
    planner.set_knowledge_store(store)
    planner.use_experience = False

    goal = TaskGoal(
        description='configure OSPF routing protocol',
        raw_request='configure OSPF',
        experiment_type='ospf',
    )
    plan = planner.plan_from_goal(goal)

    ospf_node = plan.nodes.get('ospf')
    assert ospf_node is not None
    assert 'EXPERIENCE_DISABLED_CMD' not in ospf_node.commands, \
        '开关关闭时不应使用经验命令'


def test_planner_experience_search_exception_does_not_break(tmp_path, monkeypatch):
    """knowledge_store 查询异常时，planner 静默回退模板（不破坏流程）。"""
    store = _make_store_with_experience(tmp_path, 'ospf')

    def _raise(*args, **kwargs):
        raise RuntimeError('mock search failure')

    monkeypatch.setattr(store, 'query_for_task', _raise)

    planner = DAGPlanner()
    planner.set_knowledge_store(store)

    goal = TaskGoal(
        description='configure OSPF routing protocol',
        raw_request='configure OSPF',
        experiment_type='ospf',
    )
    # 不应抛异常
    plan = planner.plan_from_goal(goal)
    assert plan is not None
