from __future__ import annotations

from flask import Blueprint, jsonify, request


def create_blueprint(services, require_auth, rate_limit):
    blueprint = Blueprint('commands', __name__)

    @blueprint.post('/api/devices/command')
    @require_auth
    @rate_limit
    def command():
        data = request.get_json(silent=True) or {}
        path, value = data.get('path'), data.get('command')
        if not isinstance(path, str) or not isinstance(value, str) or not value or len(value) > 1024:
            return jsonify({'success': False, 'error': 'Invalid command'}), 400
        return jsonify(services.commands.send(path, value.strip()))

    @blueprint.post('/api/devices/batch-command')
    @require_auth
    @rate_limit
    def batch():
        data = request.get_json(silent=True) or {}
        path, values = data.get('path'), data.get('commands')
        if not isinstance(path, str) or not isinstance(values, list) or not values or len(values) > 200:
            return jsonify({'success': False, 'error': 'Commands must be a list'}), 400
        return jsonify(services.commands.batch(path, values, data.get('wait', 0.1),
                                               data.get('auto_view', True), data.get('auto_undo_tm', True)))

    @blueprint.post('/api/devices/group-command')
    @require_auth
    @rate_limit
    def group():
        data = request.get_json(silent=True) or {}
        paths, value = data.get('paths'), data.get('command')
        if not isinstance(paths, list) or not paths or not isinstance(value, str) or not value:
            return jsonify({'success': False, 'error': 'Missing paths or command'}), 400
        return jsonify(services.commands.group(paths, value))

    @blueprint.post('/api/devices/verify')
    @require_auth
    def verify():
        data = request.get_json(silent=True) or {}
        path, check_type, target_ip = data.get('path'), data.get('check_type', 'all'), data.get('target_ip')
        if not path:
            return jsonify({'success': False, 'error': '缺少 path 参数'}), 400
        if not services.device_manager.has(path):
            return jsonify({'success': False, 'error': '设备未连接: ' + path}), 400
        from agent.verifier import SemanticVerifier
        verifier = SemanticVerifier(services.commands.send)
        if check_type == 'connectivity' and target_ip:
            results = [verifier.verify_connectivity(path, target_ip)]
        else:
            method = getattr(verifier, f'verify_{check_type}', None)
            results = [method(path)] if method and check_type != 'all' else verifier.verify_all(path, target_ip=target_ip)
        return jsonify({'success': True, 'checks': [item.to_dict() for item in results]})

    return blueprint
