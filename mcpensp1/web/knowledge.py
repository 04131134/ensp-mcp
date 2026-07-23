from __future__ import annotations

from flask import Blueprint, jsonify, request


def _search(knowledge, query, limit):
    results = knowledge.search_markdown_reference(query, limit=limit)
    structured = knowledge._skb_cache or {}
    for name, item in structured.get('troubleshooting', {}).items():
        if query.lower() in (name + str(item)).lower():
            results.append({'type': 'troubleshooting', 'name': name, 'content': item, 'score': 1})
    return results[:limit]


def create_blueprint(services, require_auth, rate_limit):
    blueprint = Blueprint('knowledge', __name__)
    knowledge, methods = services.knowledge, services.config_methods

    @blueprint.get('/api/kb/commands')
    @require_auth
    def commands():
        return jsonify(knowledge.get_global_commands(category=request.args.get('category'), device_type=request.args.get('device_type'), risk=request.args.get('risk'), limit=request.args.get('limit', 50, type=int)))

    @blueprint.get('/api/kb/catalog')
    @require_auth
    def catalog():
        return jsonify(knowledge.get_command_catalog(request.args.get('category'), request.args.get('device_type'), request.args.get('risk')))

    @blueprint.get('/api/kb/devices')
    @require_auth
    def devices(): return jsonify(knowledge.get_device_history())

    @blueprint.get('/api/kb/devices/<path:path>')
    @require_auth
    def device(path): return jsonify(knowledge.get_device_history(path))

    @blueprint.get('/api/kb/capabilities')
    @require_auth
    def capabilities(): return jsonify(knowledge.get_device_capabilities(request.args.get('path')))

    @blueprint.get('/api/kb/stats')
    @require_auth
    def stats(): return jsonify(knowledge.get_stats())

    @blueprint.get('/api/kb/suggest')
    @require_auth
    def suggest():
        model = request.args.get('model')
        if not model: return jsonify({'success': False, 'error': 'Missing model parameter'}), 400
        return jsonify(knowledge.suggest_commands(model, request.args.get('view_type')))

    @blueprint.get('/api/kb/structured')
    @require_auth
    def structured(): return jsonify(knowledge.get_structured_kb(request.args.get('view_type'), request.args.get('model')))

    @blueprint.post('/api/kb/scan')
    @require_auth
    def scan():
        path = (request.get_json(silent=True) or {}).get('path')
        if not path: return jsonify({'success': False, 'error': 'Missing path parameter'}), 400
        return jsonify(knowledge.scan_device_commands(path))

    @blueprint.get('/api/kb/troubleshooting')
    @require_auth
    def troubleshooting():
        data = (knowledge._skb_cache or {}).get('troubleshooting', {})
        return jsonify(data.get(request.args.get('symptom'), {}) if request.args.get('symptom') else data)

    @blueprint.route('/api/kb/experience', methods=['GET', 'POST'])
    @require_auth
    def experience():
        if request.method == 'GET': return jsonify(knowledge.get_experiences(request.args.get('experiment')))
        data = request.get_json(silent=True) or {}
        if not data.get('experiment'): return jsonify({'success': False, 'error': 'Missing experiment name'}), 400
        return jsonify(knowledge.record_experience(data))

    @blueprint.route('/api/kb/best-practice', methods=['GET', 'POST'])
    @require_auth
    def best_practice():
        if request.method == 'GET': return jsonify(knowledge.get_best_practices(request.args.get('priority'), request.args.get('applies_to')))
        data = request.get_json(silent=True) or {}
        if not data.get('rule'): return jsonify({'success': False, 'error': 'Missing rule'}), 400
        return jsonify(knowledge.record_best_practice(data))

    @blueprint.post('/api/kb/detect-view')
    @require_auth
    def detect_view():
        prompt = (request.get_json(silent=True) or {}).get('prompt', '')
        return jsonify({'prompt': prompt, 'view': knowledge.detect_view_mode(prompt)})

    @blueprint.post('/api/kb/reload')
    @require_auth
    def reload(): return jsonify({'success': knowledge.reload_structured_kb(), 'message': 'Structured KB reloaded from disk'})

    @blueprint.get('/api/kb/search')
    @require_auth
    def search():
        query = request.args.get('q', '')
        if not query: return jsonify({'success': False, 'error': 'Missing q'}), 400
        return jsonify(_search(knowledge, query, request.args.get('limit', 20, type=int)))

    @blueprint.get('/api/kb/help')
    @require_auth
    def help():
        value = request.args.get('cmd', '')
        if not value: return jsonify({'success': False, 'error': 'Missing cmd'}), 400
        return jsonify(knowledge.search_markdown_reference(value, limit=20))

    @blueprint.post('/api/kb/auto-extract')
    @require_auth
    def auto_extract():
        data = request.get_json(silent=True) or {}
        path, results = data.get('path'), data.get('commands_results') or []
        if not path: return jsonify({'success': False, 'error': 'Missing path'}), 400
        if not results: return jsonify({'success': False, 'error': 'No commands found'}), 400
        knowledge._auto_record_knowledge(path, services.device_manager.get_type(path), results)
        return jsonify({'success': True, 'message': 'Auto knowledge extraction triggered', 'commands_analyzed': len(results)})

    @blueprint.post('/api/kb/lab-report')
    @require_auth
    def lab_report():
        data = request.get_json(silent=True) or {}
        return jsonify({'name': data.get('name', 'eNSP Lab Report'), 'devices': services.devices.connected(), 'knowledge': knowledge.get_stats()})

    @blueprint.get('/api/config-methods/list')
    @require_auth
    def method_list():
        items = methods.list_methods(request.args.get('category') or None)
        return jsonify({'success': True, 'count': len(items), 'methods': items})

    @blueprint.get('/api/config-methods/get/<method_id>')
    @require_auth
    def method_get(method_id):
        item = methods.get_method(method_id)
        return jsonify({'success': True, 'method': item}) if item else (jsonify({'success': False, 'error': 'config method not found: ' + method_id}), 404)

    @blueprint.get('/api/config-methods/search')
    @require_auth
    def method_search():
        keyword = request.args.get('keyword', '')
        if not keyword: return jsonify({'success': False, 'error': 'keyword required'}), 400
        items = methods.search_methods(keyword)
        return jsonify({'success': True, 'count': len(items), 'methods': items})

    @blueprint.post('/api/config-methods/add')
    @require_auth
    def method_add(): return jsonify(methods.add_method(request.get_json(silent=True) or {}))

    @blueprint.get('/api/config-methods/steps/<method_id>')
    @require_auth
    def method_steps(method_id): return jsonify({'success': True, 'steps': methods.get_method_steps(method_id)})

    @blueprint.get('/api/config-methods/summary')
    @require_auth
    def method_summary(): return jsonify({'success': True, 'summary': methods.export_methods_summary()})

    @blueprint.post('/api/config-methods/update/<method_id>')
    @require_auth
    def method_update(method_id): return jsonify(methods.update_method(method_id, request.get_json(silent=True) or {}))

    return blueprint
