# -*- coding: utf-8 -*-
"""第三阶段 Step7：接口映射自动推理测试

覆盖工作记忆铁律：
- S5700/S3700/AC6605 盒式设备：srcIndex=N → G0/0/(N+1)（端口 1 起始）
- AR3260/USG6000V 子卡设备：srcIndex=N → G0/0/N（端口 0 起始）
- 永远不信任 .topo 的 srcIndex，下接口命令前必跑 display interface brief
"""
import os
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))

from interface_resolver import (
    build_interface_map, resolve_interface, InterfaceResolver,
    _is_module_model, _is_box_model,
)


def _make_dev_element(interfacename='GE', count=24, model='S5700'):
    """构造模拟的 .topo <dev> XML 元素。"""
    dev = ET.Element('dev', id='1', model=model)
    slot = ET.SubElement(dev, 'slot')
    ET.SubElement(slot, 'interface', interfacename=interfacename, count=str(count))
    return dev


# ==================== 盒式设备（端口 1 起始）====================

def test_build_map_box_s5700():
    """S5700 盒式：srcIndex=0 → G0/0/1，端口 1 起始。"""
    dev = _make_dev_element('GE', 24, 'S5700')
    iface_map = build_interface_map(dev, 'S5700')
    assert iface_map[0] == 'GE0/0/1'
    assert iface_map[1] == 'GE0/0/2'
    assert iface_map[23] == 'GE0/0/24'


def test_build_map_box_s3700():
    """S3700 盒式：Eth 接口，端口 1 起始。"""
    dev = _make_dev_element('Eth', 24, 'S3700')
    iface_map = build_interface_map(dev, 'S3700')
    assert iface_map[0] == 'Eth0/0/1'
    assert iface_map[23] == 'Eth0/0/24'


def test_build_map_box_ac6605():
    """AC6605 盒式：端口 1 起始。"""
    dev = _make_dev_element('GE', 24, 'AC6605')
    iface_map = build_interface_map(dev, 'AC6605')
    assert iface_map[0] == 'GE0/0/1'


# ==================== 子卡设备（端口 0 起始）====================

def test_build_map_module_ar3260():
    """AR3260 子卡：srcIndex=0 → G0/0/0，端口 0 起始（工作记忆铁律）。"""
    dev = _make_dev_element('GE', 8, 'AR3260')
    iface_map = build_interface_map(dev, 'AR3260')
    assert iface_map[0] == 'GE0/0/0'
    assert iface_map[1] == 'GE0/0/1'
    assert iface_map[7] == 'GE0/0/7'


def test_build_map_module_usg6000v():
    """USG6000V 子卡：端口 0 起始。"""
    dev = _make_dev_element('GE', 4, 'USG6000V')
    iface_map = build_interface_map(dev, 'USG6000V')
    assert iface_map[0] == 'GE0/0/0'
    assert iface_map[3] == 'GE0/0/3'


def test_build_map_module_ar2220():
    """AR2220 子卡：端口 0 起始。"""
    dev = _make_dev_element('GE', 8, 'AR2220')
    iface_map = build_interface_map(dev, 'AR2220')
    assert iface_map[0] == 'GE0/0/0'


# ==================== 向后兼容（model=None 默认盒式）====================

def test_build_map_model_none_defaults_box():
    """model=None 时默认盒式（1 起始），向后兼容旧 _build_interface_map 行为。"""
    dev = _make_dev_element('GE', 24, 'unknown')
    iface_map = build_interface_map(dev, None)
    assert iface_map[0] == 'GE0/0/1'  # 默认盒式


def test_build_map_box_vs_module_difference():
    """盒式与子卡对同一 srcIndex 产生不同接口名（核心修复点）。"""
    dev = _make_dev_element('GE', 4, 'X')
    box_map = build_interface_map(dev, 'S5700')
    module_map = build_interface_map(dev, 'AR3260')
    assert box_map[0] == 'GE0/0/1'    # 盒式 1 起始
    assert module_map[0] == 'GE0/0/0'  # 子卡 0 起始
    assert box_map[0] != module_map[0]


# ==================== resolve_interface 查表与回退 ====================

def test_resolve_interface_found():
    iface_map = {0: 'GE0/0/1', 1: 'GE0/0/2'}
    assert resolve_interface(iface_map, 0) == 'GE0/0/1'


def test_resolve_interface_not_found_fallback():
    iface_map = {0: 'GE0/0/1'}
    assert resolve_interface(iface_map, 99) == 'Index99'


def test_resolve_interface_invalid_index():
    iface_map = {0: 'GE0/0/1'}
    assert resolve_interface(iface_map, 'abc') == 'Indexabc'


def test_resolve_interface_none_index():
    iface_map = {0: 'GE0/0/1'}
    assert resolve_interface(iface_map, None) == 'IndexNone'


# ==================== 型号判定 ====================

def test_is_module_model_ar_usg():
    assert _is_module_model('AR3260') is True
    assert _is_module_model('AR2220') is True
    assert _is_module_model('USG6000V') is True


def test_is_module_model_switch_is_false():
    assert _is_module_model('S5700') is False
    assert _is_module_model('AC6605') is False


def test_is_module_model_none_empty():
    assert _is_module_model(None) is False
    assert _is_module_model('') is False


def test_is_box_model_switch_ac():
    assert _is_box_model('S5700') is True
    assert _is_box_model('S3700') is True
    assert _is_box_model('AC6605') is True


def test_is_box_model_none_defaults_true():
    assert _is_box_model(None) is True
    assert _is_box_model('') is True


def test_is_box_model_router_is_false():
    assert _is_box_model('AR3260') is False
    assert _is_box_model('USG6000V') is False


# ==================== InterfaceResolver 类 ====================

def test_resolver_verify_no_executor_returns_none():
    """未注入 executor 时，verify_by_display 返回 None（.topo 解析时设备未连）。"""
    resolver = InterfaceResolver()
    assert resolver.verify_by_display('127.0.0.1:2000', 'GE0/0/1') is None


def test_resolver_verify_no_device_path_returns_none():
    """无 device_path 时返回 None。"""
    def mock_exec(path, cmd):
        return {'output': 'GE0/0/1'}
    resolver = InterfaceResolver(mock_exec)
    assert resolver.verify_by_display('', 'GE0/0/1') is None


def test_resolver_verify_with_mock_executor_hit():
    """注入 mock executor，接口存在 → True。"""
    def mock_exec(path, cmd):
        return {'output': 'Interface                     Phy   Protocol  Description\nGE0/0/1  up    up'}
    resolver = InterfaceResolver(mock_exec)
    assert resolver.verify_by_display('127.0.0.1:2000', 'GE0/0/1') is True


def test_resolver_verify_with_mock_executor_miss():
    """注入 mock executor，接口不存在 → False。"""
    def mock_exec(path, cmd):
        return {'output': 'GE0/0/0  up    up'}
    resolver = InterfaceResolver(mock_exec)
    assert resolver.verify_by_display('127.0.0.1:2000', 'GE0/0/99') is False


def test_resolver_verify_executor_exception_returns_none():
    """executor 异常时返回 None（不破坏流程）。"""
    def mock_exec(path, cmd):
        raise RuntimeError('connection lost')
    resolver = InterfaceResolver(mock_exec)
    assert resolver.verify_by_display('127.0.0.1:2000', 'GE0/0/1') is None


def test_resolver_resolve_with_verification_rule():
    """多源推理：规则映射成功，source='rule'。"""
    dev = _make_dev_element('GE', 24, 'S5700')
    resolver = InterfaceResolver()
    result = resolver.resolve_with_verification(dev, 'S5700', 0)
    assert result['interface'] == 'GE0/0/1'
    assert result['source'] == 'rule'
    assert result['is_module'] is False
    assert result['verified'] is None  # 未注入 executor


def test_resolver_resolve_with_verification_module():
    """多源推理：子卡设备 srcIndex=0 → G0/0/0。"""
    dev = _make_dev_element('GE', 8, 'AR3260')
    resolver = InterfaceResolver()
    result = resolver.resolve_with_verification(dev, 'AR3260', 0)
    assert result['interface'] == 'GE0/0/0'
    assert result['is_module'] is True


def test_resolver_resolve_with_verification_fallback():
    """多源推理：查不到回退 Index{index}，source='fallback'。"""
    dev = _make_dev_element('GE', 2, 'S5700')
    resolver = InterfaceResolver()
    result = resolver.resolve_with_verification(dev, 'S5700', 99)
    assert result['interface'] == 'Index99'
    assert result['source'] == 'fallback'


def test_resolver_resolve_with_verification_display():
    """多源推理：注入 executor 时进行 display 校验。"""
    dev = _make_dev_element('GE', 8, 'AR3260')
    def mock_exec(path, cmd):
        return {'output': 'GE0/0/0  up    up'}
    resolver = InterfaceResolver(mock_exec)
    result = resolver.resolve_with_verification(dev, 'AR3260', 0, device_path='127.0.0.1:2000')
    assert result['interface'] == 'GE0/0/0'
    assert result['verified'] is True


# ==================== 多接口类型混合 ====================

def test_build_map_multiple_interface_types():
    """设备含多种接口类型（GE + Eth）时分别计数。"""
    dev = ET.Element('dev', id='1', model='S5700')
    slot = ET.SubElement(dev, 'slot')
    ET.SubElement(slot, 'interface', interfacename='GE', count='2')
    ET.SubElement(slot, 'interface', interfacename='Eth', count='2')
    iface_map = build_interface_map(dev, 'S5700')
    # GE: 0→GE0/0/1, 1→GE0/0/2; Eth: 2→Eth0/0/1, 3→Eth0/0/2
    assert iface_map[0] == 'GE0/0/1'
    assert iface_map[1] == 'GE0/0/2'
    assert iface_map[2] == 'Eth0/0/1'
    assert iface_map[3] == 'Eth0/0/2'
