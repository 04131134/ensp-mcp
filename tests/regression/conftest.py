# -*- coding: utf-8 -*-
"""自动生成的真实设备回归测试共享夹具。"""
import os
import re
from typing import Any

import pytest


def _environment_name(device_model: str) -> str:
    """生成设备路径环境变量名称。"""
    model = re.sub(r"[^A-Za-z0-9]+", "_", device_model).strip("_").upper()
    return f"ENSP_REGRESSION_{model}_PATH"


@pytest.fixture
def device_fixture(request: Any) -> str:
    """连接参数化设备型号对应的 eNSP Telnet 设备并返回设备路径。"""
    device_model = str(request.param)
    variable_name = _environment_name(device_model)
    device_path = os.environ.get(variable_name, "").strip()
    if not device_path:
        pytest.skip(f"未设置真实设备路径环境变量: {variable_name}")

    host, separator, port_text = device_path.rpartition(":")
    if host != "127.0.0.1" or not separator or not port_text.isdigit():
        pytest.fail(f"{variable_name} 必须为 127.0.0.1:<Telnet端口>")
    port = int(port_text)
    if not 1 <= port <= 65535:
        pytest.fail(f"{variable_name} 的 Telnet 端口无效")

    from app import connect_device

    result = connect_device(port)
    if not result.get("success"):
        pytest.fail(f"无法连接 {device_model}: {result.get('error', '未知错误')}")
    return str(result["path"])
