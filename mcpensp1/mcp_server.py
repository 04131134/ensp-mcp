import asyncio, json, os, httpx
from urllib.parse import quote
ENSP_API_KEY = os.environ.get('ENSP_API_KEY', '')
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

MCP_SERVER_NAME = "ensp-mcp-server"
SERVER_URL = os.environ.get('ENSP_SERVER_URL', 'http://127.0.0.1:5000')
mcp_server = Server(MCP_SERVER_NAME)

_http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))

async def mcp_req(method, path, json_data=None, params=None):
    headers = {}
    if ENSP_API_KEY:
        headers['X-API-Key'] = ENSP_API_KEY
    url = f"{SERVER_URL}{path}"
    if method == "GET":
        resp = await _http_client.get(url, params=params, headers=headers)
    elif method == "POST":
        resp = await _http_client.post(url, json=json_data, headers=headers)
    else:
        return json.dumps({"error": "Unsupported method"})
    if resp.status_code != 200:
        return json.dumps({"error": "Backend request failed", "status_code": resp.status_code})
    return resp.text

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
    "suggest_next_steps": ["path"],
    "batch_command": ["path", "commands"],
    "snapshot_config": ["path"],
    "get_snapshot": ["snapshot_id"],
    "diff_snapshots": ["snapshot1", "snapshot2"],
    "rollback_config": ["path", "snapshot_id"],
    "search_kb": ["q"],
    "get_command_help": ["cmd"],
    "generate_config_template": ["type"],
    "group_command": ["paths", "command"],
    "auto_record_experience": ["path"],
    "get_config_guidance": ["topic"],
}

@mcp_server.list_tools()
async def list_tools():
    return [
        Tool(name="scan_devices", description="扫描指定端口范围的eNSP设备", inputSchema={"type":"object","properties":{"start":{"type":"integer","default":2000},"end":{"type":"integer","default":2050}}}),
        Tool(name="connect_device", description="连接eNSP设备，自动识别设备类型和获取主机名", inputSchema={"type":"object","properties":{"port":{"type":"integer","description":"端口号(1-65535)"}},"required":["port"]}),
        Tool(name="send_command", description="向设备发送命令，自动收录知识库并标注命令作用", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径"},"command":{"type":"string","description":"命令(最长1024字符)"}},"required":["path","command"]}),
        Tool(name="disconnect_device", description="断开设备连接", inputSchema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
        Tool(name="get_connected_devices", description="获取所有已连接设备列表（含心跳状态）", inputSchema={"type":"object","properties":{}}),
        Tool(name="rename_device", description="重命名设备", inputSchema={"type":"object","properties":{"path":{"type":"string"},"name":{"type":"string"}},"required":["path","name"]}),
        Tool(name="fetch_device_name", description="从设备获取真实主机名", inputSchema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
        Tool(name="get_command_catalog", description="获取命令目录：所有支持的命令、作用描述、风险等级、支持的设备类型。AI agent用此快速了解可用命令", inputSchema={"type":"object","properties":{"category":{"type":"string","description":"分类过滤: display/config/verify/diagnostic"},"device_type":{"type":"string","description":"设备类型: huawei/h3c/cisco/juniper"},"risk":{"type":"string","description":"风险: safe/low/medium/high"}}}),
        Tool(name="get_device_capabilities", description="获取设备能力矩阵：哪些命令能执行、哪些不能、哪些已验证成功。AI agent用此快速了解特定设备的能力", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径，不传则返回所有设备"}}}),
        Tool(name="get_device_history", description="获取设备执行历史：该设备成功/失败过哪些命令，含输出预览", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径，不传则返回所有设备"}}}),
        Tool(name="get_kb_commands", description="查询知识库中已收录的命令（全局），按使用次数排序", inputSchema={"type":"object","properties":{"category":{"type":"string"},"device_type":{"type":"string"},"risk":{"type":"string"},"limit":{"type":"integer","default":50}}}),
        Tool(name="get_kb_stats", description="知识库统计信息", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_topology", description="获取拓扑摘要", inputSchema={"type":"object","properties":{}}),
        Tool(name="save_topology", description="保存拓扑数据", inputSchema={"type":"object","properties":{"data":{"type":"object","description":"含nodes和links的拓扑JSON"}}}),
        Tool(name="find_topology_path", description="查找两设备间最短路径", inputSchema={"type":"object","properties":{"start":{"type":"string"},"end":{"type":"string"}},"required":["start","end"]}),
        Tool(name="get_topology_device", description="获取设备的拓扑连接信息", inputSchema={"type":"object","properties":{"node_id":{"type":"string"}},"required":["node_id"]}),
        Tool(name="get_structured_kb", description="获取结构化命令知识库（按视图类型/设备型号分类），可按model和view_type过滤", inputSchema={"type":"object","properties":{"model":{"type":"string","description":"设备型号: S5700/S3700/USG6000V/AR2220/AC6605"},"view_type":{"type":"string","description":"视图类型: user_view/system_view"}}}),
        Tool(name="suggest_commands", description="根据设备名或型号推荐可用命令。传入设备名如LSW1/FW1/AR1/AC1，自动匹配型号并返回该型号所有命令", inputSchema={"type":"object","properties":{"model":{"type":"string","description":"设备名或型号: LSW1/S5700/FW1/AR1/AC1等"},"view_type":{"type":"string","description":"可选: user_view/system_view"}},"required":["model"]}),
        Tool(name="scan_device_commands", description="扫描已连接设备，自动识别型号，返回该型号所有可用命令建议。配置新设备前推荐使用", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径如127.0.0.1:2012"}},"required":["path"]}),
        Tool(name="get_best_practices", description="获取操作规范（配置前必读），包含视图检测、undo t m、保存等规则", inputSchema={"type":"object","properties":{"priority":{"type":"string","description":"过滤: critical/high/medium"},"applies_to":{"type":"string","description":"过滤设备型号"}}}),
        Tool(name="get_experiences", description="获取实验经验记录（每次实验后积累的新命令、教训、排障案例）", inputSchema={"type":"object","properties":{"experiment":{"type":"string","description":"实验名称过滤"}}}),
        Tool(name="record_experience", description="记录实验经验（新命令+教训+排障案例），经验会自动积累到知识库", inputSchema={"type":"object","properties":{"experiment":{"type":"string"},"date":{"type":"string"},"topology":{"type":"string"},"features_implemented":{"type":"array","items":{"type":"string"}},"new_commands_learned":{"type":"array","items":{"type":"object"}},"lessons_learned":{"type":"array","items":{"type":"string"}},"troubleshooting_cases":{"type":"array","items":{"type":"object"}}},"required":["experiment"]}),
        Tool(name="detect_device_view", description="检测设备当前视图类型：< >用户视图或[ ]系统视图。配置前必须先检测", inputSchema={"type":"object","properties":{"prompt":{"type":"string","description":"终端提示符如<LSW1>或[LSW1]"}},"required":["prompt"]}),
        Tool(name="get_config_order", description="获取推荐的设备配置顺序（20步），首次配置时参考", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_troubleshooting_kb", description="获取排障知识库（常见问题+根因+解决方案）", inputSchema={"type":"object","properties":{"symptom":{"type":"string","description":"问题症状过滤"}}}),
        Tool(name="reload_kb", description="重新加载结构化知识库（当知识库文件被外部修改后调用）", inputSchema={"type":"object","properties":{}}),
        Tool(name="suggest_next_steps", description="上下文感知建议：分析设备已执行命令，推荐下一步配置操作，显示完成进度", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径"}},"required":["path"]}),
        Tool(name="generate_lab_report", description="自动生成实验报告：汇总所有设备配置、命令执行、知识库数据，输出Markdown格式报告", inputSchema={"type":"object","properties":{"name":{"type":"string","description":"实验名称"},"paths":{"type":"array","items":{"type":"string"},"description":"设备路径列表，不传则包含所有已连接设备"}}}),
        Tool(name="auto_record_experience", description="自动提取设备最近执行的命令序列，识别配置意图（如AC/WLAN、OSPF、VLAN等），自动将经验和排障案例写入知识库", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"设备路径"}},"required":["path"]}),
        Tool(name="batch_command", description="批量发送命令到设备，自动切换视图、自动undo t m，一次最多200条", inputSchema={"type":"object","properties":{"path":{"type":"string"},"commands":{"type":"array","items":{"type":"string"}},"wait":{"type":"number","default":0.1},"auto_view":{"type":"boolean","default":True},"auto_undo_tm":{"type":"boolean","default":True}},"required":["path","commands"]}),
        Tool(name="snapshot_config", description="对设备配置做快照，保存display current-configuration到本地", inputSchema={"type":"object","properties":{"path":{"type":"string"},"label":{"type":"string"}},"required":["path"]}),
        Tool(name="list_snapshots", description="列出配置快照，可按设备路径过滤", inputSchema={"type":"object","properties":{"path":{"type":"string"}}}),
        Tool(name="get_snapshot", description="获取指定快照内容", inputSchema={"type":"object","properties":{"snapshot_id":{"type":"string"}},"required":["snapshot_id"]}),
        Tool(name="diff_snapshots", description="对比两个配置快照的差异", inputSchema={"type":"object","properties":{"snapshot1":{"type":"string"},"snapshot2":{"type":"string"}},"required":["snapshot1","snapshot2"]}),
        Tool(name="rollback_config", description="回滚设备配置到指定快照", inputSchema={"type":"object","properties":{"path":{"type":"string"},"snapshot_id":{"type":"string"}},"required":["path","snapshot_id"]}),
        Tool(name="search_kb", description="知识库全文搜索，搜索命令、排障经验、实验记录", inputSchema={"type":"object","properties":{"q":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["q"]}),
        Tool(name="get_command_help", description="查询特定命令的帮助信息，从知识库返回用法和示例", inputSchema={"type":"object","properties":{"cmd":{"type":"string"}},"required":["cmd"]}),
        Tool(name="generate_config_template", description="生成配置模板，支持vlan/vrrp/mstp/dhcp/ospf/lacp/wlan", inputSchema={"type":"object","properties":{"type":{"type":"string"},"params":{"type":"object"}},"required":["type"]}),
        Tool(name="list_templates", description="列出所有可用配置模板", inputSchema={"type":"object","properties":{}}),
        Tool(name="group_command", description="对多台设备发送相同命令", inputSchema={"type":"object","properties":{"paths":{"type":"array","items":{"type":"string"}},"command":{"type":"string"}},"required":["paths","command"]}),
        Tool(name="get_config_guidance", description="[?????] ?????????????????????????????????????????????????????????????????", inputSchema={"type":"object","properties":{"topic":{"type":"string","description":"??????: AC WLAN???VLAN???OSPF???AP??"}},"required":["topic"]}),
    ]

@mcp_server.call_tool()
async def call_tool(name, arguments):
    try:
        required = _REQUIRED_PARAMS.get(name, [])
        missing = [k for k in required if not arguments or k not in arguments]
        if missing:
            return [TextContent(type="text", text=json.dumps({"error": "Missing required parameters: " + ", ".join(missing)}))]

        if name == "scan_devices": text = await mcp_req("GET", "/api/devices/scan", params={"start": arguments.get("start",2000), "end": arguments.get("end",2050)})
        elif name == "connect_device": text = await mcp_req("POST", "/api/devices/connect", json_data={"port": arguments["port"]})
        elif name == "send_command": text = await mcp_req("POST", "/api/devices/command", json_data={"path": arguments["path"], "command": arguments["command"]})
        elif name == "disconnect_device": text = await mcp_req("POST", "/api/devices/disconnect", json_data={"path": arguments["path"]})
        elif name == "get_connected_devices": text = await mcp_req("GET", "/api/devices")
        elif name == "rename_device": text = await mcp_req("POST", "/api/devices/rename", json_data={"path": arguments["path"], "name": arguments["name"]})
        elif name == "fetch_device_name": text = await mcp_req("POST", "/api/devices/fetch-name", json_data={"path": arguments["path"]})
        elif name == "get_command_catalog":
            params = {}
            for k in ["category","device_type","risk"]:
                if arguments.get(k): params[k] = arguments[k]
            text = await mcp_req("GET", "/api/kb/catalog", params=params)
        elif name == "get_device_capabilities":
            params = {"path": arguments["path"]} if arguments.get("path") else {}
            text = await mcp_req("GET", "/api/kb/capabilities", params=params)
        elif name == "get_device_history":
            if arguments.get('path'):
                safe_path = quote(str(arguments['path']), safe='')
                text = await mcp_req("GET", f"/api/kb/devices/{safe_path}")
            else:
                text = await mcp_req("GET", "/api/kb/devices")
        elif name == "get_kb_commands":
            params = {}
            for k in ["category","device_type","risk"]:
                if arguments.get(k): params[k] = arguments[k]
            if arguments.get("limit"): params["limit"] = arguments["limit"]
            text = await mcp_req("GET", "/api/kb/commands", params=params)
        elif name == "get_kb_stats": text = await mcp_req("GET", "/api/kb/stats")
        elif name == "get_topology": text = await mcp_req("GET", "/api/topology")
        elif name == "save_topology": text = await mcp_req("POST", "/api/topology", json_data=arguments.get("data", {}))
        elif name == "find_topology_path": text = await mcp_req("GET", "/api/topology/path", params={"start": arguments["start"], "end": arguments["end"]})
        elif name == "get_topology_device":
            safe_id = quote(str(arguments['node_id']), safe='')
            text = await mcp_req("GET", f"/api/topology/device/{safe_id}")
        elif name == "get_structured_kb":
            params = {}
            if arguments.get("model"): params["model"] = arguments["model"]
            if arguments.get("view_type"): params["view_type"] = arguments["view_type"]
            text = await mcp_req("GET", "/api/kb/structured", params=params)
        elif name == "suggest_commands":
            text = await mcp_req("GET", "/api/kb/suggest", params={"model": arguments["model"], "view_type": arguments.get("view_type", "")})
        elif name == "scan_device_commands":
            text = await mcp_req("POST", "/api/kb/scan", json_data={"path": arguments["path"]})
        elif name == "get_best_practices":
            params = {}
            if arguments.get("priority"): params["priority"] = arguments["priority"]
            if arguments.get("applies_to"): params["applies_to"] = arguments["applies_to"]
            text = await mcp_req("GET", "/api/kb/best-practice", params=params)
        elif name == "get_experiences":
            params = {}
            if arguments.get("experiment"): params["experiment"] = arguments["experiment"]
            text = await mcp_req("GET", "/api/kb/experience", params=params)
        elif name == "record_experience":
            text = await mcp_req("POST", "/api/kb/experience", json_data=arguments)
        elif name == "detect_device_view":
            text = await mcp_req("POST", "/api/kb/detect-view", json_data={"prompt": arguments["prompt"]})
        elif name == "get_config_order":
            text = await mcp_req("GET", "/api/kb/config-order")
        elif name == "get_troubleshooting_kb":
            params = {}
            if arguments.get("symptom"): params["symptom"] = arguments["symptom"]
            text = await mcp_req("GET", "/api/kb/troubleshooting", params=params)
        elif name == "reload_kb":
            text = await mcp_req("POST", "/api/kb/reload")
        elif name == "batch_command":
            text = await mcp_req("POST", "/api/devices/batch-command", json_data={"path": arguments["path"], "commands": arguments["commands"], "wait": arguments.get("wait", 0.1), "auto_view": arguments.get("auto_view", True), "auto_undo_tm": arguments.get("auto_undo_tm", True)})
        elif name == "snapshot_config":
            text = await mcp_req("POST", "/api/devices/snapshot", json_data={"path": arguments["path"], "label": arguments.get("label")})
        elif name == "list_snapshots":
            params = {}
            if arguments.get("path"): params["path"] = arguments["path"]
            text = await mcp_req("GET", "/api/devices/snapshots", params=params)
        elif name == "get_snapshot":
            safe_snap = quote(str(arguments['snapshot_id']), safe='')
            text = await mcp_req("GET", f"/api/devices/snapshot/{safe_snap}")
        elif name == "diff_snapshots":
            text = await mcp_req("POST", "/api/devices/diff", json_data={"snapshot1": arguments["snapshot1"], "snapshot2": arguments["snapshot2"]})
        elif name == "rollback_config":
            text = await mcp_req("POST", "/api/devices/rollback", json_data={"path": arguments["path"], "snapshot_id": arguments["snapshot_id"]})
        elif name == "search_kb":
            text = await mcp_req("GET", "/api/kb/search", params={"q": arguments["q"], "limit": arguments.get("limit", 20)})
        elif name == "get_command_help":
            text = await mcp_req("GET", "/api/kb/help", params={"cmd": arguments["cmd"]})
        elif name == "generate_config_template":
            text = await mcp_req("POST", "/api/kb/template", json_data={"type": arguments["type"], "params": arguments.get("params", {})})
        elif name == "list_templates":
            text = await mcp_req("GET", "/api/kb/templates")
        elif name == "group_command":
            text = await mcp_req("POST", "/api/devices/group-command", json_data={"paths": arguments["paths"], "command": arguments["command"]})
        elif name == "suggest_next_steps":
            text = await mcp_req("POST", "/api/devices/suggest-next", json_data={"path": arguments["path"]})
        elif name == "generate_lab_report":
            text = await mcp_req("POST", "/api/kb/lab-report", json_data={"name": arguments.get("name", "eNSP Lab Report"), "paths": arguments.get("paths")})
        elif name == "auto_record_experience":
            text = await mcp_req("POST", "/api/kb/auto-extract", json_data={"path": arguments["path"]})
        elif name == "get_config_guidance":
            text = await mcp_req("GET", "/api/kb/config-guidance", params={"topic": arguments["topic"]})
        else: text = json.dumps({"error": "Unknown tool"})
        return [TextContent(type="text", text=text)]
    except httpx.ConnectError: return [TextContent(type="text", text=json.dumps({"error": "Cannot connect to backend server"}))]
    except httpx.TimeoutException: return [TextContent(type="text", text=json.dumps({"error": "Request timed out"}))]
    except Exception: return [TextContent(type="text", text=json.dumps({"error": "An internal error occurred"}))]

async def run_mcp_server():
    async with stdio_server() as (r, w):
        await mcp_server.run(r, w, mcp_server.create_initialization_options())

if __name__ == "__main__":
    print("eNSP MCP Server starting..."); print(f"Connecting to {SERVER_URL}")
    asyncio.run(run_mcp_server())
