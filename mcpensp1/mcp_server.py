import asyncio, json, os, logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Direct module imports for Phase 3 (bypass HTTP round-trip)
from device_manager import dm
from command_executor import cmd_executor
from services import services, kb, topo_engine, config_methods

ENSP_API_KEY = os.environ.get('ENSP_API_KEY', '')
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.types import Prompt, PromptMessage, PromptArgument
from mcp.server.stdio import stdio_server

MCP_SERVER_NAME = "ensp-mcp-server"
# 保留历史常量，MCP 工具不再使用该地址转发请求。
SERVER_URL = os.environ.get('ENSP_SERVER_URL', 'in-process')
mcp_server = Server(MCP_SERVER_NAME)


# ==================== Phase 3: Direct tool helpers (no HTTP) ====================

async def _direct_connect(port: int) -> str:
    """Connect to eNSP device directly via Telnet (async-safe)."""
    return json.dumps(services.devices.connect(port), ensure_ascii=False)
    try:
        from connection import TelnetConnection
        path = f'127.0.0.1:{port}'
        existing = dm.get(path)
        if existing:
            try:
                existing.sock.send(b'')
                return json.dumps({
                    'success': True, 'port': port, 'path': path,
                    'name': dm.get_name(path), 'device_type': dm.get_type(path),
                    'reconnected': False
                })
            except Exception:
                dm.remove(path)

        conn = TelnetConnection('127.0.0.1', port)
        await asyncio.to_thread(conn.connect)
        await asyncio.to_thread(conn.handle_firewall_login)
        try:
            await asyncio.to_thread(conn.send_cmd, 'undo terminal monitor')
            await asyncio.sleep(0.1)
        except Exception:
            pass
        dm.set(path, conn)

        # Fetch device name
        try:
            raw = await asyncio.to_thread(conn.send_cmd, 'display version')
            name = None
            dt = 'unknown'
            if raw:
                lower = raw.lower()
                if 'huawei' in lower:
                    dt = 'huawei'
                elif 'h3c' in lower or 'hpe' in lower:
                    dt = 'h3c'
                elif 'cisco' in lower:
                    dt = 'cisco'
                elif 'juniper' in lower:
                    dt = 'juniper'
                if dt in ('huawei', 'h3c'):
                    nr = await asyncio.to_thread(conn.send_cmd, 'display current-configuration | include sysname')
                    if nr and 'Unrecognized' not in nr and 'Error' not in nr:
                        import re
                        m = re.search(r'^sysname\s+(\S+)', nr, re.IGNORECASE | re.MULTILINE)
                        if m:
                            name = m.group(1)
            if name:
                dm.set_name(path, name)
            dm.set_type(path, dt)
            display = f'{dm.get_name(path)} ({dt.upper()})' if dt != 'unknown' else dm.get_name(path)
            return json.dumps({
                'success': True, 'port': port, 'path': path,
                'name': dm.get_name(path), 'display_name': display,
                'device_type': dt
            })
        except Exception:
            dm.remove(path)
            return json.dumps({'success': False, 'error': 'Connection failed'})
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)[:200]})


async def _direct_send_cmd(path: str, command: str) -> str:
    """Directly send command to device via Telnet, bypassing Flask."""
    return json.dumps(services.commands.send(path, command), ensure_ascii=False)
    conn = dm.get(path)
    if not conn:
        return json.dumps({'success': False, 'error': 'Device not connected'})
    cmd_lower = command.strip().lower()
    try:
        import time
        t0 = time.time()
        result = await conn.send_cmd_async(command)
        elapsed = round(time.time() - t0, 3)
        _errs = ['Error:', 'Unrecognized command', 'Wrong parameter',
                 'Too many parameters', 'Ambiguous command', 'Incomplete command',
                 'Please renew the default configurations']
        ok = bool(result and not any(kw in result for kw in _errs))
        return json.dumps({
            'success': True, 'path': path, 'output': result,
            'response_time': elapsed, 'cmd_success': ok
        })
    except ConnectionError:
        dm.remove(path)
        dm.remove_name(path)
        return json.dumps({'success': False, 'error': 'Connection lost, device disconnected'})
    except Exception as e:
        logger.error('Direct command failed for %s: %s', path, str(e)[:200])
        return json.dumps({'success': False, 'error': str(e)[:200]})


async def _direct_disconnect(path: str) -> str:
    """Direct disconnect without HTTP."""
    return json.dumps(services.devices.disconnect(path), ensure_ascii=False)
    result = dm.remove(path)
    dm.remove_name(path)
    if result:
        try:
            result.close()
        except OSError:
            pass
    return json.dumps({'success': True, 'path': path})


async def _direct_batch_cmd(path: str, commands: list, **opts) -> dict:
    """Batch command execution (async-safe, non-blocking between commands)."""
    return services.commands.batch(path, commands, opts.get('wait', 0.1),
                                   opts.get('auto_view', True), opts.get('auto_undo_tm', True))
    conn = dm.get(path)
    if not conn:
        return {'success': False, 'error': 'Device not connected'}
    wait = opts.get('wait', 0.1)
    results = []
    cmd_count = 0
    success_count = 0
    for cmd in commands:
        cmd_lower = cmd.strip().lower()
        if not cmd_lower:
            continue
        cmd_count += 1
        try:
            t0 = asyncio.get_event_loop().time()
            output = await conn.send_cmd_async(cmd)
            elapsed = round(asyncio.get_event_loop().time() - t0, 3)
            _errs = ['Error:', 'Unrecognized command', 'Wrong parameter',
                      'Too many parameters', 'Ambiguous command', 'Incomplete command']
            ok = bool(output and not any(kw in output for kw in _errs))
            if ok:
                success_count += 1
            results.append({'command': cmd, 'success': ok, 'output': output, 'response_time': elapsed})
            # Stop on first error -- don't blindly continue
            if not ok:
                results.append({'command': '...', 'success': False,
                                'output': '=== BATCH STOPPED: command error ===',
                                'response_time': 0})
                break
            await asyncio.sleep(wait)
        except ConnectionError:
            dm.remove(path)
            dm.remove_name(path)
            results.append({'command': cmd, 'success': False, 'output': 'Connection lost'})
            return {'success': False, 'error': 'Connection lost', 'results': results,
                    'total': cmd_count, 'success_count': success_count}
        except Exception as e:
            results.append({'command': cmd, 'success': False, 'output': str(e)[:200]})
            break
    return {'success': True, 'path': path, 'results': results,
            'total': cmd_count, 'success_count': success_count}



# ---- Snapshot / Rollback / Fetch Name / Group Cmd helpers ----

async def _direct_fetch_name(path: str) -> str:
    """Fetch device name directly via Telnet."""
    name, device_type = services.devices.fetch_name(path)
    return json.dumps({'success': True, 'path': path, 'name': name, 'device_type': device_type}, ensure_ascii=False)
    conn = dm.get(path)
    if not conn:
        return json.dumps({'success': False, 'error': 'Device not connected'})
    try:
        raw = await conn.send_cmd_async('display version')
        name = None
        dt = 'unknown'
        if raw:
            lower = raw.lower()
            if 'huawei' in lower:
                dt = 'huawei'
            elif 'h3c' in lower or 'hpe' in lower:
                dt = 'h3c'
            elif 'cisco' in lower:
                dt = 'cisco'
            elif 'juniper' in lower:
                dt = 'juniper'
            if dt in ('huawei', 'h3c'):
                nr = await conn.send_cmd_async('display current-configuration | include sysname')
                if nr and 'Unrecognized' not in nr and 'Error' not in nr:
                    import re
                    m = re.search(r'^sysname\s+(\S+)', nr, re.IGNORECASE | re.MULTILINE)
                    if m:
                        name = m.group(1)
        dm.set_name(path, name or path)
        dm.set_type(path, dt)
        return json.dumps({'success': True, 'path': path, 'name': dm.get_name(path), 'device_type': dt})
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)[:200]})


async def _direct_group_cmd(paths: list, command: str) -> dict:
    """Send command to multiple devices directly."""
    return services.commands.group(paths, command)
    results = []
    for path in paths:
        r = await _direct_send_cmd(path, command)
        try:
            results.append({'path': path, **json.loads(r)})
        except Exception:
            results.append({'path': path, 'success': False, 'error': r[:200]})
    return {'success': True, 'results': results}


def _render_lab_report_markdown(name: str, devices: list, stats: dict) -> str:
    """把设备清单与知识库统计渲染成 Markdown 实验报告。"""
    lines = [f'# {name}', '',
             f'- 生成时间: {datetime.now(timezone.utc).isoformat()}',
             f'- 已连接设备: {len(devices)}', '',
             '## 设备清单', '']
    if devices:
        lines += ['| 设备 | 类型 | 路径 | 存活 |', '|------|------|------|------|']
        for item in devices:
            lines.append(f"| {item.get('name', '')} | {item.get('device_type', '')} "
                         f"| {item.get('path', '')} | {item.get('alive', '')} |")
    else:
        lines.append('_无已连接设备_')
    lines += ['', '## 知识库统计', '']
    for key, value in (stats or {}).items():
        lines.append(f'- {key}: {value}')
    return '\n'.join(lines)


# ==================== MCP tool definitions (active) ====================

# ==================== AGENT SYSTEM PROMPT v3.0 ====================

def _load_agent_prompt(version: str = "v3") -> str:
    """从外部文件加载 Agent System Prompt"""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", version, "system.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, encoding="utf-8") as f:
            content = f.read()
        logger.info("Loaded agent prompt from %s (%d chars)", prompt_path, len(content))
        return content
    logger.warning("Prompt file not found: %s, using fallback", prompt_path)
    return "You are eNSP Network Agent. Please follow the strict workflow."

AGENT_SYSTEM_PROMPT = _load_agent_prompt()

async def mcp_req(method, path, json_data=None, params=None):
    """历史兼容占位。MCP 不再通过 HTTP 调用 Flask。"""
    raise RuntimeError('MCP HTTP 代理已移除，请直接调用 services')

_REQUIRED_PARAMS = {
    "connect_device": ["port"],
    "send_command": ["path", "command"],
    "disconnect_device": ["path"],
    "rename_device": ["path", "name"],
    "fetch_device_name": ["path"],
    "find_topology_path": ["start", "end"],
    "get_topology_device": ["node_id"],
    "suggest_commands": ["model"],
    "scan_device_commands": ["path"],
    "record_experience": ["experiment"],
    "detect_device_view": ["prompt"],
    "batch_command": ["path", "commands"],
    "search_kb": ["q"],
    "get_command_help": ["cmd"],
    "group_command": ["paths", "command"],
    "auto_record_experience": ["path"],
    "agent_plan": ["goal"],
    "agent_execute": ["request"],
    # ÷
    "config_method_list": [],
    "config_method_get": ["method_id"],
    "config_method_search": ["keyword"],
    "config_method_add": ["method_data"],
    "config_method_steps": ["method_id"],
    "config_method_update": ["method_id", "updates"],
    # ܽ
}

@mcp_server.list_tools()
async def list_tools():
    return [
        Tool(name="scan_devices", description="扫描指定端口范围的 eNSP 设备", inputSchema={"type":"object","properties":{"start":{"type":"integer","default":2000},"end":{"type":"integer","default":2050}}}),
        Tool(name="connect_device", description="连接 eNSP 设备，自动识别设备型号和获取主机名", inputSchema={"type":"object","properties":{"port":{"type":"integer","description":"端口(1-65535)"}},"required":["port"]}),
        Tool(name="send_command", description="向设备发送命令，自动记录知识库并关注错误信息", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径"},"command":{"type":"string","description":"(最多1024字符)"}},"required":["path","command"]}),
        Tool(name="disconnect_device", description="断开设备连接", inputSchema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
        Tool(name="get_connected_devices", description="获取当前已连接设备列表及其状态", inputSchema={"type":"object","properties":{}}),
        Tool(name="rename_device", description="重命名指定设备", inputSchema={"type":"object","properties":{"path":{"type":"string"},"name":{"type":"string"}},"required":["path","name"]}),
        Tool(name="fetch_device_name", description="从设备获取真实主机名", inputSchema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
        Tool(name="get_command_catalog", description="获取命令目录，包括支持的命令、参数说明、风险等级及支持设备类型。AI agent 用此了解整体能力", inputSchema={"type":"object","properties":{"category":{"type":"string","description":": display/config/verify/diagnostic"},"device_type":{"type":"string","description":"设备类型: huawei/h3c/cisco/juniper"},"risk":{"type":"string","description":": safe/low/medium/high"}}}),
        Tool(name="get_device_capabilities", description="获取设备能力：哪些命令可执行、哪些功能、哪些已验证成功。AI agent用此了解特定设备能力", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径"}}}),
        Tool(name="get_device_history", description="获取设备执行历史：该设备成功/失败执行过哪些命令，用于结果预测", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径"}}}),
        Tool(name="get_kb_commands", description="查询知识库中已记录的命令（全局），支持使用过滤条件", inputSchema={"type":"object","properties":{"category":{"type":"string"},"device_type":{"type":"string"},"risk":{"type":"string"},"limit":{"type":"integer","default":50}}}),
        Tool(name="get_kb_stats", description="知识库统计信息", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_topology", description="获取拓扑摘要", inputSchema={"type":"object","properties":{}}),
        Tool(name="save_topology", description="保存/更新拓扑数据", inputSchema={"type":"object","properties":{"data":{"type":"object","description":"nodeslinksJSON"}}}),
        Tool(name="find_topology_path", description="查找两个设备间最短路径", inputSchema={"type":"object","properties":{"start":{"type":"string"},"end":{"type":"string"}},"required":["start","end"]}),
        Tool(name="get_topology_device", description="获取设备的连接和端口信息", inputSchema={"type":"object","properties":{"node_id":{"type":"string"}},"required":["node_id"]}),
        Tool(name="get_structured_kb", description="获取结构化知识库（按拓扑视图/设备型号分类），可按 model 和 view_type 过滤", inputSchema={"type":"object","properties":{"model":{"type":"string","description":"型号: S5700/S3700/USG6000V/AR2220/AC6605"},"view_type":{"type":"string","description":"视图: user_view/system_view"}}}),
        Tool(name="suggest_commands", description="根据设备名称或型号推荐合适命令。参数为设备名如 LSW1/FW1/AR1/AC1 可自动匹配型号，不重复推荐型号", inputSchema={"type":"object","properties":{"model":{"type":"string","description":"型号: LSW1/S5700/FW1/AR1/AC1"},"view_type":{"type":"string","description":"可选: user_view/system_view"}},"required":["model"]}),
        Tool(name="scan_device_commands", description="扫描历史已连设备，自动识别型号，返回该型号下所有可用命令建议。连接设备前推荐使用", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备 127.0.0.1:2012"}},"required":["path"]}),
        Tool(name="get_best_practices", description="获取最佳实践规范（当前指定视图下：退出、信息中心、undo t m 等公共规范）", inputSchema={"type":"object","properties":{"priority":{"type":"string","description":": critical/high/medium"},"applies_to":{"type":"string","description":"型号"}}}),
        Tool(name="get_experiences", description="获取实验经验记录：每个实验的目标、命令、教训、注意事项", inputSchema={"type":"object","properties":{"experiment":{"type":"string","description":"实验"}}}),
        Tool(name="record_experience", description="记录实验经验（目标+命令+教训+注意事项），可自动归约到知识库", inputSchema={"type":"object","properties":{"experiment":{"type":"string"},"date":{"type":"string"},"topology":{"type":"string"},"features_implemented":{"type":"array","items":{"type":"string"}},"new_commands_learned":{"type":"array","items":{"type":"object"}},"lessons_learned":{"type":"array","items":{"type":"string"}},"troubleshooting_cases":{"type":"array","items":{"type":"object"}}},"required":["experiment"]}),
        Tool(name="detect_device_view", description="探测设备当前视图类型：< > 用户视图，[ ] 系统视图。命令执行前先探测", inputSchema={"type":"object","properties":{"prompt":{"type":"string","description":"示例<LSW1>[LSW1]"}},"required":["prompt"]}),
        Tool(name="get_troubleshooting_kb", description="获取排错知识库（故障现象+原因+解决方案）", inputSchema={"type":"object","properties":{"symptom":{"type":"string","description":"症状"}}}),
        Tool(name="reload_kb", description="重新加载结构化知识库（知识库文件外部修改后用）", inputSchema={"type":"object","properties":{}}),
        Tool(name="generate_lab_report", description="自动生成实验报告：包含已连接设备与知识库统计，\"markdown\" 字段为 Markdown 正文", inputSchema={"type":"object","properties":{"name":{"type":"string","description":"实验"},"paths":{"type":"array","items":{"type":"string"},"description":"设备列表"}}}),
        Tool(name="auto_record_experience", description="自动提取知识库中已记录的该设备命令序列，识别关键配置意图（AC/WLAN、OSPF、VLAN等）并归纳为实验记录", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径"}},"required":["path"]}),
        Tool(name="batch_command", description="批量发送命令到设备，自动切换视图、自动 undo t m，一次最多 200 条", inputSchema={"type":"object","properties":{"path":{"type":"string"},"commands":{"type":"array","items":{"type":"string"}},"wait":{"type":"number","default":0.1},"auto_view":{"type":"boolean","default":True},"auto_undo_tm":{"type":"boolean","default":True}},"required":["path","commands"]}),
        Tool(name="search_kb", description="知识库全文搜索：命令、排错经验、实验记录", inputSchema={"type":"object","properties":{"q":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["q"]}),
        Tool(name="get_command_help", description="查询特定命令的帮助信息，从知识库返回用法和示例", inputSchema={"type":"object","properties":{"cmd":{"type":"string"}},"required":["cmd"]}),
        Tool(name="group_command", description="对多台设备发送相同命令", inputSchema={"type":"object","properties":{"paths":{"type":"array","items":{"type":"string"}},"command":{"type":"string"}},"required":["paths","command"]}),
    
        # ---- Agent Runtime v3.0 ----
        Tool(name="agent_memory_query", description="[Memory Query] Query Agent long-term memory", inputSchema={"type":"object","properties":{"query":{"type":"string"},"category":{"type":"string"},"limit":{"type":"integer","default":20}}}),
        Tool(name="agent_memory_lessons", description="[Lessons] Get lessons from experiments", inputSchema={"type":"object","properties":{}}),
        Tool(name="agent_memory_stats", description="[Memory Stats] Memory statistics", inputSchema={"type":"object","properties":{}}),
        Tool(name="agent_knowledge_search", description="[Knowledge Search] Search growing knowledge base", inputSchema={"type":"object","properties":{"query":{"type":"string"},"category":{"type":"string"},"device_type":{"type":"string"},"limit":{"type":"integer","default":20}}}),
        Tool(name="agent_knowledge_best_practices", description="[Best Practices] Network config best practices", inputSchema={"type":"object","properties":{}}),
        Tool(name="agent_knowledge_troubleshooting", description="[Troubleshooting] Historical troubleshooting cases", inputSchema={"type":"object","properties":{"query":{"type":"string"}}}),
        Tool(name="agent_plan", description="[Smart Planning] Generate DAG execution plan. USE BEFORE config.", inputSchema={"type":"object","properties":{"goal":{"type":"string"},"experiment_type":{"type":"string"}},"required":["goal"]}),
        Tool(name="agent_execute", description="[Full Experiment] One-click closed-loop experiment. RECOMMENDED.", inputSchema={"type":"object","properties":{"request":{"type":"string"},"device_paths":{"type":"array","items":{"type":"string"}},"experiment_type":{"type":"string"},"constraints":{"type":"array","items":{"type":"string"}}},"required":["request"]}),
        Tool(name="agent_status", description="[Agent Status] Runtime status and stats", inputSchema={"type":"object","properties":{}}),
        Tool(name="agent_daily_review", description="[Daily Review] Memory review and optimization", inputSchema={"type":"object","properties":{}}),
        Tool(name="config_method_list", description="列出所有配置方法（按类别组织的标准流程）", inputSchema={"type":"object","properties":{"category":{"type":"string","description":"可选: routing/switching/security/wireless/services/management"}}}),
        Tool(name="config_method_get", description="获取指定配置方法的详细信息：包含步骤、验证命令、注意事项等", inputSchema={"type":"object","properties":{"method_id":{"type":"string","description":"ID ospf_basicvlan_config"}},"required":["method_id"]}),
        Tool(name="config_method_search", description="搜索配置方法", inputSchema={"type":"object","properties":{"keyword":{"type":"string","description":"关键词"}},"required":["keyword"]}),
        Tool(name="config_method_add", description="添加新的配置方法到知识库", inputSchema={"type":"object","properties":{"method_data":{"type":"object","description":"包含 id/name/category/steps 等字段"}},"required":["method_data"]}),
        Tool(name="config_method_steps", description="获取配置方法的步骤命令列表，可直接执行的命令序列", inputSchema={"type":"object","properties":{"method_id":{"type":"string","description":"ID"}},"required":["method_id"]}),
        Tool(name="config_method_update", description="更新配置方法：添加成功经验、更新成功率等", inputSchema={"type":"object","properties":{"method_id":{"type":"string","description":"ID"},"updates":{"type":"object","description":"需要更新的字段"}},"required":["method_id","updates"]}),
    ]

@mcp_server.call_tool()
async def call_tool(name, arguments):
    try:
        required = _REQUIRED_PARAMS.get(name, [])
        missing = [k for k in required if not arguments or k not in arguments]
        if missing:
            return [TextContent(type="text", text=json.dumps({"error": "Missing required parameters: " + ", ".join(missing)}))]

        if name == "scan_devices":
            start = arguments.get("start", 2000)
            end = arguments.get("end", 2050)
            text = json.dumps(services.devices.scan(start, end), ensure_ascii=False)
        elif name == "connect_device":
            text = await _direct_connect(arguments["port"])
        elif name == "send_command":
            text = await _direct_send_cmd(arguments["path"], arguments["command"])
        elif name == "disconnect_device":
            text = await _direct_disconnect(arguments["path"])
        elif name == "get_connected_devices":
            text = json.dumps(services.devices.connected(), ensure_ascii=False)
        elif name == "rename_device": text = json.dumps(services.devices.rename(arguments["path"], arguments["name"]), ensure_ascii=False)
        elif name == "fetch_device_name": text = await _direct_fetch_name(arguments["path"])
        elif name == "get_command_catalog": text = json.dumps(kb.get_command_catalog(arguments.get("category"), arguments.get("device_type"), arguments.get("risk")), ensure_ascii=False)
        elif name == "get_device_capabilities":
            text = json.dumps(kb.get_device_capabilities(arguments.get("path")), ensure_ascii=False)
        elif name == "get_device_history":
            text = json.dumps(kb.get_device_history(arguments.get("path")), ensure_ascii=False)
        elif name == "get_kb_commands":
            commands = kb.get_global_commands(category=arguments.get("category"),
                                              device_type=arguments.get("device_type"),
                                              risk=arguments.get("risk"),
                                              limit=arguments.get("limit", 50))
            text = json.dumps({"success": True, "commands": commands, "count": len(commands)}, ensure_ascii=False)
        elif name == "get_kb_stats": text = json.dumps(kb.get_stats(), ensure_ascii=False)
        elif name == "get_topology": text = json.dumps(topo_engine.get_summary(), ensure_ascii=False)
        elif name == "save_topology": topo_engine.load(arguments.get("data", {})); text = json.dumps({"success": True})
        elif name == "find_topology_path": text = json.dumps(topo_engine.find_path(arguments["start"], arguments["end"]) or {"error": "No path found"}, ensure_ascii=False)
        elif name == "get_topology_device":
            text = json.dumps(topo_engine.get_device_connections(arguments["node_id"]), ensure_ascii=False)
        elif name == "get_structured_kb":
            text = json.dumps(kb.get_structured_kb(arguments.get("view_type"), arguments.get("model")) or {}, ensure_ascii=False)
        elif name == "suggest_commands":
            text = json.dumps(kb.suggest_commands(arguments["model"], arguments.get("view_type", "")), ensure_ascii=False)
        elif name == "scan_device_commands":
            text = json.dumps(kb.scan_device_commands(arguments["path"]), ensure_ascii=False)
        elif name == "get_best_practices":
            text = json.dumps(kb.get_best_practices(arguments.get("priority"), arguments.get("applies_to")), ensure_ascii=False)
        elif name == "get_experiences":
            text = json.dumps(kb.get_experiences(arguments.get("experiment")), ensure_ascii=False)
        elif name == "record_experience":
            text = json.dumps(kb.record_experience(arguments), ensure_ascii=False)
        elif name == "detect_device_view":
            text = json.dumps(kb.detect_view_mode(arguments["prompt"]), ensure_ascii=False)
        elif name == "get_troubleshooting_kb":
            text = json.dumps(kb.get_troubleshooting_cases(arguments.get("symptom")), ensure_ascii=False)
        elif name == "reload_kb":
            kb._skb_cache = None
            kb.load_structured_kb()
            text = json.dumps({"success": True, "message": "KB reloaded"})
        elif name == "batch_command":
            result = await _direct_batch_cmd(
                arguments["path"], arguments["commands"],
                wait=arguments.get("wait", 0.1),
                auto_view=arguments.get("auto_view", True),
                auto_undo_tm=arguments.get("auto_undo_tm", True))
            text = json.dumps(result, ensure_ascii=False)
        elif name == "search_kb": text = json.dumps(kb.search_markdown_reference(arguments["q"], arguments.get("limit", 20)), ensure_ascii=False)
        elif name == "get_command_help": text = json.dumps(kb.search_markdown_reference(arguments["cmd"], 20), ensure_ascii=False)
        elif name == "group_command":
            text = json.dumps(await _direct_group_cmd(arguments["paths"], arguments["command"]), ensure_ascii=False)
        elif name == "generate_lab_report":
            report_name = arguments.get("name", "eNSP Lab Report")
            report_devices = services.devices.connected()
            report_stats = kb.get_stats()
            text = json.dumps({'success': True, 'name': report_name,
                               'devices': report_devices, 'knowledge': report_stats,
                               'markdown': _render_lab_report_markdown(report_name, report_devices, report_stats)},
                              ensure_ascii=False)
        elif name == "auto_record_experience":
            path = arguments["path"]
            history = kb.get_device_history(path) or {}
            results = list(history.get("executed_commands", [])) + list(history.get("failed_commands", []))
            if not results:
                text = json.dumps({'success': False,
                                   'error': 'No command history recorded for ' + path}, ensure_ascii=False)
            else:
                before = len(kb.get_experiences() or [])
                kb._auto_record_knowledge(path, dm.get_type(path), results)
                text = json.dumps({'success': True, 'path': path,
                                   'commands_analyzed': len(results),
                                   'experiences_created': len(kb.get_experiences() or []) - before},
                                  ensure_ascii=False)
        # ---- Agent Runtime v3.0 ----
        # 以下 6 个 agent 记忆/知识工具原调用旧 knowledge.py 的 kb（与 AgentRuntime 记忆无关），
        # 现统一经 mcp_req 代理到真实 AgentRuntime 后端（/api/agent/*），避免“冒牌 Agent 记忆”。
        elif name == "agent_memory_query":
            runtime = services.agent_runtime; entries = runtime.memory.recall(query=arguments.get("query", ""), category=arguments.get("category"), limit=arguments.get("limit", 20)); text = json.dumps({'success': True, 'data': {'entries': [entry.to_dict() for entry in entries], 'total': len(entries)}}, ensure_ascii=False)
        elif name == "agent_memory_lessons":
            text = json.dumps({'success': True, 'data': {'lessons': [entry.to_dict() for entry in services.agent_runtime.memory.get_lessons(limit=50)]}}, ensure_ascii=False)
        elif name == "agent_memory_stats":
            text = json.dumps({'success': True, 'data': services.agent_runtime.memory.get_stats()}, ensure_ascii=False)
        elif name == "agent_knowledge_search":
            records = services.agent_runtime.knowledge.search(arguments.get("query", ""), arguments.get("category"), arguments.get("device_type"), arguments.get("limit", 20)); text = json.dumps({'success': True, 'data': {'records': [record.to_dict() for record in records], 'total': len(records)}}, ensure_ascii=False)
        elif name == "agent_knowledge_best_practices":
            text = json.dumps({'success': True, 'data': {'practices': [record.to_dict() for record in services.agent_runtime.knowledge.search(category='best_practice', limit=20)]}}, ensure_ascii=False)
        elif name == "agent_knowledge_troubleshooting":
            text = json.dumps({'success': True, 'data': {'cases': [record.to_dict() for record in services.agent_runtime.knowledge.search(arguments.get("query", ""), 'troubleshoot', limit=20)]}}, ensure_ascii=False)
        elif name == "agent_plan":
            text = json.dumps({'success': True, 'data': services.agent_runtime.get_plan(arguments["goal"], arguments.get("experiment_type", "general"))}, ensure_ascii=False)
        elif name == "agent_execute":
            result = services.agent_runtime.execute_task(arguments["request"], arguments.get("device_paths", []), arguments.get("experiment_type", "general"), arguments.get("constraints", [])); text = json.dumps({'success': True, 'data': result.to_dict()}, ensure_ascii=False)
        elif name == "agent_status":
            text = json.dumps({'success': True, 'data': services.agent_runtime.get_status()}, ensure_ascii=False)
        elif name == "agent_daily_review":
            text = json.dumps({'success': True, 'data': services.agent_runtime.learning.daily_review()}, ensure_ascii=False)
        # ---- ÷ ----
        elif name == "config_method_list": text = json.dumps(config_methods.list_methods(arguments.get("category")), ensure_ascii=False)
        elif name == "config_method_get": text = json.dumps(config_methods.get_method(arguments["method_id"]), ensure_ascii=False)
        elif name == "config_method_search": text = json.dumps(config_methods.search_methods(arguments["keyword"]), ensure_ascii=False)
        elif name == "config_method_add": text = json.dumps(config_methods.add_method(arguments["method_data"]), ensure_ascii=False)
        elif name == "config_method_steps": text = json.dumps(config_methods.get_method_steps(arguments["method_id"]), ensure_ascii=False)
        elif name == "config_method_update": text = json.dumps(config_methods.update_method(arguments["method_id"], arguments["updates"]), ensure_ascii=False)
        else: text = json.dumps({"error": "Unknown tool"})
        return [TextContent(type="text", text=text)]
    except Exception as e:
        logger.exception("Unhandled error in tool call: %s", e)
        return [TextContent(type="text", text=json.dumps({"error": "An internal error occurred"}))]

async def check_backend_health():
    """统一服务已在当前进程初始化，无需探测 Web 后端。"""
    return True

async def run_mcp_server():
    async with stdio_server() as (r, w):
        await mcp_server.run(r, w, mcp_server.create_initialization_options())



# ==================== MCP PROMPT REGISTRATION v3.0 ====================
@mcp_server.list_prompts()
async def list_prompts():
    return [
        Prompt(
            name="ensp_network_agent",
            description="eNSP Network Agent system prompt with workflow, knowledge, and verification rules.",
            arguments=[
                PromptArgument(name="experiment_type", description="Experiment type", required=False)
            ]
        )
    ]

@mcp_server.get_prompt()
async def get_prompt(name, arguments):
    if name == "ensp_network_agent":
        exp_type = (arguments or {}).get("experiment_type", "general")
        return {"messages": [{"role": "user", "content": {"type": "text", "text": AGENT_SYSTEM_PROMPT}}]}
    raise ValueError(f"Unknown prompt: {name}")

if __name__ == "__main__":
    logger.info("eNSP MCP Server starting (direct mode)...")
    asyncio.run(run_mcp_server())


