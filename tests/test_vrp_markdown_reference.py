# -*- coding: utf-8 -*-
"""验证导入的 VRP Markdown 命令库可被知识库检索。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from knowledge import KnowledgeBase


def _make_kb():
    kb_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'mcpensp1', 'kb')
    return KnowledgeBase(kb_folder=kb_dir)


def test_markdown_reference_is_loaded():
    kb = _make_kb()

    stats = kb.get_markdown_reference_stats()

    assert stats['loaded'] is True
    assert stats['source'] == 'vrp_command_knowledge_agent.md'
    assert stats['section_count'] > 10
    assert stats['command_count'] > 20


def test_markdown_reference_search_returns_ospf_section():
    kb = _make_kb()

    results = kb.search_markdown_reference('ospf')

    assert results
    assert all(result['type'] == 'markdown_reference' for result in results)
    assert any('ospf' in str(result).lower() for result in results)
