# -*- coding: utf-8 -*-
"""ErrorClassifier 的规则分类测试。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpensp1"))

from agent.error_library import ErrorClassifier


DEVICE_INFO = {
    "model": "AR2220",
    "role": "router",
    "software_version": "V200R003",
}


@pytest.mark.parametrize(
    ("output", "expected_type"),
    [
        ("Error: Unrecognized command found at '^' position.", "syntax_error"),
        ("Error: Wrong parameter found at '^' position.", "syntax_error"),
        ("The configuration already exists.", "config_conflict"),
        ("Configuration conflict detected.", "config_conflict"),
        ("---- More ----", "environment_issue"),
        ("Connection timed out", "environment_issue"),
        ("Press any key to continue", "environment_issue"),
        ("Error: Timeout", "environment_issue"),
    ],
)
def test_classify_known_output_rules(output, expected_type):
    """已知输出应命中对应的规则分类。"""
    result = ErrorClassifier().classify(DEVICE_INFO, "display version", output, "user-view")

    assert result["error_type"] == expected_type
    assert 0 <= result["confidence"] <= 1
    assert result["raw_output_summary"] == output[:200]
    assert "constraint" not in result


def test_classify_incomplete_configuration_command_in_wrong_view():
    """配置命令在用户视图不完整时应判定为视图错误。"""
    result = ErrorClassifier().classify(
        DEVICE_INFO, "interface", "Error: Incomplete command", "<AR1>"
    )

    assert result["error_type"] == "context_error"


def test_classify_incomplete_command_in_expected_view_is_not_context_error():
    """位于配置视图的不完整命令不应被误判为视图错误。"""
    result = ErrorClassifier().classify(
        DEVICE_INFO, "interface", "Error: Incomplete command", "[AR1]"
    )

    assert result["error_type"] == "planning_error"
    assert result["confidence"] == 0.4


def test_classify_device_not_supported_creates_constraint():
    """设备不支持命令时应生成包含替代建议的约束记录。"""
    result = ErrorClassifier().classify(
        DEVICE_INFO,
        "wlan ap-group name office",
        "This feature is not supported on this device.",
        "system-view",
    )

    assert result["error_type"] == "device_not_supported"
    assert result["constraint"] == {
        "command_pattern": "wlan ap-group name office",
        "alternative": "查询 AR2220（router） 支持的等价命令或改用支持该特性的设备。",
    }


def test_classify_unknown_output_is_planning_error_and_truncates_summary():
    """未知错误回退为计划错误，并限制原始输出摘要长度。"""
    output = "x" * 250
    result = ErrorClassifier().classify(DEVICE_INFO, "display version", output, "user-view")

    assert result["error_type"] == "planning_error"
    assert result["confidence"] == 0.4
    assert result["raw_output_summary"] == "x" * 200
