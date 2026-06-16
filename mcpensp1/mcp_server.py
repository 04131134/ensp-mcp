import asyncio, json, os, httpx
ENSP_API_KEY = os.environ.get('ENSP_API_KEY', '')
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

MCP_SERVER_NAME = "ensp-mcp-server"
SERVER_URL = os.environ.get('ENSP_SERVER_URL', 'http://127.0.0.1:5000')
mcp_server = Server(MCP_SERVER_NAME)

async def mcp_req(method, path, json_data=None, params=None):
    timeout = httpx.Timeout(30.0, connect=5.0)
    headers = {}
    if ENSP_API_KEY:
        headers['X-API-Key'] = ENSP_API_KEY
    async with httpx.AsyncClient(timeout=timeout) as c:
        url = f"{SERVER_URL}{path}"
        if method == "GET": resp = await c.get(url, params=params, headers=headers)
        elif method == "POST": resp = await c.post(url, json=json_data, headers=headers)
        else: return json.dumps({"error": "Unsupported method"})
        return resp.text

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
    ]

@mcp_server.call_tool()
async def call_tool(name, arguments):
    try:
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
            text = await mcp_req("GET", f"/api/kb/devices/{arguments['path']}") if arguments.get("path") else await mcp_req("GET", "/api/kb/devices")
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
        elif name == "get_topology_device": text = await mcp_req("GET", f"/api/topology/device/{arguments['node_id']}")
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
        else: text = json.dumps({"error": "Unknown tool"})
        return [TextContent(type="text", text=text)]
    except httpx.ConnectError: return [TextContent(type="text", text=json.dumps({"error": f"无法连接 {SERVER_URL}，请确保 app.py 运行中"}))]
    except httpx.TimeoutException: return [TextContent(type="text", text=json.dumps({"error": "请求超时"}))]
    except Exception as e: return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

async def run_mcp_server():
    async with stdio_server() as (r, w):
        await mcp_server.run(r, w, mcp_server.create_initialization_options())

if __name__ == '__main__':
    print("eNSP MCP Server starting..."); print(f"Connecting to {SERVER_URL}")
    asyncio.run(run_mcp_server())