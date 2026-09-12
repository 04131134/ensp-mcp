from __future__ import annotations

import logging
import secrets
from functools import wraps

logger = logging.getLogger(__name__)

# 设备实时事件使用的命名空间（前端必须连接到同样的命名空间）
DEVICE_NAMESPACE = '/devices'
COMMAND_NAMESPACE = '/commands'


def register_device_namespace(socketio, services, limiter, api_key=''):
    """集中注册设备命名空间事件，HTTP 路由仅负责请求响应。

    鉴权：设置了 ENSP_API_KEY 时，两个命名空间的连接以及每条事件都必须携带
    正确的 X-API-Key 头；未设置时为历史行为，全部放行。
    """
    def authorized():
        if not api_key:
            return True
        from flask import request
        provided = request.headers.get('X-API-Key', '')
        return bool(provided) and secrets.compare_digest(str(provided), str(api_key))

    def require_key(function):
        """事件级鉴权：未通过时不执行任何设备操作（连接已拒绝，此处为兜底）。"""
        @wraps(function)
        def wrapped(*args, **kwargs):
            if not authorized():
                logger.warning('SocketIO 事件被拒绝（未授权）: %s', function.__name__)
                return None
            return function(*args, **kwargs)
        return wrapped

    @socketio.on('connect', namespace=DEVICE_NAMESPACE)
    def connect_devices():
        # 返回 False 表示拒绝连接
        return True if authorized() else False

    @socketio.on('connect', namespace=COMMAND_NAMESPACE)
    def connect_commands():
        return True if authorized() else False

    @socketio.on('scan', namespace=DEVICE_NAMESPACE)
    @require_key
    def scan(data):
        from flask_socketio import emit
        data = data or {}
        emit('scan_result', services.devices.scan(data.get('start', 2000), data.get('end', 2050)))

    @socketio.on('get_connected_devices', namespace=DEVICE_NAMESPACE)
    @require_key
    def connected():
        from flask_socketio import emit
        emit('connected_devices_list', services.devices.connected())

    @socketio.on('connect_device', namespace=DEVICE_NAMESPACE)
    @require_key
    def connect_device(data):
        from flask_socketio import emit
        result = services.devices.connect((data or {}).get('port'))
        emit('device_connected' if result.get('success') else 'device_error', result)

    @socketio.on('send_command', namespace=COMMAND_NAMESPACE)
    @require_key
    def send_command(data):
        from flask_socketio import emit
        data = data or {}
        result = services.commands.send(data.get('path', ''), data.get('command', ''))
        emit('device_output' if result.get('success') else 'device_error', result)

    @socketio.on('disconnect_device', namespace=DEVICE_NAMESPACE)
    @require_key
    def disconnect_device(data):
        from flask_socketio import emit
        result = services.devices.disconnect((data or {}).get('path', ''))
        if result.get('success'): emit('device_disconnected', result)

    @socketio.on('rename_device', namespace=DEVICE_NAMESPACE)
    @require_key
    def rename_device(data):
        from flask_socketio import emit
        data = data or {}
        result = services.devices.rename(data.get('path', ''), data.get('name', ''))
        if result.get('success'): emit('device_renamed', result)
