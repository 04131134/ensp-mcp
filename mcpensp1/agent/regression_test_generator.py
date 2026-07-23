# -*- coding: utf-8 -*-
"""根据设备能力约束生成真实设备回归测试。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional, Union


class RegressionTestGenerator:
    """将命令约束写成可由 pytest 收集的设备回归测试。"""

    _REQUIRED_FIELDS = ("command_pattern", "device_model", "alternative")

    def __init__(self, output_dir: Optional[Union[str, Path]] = None):
        """初始化生成器。

        参数:
            output_dir: 测试输出目录，默认使用仓库的 tests/regression。
        """
        default_dir = Path(__file__).resolve().parents[2] / "tests" / "regression"
        self._output_dir = Path(output_dir) if output_dir is not None else default_dir

    def generate_test(self, constraint: Mapping[str, Any]) -> str:
        """从设备能力约束生成或更新一份 pytest 回归测试。

        参数:
            constraint: 包含 command_pattern、device_model 和 alternative 的约束。

        返回:
            生成测试文件的绝对路径。
        """
        values = self._validated_values(constraint)
        short_hash = self._short_hash(values)
        device_name = self._to_identifier(values["device_model"])
        command_name = self._to_identifier(values["command_pattern"])
        function_name = f"test_avoid_{command_name}_on_{device_name}"
        target = self._output_dir / f"test_{device_name}_{short_hash}.py"
        source = self._render_test(function_name, values)
        self._atomic_write(target, source)
        return str(target.resolve())

    @classmethod
    def _validated_values(cls, constraint: Mapping[str, Any]) -> Mapping[str, str]:
        """验证并规范化生成测试所需的约束字段。"""
        values = {}
        for field in cls._REQUIRED_FIELDS:
            value = str(constraint.get(field, "")).strip()
            if not value:
                raise ValueError(f"约束缺少必填字段: {field}")
            values[field] = value
        return values

    @staticmethod
    def _to_identifier(value: str) -> str:
        """将设备型号或命令转换为安全、稳定的 Python 标识片段。"""
        identifier = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return identifier[:80] or "command"

    @staticmethod
    def _short_hash(values: Mapping[str, str]) -> str:
        """计算基于规范化约束内容的短哈希。"""
        payload = json.dumps(dict(values), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]

    @staticmethod
    def _render_test(function_name: str, values: Mapping[str, str]) -> str:
        """渲染单文件回归测试源码。"""
        model_literal = repr(values["device_model"])
        command_literal = repr(values["command_pattern"])
        alternative_literal = repr(values["alternative"])
        docstring_literal = repr(
            f"验证 {values['device_model']} 不使用受限命令；替代建议: {values['alternative']}"
        )
        return f'''# -*- coding: utf-8 -*-
"""由 RegressionTestGenerator 自动生成的真实设备回归测试。"""
import pytest

from app import send_command


DEVICE_MODEL = {model_literal}
ORIGINAL_COMMAND = {command_literal}
ALTERNATIVE_COMMAND = {alternative_literal}


@pytest.mark.regression_device
@pytest.mark.parametrize("device_fixture", [DEVICE_MODEL], indirect=True)
def {function_name}(device_fixture):
    {docstring_literal}
    original_result = send_command(device_fixture, ORIGINAL_COMMAND)
    assert original_result.get("success") is True, original_result.get("error")
    assert original_result.get("cmd_success") is False, original_result.get("output")

    alternative_result = send_command(device_fixture, ALTERNATIVE_COMMAND)
    assert alternative_result.get("success") is True, alternative_result.get("error")
    assert alternative_result.get("cmd_success") is True, alternative_result.get("output")
'''

    @staticmethod
    def _atomic_write(target: Path, source: str) -> None:
        """原子写入测试文件，避免生成过程留下半截源码。"""
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            dir=str(target.parent), suffix=".tmp", text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                file.write(source)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, target)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise
