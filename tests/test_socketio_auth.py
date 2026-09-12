# -*- coding: utf-8 -*-
"""SocketIO 设备命名空间：鉴权与事件接线测试。

覆盖三个历史缺陷：
1. `/commands` 命名空间完全没有鉴权，即使设置了 ENSP_API_KEY 也能发命令；
2. API Key 用 == 比较，未使用 secrets.compare_digest；
3. 服务端把事件注册在 /devices、/commands 下，前端却连默认命名空间，
   导致所有实时事件都收不到。
"""
from __future__ import annotations

from flask import Flask
from flask_socketio import SocketIO

from web.socketio_handlers import (
    COMMAND_NAMESPACE,
    DEVICE_NAMESPACE,
    register_device_namespace,
)


class _StubDevices:
    def __init__(self):
        self.scan_calls = 0
        self.connected_calls = 0

    def scan(self, start, end):
        self.scan_calls += 1
        return []

    def connected(self):
        self.connected_calls += 1
        return []

    def connect(self, port):
        return {'success': True, 'path': '127.0.0.1:%s' % port}

    def disconnect(self, path):
        return {'success': True, 'path': path}

    def rename(self, path, name):
        return {'success': True, 'path': path, 'name': name}


class _StubCommands:
    def __init__(self):
        self.send_calls = 0

    def send(self, path, command):
        self.send_calls += 1
        return {'success': True, 'path': path, 'output': ''}


class _StubServices:
    def __init__(self):
        self.devices = _StubDevices()
        self.commands = _StubCommands()


def _client(api_key='', header=None, namespace=DEVICE_NAMESPACE):
    """基于真实 Flask-SocketIO 栈构造测试客户端。"""
    application = Flask(__name__)
    socketio = SocketIO(application, async_mode='threading')
    services = _StubServices()
    register_device_namespace(socketio, services, None, api_key=api_key)
    headers = {'X-API-Key': header} if header else None
    return socketio.test_client(application, namespace=namespace, headers=headers), services


def test_device_events_are_registered_on_documented_namespaces():
    """前端连接的命名空间必须与服务端注册的一致。"""
    application = Flask(__name__)
    socketio = SocketIO(application, async_mode='threading')
    recorded = []
    original_on = socketio.on

    def spy_on(event, namespace='/'):
        recorded.append((namespace, event))
        return original_on(event, namespace=namespace)

    socketio.on = spy_on
    register_device_namespace(socketio, _StubServices(), None)
    namespaces = {namespace for namespace, _ in recorded}
    assert namespaces == {DEVICE_NAMESPACE, COMMAND_NAMESPACE}


def test_without_api_key_connections_are_allowed():
    device_client, _ = _client()
    command_client, _ = _client(namespace=COMMAND_NAMESPACE)
    assert device_client.is_connected(DEVICE_NAMESPACE)
    assert command_client.is_connected(COMMAND_NAMESPACE)


def test_without_api_key_device_event_is_handled():
    client, services = _client()
    client.emit('get_connected_devices', namespace=DEVICE_NAMESPACE)
    assert services.devices.connected_calls == 1
    received = client.get_received(DEVICE_NAMESPACE)
    assert any(item['name'] == 'connected_devices_list' for item in received)


def test_api_key_rejects_unauthenticated_devices_namespace():
    client, services = _client(api_key='secret-key')
    assert not client.is_connected(DEVICE_NAMESPACE)
    assert services.devices.connected_calls == 0


def test_api_key_rejects_unauthenticated_commands_namespace():
    """回归：/commands 曾经完全没有鉴权，未授权客户端可以直接发命令。"""
    client, services = _client(api_key='secret-key', namespace=COMMAND_NAMESPACE)
    assert not client.is_connected(COMMAND_NAMESPACE)
    assert services.commands.send_calls == 0


def test_unauthorized_event_is_blocked_even_without_connection_gate():
    """兜底：即使有人绕过连接鉴权直接触发事件，也不得操作设备。"""
    application = Flask(__name__)
    socketio = SocketIO(application, async_mode='threading')
    services = _StubServices()
    register_device_namespace(socketio, services, None, api_key='secret-key')
    # flask_socketio 用 @wraps 包了一层，__wrapped__ 即本模块注册的处理器
    handler = socketio.server.handlers[DEVICE_NAMESPACE]['get_connected_devices'].__wrapped__
    with application.test_request_context(headers={}):
        assert handler() is None
    assert services.devices.connected_calls == 0


def test_api_key_rejects_wrong_key():
    client, _ = _client(api_key='secret-key', header='wrong-key')
    assert not client.is_connected(DEVICE_NAMESPACE)


def test_api_key_accepts_correct_key():
    client, services = _client(api_key='secret-key', header='secret-key')
    assert client.is_connected(DEVICE_NAMESPACE)
    client.emit('get_connected_devices', namespace=DEVICE_NAMESPACE)
    assert services.devices.connected_calls == 1


def test_real_app_serves_device_namespace_end_to_end():
    """端到端：真实 app 必须在 /devices 上响应设备列表（前端连的就是它）。"""
    from app import app as flask_application, socketio

    client = socketio.test_client(flask_application, namespace=DEVICE_NAMESPACE)
    try:
        assert client.is_connected(DEVICE_NAMESPACE)
        client.emit('get_connected_devices', namespace=DEVICE_NAMESPACE)
        received = client.get_received(DEVICE_NAMESPACE)
        assert any(item['name'] == 'connected_devices_list' for item in received)
    finally:
        client.disconnect(namespace=DEVICE_NAMESPACE)
