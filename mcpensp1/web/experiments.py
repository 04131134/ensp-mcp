from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request


def create_blueprint(services, require_auth, rate_limit):
    blueprint = Blueprint('experiments', __name__)

    @blueprint.route('/api/experiments', methods=['GET', 'POST'])
    @require_auth
    def experiments():
        if request.method == 'GET': return jsonify(services.experiments)
        data = request.get_json(silent=True) or {}
        if 'name' not in data: return jsonify({'success': False, 'error': '缺少实验名称'}), 400
        exp_id = hashlib.md5((data['name'] + str(time.time())).encode()).hexdigest()[:12]
        experiment = {'name': data['name'], 'goal': data.get('goal', ''), 'devices': {}, 'links': [],
                      'status': 'created', 'created_at': datetime.now(timezone.utc).isoformat(), 'phase_history': []}
        services.experiments[exp_id] = experiment
        return jsonify({'success': True, 'experiment_id': exp_id, 'experiment': experiment})

    @blueprint.get('/api/experiments/<exp_id>')
    @require_auth
    def get_experiment(exp_id):
        value = services.experiments.get(exp_id)
        return jsonify(value) if value else (jsonify({'error': '实验未找到: ' + exp_id}), 404)

    @blueprint.post('/api/experiments/<exp_id>/plan')
    @require_auth
    def plan(exp_id):
        experiment = services.experiments.get(exp_id)
        if not experiment: return jsonify({'success': False, 'error': '实验未找到: ' + exp_id}), 404
        if not experiment.get('goal'): return jsonify({'success': False, 'error': 'experiment has no goal'}), 400
        runtime = services.agent_runtime
        if not runtime: return jsonify({'success': False, 'error': 'Agent Runtime 未初始化'}), 500
        result = runtime.get_plan(experiment['goal'], experiment.get('experiment_type', 'general'))
        experiment.update({'plan': result, 'status': 'planned'})
        return jsonify({'success': True, 'plan': result, 'experiment': experiment})

    @blueprint.post('/api/experiments/<exp_id>/verify')
    @require_auth
    def verify(exp_id):
        path = (request.get_json(silent=True) or {}).get('path')
        if not path: return jsonify({'success': False, 'error': '缺少 path 参数'}), 400
        from agent.verifier import SemanticVerifier
        results = SemanticVerifier(services.commands.send).verify_all(path)
        return jsonify({'success': True, 'checks': [item.to_dict() for item in results]})

    @blueprint.get('/api/experiments/dependency-graph')
    @require_auth
    def graph(): return jsonify({'success': False, 'implemented': False, 'error': 'dependency graph not implemented'}), 501

    return blueprint
