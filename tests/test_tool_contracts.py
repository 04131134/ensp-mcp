# -*- coding: utf-8 -*-
"""MCP 工具契约测试：工具必须兑现 schema 声明的参数与返回语义。

覆盖四个曾"声明了却不兑现"的工具：
- get_kb_commands：schema 声明可按 category/device_type/risk/limit 过滤，实现却返回全部设备历史；
- get_structured_kb：schema 声明可按 model/view_type 过滤，实现却无参加载；
- auto_record_experience：文档声明可归纳实验记录，实现恒定返回失败；
- generate_lab_report：描述声明输出 Markdown，实现完全没有 Markdown。
"""
from __future__ import annotations

import asyncio
import json

import pytest

import mcp_server


class _StubKnowledge:
    def __init__(self, history=None):
        self.calls = {}
        self._experiences = []
        self._history = history if history is not None else {
            'executed_commands': [{'command': 'system-view'}, {'command': 'vlan 10'},
                                  {'command': 'interface Vlanif 10'}, {'command': 'ip address 192.168.10.1 24'}],
            'failed_commands': [],
        }

    def get_global_commands(self, category=None, device_type=None, risk=None, limit=50):
        self.calls['get_global_commands'] = {'category': category, 'device_type': device_type,
                                             'risk': risk, 'limit': limit}
        return [{'command': 'display vlan', 'category': category or 'display'}]

    def get_structured_kb(self, view_type=None, device_model=None):
        self.calls['get_structured_kb'] = {'view_type': view_type, 'device_model': device_model}
        return {'user_view_commands': {'commands': []}, 'system_view_commands': {'commands': []}}

    def get_device_history(self, path=None):
        self.calls['get_device_history'] = path
        return self._history

    def get_experiences(self, experiment=None):
        return list(self._experiences)

    def _auto_record_knowledge(self, device_path, device_type, command_results):
        self.calls['auto_record'] = {'path': device_path, 'device_type': device_type,
                                     'results': command_results}
        self._experiences.append({'experiment': 'vlan_config'})

    def get_stats(self):
        return {'total_devices': 0, 'total_commands_recorded': 0}


class _StubDevices:
    def connected(self):
        return [{'path': '127.0.0.1:2000', 'name': 'LSW1', 'device_type': 'huawei', 'alive': True}]


class _StubServices:
    def __init__(self):
        self.devices = _StubDevices()


def _call(name, arguments):
    """直接调用 MCP 分发函数，返回解析后的 JSON。"""
    result = asyncio.run(mcp_server.call_tool(name, arguments))
    return json.loads(result[0].text)


@pytest.fixture
def stub_kb(monkeypatch):
    stub = _StubKnowledge()
    monkeypatch.setattr(mcp_server, 'kb', stub)
    monkeypatch.setattr(mcp_server, 'services', _StubServices())
    monkeypatch.setattr(mcp_server.dm, 'get_type', lambda path: 'huawei')
    return stub


def test_get_kb_commands_honours_filters(stub_kb):
    payload = _call('get_kb_commands', {'category': 'display', 'device_type': 'huawei',
                                        'risk': 'safe', 'limit': 7})
    assert stub_kb.calls['get_global_commands'] == {'category': 'display', 'device_type': 'huawei',
                                                    'risk': 'safe', 'limit': 7}
    assert payload['success'] is True
    assert payload['count'] == 1
    assert payload['commands'][0]['command'] == 'display vlan'
    # 回归：不得再返回"全部设备历史"这种与命令列表无关的结构
    assert 'devices' not in payload


def test_get_structured_kb_honours_model_and_view_type(stub_kb):
    _call('get_structured_kb', {'model': 'S5700', 'view_type': 'user_view'})
    assert stub_kb.calls['get_structured_kb'] == {'view_type': 'user_view', 'device_model': 'S5700'}


def test_auto_record_experience_uses_recorded_history(stub_kb):
    payload = _call('auto_record_experience', {'path': '127.0.0.1:2000'})
    assert payload['success'] is True
    assert payload['commands_analyzed'] == 4
    assert payload['experiences_created'] == 1
    assert stub_kb.calls['auto_record']['path'] == '127.0.0.1:2000'
    assert stub_kb.calls['auto_record']['device_type'] == 'huawei'


def test_auto_record_experience_reports_missing_history(monkeypatch):
    stub = _StubKnowledge(history={'executed_commands': [], 'failed_commands': []})
    monkeypatch.setattr(mcp_server, 'kb', stub)
    payload = _call('auto_record_experience', {'path': '127.0.0.1:2999'})
    assert payload['success'] is False
    assert 'No command history' in payload['error']


def test_generate_lab_report_returns_markdown(stub_kb):
    payload = _call('generate_lab_report', {'name': 'VLAN 实验'})
    assert payload['success'] is True
    assert payload['devices'][0]['name'] == 'LSW1'
    markdown = payload['markdown']
    assert markdown.startswith('# VLAN 实验')
    assert 'LSW1' in markdown
    assert '## 知识库统计' in markdown
