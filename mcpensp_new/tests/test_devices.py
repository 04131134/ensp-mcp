# -*- coding: utf-8 -*-
"""Tests for DeviceManager — connection, metadata, topology, scanning."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.devices import DeviceManager
from driver.telnet import TelnetDriver


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def dm():
    return DeviceManager()


# ── Connection CRUD ─────────────────────────────────────────────

def test_empty_state(dm):
    assert dm.list_all() == []
    assert dm.get_driver('127.0.0.1:2000') is None
    assert not dm.has('127.0.0.1:2000')


def test_manual_driver_registration(dm):
    """Test that we can manually inject a driver and query it."""
    driver = TelnetDriver('127.0.0.1', 2000)
    dm._drivers['127.0.0.1:2000'] = driver
    dm._names['127.0.0.1:2000'] = 'TestRouter'
    dm._types['127.0.0.1:2000'] = 'router'

    assert dm.has('127.0.0.1:2000')
    assert dm.get_driver('127.0.0.1:2000') is driver
    assert dm.get_name('127.0.0.1:2000') == 'TestRouter'
    assert dm.get_type('127.0.0.1:2000') == 'router'


def test_disconnect(dm):
    driver = MagicMock()
    dm._drivers['127.0.0.1:2000'] = driver
    dm._names['127.0.0.1:2000'] = 'R1'
    dm._types['127.0.0.1:2000'] = 'router'

    dm.disconnect('127.0.0.1:2000')

    assert not dm.has('127.0.0.1:2000')
    assert dm.get_name('127.0.0.1:2000') == '127.0.0.1:2000'
    assert dm.get_type('127.0.0.1:2000') == 'unknown'
    driver.close.assert_called_once()


def test_disconnect_nonexistent(dm):
    """Disconnecting a non-existent path should not raise."""
    dm.disconnect('127.0.0.1:9999')
    assert not dm.has('127.0.0.1:9999')


# ── Metadata ────────────────────────────────────────────────────

def test_get_name_default(dm):
    assert dm.get_name('127.0.0.1:3000') == '127.0.0.1:3000'


def test_rename(dm):
    dm._names['127.0.0.1:2000'] = 'old'
    dm.rename('127.0.0.1:2000', 'new_name')
    assert dm.get_name('127.0.0.1:2000') == 'new_name'


def test_get_type_default(dm):
    assert dm.get_type('127.0.0.1:3000') == 'unknown'


def test_list_all(dm):
    dm._drivers['127.0.0.1:2000'] = MagicMock()
    dm._drivers['127.0.0.1:2001'] = MagicMock()
    dm._names['127.0.0.1:2000'] = 'R1'
    dm._names['127.0.0.1:2001'] = 'SW1'
    dm._types['127.0.0.1:2000'] = 'router'
    dm._types['127.0.0.1:2001'] = 'switch'

    devices = dm.list_all()
    assert len(devices) == 2
    paths = {d['path'] for d in devices}
    assert '127.0.0.1:2000' in paths
    assert '127.0.0.1:2001' in paths


def test_list_all_with_topo_name(dm):
    dm._drivers['127.0.0.1:2000'] = MagicMock()
    dm.set_topo_name(2000, 'CoreRouter')

    devices = dm.list_all()
    assert devices[0]['name'] == 'CoreRouter'


# ── Topology Names ──────────────────────────────────────────────

def test_topo_names(dm):
    dm.set_topo_name(2000, 'R1')
    dm.set_topo_name(2001, 'SW1')

    assert dm.get_topo_name(2000) == 'R1'
    assert dm.get_topo_name(2001) == 'SW1'
    assert dm.get_topo_name(2999) is None

    all_names = dm.get_topo_names()
    assert all_names == {2000: 'R1', 2001: 'SW1'}


# ── Scanning ────────────────────────────────────────────────────

def test_scan_ports_open():
    dm = DeviceManager()
    with patch('socket.socket') as mock_socket_class:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.connect_ex.return_value = 0  # port open

        ports = dm.scan_ports(2000, 2002)
        assert 2000 in ports
        assert 2001 in ports
        assert 2002 in ports


def test_scan_ports_closed():
    dm = DeviceManager()
    with patch('socket.socket') as mock_socket_class:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.connect_ex.return_value = 1  # port closed

        ports = dm.scan_ports(2000, 2000)
        assert ports == []


def test_scan_devices(dm):
    with patch.object(dm, 'scan_ports', return_value=[2000, 2001]):
        dm._names['127.0.0.1:2000'] = 'R1'
        dm._types['127.0.0.1:2000'] = 'router'

        devices = dm.scan_devices()
        assert len(devices) == 2
        assert devices[0]['port'] == 2000
        assert devices[0]['name'] == 'R1'
        assert devices[0]['device_type'] == 'router'
        assert devices[1]['name'] == '127.0.0.1:2001'


# ── Device Type Detection ───────────────────────────────────────

@pytest.mark.parametrize('name,expected', [
    ('LSW1', 'switch'),
    ('Switch1', 'switch'),
    ('AR1', 'router'),
    ('AR2220', 'router'),
    ('AC1', 'ac'),
    ('AP1', 'ap'),
    ('USG6000', 'firewall'),
    ('FW1', 'firewall'),
    ('PC1', 'pc'),
    ('XyzDevice', 'unknown'),
])
def test_detect_device_type(name, expected):
    assert DeviceManager._detect_device_type(name) == expected


# ── Status Change Callback ──────────────────────────────────────

def test_status_change_callback(dm):
    calls = []

    def cb(path, alive, msg):
        calls.append((path, alive, msg))

    dm.on_status_change(cb)
    dm._on_status_change('127.0.0.1:2000', False, 'R1 已断开')

    assert len(calls) == 1
    assert calls[0] == ('127.0.0.1:2000', False, 'R1 已断开')