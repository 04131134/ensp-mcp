# -*- coding: utf-8 -*-
"""Tests for KnowledgeService — CRUD, search, stats, JSONL persistence."""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from core.knowledge import KnowledgeEntry, KnowledgeService


@pytest.fixture
def kb_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def knowledge(kb_dir):
    return KnowledgeService(kb_dir)


def test_empty_kb(knowledge):
    stats = knowledge.get_stats()
    assert stats['total'] == 0


def test_add_and_search(knowledge):
    entry = KnowledgeEntry(
        category='command',
        title='system-view',
        content={'description': '进入系统视图'},
        device_type='huawei',
        tags=['config', 'huawei'],
        success=True,
        command='system-view',
        output_preview='System view successfully',
        risk='safe',
        use_count=10,
        confidence=0.95,
    )
    knowledge.add(entry)

    results = knowledge.search(query='系统视图')
    assert len(results) >= 1
    assert results[0].title == 'system-view'

    stats = knowledge.get_stats()
    assert stats['total'] >= 1


def test_search_by_category(knowledge):
    knowledge.add(KnowledgeEntry(category='command', title='cmd1', tags=['t']))
    knowledge.add(KnowledgeEntry(category='experience', title='exp1', tags=['t']))

    results = knowledge.search(category='experience')
    assert all(r.category == 'experience' for r in results)


def test_search_by_device_type(knowledge):
    knowledge.add(KnowledgeEntry(category='command', title='c1',
                                 device_type='huawei', tags=['t']))
    knowledge.add(KnowledgeEntry(category='command', title='c2',
                                 device_type='cisco', tags=['t']))

    results = knowledge.search(device_type='huawei')
    assert all(r.device_type == 'huawei' for r in results)


def test_record_command(knowledge):
    from driver.telnet import CommandResult
    result = CommandResult(output='display version output...',
                           success=True, elapsed_ms=100.0)
    knowledge.record_command('display version', result,
                             '127.0.0.1:2000', 'huawei')

    results = knowledge.search(query='display version')
    assert len(results) >= 1
    assert results[0].success is True


def test_record_experience(knowledge):
    r = knowledge.record_experience(
        experiment='测试OSPF',
        commands=['system-view', 'ospf 1', 'router-id 1.1.1.1'],
        success=True,
        lessons=['OSPF配置成功', '注意router-id唯一性'],
        device_type='huawei',
    )
    assert r['success'] is True

    results = knowledge.search(query='OSPF')
    assert len(results) >= 1


def test_get_config_guidance(knowledge):
    knowledge.record_experience(
        experiment='OSPF配置实验',
        commands=['system-view', 'ospf 1', 'router-id 1.1.1.1',
                   'area 0', 'network 192.168.1.0 0.0.0.255'],
        success=True,
        lessons=['Area 0必须先配置'],
        device_type='huawei',
    )

    guidance = knowledge.get_config_guidance('OSPF')
    assert guidance['topic'] == 'OSPF'
    assert len(guidance['experiences']) >= 1


def test_persistence_across_instances(kb_dir):
    k1 = KnowledgeService(kb_dir)
    k1.record_experience('持久化测试', ['system-view'], True, device_type='huawei')

    k2 = KnowledgeService(kb_dir)
    results = k2.search(query='持久化')
    assert len(results) >= 1
