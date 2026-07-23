from __future__ import annotations

from flask import Blueprint, jsonify, request


def create_blueprint(services, require_auth, rate_limit):
    blueprint = Blueprint('devices', __name__)

    @blueprint.get('/api/devices/scan')
    @require_auth
    @rate_limit
    def scan():
        start, end = request.args.get('start', 2000, type=int), request.args.get('end', 2050, type=int)
        if not (1 <= start <= end <= 65535) or end - start + 1 > 1000:
            return jsonify({'success': False, 'error': 'Invalid range'}), 400
        return jsonify(services.devices.scan(start, end))

    @blueprint.post('/api/devices/connect')
    @require_auth
    @rate_limit
    def connect():
        data = request.get_json(silent=True) or {}
        port = data.get('port')
        if not isinstance(port, int) or not 1 <= port <= 65535:
            return jsonify({'success': False, 'error': 'Invalid port'}), 400
        return jsonify(services.devices.connect(port))

    @blueprint.post('/api/devices/disconnect')
    @require_auth
    def disconnect():
        path = (request.get_json(silent=True) or {}).get('path')
        if not isinstance(path, str) or not path:
            return jsonify({'success': False, 'error': 'Invalid'}), 400
        return jsonify(services.devices.disconnect(path))

    @blueprint.get('/api/devices')
    @require_auth
    def connected():
        return jsonify(services.devices.connected())

    @blueprint.post('/api/devices/rename')
    @require_auth
    def rename():
        data = request.get_json(silent=True) or {}
        path, name = data.get('path'), data.get('name')
        if not isinstance(path, str) or not isinstance(name, str) or not name or len(name) > 128:
            return jsonify({'success': False}), 400
        return jsonify(services.devices.rename(path, name.strip()))

    @blueprint.post('/api/devices/fetch-name')
    @require_auth
    def fetch_name():
        path = (request.get_json(silent=True) or {}).get('path')
        if not isinstance(path, str) or not path:
            return jsonify({'success': False, 'error': 'Invalid path'}), 400
        name, dtype = services.devices.fetch_name(path)
        return jsonify({'success': True, 'path': path, 'name': name, 'device_type': dtype})

    @blueprint.get('/api/devices/heartbeat')
    @require_auth
    def heartbeat():
        return jsonify(services.heartbeat.get_status())

    return blueprint
