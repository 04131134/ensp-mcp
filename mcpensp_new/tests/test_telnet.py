# -*- coding: utf-8 -*-
"""Tests for TelnetDriver — prompt detection, command classification, error extraction."""
from __future__ import annotations

import asyncio
import socket
import time
from unittest.mock import MagicMock, patch

import pytest

from driver.telnet import (
    CommandResult,
    SocketTransport,
    TelnetDriver,
    _extract_errors,
)


# ── Mock Transport ─────────────────────────────────────────────

class MockTransport:
    """Controllable transport for testing TelnetDriver logic.

    Supports two-phase operation:
    - Phase 1 (flush): returns empty data / timeouts until flush_done is set
    - Phase 2 (command): returns actual response data
    """

    def __init__(self, responses: list[bytes] | None = None):
        self._responses = responses or []
        self._idx = 0
        self._sent: list[bytes] = []
        self._timeout = 10.0
        self._closed = False
        self._flush_done = False

    def connect(self, host: str, port: int) -> None:
        pass

    def send(self, data: bytes) -> None:
        self._sent.append(data)
        # After the first command is sent, activate actual response mode
        self._flush_done = True

    def recv(self, bufsize: int) -> bytes:
        if not self._flush_done:
            raise socket.timeout('flush phase')
        if self._idx < len(self._responses):
            data = self._responses[self._idx]
            self._idx += 1
            return data
        raise socket.timeout('no more data')

    def close(self) -> None:
        self._closed = True

    def settimeout(self, timeout: float) -> None:
        self._timeout = timeout

    def gettimeout(self) -> float | None:
        return self._timeout

    @property
    def sent_commands(self) -> list[str]:
        return [d.decode('utf-8', errors='ignore').strip()
                for d in self._sent if b'\r\n' in d]


# ── Prompt Detection ───────────────────────────────────────────

def test_prompt_detection_huawei_user_view():
    driver = TelnetDriver('127.0.0.1', 2000, transport=MockTransport())
    assert driver._has_prompt(b'<Huawei>')
    assert driver._has_prompt(b'extra text\r\n<Huawei>')
    assert driver._has_prompt(b'<R1>')
    # Should NOT match if no angle bracket
    assert not driver._has_prompt(b'plain text')


def test_prompt_detection_huawei_system_view():
    driver = TelnetDriver('127.0.0.1', 2000, transport=MockTransport())
    assert driver._has_prompt(b'[Huawei]')
    assert driver._has_prompt(b'[R1-GigabitEthernet0/0/1]')
    assert driver._has_prompt(b'text\r\n[Huawei]')


def test_prompt_detection_cisco():
    driver = TelnetDriver('127.0.0.1', 2000, transport=MockTransport())
    assert driver._has_prompt(b'Router>')
    assert driver._has_prompt(b'Router(config)#')
    assert driver._has_prompt(b'Router(config-if)#')


def test_prompt_detection_multiline():
    driver = TelnetDriver('127.0.0.1', 2000, transport=MockTransport())
    data = b'GigabitEthernet0/0/1 current state : UP\r\nLine protocol current state : UP\r\n<Huawei>'
    assert driver._has_prompt(data)


# ── Command Classification ─────────────────────────────────────

def test_classify_display():
    assert TelnetDriver._classify_cmd('display version') == 'display'
    assert TelnetDriver._classify_cmd('display current-configuration') == 'display'
    assert TelnetDriver._classify_cmd('dir') == 'display'


def test_classify_diag():
    assert TelnetDriver._classify_cmd('ping 192.168.1.1') == 'diag'
    assert TelnetDriver._classify_cmd('tracert 10.0.0.1') == 'diag'


def test_classify_interactive():
    assert TelnetDriver._classify_cmd('save') == 'interactive'
    assert TelnetDriver._classify_cmd('reboot') == 'interactive'


def test_classify_config():
    assert TelnetDriver._classify_cmd('system-view') == 'config'
    assert TelnetDriver._classify_cmd('ospf 1') == 'config'
    assert TelnetDriver._classify_cmd('vlan 10') == 'config'


# ── Error Extraction ───────────────────────────────────────────

def test_extract_errors_display_never_error():
    """display commands are never classified as errors."""
    output = 'Error: Something went wrong'
    errors = _extract_errors(output, 'display version')
    assert errors == []


def test_extract_errors_config_command():
    output = 'Error: Unrecognized command found at ^ position.'
    errors = _extract_errors(output, 'system-view')
    assert len(errors) > 0
    assert 'Unrecognized command' in errors[0]


def test_extract_errors_cisco_ios():
    output = '% Incomplete command.'
    errors = _extract_errors(output, 'interface')
    assert len(errors) > 0
    assert '% Incomplete' in errors[0]


def test_extract_errors_no_error():
    output = 'Info: Interface GigabitEthernet0/0/1 has been configured.'
    errors = _extract_errors(output, 'ip address 192.168.1.1 255.255.255.0')
    assert errors == []


# ── Command Execute (with Mock) ─────────────────────────────────

_HUAWEI_VERSION_RESPONSE = [
    b'\r\ndisplay version\r\n',
    b'Huawei Versatile Routing Platform Software\r\n',
    b'VRP (R) software, Version 5.170 (S5700 V200R019C00SPC500)\r\n',
    b'Copyright (C) 2000-2020 HUAWEI TECH CO., LTD\r\n',
    b'<Huawei>',
]

_HUAWEI_ERROR_RESPONSE = [
    b'\r\nospf 1\r\n',
    b'                      ^\r\n',
    b'Error: Unrecognized command found at \'^\' position.\r\n',
    b'<Huawei>',
]


def test_execute_success():
    transport = MockTransport(responses=_HUAWEI_VERSION_RESPONSE.copy())
    driver = TelnetDriver('127.0.0.1', 2000, transport=transport)

    _t = [0.0]
    def fake_time():
        _t[0] += 0.05
        return _t[0]

    with patch('time.sleep', return_value=None), \
         patch('time.time', side_effect=fake_time):
        result = driver.execute('display version')

    assert result.success is True
    assert 'Huawei Versatile Routing Platform' in result.output
    assert len(result.errors) == 0


def test_execute_failure():
    transport = MockTransport(responses=_HUAWEI_ERROR_RESPONSE.copy())
    driver = TelnetDriver('127.0.0.1', 2000, transport=transport)

    _t = [0.0]
    def fake_time():
        _t[0] += 0.05
        return _t[0]

    with patch('time.sleep', return_value=None), \
         patch('time.time', side_effect=fake_time):
        result = driver.execute('ospf 1')

    assert result.success is False
    assert len(result.errors) > 0
    assert 'Unrecognized command' in str(result.errors)


# ── is_alive ───────────────────────────────────────────────────

def test_is_alive_prompt_detected():
    driver = TelnetDriver('127.0.0.1', 2000)
    with patch('socket.socket') as mock_socket_class:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.recv.side_effect = [
            b'Welcome message\r\n',
            socket.timeout(),
            b'<Huawei>',
        ]

        # We need to handle the probe socket that's created inside is_alive
        with patch('driver.telnet.socket.socket', return_value=mock_sock):
            with patch('time.sleep', return_value=None):
                result = driver.is_alive(timeout=1.0)
                assert result is True


def test_is_alive_connection_refused():
    driver = TelnetDriver('127.0.0.1', 2000)
    with patch('socket.socket') as mock_socket_class:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.connect.side_effect = ConnectionRefusedError()

        with patch('driver.telnet.socket.socket', return_value=mock_sock):
            result = driver.is_alive(timeout=1.0)
            assert result is False


# ── CommandResult dataclass ─────────────────────────────────────

def test_command_result():
    r = CommandResult(output='test output', success=True, elapsed_ms=123.4)
    assert r.output == 'test output'
    assert r.success is True
    assert r.elapsed_ms == 123.4
    assert r.errors == []


def test_command_result_with_errors():
    r = CommandResult(
        output='Error: bad command',
        success=False,
        elapsed_ms=50.0,
        errors=['Error: Unrecognized command'],
    )
    assert r.success is False
    assert len(r.errors) == 1
