from __future__ import annotations

import json
from flask import Blueprint, jsonify, request


def create_blueprint(services, require_auth, rate_limit):
    blueprint = Blueprint('topology', __name__)

    @blueprint.get('/api/topology')
    @require_auth
    def get_topology(): return jsonify(services.topology.get_summary())

    @blueprint.post('/api/topology')
    @require_auth
    def save_topology():
        data = request.get_json(silent=True) or {}
        nodes, links = data.get('nodes'), data.get('links')
        if not isinstance(nodes, list) or not isinstance(links, list):
            return jsonify({'success': False, 'error': 'nodes and links must be arrays'}), 400
        services.topology.load(data)
        for node in nodes:
            if isinstance(node, dict) and node.get('port') and node.get('name'):
                services.device_manager.set_topo_name(int(node['port']), node['name'])
        return jsonify({'success': True, 'topology': services.topology.get_summary()})

    @blueprint.post('/api/topology/file')
    @require_auth
    def upload_topology():
        file = request.files.get('file')
        if not file: return jsonify({'success': False, 'error': 'No file'}), 400
        try:
            data = json.loads(file.read(10 * 1024 * 1024).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return jsonify({'success': False, 'error': 'Invalid topology file'}), 400
        services.topology.load(data)
        return jsonify({'success': True, 'topology': services.topology.get_summary()})

    @blueprint.get('/api/topology/path')
    @require_auth
    def find_path():
        start, end = request.args.get('start'), request.args.get('end')
        if not start or not end: return jsonify({'success': False, 'error': 'Missing start or end'}), 400
        path = services.topology.find_path(start, end)
        return jsonify({'success': True, 'path': path}) if path else (jsonify({'success': False, 'error': 'No path found'}), 404)

    @blueprint.get('/api/topology/device/<path:node_id>')
    @require_auth
    def device(node_id): return jsonify({'node_id': node_id, 'connections': services.topology.get_device_connections(node_id)})

    return blueprint
