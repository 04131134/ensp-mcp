# -*- coding: utf-8 -*-
"""第四阶段 Step8: 统一异常体系测试

验证：
1. 所有异常继承 ENSPError → Exception（向后兼容现有 except Exception）
2. to_dict 序列化、__str__ 可读
3. is_recoverable / classify_exception 辅助函数
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from exceptions import (
    ENSPError, NetworkError, CommandError, ValidationError, KnowledgeError,
    ExecutionError, CapabilityNotSupported, PlanReviewRejected,
    TransactionRollbackFailed, is_recoverable, classify_exception,
)


def test_all_exceptions_inherit_ensp_error():
    """所有自定义异常继承 ENSPError（向后兼容 except Exception）。"""
    for exc_cls in [NetworkError, CommandError, ValidationError, KnowledgeError,
                    ExecutionError, CapabilityNotSupported, PlanReviewRejected,
                    TransactionRollbackFailed]:
        assert issubclass(exc_cls, ENSPError)
        assert issubclass(exc_cls, Exception)  # 向后兼容


def test_ensp_error_caught_by_except_exception():
    """ENSPError 能被现有 except Exception 捕获（向后兼容关键点）。"""
    try:
        raise CommandError('test command failed')
    except Exception as e:
        assert isinstance(e, CommandError)
        assert isinstance(e, ENSPError)


def test_to_dict_serialization():
    """to_dict 返回结构化字典（供 API/日志）。"""
    err = CommandError('命令失败', device_path='127.0.0.1:2000', command='display version')
    d = err.to_dict()
    assert d['error_type'] == 'CommandError'
    assert d['message'] == '命令失败'
    assert d['context']['device_path'] == '127.0.0.1:2000'
    assert d['context']['command'] == 'display version'


def test_str_includes_context():
    """__str__ 包含上下文信息（可读）。"""
    err = NetworkError('连接超时', device_path='127.0.0.1:2000')
    s = str(err)
    assert '连接超时' in s
    assert '127.0.0.1:2000' in s


def test_str_without_context():
    """无上下文时 __str__ 仅返回 message。"""
    err = ENSPError('简单错误')
    assert str(err) == '简单错误'


def test_network_error_attributes():
    err = NetworkError('timeout', device_path='path1')
    assert err.device_path == 'path1'
    assert err.message == 'timeout'


def test_command_error_attributes():
    err = CommandError('fail', device_path='p', command='cmd')
    assert err.device_path == 'p'
    assert err.command == 'cmd'


def test_capability_not_supported_attributes():
    err = CapabilityNotSupported('不支持', model='S3700', protocol='bgp')
    assert err.model == 'S3700'
    assert err.protocol == 'bgp'


def test_plan_review_rejected_attributes():
    issues = [{'severity': 'critical', 'message': 'dangerous'}]
    err = PlanReviewRejected('rejected', issues=issues, score=0.2)
    assert err.issues == issues
    assert err.score == 0.2


def test_is_recoverable_network_command():
    """NetworkError/CommandError 可恢复。"""
    assert is_recoverable(NetworkError('x')) is True
    assert is_recoverable(CommandError('x')) is True


def test_is_recoverable_validation_capability_plan():
    """ValidationError/CapabilityNotSupported/PlanReviewRejected 不可恢复。"""
    assert is_recoverable(ValidationError('x')) is False
    assert is_recoverable(CapabilityNotSupported('x')) is False
    assert is_recoverable(PlanReviewRejected('x')) is False


def test_classify_exception_ensp_error():
    assert classify_exception(NetworkError('x')) == 'NetworkError'
    assert classify_exception(CommandError('x')) == 'CommandError'


def test_classify_exception_builtin():
    """内置异常被分类到标准类型。"""
    assert classify_exception(ConnectionError('x')) == 'NetworkError'
    assert classify_exception(TimeoutError('x')) == 'NetworkError'
    assert classify_exception(ValueError('x')) == 'ValidationError'
    assert classify_exception(KeyError('x')) == 'ValidationError'


def test_classify_exception_unknown():
    """未知异常默认 ExecutionError。"""
    assert classify_exception(RuntimeError('x')) == 'ExecutionError'


def test_empty_context_str():
    """空 context 时 __str__ 仅 message。"""
    err = CommandError('只消息')
    assert str(err) == '只消息'
