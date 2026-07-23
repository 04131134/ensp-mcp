# -*- coding: utf-8 -*-
"""RegressionTestGenerator 和真实设备夹具的测试。"""
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpensp1"))

from agent.regression_test_generator import RegressionTestGenerator


CONSTRAINT = {
    "command_pattern": "display wlan ap all",
    "device_model": "AC6005",
    "alternative": "display ap all",
}


def _load_regression_conftest():
    """以独立模块方式加载真实设备回归测试夹具。"""
    path = Path(__file__).parent / "regression" / "conftest.py"
    specification = importlib.util.spec_from_file_location("regression_conftest", path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_generate_test_writes_compilable_sanitized_test(tmp_path):
    """生成代码应使用稳定命名、所需夹具和命令级断言。"""
    path = Path(RegressionTestGenerator(tmp_path).generate_test(CONSTRAINT))
    source = path.read_text(encoding="utf-8")

    assert path.name == "test_ac6005_ebbddb4a.py"
    assert "def test_avoid_display_wlan_ap_all_on_ac6005" in source
    assert "from app import send_command" in source
    assert "indirect=True" in source
    assert "display wlan ap all" in source
    assert "display ap all" in source
    assert 'get("cmd_success") is False' in source
    assert 'get("cmd_success") is True' in source
    compile(source, str(path), "exec")


@pytest.mark.parametrize("field", ["command_pattern", "device_model", "alternative"])
def test_generate_test_rejects_missing_required_constraint_field(tmp_path, field):
    """缺失任一必填约束字段时应拒绝生成不可执行测试。"""
    constraint = dict(CONSTRAINT)
    constraint[field] = ""

    with pytest.raises(ValueError, match=field):
        RegressionTestGenerator(tmp_path).generate_test(constraint)


def test_generate_test_is_idempotent(tmp_path):
    """同一约束重复生成应覆盖同一路径而不新增测试文件。"""
    generator = RegressionTestGenerator(tmp_path)
    first = generator.generate_test(CONSTRAINT)
    second = generator.generate_test(CONSTRAINT)

    assert first == second
    assert len(list(tmp_path.glob("test_*.py"))) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_device_fixture_skips_without_environment_variable(monkeypatch):
    """未配置型号路径时共享夹具应跳过真实设备测试。"""
    module = _load_regression_conftest()
    monkeypatch.delenv("ENSP_REGRESSION_AC6005_PATH", raising=False)
    request = types.SimpleNamespace(param="AC6005")

    with pytest.raises(pytest.skip.Exception):
        module.device_fixture.__wrapped__(request)


def test_device_fixture_rejects_invalid_path(monkeypatch):
    """显式配置的非本地 Telnet 路径应快速失败。"""
    module = _load_regression_conftest()
    monkeypatch.setenv("ENSP_REGRESSION_AC6005_PATH", "invalid-path")
    request = types.SimpleNamespace(param="AC6005")

    with pytest.raises(pytest.fail.Exception):
        module.device_fixture.__wrapped__(request)


def test_device_fixture_connects_configured_local_device(monkeypatch):
    """夹具应把环境变量端口交给应用层连接函数并返回连接路径。"""
    module = _load_regression_conftest()
    calls = []

    def connect_device(port):
        calls.append(port)
        return {"success": True, "path": "127.0.0.1:2001"}

    monkeypatch.setenv("ENSP_REGRESSION_AC6005_PATH", "127.0.0.1:2001")
    monkeypatch.setitem(sys.modules, "app", types.SimpleNamespace(connect_device=connect_device))
    request = types.SimpleNamespace(param="AC6005")

    assert module.device_fixture.__wrapped__(request) == "127.0.0.1:2001"
    assert calls == [2001]
