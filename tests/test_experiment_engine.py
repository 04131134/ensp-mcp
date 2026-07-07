# -*- coding: utf-8 -*-
"本地闭环测试：验证实验状态管理、前置条件、恢复建议、验证解析与依赖图。"
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))
from experiment_engine import ExperimentEngine, OutputParsers, _now_iso


def fake_executor(state):
    def executor(path, command):
        cmd = command.strip().lower()
        if cmd == 'display ip interface brief':
            return {'success': True, 'output': 'GE0/0/0 10.0.0.1 255.255.255.0 up'}
        if cmd == 'display ospf peer brief':
            return {'success': True, 'output': '0 GE0/0/0 10.0.0.2 Full'}
        if cmd == 'display ip routing-table':
            return {'success': True, 'output': 'O 10.0.1.0/24 10.0.0.2'}
        if cmd.startswith('ping '):
            return {'success': True, 'output': 'Reply from 10.0.0.2: bytes=32 time=1ms TTL=255\n0.00% packet loss'}
        if cmd == 'display current-configuration':
            return {'success': True, 'output': 'sysname R1'}
        if cmd == 'display vlan':
            return {'success': True, 'output': '10 VLAN0010 GE0/0/1 GE0/0/2'}
        return {'success': True, 'output': ''}
    return executor


def build_engine(tmp_path):
    return ExperimentEngine(fake_executor({}), persist_dir=str(tmp_path))


def test_basic_state_workflow(tmp_path):
    engine = build_engine(tmp_path)
    engine.create_experiment('exp1', 'OSPF实验', goal='验证OSPF邻居', devices=[{'path': 'R1', 'name': 'R1', 'connected': True}])
    engine.update_interface('exp1', 'R1', 'GE0/0/0', status='up', ip='10.0.0.1', mask='255.255.255.0')
    engine.record_protocol_state('exp1', 'R1', 'vlans', OutputParsers.parse_vlan('10 VLAN0010 GE0/0/1'))
    engine.add_link('exp1', {'source': 'R1', 'target': 'SW1'})

    exp = engine.get_experiment('exp1')
    assert exp.devices['R1'].interfaces['GE0/0/0'].is_up()
    assert exp.devices['R1'].protocols['vlans'][0]['vlan_id'] == 10
    assert len(exp.links) == 1


def test_precondition_blocks_phase(tmp_path):
    engine = build_engine(tmp_path)
    engine.create_experiment('exp2', '接口实验', devices=[{'path': 'R1', 'name': 'R1', 'connected': False}])
    result = engine.execute_phase('exp2', 'interface', {'path': 'R1', 'interface': 'GE0/0/0', 'ip': '10.0.0.1', 'mask': '255.255.255.0'})
    assert result['success'] is False
    assert '前置条件不满足' in result['error']


def test_execute_phase_and_verify(tmp_path):
    engine = build_engine(tmp_path)
    engine.create_experiment('exp3', '连通实验', devices=[{'path': 'R1', 'name': 'R1', 'connected': True}])
    engine.update_interface('exp3', 'R1', 'GE0/0/0', ip='10.0.0.1')
    result = engine.execute_phase('exp3', 'interface', {'path': 'R1', 'interface': 'GE0/0/0', 'ip': '10.0.0.1', 'mask': '255.255.255.0'})
    assert result['success'] is True
    assert any(v['check_name'] == 'interface' and v['passed'] for v in result['verification'])


def test_recovery_suggestions_cover_common_errors(tmp_path):
    engine = build_engine(tmp_path)
    suggestions = engine.recoveries.suggest('OSPF neighbor not Full')
    assert 'check_ospf_consistency' in suggestions
    suggestions = engine.recoveries.suggest('Interface does not exist')
    assert 'refresh_interface_state' in suggestions


def test_dependency_graph_contains_expected_edges(tmp_path):
    engine = build_engine(tmp_path)
    graph = engine.build_dependency_graph()
    assert 'interface' in graph and 'ospf' in graph['interface']
    assert 'ospf' in graph and 'verify' in graph['ospf']
