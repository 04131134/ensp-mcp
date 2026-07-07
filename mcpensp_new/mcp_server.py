# -*- coding: utf-8 -*-
"""MCP Server — configuration-driven, zero business logic.

Loads tool definitions from config/tools.yaml (UTF-8, no garbled text).
Routes MCP JSON-RPC calls directly to core services.
No HTTP round-trips. No Flask dependency. No Agent subsystem.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from core.devices import DeviceManager
from core.commands import CommandContext, create_default_pipeline
from core.knowledge import KnowledgeService
from core.diagnostics import diagnose as diag_cmd, diagnose_result
from core.status import StatusMonitor
from core.config_methods import ConfigMethodStore

logger = logging.getLogger('ensp_mcp')

# ── Bootstrap ──────────────────────────────────────────────────

HERE = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(HERE, 'kb')
LOG_DIR = os.path.join(HERE, 'logs')

os.makedirs(KB_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

devices = DeviceManager()
knowledge = KnowledgeService(KB_DIR)
pipeline = create_default_pipeline(devices, knowledge)
status_monitor = StatusMonitor(devices)
config_methods = ConfigMethodStore(KB_DIR)

# ── Tool definitions ───────────────────────────────────────────

def _load_tools() -> list[Tool]:
    """Load tool definitions from YAML, with fallback to defaults."""
    tools_path = os.path.join(HERE, 'config', 'tools.yaml')
    try:
        with open(tools_path, encoding='utf-8') as f:
            data = yaml.safe_load(f)
        tools = []
        for t in data.get('tools', []):
            schema: dict = {'type': 'object', 'properties': {}}
            required: list[str] = []
            for name, param in t.get('parameters', {}).items():
                prop: dict = {'type': param.get('type', 'string')}
                if 'description' in param:
                    prop['description'] = param['description']
                if 'default' in param:
                    prop['default'] = param['default']
                if 'items' in param:
                    prop['items'] = {'type': param['items']}
                schema['properties'][name] = prop
                if param.get('required'):
                    required.append(name)
            if required:
                schema['required'] = required
            tools.append(Tool(
                name=t['name'],
                description=t.get('description', ''),
                inputSchema=schema,
            ))
        logger.info('Loaded %d tools from config/tools.yaml', len(tools))
        return tools
    except Exception as e:
        logger.warning('Failed to load tools.yaml: %s. Using fallback.', e)
        return _DEFAULT_TOOLS


_DEFAULT_TOOLS = [
    Tool(name='scan_devices', description='扫描设备',
         inputSchema={'type': 'object', 'properties': {
             'start': {'type': 'integer', 'default': 2000},
             'end': {'type': 'integer', 'default': 2050}}}),
    Tool(name='connect_device', description='连接设备',
         inputSchema={'type': 'object', 'properties': {
             'port': {'type': 'integer'}}, 'required': ['port']}),
    Tool(name='send_command', description='发送命令',
         inputSchema={'type': 'object', 'properties': {
             'path': {'type': 'string'}, 'command': {'type': 'string'}},
             'required': ['path', 'command']}),
    Tool(name='disconnect_device', description='断开设备',
         inputSchema={'type': 'object', 'properties': {
             'path': {'type': 'string'}}, 'required': ['path']}),
    Tool(name='get_connected_devices', description='已连接设备',
         inputSchema={'type': 'object', 'properties': {}}),
    Tool(name='batch_command', description='批量命令',
         inputSchema={'type': 'object', 'properties': {
             'path': {'type': 'string'}, 'commands': {'type': 'array', 'items': {'type': 'string'}}},
             'required': ['path', 'commands']}),
    Tool(name='search_kb', description='搜索知识库',
         inputSchema={'type': 'object', 'properties': {
             'query': {'type': 'string'}}, 'required': ['query']}),
    Tool(name='get_kb_stats', description='知识库统计',
         inputSchema={'type': 'object', 'properties': {}}),
    Tool(name='diagnose_command', description='诊断命令错误',
         inputSchema={'type': 'object', 'properties': {
             'output': {'type': 'string'}}, 'required': ['output']}),
    Tool(name='check_device_status', description='检测设备状态',
         inputSchema={'type': 'object', 'properties': {
             'path': {'type': 'string'}}, 'required': ['path']}),
    Tool(name='check_all_status', description='检测所有设备状态',
         inputSchema={'type': 'object', 'properties': {}}),
    Tool(name='status_summary', description='设备状态摘要',
         inputSchema={'type': 'object', 'properties': {}}),
    Tool(name='config_method_list', description='配置方法列表',
         inputSchema={'type': 'object', 'properties': {}}),
    Tool(name='config_method_search', description='搜索配置方法',
         inputSchema={'type': 'object', 'properties': {
             'keyword': {'type': 'string'}}, 'required': ['keyword']}),
    Tool(name='config_method_get', description='获取配置方法',
         inputSchema={'type': 'object', 'properties': {
             'method_id': {'type': 'string'}}, 'required': ['method_id']}),
    Tool(name='config_method_steps', description='配置方法步骤',
         inputSchema={'type': 'object', 'properties': {
             'method_id': {'type': 'string'}}, 'required': ['method_id']}),
    Tool(name='record_experience', description='记录实验经验',
         inputSchema={'type': 'object', 'properties': {
             'experiment': {'type': 'string'}, 'commands': {'type': 'array', 'items': {'type': 'string'}},
             'success': {'type': 'boolean'}}, 'required': ['experiment', 'commands', 'success']}),
    Tool(name='get_config_guidance', description='配置指导',
         inputSchema={'type': 'object', 'properties': {
             'topic': {'type': 'string'}}, 'required': ['topic']}),
]

# ── MCP Server ──────────────────────────────────────────────────

_TOOLS = _load_tools()
mcp_server = Server('ensp-mcp-server')


@mcp_server.list_tools()
async def list_tools():
    return _TOOLS


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        return await _dispatch(name, arguments or {})
    except Exception as e:
        logger.exception('Unhandled error in tool %s', name)
        return [TextContent(type='text', text=json.dumps(
            {'error': str(e)[:200]}, ensure_ascii=False))]


async def _dispatch(name: str, args: dict):
    j = lambda d: json.dumps(d, ensure_ascii=False, default=str)

    # ── Device Management ──
    if name == 'scan_devices':
        return [TextContent(type='text', text=j(
            devices.scan_devices(args.get('start', 2000), args.get('end', 2050))))]

    if name == 'connect_device':
        port = args['port']
        try:
            path = devices.connect(port)
            return [TextContent(type='text', text=j({
                'success': True, 'port': port, 'path': path,
                'name': devices.get_name(path),
                'device_type': devices.get_type(path),
            }))]
        except Exception as e:
            return [TextContent(type='text', text=j(
                {'success': False, 'error': str(e)[:200]}))]

    if name == 'send_command':
        ctx = CommandContext(
            path=args['path'], command=args['command'],
            device_name=devices.get_name(args['path']),
            device_type=devices.get_type(args['path']),
        )
        result = await pipeline.execute(ctx)
        return [TextContent(type='text', text=j(result))]

    if name == 'disconnect_device':
        devices.disconnect(args['path'])
        return [TextContent(type='text', text=j(
            {'success': True, 'path': args['path']}))]

    if name == 'get_connected_devices':
        return [TextContent(type='text', text=j(devices.list_all()))]

    if name == 'rename_device':
        devices.rename(args['path'], args['name'])
        return [TextContent(type='text', text=j(
            {'success': True, 'path': args['path'], 'name': args['name']}))]

    if name == 'fetch_device_name':
        driver = devices.get_driver(args['path'])
        if not driver:
            return [TextContent(type='text', text=j(
                {'success': False, 'error': '设备未连接'}))]
        try:
            r = await driver.execute_async('display version')
            name = devices.get_name(args['path'])
            return [TextContent(type='text', text=j({
                'success': True, 'path': args['path'], 'name': name,
                'device_type': devices.get_type(args['path']),
                'version_preview': r.output[:500],
            }))]
        except Exception as e:
            return [TextContent(type='text', text=j(
                {'success': False, 'error': str(e)[:200]}))]

    # ── Command Execution ──
    if name == 'batch_command':
        results = []
        for cmd in args['commands']:
            ctx = CommandContext(
                path=args['path'], command=cmd,
                device_name=devices.get_name(args['path']),
                device_type=devices.get_type(args['path']),
            )
            r = await pipeline.execute(ctx)
            results.append({'command': cmd, **r})
        success_count = sum(1 for r in results if r.get('cmd_success'))
        return [TextContent(type='text', text=j({
            'success': True, 'path': args['path'],
            'results': results,
            'total': len(results),
            'success_count': success_count,
        }))]

    if name == 'group_command':
        results = []
        for path in args['paths']:
            ctx = CommandContext(
                path=path, command=args['command'],
                device_name=devices.get_name(path),
                device_type=devices.get_type(path),
            )
            r = await pipeline.execute(ctx)
            results.append({'path': path, **r})
        return [TextContent(type='text', text=j(
            {'success': True, 'results': results}))]

    if name == 'diagnose_command':
        return [TextContent(type='text', text=j(diag_cmd(args['output'])))]

    if name == 'diagnose_batch':
        return [TextContent(type='text', text=j(
            diagnose_result(args['results'])))]

    # ── Knowledge Base ──
    if name == 'search_kb':
        entries = knowledge.search(
            query=args.get('query', ''),
            category=args.get('category'),
            device_type=args.get('device_type'),
            limit=args.get('limit', 20),
        )
        return [TextContent(type='text', text=j(
            {'results': [e.to_dict() for e in entries], 'total': len(entries)}))]

    if name == 'get_kb_stats':
        return [TextContent(type='text', text=j(knowledge.get_stats()))]

    if name == 'get_config_guidance':
        return [TextContent(type='text', text=j(
            knowledge.get_config_guidance(args['topic'])))]

    if name == 'record_experience':
        result = knowledge.record_experience(
            experiment=args['experiment'],
            commands=args.get('commands', []),
            success=args.get('success', False),
            lessons=args.get('lessons'),
            device_type=args.get('device_type', 'unknown'),
        )
        return [TextContent(type='text', text=j(result))]

    if name == 'get_command_catalog':
        return [TextContent(type='text', text=j({
            'catalog': [], 'note': 'Command catalog is now in config/catalog.yaml'
        }))]

    if name == 'generate_lab_report':
        paths = args.get('paths') or [d['path'] for d in devices.list_all()]
        report_lines = ['# eNSP Lab Report', f'Generated: {args.get("name", "Lab")}', '']
        for path in paths:
            driver = devices.get_driver(path)
            if not driver:
                continue
            name = devices.get_name(path)
            report_lines.append(f'## Device: {name} ({path})')
            report_lines.append('')
            try:
                r = await driver.execute_async('display current-configuration')
                report_lines.append('```')
                report_lines.append(r.output[:5000])
                report_lines.append('```')
            except Exception:
                report_lines.append('(无法获取配置)')
            report_lines.append('')
        return [TextContent(type='text', text='\n'.join(report_lines))]

    # ── Device Status ──
    if name == 'check_device_status':
        status = status_monitor.check_one(args['path'])
        if status is None:
            return [TextContent(type='text', text=j(
                {'success': False, 'error': '设备未连接'}))]
        return [TextContent(type='text', text=j({
            'path': status.path,
            'name': status.name,
            'device_type': status.device_type,
            'tcp_alive': status.tcp_alive,
            'session_alive': status.session_alive,
            'checked_at': status.checked_at,
        }))]

    if name == 'check_all_status':
        return [TextContent(type='text', text=j(
            status_monitor.check_all()))]

    if name == 'status_summary':
        return [TextContent(type='text', text=j(
            status_monitor.summary()))]

    # ── Topology ──
    if name == 'get_topology':
        return [TextContent(type='text', text=j({
            'topo_names': devices.get_topo_names(),
            'devices': devices.list_all(),
        }))]

    if name == 'save_topology':
        data = args.get('data', {})
        for node in data.get('nodes', []):
            port = node.get('port')
            name = node.get('name')
            if port and name:
                devices.set_topo_name(port, name)
        return [TextContent(type='text', text=j({'success': True}))]

    if name == 'find_topology_path':
        return [TextContent(type='text', text=j({
            'path': [args['start'], args['end']],
            'note': 'Topology graph traversal requires topology engine setup',
        }))]

    if name == 'get_topology_device':
        return [TextContent(type='text', text=j(
            {'node_id': args['node_id'], 'connections': []}))]

    # ── Configuration Methods ──
    if name == 'config_method_list':
        return [TextContent(type='text', text=j(
            config_methods.list(args.get('category', ''))))]

    if name == 'config_method_get':
        m = config_methods.get(args['method_id'])
        return [TextContent(type='text', text=j(
            m or {'error': f'Method not found: {args["method_id"]}'}))]

    if name == 'config_method_search':
        return [TextContent(type='text', text=j(
            config_methods.search(args['keyword'])))]

    if name == 'config_method_steps':
        return [TextContent(type='text', text=j(
            config_methods.get_steps(args['method_id'])))]

    if name == 'config_method_add':
        result = config_methods.add(args['method_data'])
        return [TextContent(type='text', text=j(result))]

    if name == 'config_method_update':
        result = config_methods.update(args['method_id'], args['updates'])
        return [TextContent(type='text', text=j(result))]

    return [TextContent(type='text', text=j(
        {'error': f'Unknown tool: {name}'}))]


# ── Main ───────────────────────────────────────────────────────

async def run() -> None:
    """Start the MCP server (stdio transport)."""
    logger.info('eNSP MCP Server starting...')
    async with stdio_server() as (reader, writer):
        await mcp_server.run(reader, writer,
                              mcp_server.create_initialization_options())


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(os.path.join(LOG_DIR, 'mcp_server.log'),
                                encoding='utf-8'),
        ],
    )
    asyncio.run(run())
