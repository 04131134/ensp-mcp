# -*- coding: utf-8 -*-
"""知识库视图分类修复验证测试。

验证：
1. system_view 不再为空（有配置命令）
2. user_view 仍然只有 display/ping/save 查看命令
3. suggest_commands 按 view_type 正确过滤
4. _flatten_commands 型号匹配（含 FW1→USG6000V 别名）
5. structured KB 可正确加载
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from knowledge import KnowledgeBase


def _make_kb():
    """构造 KnowledgeBase 加载结构化 KB。"""
    kb_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'mcpensp1', 'kb')
    kb = KnowledgeBase(kb_folder=kb_dir)
    return kb


def test_system_view_not_empty():
    """system_view 有配置命令（修复后不应为空）。"""
    kb = _make_kb()
    cmds = kb._flatten_commands('system_view')
    assert len(cmds) > 0, 'system_view 不应为空'
    # 应至少包含 vlan/interface/ospf 等配置命令
    cmd_texts = ' '.join(c.get('cmd', '') for c in cmds)
    assert 'vlan' in cmd_texts.lower()


def test_user_view_only_display_commands():
    """user_view 只有查看命令，不含配置命令。"""
    kb = _make_kb()
    cmds = kb._flatten_commands('user_view')
    assert len(cmds) > 0, 'user_view 不应为空'
    # 检查所有命令都是 display/ping/save/telnet 等查看类
    for c in cmds:
        cmd = c.get('cmd', '').lower().strip()
        is_display = cmd.startswith('display') or cmd.startswith('show')
        is_ping = cmd.startswith('ping')
        is_other = cmd in ('save', 'quit', 'return', 'telnet', 'tracert')
        if not (is_display or is_ping or is_other):
            # system-view 属于切换命令，允许在 user_view
            if 'system-view' not in cmd:
                assert False, f'user_view 不应含配置命令: {cmd}'


def test_suggest_commands_system_view_has_config():
    """suggest_commands system_view 返回配置命令（非 display 类）。"""
    kb = _make_kb()
    result = kb.suggest_commands('S5700', view_type='system_view')
    cmds = result.get('system_view', [])
    assert len(cmds) > 0, 'S5700 system_view 应有配置命令'
    # 配置命令不应全是 display 开头
    non_display = [c for c in cmds if not c.get('cmd', '').startswith('display')]
    assert len(non_display) > 0, 'system_view 应含非 display 的配置命令'


def test_suggest_commands_user_view_no_config():
    """suggest_commands user_view 不返回配置命令（vlan/interface/ospf 等）。"""
    kb = _make_kb()
    result = kb.suggest_commands('S5700', view_type='user_view')
    cmds = result.get('user_view', [])
    for c in cmds:
        cmd = c.get('cmd', '').lower()
        # 配置命令关键词不应出现在 user_view
        for config_keyword in ('vlan', 'interface', 'ospf', 'bgp', 'acl', 'nat', 'stp'):
            if config_keyword in cmd and not cmd.startswith('display'):
                assert False, f'user_view 不应含配置命令: {cmd}'


def test_flatten_commands_fw1_alias_mapping():
    """_flatten_commands FW1 别名映射到 USG6000V。"""
    kb = _make_kb()
    cmds = kb._flatten_commands('system_view', 'FW1')
    # FW1→USG6000V，应返回防火墙的 system_view 命令
    assert len(cmds) > 0, 'FW1 别名应映射到 USG6000V'
    models = set(c.get('model', '') for c in cmds)
    assert 'USG6000V' in models or any('USG' in m for m in models)


def test_flatten_commands_s3700_no_filter_returns_all():
    """_flatten_commands 无型号过滤时返回所有设备命令。"""
    kb = _make_kb()
    cmds = kb._flatten_commands('system_view')
    models = set(c.get('model', '') for c in cmds)
    assert len(models) >= 5, f'应覆盖 5 种设备型号，实际 {len(models)}'


def test_structured_kb_loads_without_error():
    """structured KB 可正确加载。"""
    kb = _make_kb()
    skb = kb._skb_cache
    assert skb is not None
    assert 'views' in skb
    assert 'user_view' in skb['views']
    assert 'system_view' in skb['views']
