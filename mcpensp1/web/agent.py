from __future__ import annotations

from flask import Blueprint, jsonify, request


def _records(items): return [item.to_dict() for item in items]


def create_blueprint(services, require_auth, rate_limit):
    blueprint = Blueprint('agent', __name__)

    def runtime():
        if not services.agent_runtime: raise RuntimeError('Agent Runtime 未初始化')
        return services.agent_runtime

    @blueprint.get('/api/agent/status')
    @require_auth
    def status(): return jsonify({'success': True, 'data': runtime().get_status()})

    @blueprint.get('/api/agent/status/<experiment_id>')
    @require_auth
    def experiment_status(experiment_id): return jsonify({'success': True, 'data': runtime().get_status(experiment_id)})

    @blueprint.get('/api/agent/memory')
    @require_auth
    def memory():
        items = runtime().memory.recall(query=request.args.get('query', ''), category=request.args.get('category'), limit=request.args.get('limit', 20, type=int))
        return jsonify({'success': True, 'data': {'entries': _records(items), 'total': len(items)}})

    @blueprint.get('/api/agent/memory/lessons')
    @require_auth
    def lessons(): return jsonify({'success': True, 'data': {'lessons': _records(runtime().memory.get_lessons(limit=50))}})

    @blueprint.get('/api/agent/memory/stats')
    @require_auth
    def memory_stats(): return jsonify({'success': True, 'data': runtime().memory.get_stats()})

    @blueprint.get('/api/agent/knowledge/search')
    @require_auth
    def knowledge_search():
        items = runtime().knowledge.search(request.args.get('query', ''), request.args.get('category'), request.args.get('device_type'), request.args.get('limit', 20, type=int))
        return jsonify({'success': True, 'data': {'records': _records(items), 'total': len(items)}})

    @blueprint.get('/api/agent/knowledge/best-practices')
    @require_auth
    def practices(): return jsonify({'success': True, 'data': {'practices': _records(runtime().knowledge.search(category='best_practice', limit=20))}})

    @blueprint.get('/api/agent/knowledge/troubleshooting')
    @require_auth
    def troubleshooting(): return jsonify({'success': True, 'data': {'cases': _records(runtime().knowledge.search(request.args.get('query', ''), 'troubleshoot', limit=20))}})

    @blueprint.post('/api/agent/plan')
    @require_auth
    def plan():
        data = request.get_json(silent=True) or {}
        return jsonify({'success': True, 'data': runtime().get_plan(data.get('goal', ''), data.get('experiment_type', 'general'))})

    @blueprint.post('/api/agent/execute')
    @require_auth
    def execute():
        data = request.get_json(silent=True) or {}
        if not data.get('request'): return jsonify({'success': False, 'error': '缺少 request 参数'}), 400
        result = runtime().execute_task(data['request'], data.get('device_paths', []), data.get('experiment_type', 'general'), data.get('constraints', []))
        return jsonify({'success': True, 'data': result.to_dict()})

    @blueprint.post('/api/agent/learning/daily-review')
    @require_auth
    def daily_review(): return jsonify({'success': True, 'data': runtime().learning.daily_review()})

    return blueprint
