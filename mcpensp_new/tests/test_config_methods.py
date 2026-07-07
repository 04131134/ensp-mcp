# -*- coding: utf-8 -*-
"""Tests for ConfigMethodStore — CRUD, search, usage tracking."""
from __future__ import annotations

import tempfile

import pytest

from core.config_methods import ConfigMethodStore


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def cm_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def store(cm_dir):
    return ConfigMethodStore(cm_dir)


# ── List ────────────────────────────────────────────────────────

def test_list_empty(store):
    methods = store.list()
    assert methods == []


def test_add_and_list(store):
    store.add({
        'id': 'ospf_basic',
        'name': 'OSPF基础配置',
        'category': 'routing',
        'description': '配置OSPF路由协议',
        'steps': [
            {'step': 1, 'commands': ['system-view', 'ospf 1']},
            {'step': 2, 'commands': ['router-id 1.1.1.1']},
        ],
        'verification': ['display ospf peer brief'],
        'device_types': ['router'],
    })

    methods = store.list()
    assert len(methods) == 1
    assert methods[0]['id'] == 'ospf_basic'
    assert methods[0]['name'] == 'OSPF基础配置'


def test_list_filter_by_category(store):
    store.add({
        'id': 'ospf_basic', 'name': 'OSPF', 'category': 'routing',
        'description': 'OSPF config', 'steps': [],
    })
    store.add({
        'id': 'vlan_config', 'name': 'VLAN', 'category': 'switching',
        'description': 'VLAN config', 'steps': [],
    })

    routing = store.list(category='routing')
    assert len(routing) == 1
    assert routing[0]['id'] == 'ospf_basic'

    switching = store.list(category='switching')
    assert len(switching) == 1
    assert switching[0]['id'] == 'vlan_config'


# ── Get ─────────────────────────────────────────────────────────

def test_get_existing(store):
    store.add({
        'id': 'static_route',
        'name': '静态路由',
        'category': 'routing',
        'description': '配置静态路由',
        'steps': [{'step': 1, 'commands': ['ip route-static 0.0.0.0 0.0.0.0 192.168.1.254']}],
        'verification': ['display ip routing-table'],
    })

    method = store.get('static_route')
    assert method is not None
    assert method['name'] == '静态路由'
    assert len(method['steps']) == 1


def test_get_nonexistent(store):
    assert store.get('nonexistent') is None


# ── Search ──────────────────────────────────────────────────────

def test_search_by_keyword(store):
    store.add({
        'id': 'dhcp_server', 'name': 'DHCP服务器', 'category': 'services',
        'description': '配置DHCP服务器', 'steps': [],
    })
    store.add({
        'id': 'vlan_config', 'name': 'VLAN配置', 'category': 'switching',
        'description': '配置VLAN', 'steps': [],
    })

    results = store.search('DHCP')
    assert len(results) == 1
    assert results[0]['id'] == 'dhcp_server'


def test_search_no_match(store):
    store.add({
        'id': 'ospf_basic', 'name': 'OSPF', 'category': 'routing',
        'description': 'OSPF', 'steps': [],
    })

    results = store.search('BGP')
    assert results == []


# ── Steps ───────────────────────────────────────────────────────

def test_get_steps(store):
    store.add({
        'id': 'vlan_config',
        'name': 'VLAN',
        'category': 'switching',
        'description': 'VLAN config',
        'steps': [
            {'step': 1, 'commands': ['system-view', 'vlan batch 10 20']},
            {'step': 2, 'commands': ['interface GigabitEthernet0/0/1', 'port link-type access', 'port default vlan 10']},
        ],
    })

    steps = store.get_steps('vlan_config')
    assert len(steps) == 2
    assert steps[0]['step'] == 1


def test_get_steps_nonexistent(store):
    assert store.get_steps('bad_id') == []


def test_get_commands(store):
    store.add({
        'id': 'test_cmd',
        'name': 'Test',
        'category': 'routing',
        'description': 'Test',
        'steps': [
            {'step': 1, 'commands': ['cmd1', 'cmd2']},
            {'step': 2, 'commands': ['cmd3']},
        ],
    })

    cmds = store.get_commands('test_cmd')
    assert cmds == ['cmd1', 'cmd2', 'cmd3']


def test_get_verification(store):
    store.add({
        'id': 'test_verify',
        'name': 'Test Verify',
        'category': 'routing',
        'description': 'Test',
        'steps': [],
        'verification': ['display ospf peer brief', 'display ip routing-table'],
    })

    verify = store.get_verification('test_verify')
    assert len(verify) == 2
    assert 'display ospf peer brief' in verify


def test_get_verification_nonexistent(store):
    assert store.get_verification('bad_id') == []


# ── Update ──────────────────────────────────────────────────────

def test_update(store):
    store.add({
        'id': 'test_update',
        'name': 'Test',
        'category': 'routing',
        'description': 'Old desc',
        'steps': [],
    })

    result = store.update('test_update', {'description': 'New desc', 'note': 'added'})
    assert result['success'] is True

    method = store.get('test_update')
    assert method['description'] == 'New desc'
    assert method['note'] == 'added'


def test_update_nonexistent(store):
    result = store.update('bad_id', {'description': 'test'})
    assert result['success'] is False
    assert '不存在' in result['error']


# ── Record Usage ────────────────────────────────────────────────

def test_record_usage(store):
    store.add({
        'id': 'test_usage',
        'name': 'Usage Test',
        'category': 'routing',
        'description': 'Test',
        'steps': [],
    })

    store.record_usage('test_usage', success=True)
    store.record_usage('test_usage', success=True)
    store.record_usage('test_usage', success=False)

    method = store.get('test_usage')
    assert method['usage_count'] == 3
    assert method['success_rate'] == pytest.approx(2.0 / 3.0, rel=0.1)


def test_record_usage_nonexistent(store):
    """Should not raise when recording usage for non-existent method."""
    store.record_usage('bad_id', success=True)


# ── Categories ──────────────────────────────────────────────────

def test_get_categories(store):
    cats = store.get_categories()
    assert 'routing' in cats
    assert 'switching' in cats
    assert 'security' in cats
    assert 'wireless' in cats
    assert 'services' in cats
    assert 'management' in cats


# ── Add with missing id ─────────────────────────────────────────

def test_add_missing_id(store):
    result = store.add({'name': 'No ID', 'steps': []})
    assert result['success'] is False
    assert 'id' in result['error']