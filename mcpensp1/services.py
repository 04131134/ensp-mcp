# -*- coding: utf-8 -*-
"""Shared service singletons for eNSP-MCP.

Both app.py (Flask) and mcp_server.py (MCP stdio) import from here
to share the same knowledge base, topology engine, and config methods.
"""
from __future__ import annotations
import os
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from knowledge import KnowledgeBase
from topology import TopologyEngine
from config_method_store import ConfigMethodStore
from device_manager import dm
from command_executor import CommandExecutor
from connection import TelnetConnection
from heartbeat import HeartbeatMonitor
from view_router import view_router, check_command_error
from exceptions import (AgentError, CommandExecutionError, DeviceConnectionError,
                        ExperimentError, TopologyError)

import knowledge as _knowledge_module

_knowledge_module.COMMAND_CATALOG = {
    'display version': {'description': '显示设备版本信息', 'category': 'display', 'tags': ['info', 'version'], 'risk': 'safe', 'huawei': True, 'h3c': True, 'cisco': True, 'juniper': True},
    'display current-configuration': {'description': '显示完整运行配置', 'category': 'display', 'tags': ['config'], 'risk': 'safe', 'huawei': True, 'h3c': True, 'cisco': True, 'juniper': True},
    'display ip interface brief': {'description': '显示接口地址与状态', 'category': 'display', 'tags': ['interface'], 'risk': 'safe', 'huawei': True, 'h3c': True, 'cisco': True, 'juniper': True},
    'display vlan': {'description': '显示 VLAN 配置', 'category': 'display', 'tags': ['vlan'], 'risk': 'safe', 'huawei': True, 'h3c': True, 'cisco': True, 'juniper': True},
    'system-view': {'description': '进入系统视图', 'category': 'config', 'tags': ['view'], 'risk': 'safe', 'huawei': True, 'h3c': True, 'cisco': False, 'juniper': False},
    'reboot': {'description': '重启设备', 'category': 'config', 'tags': ['danger'], 'risk': 'high', 'huawei': True, 'h3c': True, 'cisco': True, 'juniper': True},
}
for _catalog_entry in _knowledge_module.COMMAND_CATALOG.values():
    _catalog_entry.setdefault('output_hint', '')

# ---- Shared singletons ----

_KB_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kb')

kb = KnowledgeBase(_KB_FOLDER)
topo_engine = TopologyEngine()
config_methods = ConfigMethodStore(_KB_FOLDER)

logger = logging.getLogger(__name__)


class DeviceService:
    """设备连接与状态服务，复用 DeviceManager 连接池。"""

    def __init__(self, manager, heartbeat):
        self.manager = manager
        self.heartbeat = heartbeat

    def scan(self, start=2000, end=2050):
        return self.manager.scan_devices(start, end)

    def connect(self, port: int):
        path = f'127.0.0.1:{port}'
        existing = self.manager.get(path)
        if existing:
            try:
                existing.sock.send(b'')
                return {'success': True, 'port': port, 'path': path,
                        'name': self.manager.get_name(path),
                        'device_type': self.manager.get_type(path), 'reconnected': False}
            except Exception:
                self.manager.remove(path)
        connection = None
        try:
            connection = TelnetConnection('127.0.0.1', port)
            connection.connect()
            connection.handle_firewall_login()
            try:
                connection.send_cmd('undo terminal monitor')
                time.sleep(0.1)
            except Exception:
                pass
            self.manager.set(path, connection)
            name, dtype = self.fetch_name(path)
            self.manager.set_type(path, dtype)
            display = f'{name} ({dtype.upper()})' if dtype != 'unknown' else name
            return {'success': True, 'port': port, 'path': path, 'name': name,
                    'display_name': display, 'device_type': dtype}
        except Exception as error:
            if connection:
                try:
                    connection.close()
                except OSError:
                    pass
            self.manager.remove(path)
            raise DeviceConnectionError(f'Connection failed: {type(error).__name__}: {error}',
                                        device_path=path) from error

    def fetch_name(self, path: str):
        connection = self.manager.get(path)
        if not connection:
            raise DeviceConnectionError('Device not connected', device_path=path)
        name, dtype = path, 'unknown'
        try:
            output = connection.send_cmd('display version') or ''
            lower = output.lower()
            dtype = next((item for item in ('huawei', 'h3c', 'cisco', 'juniper') if item in lower), 'unknown')
            if dtype == 'huawei':
                config = connection.send_cmd('display current-configuration | include sysname') or ''
                for line in config.splitlines():
                    if line.lower().startswith('sysname '):
                        name = line.split(None, 1)[1]
                        break
            self.manager.set_name(path, name)
            self.manager.set_type(path, dtype)
            return name, dtype
        except Exception as error:
            raise DeviceConnectionError(str(error), device_path=path) from error

    def disconnect(self, path: str):
        connection = self.manager.remove(path)
        if not connection:
            return {'success': False, 'error': 'Not connected'}
        try:
            connection.close()
        except Exception:
            logger.warning('关闭设备连接失败: %s', path, exc_info=True)
        self.manager.remove_name(path)
        return {'success': True, 'path': path}

    def connected(self):
        result = []
        for item in self.manager.get_connected_summary():
            heartbeat = self.heartbeat.get_status(item['path'])
            dtype = item['device_type']
            name = item['name']
            result.append({**item, 'display_name': f'{name} ({dtype.upper()})' if dtype != 'unknown' else name,
                           'alive': heartbeat.get('alive', False),
                           'response_time': heartbeat.get('response_time', 0)})
        return result

    def rename(self, path: str, name: str):
        if not self.manager.has(path):
            return {'success': False, 'error': 'Not connected'}
        self.manager.set_name(path, name)
        return {'success': True, 'path': path, 'name': name}


class CommandService:
    """统一命令服务，供 Web 与 MCP 共享。"""

    def __init__(self, manager, knowledge):
        self.manager, self.knowledge = manager, knowledge
        self._undo_done = set()

    def send(self, path: str, command: str):
        connection = self.manager.get(path)
        if not connection:
            return {'success': False, 'error': 'Device not connected'}
        try:
            required_view = view_router.classify(command)
            started = time.time()
            output = connection.send_cmd(command)
            elapsed = round(time.time() - started, 3)
            errors = check_command_error(output or '')
            if not errors['success'] and errors['errors'] and view_router.ensure_view(connection, path, required_view):
                started = time.time()
                output = connection.send_cmd(command)
                elapsed = round(time.time() - started, 3)
                errors = check_command_error(output or '')
            success = errors['success']
            self.knowledge.record_command(command, output, device_type=self.manager.get_type(path),
                                          device_path=path, success=success)
            return {'success': True, 'path': path, 'output': output,
                    'response_time': elapsed, 'cmd_success': success}
        except ConnectionError:
            self.manager.remove(path)
            self.manager.remove_name(path)
            return {'success': False, 'error': 'Connection lost, device disconnected'}
        except Exception as error:
            logger.exception('命令执行失败: %s', path)
            return {'success': False, 'error': f'Command execution failed: {type(error).__name__}: {error}'}

    def batch(self, path, commands, wait=0.1, auto_view=True, auto_undo_tm=True):
        connection = self.manager.get(path)
        if not connection:
            return {'success': False, 'error': 'Device not connected'}
        results, success_count = [], 0
        for command in filter(lambda value: bool(value and value.strip()), commands):
            command = command.strip()
            if auto_view:
                view_router.before_command(connection, path, command)
            item = self.send(path, command)
            ok = item.get('cmd_success', item.get('success', False))
            results.append({'command': command, 'success': ok, 'output': item.get('output', item.get('error', '')),
                            'response_time': item.get('response_time', 0), 'cmd_success': ok})
            if not ok:
                results.append({'command': '?', 'success': False,
                                'output': '=== BATCH STOPPED: command error ===', 'response_time': 0})
                return {'success': False, 'path': path, 'results': results, 'total': len(results) - 1,
                        'success_count': success_count, 'stopped_due_to_error': True}
            success_count += 1
            time.sleep(wait)
        return {'success': bool(results), 'path': path, 'results': results, 'total': len(results),
                'success_count': success_count, 'stopped_due_to_error': False}

    def group(self, paths, command):
        results = [{'path': path, **self.send(path, command)} for path in paths]
        return {'success': all(item.get('success') for item in results), 'total': len(results), 'results': results}


@dataclass
class ServiceRegistry:
    device_manager: Any
    command_executor: Any
    knowledge: Any
    topology: Any
    config_methods: Any
    heartbeat: Any
    devices: DeviceService
    commands: CommandService
    experiments: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    agent_runtime: Optional[Any] = None

    def set_agent_runtime(self, runtime):
        self.agent_runtime = runtime


heartbeat = HeartbeatMonitor(kb)
command_executor = CommandExecutor(kb)
command_service = CommandService(dm, kb)
services = ServiceRegistry(dm, command_executor, kb, topo_engine, config_methods, heartbeat,
                           DeviceService(dm, heartbeat), command_service)
