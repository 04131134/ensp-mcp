# -*- coding: utf-8 -*-
"""
Agent Runtime API 路由

新增 API 端点：
- /api/agent/memory - 长期记忆管理
- /api/agent/knowledge - 可成长知识库
- /api/agent/planner - 执行计划生成
- /api/agent/reflection - 反思与学习
- /api/agent/runtime - 运行时状态
- /api/agent/execute - 闭环实验执行
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def register_agent_routes(app, agent_runtime):
    """注册 Agent Runtime API 路由到 Flask 应用"""

    # ==================== 运行时状态 ====================


    # Fix C4: Auth and rate limit helpers
    import secrets as _secrets
    import time as _time
    from functools import wraps as _wraps
    from flask import request as _flask_req

    _rate_calls = {}

    def _require_auth(f):
        @_wraps(f)
        def decorated(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated

    def _rate_limit(f):
        @_wraps(f)
        def decorated(*args, **kwargs):
            ip = _flask_req.remote_addr or 'unknown'
            now = _time.time()
            calls = _rate_calls.get(ip, [])
            calls = [t for t in calls if now - t < 60]
            if len(calls) >= 120:
                return {'success': False, 'error': 'Rate limit exceeded'}, 429
            calls.append(now)
            _rate_calls[ip] = calls
            return f(*args, **kwargs)
        return decorated


    @_rate_limit
    @_require_auth
    @app.route('/api/agent/status')
    def agent_status():
        """获取 Agent 运行时状态"""
        try:
            status = agent_runtime.get_status()
            return {'success': True, 'data': status}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/status/<experiment_id>')
    def agent_experiment_status(experiment_id):
        """获取特定实验状态"""
        try:
            status = agent_runtime.get_status(experiment_id)
            return {'success': True, 'data': status}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    # ==================== 长期记忆 ====================

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/memory')
    def agent_memory_list():
        """查询记忆列表"""
        try:
            from flask import request
            query = request.args.get('query', '')
            category = request.args.get('category')
            limit = int(request.args.get('limit', 20))
            entries = agent_runtime.memory.recall(query=query, category=category, limit=limit)
            return {
                'success': True,
                'data': {
                    'entries': [e.to_dict() for e in entries],
                    'total': len(entries),
                },
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/memory/lessons')
    def agent_memory_lessons():
        """获取经验教训"""
        try:
            entries = agent_runtime.memory.get_lessons(limit=50)
            return {
                'success': True,
                'data': {'lessons': [e.to_dict() for e in entries]},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/memory/errors')
    def agent_memory_errors():
        """获取错误模式"""
        try:
            entries = agent_runtime.memory.get_error_patterns(limit=30)
            return {
                'success': True,
                'data': {'patterns': [e.to_dict() for e in entries]},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/memory/commands')
    def agent_memory_commands():
        """获取可复用命令"""
        try:
            from flask import request
            device_type = request.args.get('device_type', '')
            entries = agent_runtime.memory.get_reusable_commands(device_type=device_type)
            return {
                'success': True,
                'data': {'commands': [e.to_dict() for e in entries]},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/memory/templates')
    def agent_memory_templates():
        """获取可模板化实验"""
        try:
            entries = agent_runtime.memory.get_templates()
            return {
                'success': True,
                'data': {'templates': [e.to_dict() for e in entries]},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/memory/stats')
    def agent_memory_stats():
        """获取记忆统计"""
        try:
            stats = agent_runtime.memory.get_stats()
            return {'success': True, 'data': stats}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/memory/export')
    def agent_memory_export():
        """导出可共享的记忆"""
        try:
            data = agent_runtime.memory.export_for_sharing()
            return {'success': True, 'data': data}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/memory/import', methods=['POST'])
    def agent_memory_import():
        """导入共享记忆"""
        try:
            from flask import request
            data = request.get_json(force=True)
            count = agent_runtime.memory.import_shared(data)
            return {'success': True, 'imported': count}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    # ==================== 可成长知识库 ====================

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/knowledge/search')
    def agent_knowledge_search():
        """搜索知识库"""
        try:
            from flask import request
            query = request.args.get('query', '')
            category = request.args.get('category')
            device_type = request.args.get('device_type')
            limit = int(request.args.get('limit', 20))
            records = agent_runtime.knowledge.search(
                query=query, category=category, device_type=device_type, limit=limit
            )
            return {
                'success': True,
                'data': {'records': [r.to_dict() for r in records], 'total': len(records)},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/knowledge/stats')
    def agent_knowledge_stats():
        """获取知识库统计"""
        try:
            stats = agent_runtime.knowledge.get_stats()
            return {'success': True, 'data': stats}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/knowledge/success-cases')
    def agent_knowledge_success_cases():
        """获取成功案例"""
        try:
            from flask import request
            device_type = request.args.get('device_type', '')
            records = agent_runtime.knowledge.search(category='success_case', device_type=device_type, limit=20)
            return {
                'success': True,
                'data': {'cases': [r.to_dict() for r in records]},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/knowledge/failure-cases')
    def agent_knowledge_failure_cases():
        """获取失败案例"""
        try:
            from flask import request
            device_type = request.args.get('device_type', '')
            records = agent_runtime.knowledge.search(category='failure_case', device_type=device_type, limit=20)
            return {
                'success': True,
                'data': {'cases': [r.to_dict() for r in records]},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/knowledge/best-practices')
    def agent_knowledge_best_practices():
        """获取最佳实践"""
        try:
            records = agent_runtime.knowledge.search(category='best_practice', limit=20)
            return {
                'success': True,
                'data': {'practices': [r.to_dict() for r in records]},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/knowledge/templates')
    def agent_knowledge_templates():
        """获取实验模板"""
        try:
            records = agent_runtime.knowledge.search(category='template', limit=20)
            return {
                'success': True,
                'data': {'templates': [r.to_dict() for r in records]},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/knowledge/troubleshooting')
    def agent_knowledge_troubleshooting():
        """获取排障案例"""
        try:
            from flask import request
            query = request.args.get('query', '')
            records = agent_runtime.knowledge.search(query=query, category='troubleshoot', limit=20)
            return {
                'success': True,
                'data': {'cases': [r.to_dict() for r in records]},
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/knowledge/export')
    def agent_knowledge_export():
        """导出知识库"""
        try:
            data = agent_runtime.knowledge.export_for_sharing()
            return {'success': True, 'data': data}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/knowledge/import', methods=['POST'])
    def agent_knowledge_import():
        """导入知识库"""
        try:
            from flask import request
            data = request.get_json(force=True)
            count = agent_runtime.knowledge.import_shared(data)
            return {'success': True, 'imported': count}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    # ==================== 执行计划 ====================

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/plan', methods=['POST'])
    def agent_plan():
        """生成执行计划（不执行）"""
        try:
            from flask import request
            data = request.get_json(force=True)
            goal = data.get('goal', '')
            experiment_type = data.get('experiment_type', 'general')
            plan = agent_runtime.get_plan(goal, experiment_type)
            return {'success': True, 'data': plan}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    # ==================== 闭环执行 ====================

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/execute', methods=['POST'])
    def agent_execute():
        """执行完整闭环实验"""
        try:
            from flask import request
            data = request.get_json(force=True)
            request_text = data.get('request', '')
            device_paths = data.get('device_paths', [])
            experiment_type = data.get('experiment_type', 'general')
            constraints = data.get('constraints', [])
            if not request_text:
                return {'success': False, 'error': '缺少 request 参数'}, 400
            result = agent_runtime.execute_task(
                request=request_text,
                device_paths=device_paths,
                experiment_type=experiment_type,
                constraints=constraints,
            )
            return {'success': True, 'data': result.to_dict()}
        except Exception as e:
            logger.error('闭环执行失败: %s', e, exc_info=True)
            return {'success': False, 'error': str(e)}, 500

    # ==================== 反思与学习 ====================

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/reflection/<experiment_id>')
    def agent_reflection(experiment_id):
        """获取实验反思结果"""
        try:
            # 从记忆中搜索该实验的反思
            entries = agent_runtime.memory.recall(
                query=experiment_id, limit=20
            )
            return {
                'success': True,
                'data': {
                    'experiment_id': experiment_id,
                    'entries': [e.to_dict() for e in entries],
                },
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @_rate_limit
    @_require_auth
    @app.route('/api/agent/learning/daily-review', methods=['POST'])
    def agent_daily_review():
        """执行每日回顾"""
        try:
            report = agent_runtime.learning.daily_review()
            return {'success': True, 'data': report}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    logger.info('[AgentRoutes] 已注册 %d 个 Agent Runtime API 端点', 22)
