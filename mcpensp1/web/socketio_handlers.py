from __future__ import annotations


def register_device_namespace(socketio, services, limiter, api_key=''):
    """集中注册设备命名空间事件，HTTP 路由仅负责请求响应。"""
    def allowed():
        from flask import request
        return not api_key or request.headers.get('X-API-Key', '') == api_key

    @socketio.on('connect', namespace='/devices')
    def connect():
        return True if allowed() else False

    @socketio.on('scan', namespace='/devices')
    def scan(data):
        from flask_socketio import emit
        data = data or {}
        emit('scan_result', services.devices.scan(data.get('start', 2000), data.get('end', 2050)))

    @socketio.on('get_connected_devices', namespace='/devices')
    def connected():
        from flask_socketio import emit
        emit('connected_devices_list', services.devices.connected())

    @socketio.on('connect_device', namespace='/devices')
    def connect_device(data):
        from flask_socketio import emit
        result = services.devices.connect((data or {}).get('port'))
        emit('device_connected' if result.get('success') else 'device_error', result)

    @socketio.on('send_command', namespace='/commands')
    def send_command(data):
        from flask_socketio import emit
        data = data or {}
        result = services.commands.send(data.get('path', ''), data.get('command', ''))
        emit('device_output' if result.get('success') else 'device_error', result)

    @socketio.on('disconnect_device', namespace='/devices')
    def disconnect_device(data):
        from flask_socketio import emit
        result = services.devices.disconnect((data or {}).get('path', ''))
        if result.get('success'): emit('device_disconnected', result)

    @socketio.on('rename_device', namespace='/devices')
    def rename_device(data):
        from flask_socketio import emit
        data = data or {}
        result = services.devices.rename(data.get('path', ''), data.get('name', ''))
        if result.get('success'): emit('device_renamed', result)
