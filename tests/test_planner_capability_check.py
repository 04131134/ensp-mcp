# -*- coding: utf-8 -*-
"""Step2: planner 接入 capability_manager 能力校验测试

验证：planner 注入 CapabilityManager 后，plan_from_goal 校验设备是否支持目标协议；
      未注入/开关关闭/未传 devices 时跳过（向后兼容，不阻塞）。
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from agent.planner import DAGPlanner
from agent.types import TaskGoal
from agent.capability_manager import CapabilityManager


def _make_goal():
    return TaskGoal(
        description='configure OSPF routing protocol',
        raw_request='configure OSPF',
        experiment_type='ospf',
    )


def test_planner_capability_check_with_known_model(caplog):
    """注入 cm 后，已知支持设备的协议校验通过（不报 warning）。"""
    planner = DAGPlanner()
    planner.set_capability_manager(CapabilityManager())

    with caplog.at_level(logging.WARNING, logger='mcpensp1.agent.planner'):
        plan = planner.plan_from_goal(_make_goal(), devices={'model': 'S5700'})

    assert plan is not None
    # S5700 支持 ospf，不应有"不支持协议"的 warning
    unsupported_warnings = [r for r in caplog.records if '不支持协议' in r.getMessage()]
    assert not unsupported_warnings, 'S5700 应支持 OSPF，不应报不支持'


def test_planner_capability_check_unknown_model_warns(caplog):
    """注入 cm 后，未知设备型号触发 warning（不阻塞）。"""
    planner = DAGPlanner()
    planner.set_capability_manager(CapabilityManager())

    with caplog.at_level(logging.WARNING, logger='mcpensp1.agent.planner'):
        plan = planner.plan_from_goal(_make_goal(), devices={'model': 'UnknownModelXYZ'})

    assert plan is not None, '能力校验不应阻塞计划生成'
    # 未知型号应产生 warning
    warnings = [r for r in caplog.records if '能力校验' in r.getMessage()]
    assert warnings, '未知设备型号应触发能力校验 warning'


def test_planner_capability_check_disabled(caplog):
    """check_capability=False 时，不校验。"""
    planner = DAGPlanner()
    planner.set_capability_manager(CapabilityManager())
    planner.check_capability = False

    with caplog.at_level(logging.WARNING, logger='mcpensp1.agent.planner'):
        plan = planner.plan_from_goal(_make_goal(), devices={'model': 'UnknownModelXYZ'})

    assert plan is not None
    warnings = [r for r in caplog.records if '能力校验' in r.getMessage()]
    assert not warnings, '开关关闭时不应有能力校验 warning'


def test_planner_capability_without_cm_skips():
    """未注入 cm 时，能力校验跳过（向后兼容）。"""
    planner = DAGPlanner()  # 不注入 cm
    plan = planner.plan_from_goal(_make_goal(), devices={'model': 'S5700'})
    assert plan is not None


def test_planner_capability_without_devices_skips():
    """未传 devices 时，能力校验跳过（当前 runtime 行为）。"""
    planner = DAGPlanner()
    planner.set_capability_manager(CapabilityManager())
    plan = planner.plan_from_goal(_make_goal())  # 不传 devices
    assert plan is not None
