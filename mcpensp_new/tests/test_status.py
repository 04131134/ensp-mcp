# -*- coding: utf-8 -*-
"""Tests for StatusMonitor — device health probing."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.devices import DeviceManager
from core.status import DeviceStatus, StatusMonitor


@pytest.fixture
def dm():
    devices = DeviceManager()
    driver = MagicMock()
    driver.is_alive.return_value = True
    devices._drivers['127.0.0.1:2000'] = driver
    devices._names['127.0.0.1:2000'] = 'Router1'
    devices._types['127.0.0.1:2000'] = 'router'

    driver2 = MagicMock()
    driver2.is_alive.return_value = False
    devices._drivers['127.0.0.1:2001'] = driver2
    devices._names['127.0.0.1:2001'] = 'Switch1'
    devices._types['127.0.0.1:2001'] = 'switch'

    return devices


@pytest.fixture
def monitor(dm):
    return StatusMonitor(dm)


def test_device_status_dataclass():
    s = DeviceStatus(
        path='127.0.0.1:2000',
        name='R1',
        device_type='router',
        tcp_alive=True,
        session_alive=True,
        checked_at='2025-01-01T00:00:00',
    )
    assert s.path == '127.0.0.1:2000'
    assert s.tcp_alive is True
    assert s.session_alive is True


def test_check_one_alive(monitor):
    status = monitor.check_one('127.0.0.1:2000')
    assert status is not None
    assert status.tcp_alive is True
    assert status.name == 'Router1'


def test_check_one_dead(monitor):
    status = monitor.check_one('127.0.0.1:2001')
    assert status is not None
    assert status.tcp_alive is False
    assert status.name == 'Switch1'


def test_check_one_not_registered(monitor):
    status = monitor.check_one('127.0.0.1:9999')
    assert status is None


def test_check_all(monitor):
    results = monitor.check_all()
    assert len(results) == 2
    paths = {r['path'] for r in results}
    assert '127.0.0.1:2000' in paths
    assert '127.0.0.1:2001' in paths


def test_summary(monitor):
    s = monitor.summary()
    assert s['total'] == 2
    assert s['tcp_alive'] == 1
    assert s['session_alive'] == 1
    assert s['has_dead_devices'] is True
    assert 'checked_at' in s
    assert len(s['devices']) == 2


def test_check_all_empty():
    dm = DeviceManager()
    monitor = StatusMonitor(dm)
    assert monitor.check_all() == []


def test_summary_empty():
    dm = DeviceManager()
    monitor = StatusMonitor(dm)
    s = monitor.summary()
    assert s['total'] == 0
    assert s['tcp_alive'] == 0
    assert s['has_dead_devices'] is False
