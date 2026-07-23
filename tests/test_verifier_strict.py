# -*- coding: utf-8 -*-
"""第四阶段 Step6: verifier 严格校验测试

验证修复两个永真判定：
1. verify_acl: 严格模式统计实际 rule 数（非仅判字符串）
2. verify_connectivity: ping 丢包率 <= 阈值才通过（默认 0%）
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from agent.verifier import SemanticVerifier


def _make_executor(output_map):
    """构造 mock executor，按命令前缀返回预设 output。"""
    def _exec(device_path, command):
        for prefix, output in output_map.items():
            if command.startswith(prefix):
                return {'success': True, 'output': output}
        return {'success': False, 'output': ''}
    return _exec


# ==================== verify_acl 严格模式 ====================

def test_verify_acl_strict_with_rules():
    """严格模式：输出含实际 rule 行 → 通过。"""
    output = (
        'Advanced ACL 3001, 2 rules\n'
        "ACL's step is 5\n"
        'rule 5 permit ip source 192.168.1.0 0.0.0.255\n'
        'rule 10 deny ip\n'
    )
    v = SemanticVerifier(_make_executor({'display acl': output}))
    v.strict_acl = True
    result = v.verify_acl('dev')
    assert result.passed is True
    assert result.evidence['rule_count'] == 2


def test_verify_acl_strict_no_rules():
    """严格模式：输出无 rule 行（仅表头）→ 不通过（修复永真判定）。"""
    output = 'Advanced ACL 3001, 0 rules\n'  # 0 rules，无实际 rule 行
    v = SemanticVerifier(_make_executor({'display acl': output}))
    v.strict_acl = True
    result = v.verify_acl('dev')
    assert result.passed is False
    assert result.evidence['rule_count'] == 0


def test_verify_acl_strict_header_only_not_pass():
    """严格模式：旧逻辑会误判通过的场景（输出含 'acl' 但无 rule 行）→ 不通过。"""
    output = 'ACL information:\nNo ACL configured.\n'  # 含 'acl' 字符串但无 rule
    v = SemanticVerifier(_make_executor({'display acl': output}))
    v.strict_acl = True
    result = v.verify_acl('dev')
    assert result.passed is False  # 严格模式不再因 'acl' 字符串误判


def test_verify_acl_non_strict_legacy_behavior():
    """非严格模式：回退旧逻辑（含 'acl' 字符串即通过，向后兼容）。"""
    output = 'ACL information:\nNo ACL configured.\n'
    v = SemanticVerifier(_make_executor({'display acl': output}))
    v.strict_acl = False
    result = v.verify_acl('dev')
    assert result.passed is True  # 旧逻辑：含 'acl' 即通过
    assert result.evidence['strict'] is False


def test_verify_acl_default_strict_true():
    """默认 strict_acl=True（严格）。"""
    v = SemanticVerifier(_make_executor({}))
    assert v.strict_acl is True


def test_verify_acl_execution_failure():
    """命令执行失败 → 不通过。"""
    v = SemanticVerifier(lambda p, c: {'success': False, 'output': ''})
    result = v.verify_acl('dev')
    assert result.passed is False


# ==================== verify_connectivity 阈值 ====================

def test_verify_connectivity_zero_loss_pass():
    """0% 丢包 → 通过（默认阈值 0）。"""
    output = 'PING 192.168.1.1: 56 data bytes\n5 packets transmitted, 5 received, 0% packet loss\n'
    v = SemanticVerifier(_make_executor({'ping': output}))
    result = v.verify_connectivity('dev', '192.168.1.1')
    assert result.passed is True
    assert result.evidence['loss_rate'] == 0


def test_verify_connectivity_partial_loss_fail():
    """50% 丢包 → 不通过（默认阈值 0，修复 0%与99%同等对待）。"""
    output = '5 packets transmitted, 2 received, 60% packet loss\n'
    v = SemanticVerifier(_make_executor({'ping': output}))
    result = v.verify_connectivity('dev', '192.168.1.1')
    assert result.passed is False  # 默认阈值 0，60% > 0


def test_verify_connectivity_full_loss_fail():
    """100% 丢包 → 不通过。"""
    output = '5 packets transmitted, 0 received, 100% packet loss\n'
    v = SemanticVerifier(_make_executor({'ping': output}))
    result = v.verify_connectivity('dev', '192.168.1.1')
    assert result.passed is False


def test_verify_connectivity_threshold_configurable():
    """阈值可配置：设为 100 时等价旧逻辑（<100% 即通过，向后兼容）。"""
    output = '5 packets transmitted, 2 received, 60% packet loss\n'
    v = SemanticVerifier(_make_executor({'ping': output}))
    v.ping_loss_threshold = 100  # 旧逻辑
    result = v.verify_connectivity('dev', '192.168.1.1')
    assert result.passed is True  # 60% < 100，旧逻辑通过


def test_verify_connectivity_threshold_50():
    """阈值 50：50% 丢包通过，51% 不通过。"""
    v = SemanticVerifier(_make_executor({
        'ping 50': '5 packets transmitted, 2 received, 50% packet loss\n',
        'ping 51': '5 packets transmitted, 2 received, 51% packet loss\n',
    }))
    v.ping_loss_threshold = 50
    assert v.verify_connectivity('dev', '50').passed is True
    assert v.verify_connectivity('dev', '51').passed is False


def test_verify_connectivity_default_threshold_zero():
    """默认 ping_loss_threshold=0（要求 0% 丢包）。"""
    v = SemanticVerifier(_make_executor({}))
    assert v.ping_loss_threshold == 0


def test_verify_connectivity_execution_failure():
    """ping 命令执行失败 → 不通过。"""
    v = SemanticVerifier(lambda p, c: {'success': False, 'output': ''})
    result = v.verify_connectivity('dev', '192.168.1.1')
    assert result.passed is False


def test_verify_connectivity_no_loss_match_defaults_100():
    """输出无丢包率信息 → 默认 100% 丢包 → 不通过。"""
    output = 'some random output without loss info'
    v = SemanticVerifier(_make_executor({'ping': output}))
    result = v.verify_connectivity('dev', '192.168.1.1')
    assert result.passed is False
    assert result.evidence['loss_rate'] == 100
