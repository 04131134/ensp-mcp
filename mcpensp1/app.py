# -*- coding: utf-8 -*-
"""Flask 应用装配入口。业务路由与 SocketIO 事件位于 web 包。"""
from __future__ import annotations

import os
import secrets

from flask import Flask, make_response, render_template
from flask_socketio import SocketIO

from agent.bootstrap import init_agent_runtime
from services import services
from web import agent, commands, devices, experiments, knowledge, topology
from web.common import install_error_handlers, make_guards
from web.socketio_handlers import register_device_namespace


def create_app():
    application = Flask(__name__)
    application.config.update(
        SECRET_KEY=os.environ.get('ENSP_SECRET_KEY', secrets.token_hex(32)),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    )
    socket = SocketIO(application, cors_allowed_origins=os.environ.get('CORS_ORIGINS', 'http://127.0.0.1:5000'), async_mode='threading')
    require_auth, rate_limit, limiter = make_guards()
    for factory in (devices.create_blueprint, commands.create_blueprint, knowledge.create_blueprint,
                    topology.create_blueprint, experiments.create_blueprint, agent.create_blueprint):
        application.register_blueprint(factory(services, require_auth, rate_limit))

    @application.get('/')
    @require_auth
    def index():
        response = make_response(render_template('index.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        return response

    @application.get('/api/health')
    def health():
        return {'status': 'ok', 'devices': len(services.device_manager.list_all()), 'kb': services.knowledge.get_stats()}

    install_error_handlers(application)
    register_device_namespace(socket, services, limiter, os.environ.get('ENSP_API_KEY', ''))
    runtime = init_agent_runtime(None, services.commands.send, device_scanner=services.devices.connected,
                                 topology_provider=services.topology.get_summary, register_routes=False)
    services.set_agent_runtime(runtime)
    return application, socket


app, socketio = create_app()

# 兼容历史导入点；实际实现位于统一服务层。
devices = services.device_manager.list_all()
device_names = services.device_manager._names
device_types = services.device_manager._types
scan_devices = services.devices.scan
connect_device = services.devices.connect
send_command = services.commands.send
send_command_batch = services.commands.batch
send_command_to_group = services.commands.group
disconnect_device = services.devices.disconnect
get_connected_devices = services.devices.connected
rename_device = services.devices.rename
heartbeat = services.heartbeat
kb = services.knowledge
topo_engine = services.topology


if __name__ == '__main__':
    services.heartbeat.start()
    socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True)
