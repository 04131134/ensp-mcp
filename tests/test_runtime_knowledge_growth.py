# -*- coding: utf-8 -*-
"""验证 AgentRuntime 的知识成长接入。"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from agent.runtime import AgentRuntime
from agent.types import ExperimentResult, PlanNode


class _CallRecorder:
    """记录被测调用的简单替身。"""

    def __init__(self) -> None:
        self.calls: List[Any] = []


class _BlueprintLearner(_CallRecorder):
    def learn_from_success(self, *args: Any) -> None:
        self.calls.append(args)


class _ErrorClassifier(_CallRecorder):
    def __init__(self, record: Dict[str, Any]) -> None:
        super().__init__()
        self.record = record

    def classify(self, *args: Any) -> Dict[str, Any]:
        self.calls.append(args)
        return dict(self.record)


class _ConstraintUpdater(_CallRecorder):
    def update_from_error(self, record: Dict[str, Any]) -> None:
        self.calls.append(dict(record))


class _RegressionGenerator(_CallRecorder):
    def generate_test(self, constraint: Dict[str, Any]) -> str:
        self.calls.append(dict(constraint))
        return 'generated.py'


@pytest.fixture
def runtime(tmp_path: Any) -> AgentRuntime:
    return AgentRuntime(
        str(tmp_path),
        lambda _path, _command: {'success': True, 'cmd_success': True, 'output': '<R1>'},
        device_scanner=lambda: [
            {'path': '127.0.0.1:2001', 'model': 'AC6005', 'role': 'ac'},
        ],
        topology_provider=lambda: {'links': [{'interface': 'GE0/0/1', 'ip': '10.0.0.1/24'}]},
    )


def test_success_runs_blueprint_learning_with_execution_context(runtime: AgentRuntime) -> None:
    learner = _BlueprintLearner()
    runtime._blueprint_learner = learner
    result = ExperimentResult(
        experiment_id='exp-success',
        success=True,
        execution_log=[{
            'command': 'ip address 10.0.0.1 255.255.255.0',
            'output': '[R1-GE0/0/1]',
            'view': '[R1-GE0/0/1]',
            'device_path': '127.0.0.1:2001',
            'node_id': 'interface',
            'success': True,
        }],
    )

    runtime._run_knowledge_growth(result)

    task_id, execution_log, device_info, topology_data = learner.calls[0]
    assert task_id == 'exp-success'
    assert execution_log[0]['output'] == '[R1-GE0/0/1]'
    assert device_info['model'] == 'AC6005'
    assert topology_data['links'][0]['ip'] == '10.0.0.1/24'


def test_failed_command_updates_constraint_and_generates_regression(runtime: AgentRuntime) -> None:
    classifier = _ErrorClassifier({
        'error_type': 'device_not_supported',
        'constraint': {'command_pattern': 'display wlan ap all'},
        'alternative_command': 'display ap all',
    })
    updater = _ConstraintUpdater()
    generator = _RegressionGenerator()
    runtime._error_classifier = classifier
    runtime._constraint_updater = updater
    runtime._regression_test_generator = generator
    result = ExperimentResult(
        experiment_id='exp-failure',
        success=False,
        execution_log=[{
            'command': 'display wlan ap all',
            'output': 'feature not available\n<R1>',
            'view': '<R1>',
            'device_path': '127.0.0.1:2001',
            'node_id': 'wlan',
            'success': False,
        }],
    )

    runtime._run_knowledge_growth(result)

    assert classifier.calls[0][1:] == ('display wlan ap all', 'feature not available\n<R1>', '<R1>')
    error_record = updater.calls[0]
    assert error_record['task_id'] == 'exp-failure'
    assert error_record['device_model'] == 'AC6005'
    assert error_record['failed_command'] == 'display wlan ap all'
    assert generator.calls == [{
        'command_pattern': 'display wlan ap all',
        'device_model': 'AC6005',
        'alternative': 'display ap all',
    }]


def test_environment_error_without_constraint_skips_regression(runtime: AgentRuntime) -> None:
    runtime._error_classifier = _ErrorClassifier({'error_type': 'environment_issue'})
    runtime._constraint_updater = _ConstraintUpdater()
    generator = _RegressionGenerator()
    runtime._regression_test_generator = generator
    result = ExperimentResult(
        experiment_id='exp-environment',
        success=False,
        execution_log=[{
            'command': 'display version', 'output': 'Error: Timeout', 'view': '<R1>',
            'device_path': '127.0.0.1:2001', 'node_id': 'check', 'success': False,
        }],
    )

    runtime._run_knowledge_growth(result)

    assert generator.calls == []


def test_context_error_adds_required_view_for_constraint_update(runtime: AgentRuntime) -> None:
    runtime._error_classifier = _ErrorClassifier({'error_type': 'context_error'})
    updater = _ConstraintUpdater()
    runtime._constraint_updater = updater
    result = ExperimentResult(
        experiment_id='exp-context',
        success=False,
        execution_log=[{
            'command': 'vlan 10', 'output': 'Incomplete command\n<R1>', 'view': '<R1>',
            'device_path': '127.0.0.1:2001', 'node_id': 'vlan', 'success': False,
        }],
    )

    runtime._run_knowledge_growth(result)

    assert updater.calls[0]['required_view'] == 'system-view'
    assert updater.calls[0]['view_entry_command'] == 'system-view'


def test_learning_exception_does_not_escape(runtime: AgentRuntime, caplog: pytest.LogCaptureFixture) -> None:
    class _FailingLearner:
        def learn_from_success(self, *args: Any) -> None:
            raise RuntimeError('学习存储不可用')

    runtime._blueprint_learner = _FailingLearner()
    result = ExperimentResult(experiment_id='exp-isolated', success=True)

    runtime._run_knowledge_growth(result)

    assert '蓝图学习失败' in caplog.text


def test_execution_log_keeps_full_output_and_extracts_view(tmp_path: Any) -> None:
    full_output = ('x' * 260) + '\n[R1-GigabitEthernet0/0/1]'
    runtime = AgentRuntime(
        str(tmp_path),
        lambda _path, _command: {
            'success': True, 'cmd_success': False, 'output': full_output,
        },
    )
    result = ExperimentResult(experiment_id='exp-log', success=False)
    node = PlanNode(node_id='interface', label='接口配置', commands=['ip address 10.0.0.1 24'])

    runtime._execute_config_node(node, '127.0.0.1:2001', result)

    assert node.result['commands'][0]['output'] == full_output[:200]
    assert result.execution_log[0]['output'] == full_output
    assert result.execution_log[0]['view'] == '[R1-GigabitEthernet0/0/1]'
    assert result.execution_log[0]['success'] is False
