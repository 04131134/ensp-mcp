import asyncio, json, os, httpx
from urllib.parse import quote
ENSP_API_KEY = os.environ.get('ENSP_API_KEY', '')
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.types import Prompt, PromptMessage, PromptArgument
from mcp.server.stdio import stdio_server

MCP_SERVER_NAME = "ensp-mcp-server"
SERVER_URL = os.environ.get('ENSP_SERVER_URL', 'http://127.0.0.1:5000')
mcp_server = Server(MCP_SERVER_NAME)

_http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))

_MAX_RETRIES = 2
_RETRY_DELAY = 1.0

# ==================== AGENT SYSTEM PROMPT v3.0 ====================
AGENT_SYSTEM_PROMPT = """You are eNSP Network Agent Runtime with HCIE-level Huawei networking skills.

## ?? ԭ֪ʶ + ǿܽ

### ǿƹ򣨱أ
1. **Ŀ֪ʶ**κòǰȲѯĿе÷֪ʶ
2. **ֹƾմ**Ŀб׼ʱϸձ׼ִ
3. **ֹѯ**ʹ"֪"ôҲȲѯĿ֪ʶ
4. **úܽ**ÿɺ󣬱ִܽͼ¼

## ǿƹ̣Strict Workflow

### Phase 1: ֪ʶѯɣ
Step 1: Ŀ꣬ȡؼ
Step 2: ѯ÷
  - ʹ config_method_search ÷
  - ʹ config_method_get ȡ巽
  - ʹ config_method_steps ȡ׼
Step 3: ѯ֪ʶ⾭
  - ʹ agent_knowledge_search ؾ
  - ʹ get_config_guidance ȡָ
Step 4: ѯʷ
  - ʹ agent_memory_query ѯؼ

### Phase 2: ƻɣĿ֪ʶ
Step 5: ִмƻ
  -  Phase 1 ȡ֪ʶɼƻ
  - ʹ÷еı׼

### Phase 3: ִУϸ񰴼ƻ
Step 6: ִ
  - ϸռƻִУ
  - ʹ batch_command ִ
  - ¼ÿִн

### Phase 4: ?? ܽ¼ִУ

#### Step 7: ܽᣨǿƣ
ִú󣬱ܽ᣺

**ܽݣ**
1. Ŀ꣺ղõʲô
2. ýɹʧ
3. ɹбЩִгɹ
4. ʧбЩʧˣУ
5. ֤֤

**ܽʽ**
```
## ܽ

### Ŀ
[õĿ]

### ý
? ɹ / ? ʧ

### ִе
|  |  | ״̬ | ˵ |
|------|------|------|------|
| 1 | system-view | ? | ϵͳͼ |
| 2 | ospf 1 | ? | OSPF |
| ... | ... | ... | ... |

### ֤
- display ospf peer brief: []
- display ip routing-table: []

### ѵ
[õעȿӵ]
```

#### Step 8: ¼֪ʶ⣨ǿƣ
**뽫ɹü¼Ŀ֪ʶ⣺**

1. ¼÷⣨µ÷
```
config_method_add({
    "id": "ID",
    "name": "",
    "category": "",
    "steps": [ɹĲ],
    "verification": [֤]
})
```

2. ¼֪ʶ⾭飨ÿζҪ¼
```
record_experience({
    "experiment": "ʵ",
    "commands": [ɹб],
    "success": true/false,
    "lessons": ["ѵ"]
})
```

**¼**
- ֻ¼ִгɹ
- ·÷
- зʹͳƺͳɹ
- ¼֤ͽ

### Phase 5: 
Step 9: ܽû

## ΥΪϸֹ
- ? 겻ܽ
- ? ܽ˲¼֪ʶ
- ? ÷ѯ
- ? ƾմò
- ? ִ֤

## ʾ

û OSPF

Agent ִУ
1. config_method_search("OSPF")  ҵ ospf_basic
2. config_method_get("ospf_basic")  ȡ׼
3. ׼ִ
4. ִ֤
5. **ǿܽ**
   ```
   Ŀ꣺OSPF·Э
   ý? ɹ
   ɹsystem-view, ospf 1, router-id 1.1.1.1, area 0, network 192.168.1.0 0.0.0.255
   ```
6. **ǿƼ¼**
   -  ospf_basic ʹôͳɹ
   - ¼ʵ龭鵽֪ʶ

## ÷⹤
- config_method_list: г÷
- config_method_get: ȡ÷
- config_method_search: ÷
- config_method_steps: ȡ׼
- config_method_add: µ÷
- config_method_update: ÷ӳɹ飩

## ֪ʶ⹤
- agent_knowledge_search: ֪ʶ⾭
- get_config_guidance: ȡָ
- record_experience: ¼ʵ龭飨ʹã
- auto_record_experience: Զ¼
"""

async def mcp_req(method, path, json_data=None, params=None):
    headers = {}
    if ENSP_API_KEY:
        headers['X-API-Key'] = ENSP_API_KEY
    url = f"{SERVER_URL}{path}"
    last_error = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            if method == "GET":
                resp = await _http_client.get(url, params=params, headers=headers)
            elif method == "POST":
                resp = await _http_client.post(url, json=json_data, headers=headers)
            else:
                return json.dumps({"error": "Unsupported method"})
            if resp.status_code != 200:
                return json.dumps({"error": "Backend request failed", "status_code": resp.status_code, "detail": resp.text[:200]})
            return resp.text
        except httpx.ConnectError as e:
            last_error = f"Cannot connect to backend at {SERVER_URL}. Is app.py running?"
            if attempt < _MAX_RETRIES:
                import asyncio
                await asyncio.sleep(_RETRY_DELAY)
        except httpx.TimeoutException:
            last_error = f"Request to {url} timed out (attempt {attempt+1})"
            if attempt < _MAX_RETRIES:
                import asyncio
                await asyncio.sleep(_RETRY_DELAY)
    return json.dumps({"error": last_error})

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
    "config_summary": ["goal", "commands", "success"],
    "config_record_experience": ["experiment", "commands", "success"],
}

@mcp_server.list_tools()
async def list_tools():
    return [
        Tool(name="scan_devices", description="扫描指定端口范围的 eNSP 设备", inputSchema={"type":"object","properties":{"start":{"type":"integer","default":2000},"end":{"type":"integer","default":2050}}}),
        Tool(name="connect_device", description="连接 eNSP 设备，自动识别设备型号和获取主机名", inputSchema={"type":"object","properties":{"port":{"type":"integer","description":"˿ں(1-65535)"}},"required":["port"]}),
        Tool(name="send_command", description="向设备发送命令，自动记录知识库并关注错误信息", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"豸·"},"command":{"type":"string","description":"(1024ַ)"}},"required":["path","command"]}),
        Tool(name="disconnect_device", description="断开设备连接", inputSchema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
        Tool(name="get_connected_devices", description="获取当前已连接设备列表及其状态", inputSchema={"type":"object","properties":{}}),
        Tool(name="rename_device", description="重命名指定设备", inputSchema={"type":"object","properties":{"path":{"type":"string"},"name":{"type":"string"}},"required":["path","name"]}),
        Tool(name="fetch_device_name", description="从设备获取真实主机名", inputSchema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
        Tool(name="get_command_catalog", description="获取命令目录，包括支持的命令、参数说明、风险等级及支持设备类型。AI agent 用此了解整体能力", inputSchema={"type":"object","properties":{"category":{"type":"string","description":": display/config/verify/diagnostic"},"device_type":{"type":"string","description":"豸: huawei/h3c/cisco/juniper"},"risk":{"type":"string","description":": safe/low/medium/high"}}}),
        Tool(name="get_device_capabilities", description="获取设备能力：哪些命令可执行、哪些功能、哪些已验证成功。AI agent用此了解特定设备能力", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"豸·򷵻豸"}}}),
        Tool(name="get_device_history", description="获取设备执行历史：该设备成功/失败执行过哪些命令，用于结果预测", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"豸·򷵻豸"}}}),
        Tool(name="get_kb_commands", description="查询知识库中已记录的命令（全局），支持使用过滤条件", inputSchema={"type":"object","properties":{"category":{"type":"string"},"device_type":{"type":"string"},"risk":{"type":"string"},"limit":{"type":"integer","default":50}}}),
        Tool(name="get_kb_stats", description="知识库统计信息", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_topology", description="获取拓扑摘要", inputSchema={"type":"object","properties":{}}),
        Tool(name="save_topology", description="保存/更新拓扑数据", inputSchema={"type":"object","properties":{"data":{"type":"object","description":"nodeslinksJSON"}}}),
        Tool(name="find_topology_path", description="查找两个设备间最短路径", inputSchema={"type":"object","properties":{"start":{"type":"string"},"end":{"type":"string"}},"required":["start","end"]}),
        Tool(name="get_topology_device", description="获取设备的连接和端口信息", inputSchema={"type":"object","properties":{"node_id":{"type":"string"}},"required":["node_id"]}),
        Tool(name="get_structured_kb", description="获取结构化知识库（按拓扑视图/设备型号分类），可按 model 和 view_type 过滤", inputSchema={"type":"object","properties":{"model":{"type":"string","description":"豸ͺ: S5700/S3700/USG6000V/AR2220/AC6605"},"view_type":{"type":"string","description":"ͼ: user_view/system_view"}}}),
        Tool(name="suggest_commands", description="根据设备名称或型号推荐合适命令。参数为设备名如 LSW1/FW1/AR1/AC1 可自动匹配型号，不重复推荐型号", inputSchema={"type":"object","properties":{"model":{"type":"string","description":"豸ͺ: LSW1/S5700/FW1/AR1/AC1"},"view_type":{"type":"string","description":"ѡ: user_view/system_view"}},"required":["model"]}),
        Tool(name="scan_device_commands", description="扫描历史已连设备，自动识别型号，返回该型号下所有可用命令建议。连接设备前推荐使用", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"豸·127.0.0.1:2012"}},"required":["path"]}),
        Tool(name="get_best_practices", description="获取最佳实践规范（当前指定视图下：退出、信息中心、undo t m 等公共规范）", inputSchema={"type":"object","properties":{"priority":{"type":"string","description":": critical/high/medium"},"applies_to":{"type":"string","description":"豸ͺ"}}}),
        Tool(name="get_experiences", description="获取实验经验记录：每个实验的目标、命令、教训、注意事项", inputSchema={"type":"object","properties":{"experiment":{"type":"string","description":"ʵƹ"}}}),
        Tool(name="record_experience", description="记录实验经验（目标+命令+教训+注意事项），可自动归约到知识库", inputSchema={"type":"object","properties":{"experiment":{"type":"string"},"date":{"type":"string"},"topology":{"type":"string"},"features_implemented":{"type":"array","items":{"type":"string"}},"new_commands_learned":{"type":"array","items":{"type":"object"}},"lessons_learned":{"type":"array","items":{"type":"string"}},"troubleshooting_cases":{"type":"array","items":{"type":"object"}}},"required":["experiment"]}),
        Tool(name="detect_device_view", description="探测设备当前视图类型：< > 用户视图，[ ] 系统视图。命令执行前先探测", inputSchema={"type":"object","properties":{"prompt":{"type":"string","description":"նʾ<LSW1>[LSW1]"}},"required":["prompt"]}),
        Tool(name="get_config_order", description="获取推荐新设备配置顺序（20条），首次配置时参考", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_troubleshooting_kb", description="获取排错知识库（故障现象+原因+解决方案）", inputSchema={"type":"object","properties":{"symptom":{"type":"string","description":"֢״"}}}),
        Tool(name="reload_kb", description="重新加载结构化知识库（知识库文件外部修改后用）", inputSchema={"type":"object","properties":{}}),
        Tool(name="suggest_next_steps", description="增强型感知建议：根据设备已执行命令，推荐下一步配置操作并显示完成进度", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"豸·"}},"required":["path"]}),
        Tool(name="generate_lab_report", description="自动生成实验报告：包含所有设备配置、命令执行、知识库数据，输出 Markdown 格式", inputSchema={"type":"object","properties":{"name":{"type":"string","description":"ʵ"},"paths":{"type":"array","items":{"type":"string"},"description":"豸·б豸"}}}),
        Tool(name="auto_record_experience", description="自动提取设备已执行的命令序列，识别关键配置意图（AC/WLAN、OSPF、VLAN等）并归纳为实验记录", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"豸·"}},"required":["path"]}),
        Tool(name="batch_command", description="批量发送命令到设备，自动切换视图、自动 undo t m，一次最多 200 条", inputSchema={"type":"object","properties":{"path":{"type":"string"},"commands":{"type":"array","items":{"type":"string"}},"wait":{"type":"number","default":0.1},"auto_view":{"type":"boolean","default":True},"auto_undo_tm":{"type":"boolean","default":True}},"required":["path","commands"]}),
        Tool(name="snapshot_config", description="为设备配置创建快照（执行 display current-configuration 后保存）", inputSchema={"type":"object","properties":{"path":{"type":"string"},"label":{"type":"string"}},"required":["path"]}),
        Tool(name="list_snapshots", description="列出所有配置快照，可按设备路径过滤", inputSchema={"type":"object","properties":{"path":{"type":"string"}}}),
        Tool(name="get_snapshot", description="获取指定快照内容", inputSchema={"type":"object","properties":{"snapshot_id":{"type":"string"}},"required":["snapshot_id"]}),
        Tool(name="diff_snapshots", description="比较两个配置快照的差异", inputSchema={"type":"object","properties":{"snapshot1":{"type":"string"},"snapshot2":{"type":"string"}},"required":["snapshot1","snapshot2"]}),
        Tool(name="rollback_config", description="回滚设备配置到指定快照", inputSchema={"type":"object","properties":{"path":{"type":"string"},"snapshot_id":{"type":"string"}},"required":["path","snapshot_id"]}),
        Tool(name="search_kb", description="知识库全文搜索：命令、排错经验、实验记录", inputSchema={"type":"object","properties":{"q":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["q"]}),
        Tool(name="get_command_help", description="查询特定命令的帮助信息，从知识库返回用法和示例", inputSchema={"type":"object","properties":{"cmd":{"type":"string"}},"required":["cmd"]}),
        Tool(name="generate_config_template", description="生成配置模板，支持 vlan/vrrp/mstp/dhcp/ospf/lacp/wlan", inputSchema={"type":"object","properties":{"type":{"type":"string"},"params":{"type":"object"}},"required":["type"]}),
        Tool(name="list_templates", description="列出所有可用的配置模板", inputSchema={"type":"object","properties":{}}),
        Tool(name="group_command", description="对多台设备发送相同命令", inputSchema={"type":"object","properties":{"paths":{"type":"array","items":{"type":"string"}},"command":{"type":"string"}},"required":["paths","command"]}),
        Tool(name="get_config_guidance", description="根据场景获取配置指导。融合知识库中相关的经验、规范、失败案例。AI agent 用此快速定位配置路径", inputSchema={"type":"object","properties":{"topic":{"type":"string","description":": AC WLAN VLAN OSPF APߵ"}},"required":["topic"]}),
    
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
        Tool(name="config_method_list", description="列出所有配置方法（按类别组织的标准流程）", inputSchema={"type":"object","properties":{"category":{"type":"string","description":"ѡ: routing/switching/security/wireless/services/management"}}}),
        Tool(name="config_method_get", description="获取指定配置方法的详细信息：包含步骤、验证命令、注意事项等", inputSchema={"type":"object","properties":{"method_id":{"type":"string","description":"ID ospf_basicvlan_config"}},"required":["method_id"]}),
        Tool(name="config_method_search", description="搜索配置方法", inputSchema={"type":"object","properties":{"keyword":{"type":"string","description":"ؼ"}},"required":["keyword"]}),
        Tool(name="config_method_add", description="添加新的配置方法到知识库", inputSchema={"type":"object","properties":{"method_data":{"type":"object","description":"ݣ id/name/category/steps ֶ"}},"required":["method_data"]}),
        Tool(name="config_method_steps", description="获取配置方法的步骤命令列表，可直接执行的命令序列", inputSchema={"type":"object","properties":{"method_id":{"type":"string","description":"ID"}},"required":["method_id"]}),
        Tool(name="config_method_update", description="更新配置方法：添加成功经验、更新成功率等", inputSchema={"type":"object","properties":{"method_id":{"type":"string","description":"ID"},"updates":{"type":"object","description":"Ҫµֶ"}},"required":["method_id","updates"]}),
        Tool(name="config_summary", description="对配置进行总结并记录到知识库（配置后每条配置用）", inputSchema={"type":"object","properties":{"goal":{"type":"string","description":"Ŀ"},"commands":{"type":"array","items":{"type":"string"},"description":"ִгɹб"},"success":{"type":"boolean","description":"Ƿɹ"},"verification_results":{"type":"array","items":{"type":"string"},"description":"֤"},"lessons":{"type":"array","items":{"type":"string"},"description":"ѵ"}},"required":["goal","commands","success"]}),
        Tool(name="config_record_experience", description="记录配置经验到知识库", inputSchema={"type":"object","properties":{"experiment":{"type":"string","description":"ʵ"},"commands":{"type":"array","items":{"type":"string"},"description":"ɹб"},"success":{"type":"boolean","description":"Ƿɹ"},"lessons":{"type":"array","items":{"type":"string"},"description":"ѵ"}},"required":["experiment","commands","success"]}),
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
        # ---- Agent Runtime v3.0 ----
        elif name == "agent_memory_query":
            params = {"limit": arguments.get("limit", 20)}
            if arguments.get("query"): params["query"] = arguments["query"]
            if arguments.get("category"): params["category"] = arguments["category"]
            text = await mcp_req("GET", "/api/agent/memory", params=params)
        elif name == "agent_memory_lessons":
            text = await mcp_req("GET", "/api/agent/memory/lessons")
        elif name == "agent_memory_stats":
            text = await mcp_req("GET", "/api/agent/memory/stats")
        elif name == "agent_knowledge_search":
            params = {"limit": arguments.get("limit", 20)}
            if arguments.get("query"): params["query"] = arguments["query"]
            if arguments.get("category"): params["category"] = arguments["category"]
            if arguments.get("device_type"): params["device_type"] = arguments["device_type"]
            text = await mcp_req("GET", "/api/agent/knowledge/search", params=params)
        elif name == "agent_knowledge_best_practices":
            text = await mcp_req("GET", "/api/agent/knowledge/best-practices")
        elif name == "agent_knowledge_troubleshooting":
            params = {}
            if arguments.get("query"): params["query"] = arguments["query"]
            text = await mcp_req("GET", "/api/agent/knowledge/troubleshooting", params=params)
        elif name == "agent_plan":
            text = await mcp_req("POST", "/api/agent/plan", json_data={"goal": arguments["goal"], "experiment_type": arguments.get("experiment_type", "general")})
        elif name == "agent_execute":
            text = await mcp_req("POST", "/api/agent/execute", json_data={"request": arguments["request"], "device_paths": arguments.get("device_paths", []), "experiment_type": arguments.get("experiment_type", "general"), "constraints": arguments.get("constraints", [])})
        elif name == "agent_status":
            text = await mcp_req("GET", "/api/agent/status")
        elif name == "agent_daily_review":
            text = await mcp_req("POST", "/api/agent/learning/daily-review")
        # ---- ÷ ----
        elif name == "config_method_list":
            text = await mcp_req("GET", "/api/config-methods/list", params={"category": arguments.get("category", "")})
        elif name == "config_method_get":
            text = await mcp_req("GET", f"/api/config-methods/get/{arguments['method_id']}")
        elif name == "config_method_search":
            text = await mcp_req("GET", "/api/config-methods/search", params={"keyword": arguments["keyword"]})
        elif name == "config_method_add":
            text = await mcp_req("POST", "/api/config-methods/add", json_data=arguments["method_data"])
        elif name == "config_method_steps":
            text = await mcp_req("GET", f"/api/config-methods/steps/{arguments['method_id']}")
        elif name == "config_method_update":
            text = await mcp_req("POST", f"/api/config-methods/update/{arguments['method_id']}", json_data=arguments["updates"])
        elif name == "config_summary":
            text = await mcp_req("POST", "/api/config-summary", json_data={
                "goal": arguments["goal"],
                "commands": arguments["commands"],
                "success": arguments["success"],
                "verification_results": arguments.get("verification_results", []),
                "lessons": arguments.get("lessons", [])
            })
        elif name == "config_record_experience":
            text = await mcp_req("POST", "/api/kb/experience", json_data={
                "experiment": arguments["experiment"],
                "commands": arguments["commands"],
                "success": arguments["success"],
                "lessons": arguments.get("lessons", [])
            })

        else: text = json.dumps({"error": "Unknown tool"})
        return [TextContent(type="text", text=text)]
    except httpx.ConnectError: return [TextContent(type="text", text=json.dumps({"error": "Cannot connect to backend server"}))]
    except httpx.TimeoutException: return [TextContent(type="text", text=json.dumps({"error": "Request timed out"}))]
    except Exception: return [TextContent(type="text", text=json.dumps({"error": "An internal error occurred"}))]

async def check_backend_health():
    """Probe backend readiness before accepting MCP tool calls."""
    import asyncio
    for attempt in range(10):
        try:
            resp = await _http_client.get(f"{SERVER_URL}/api/health")
            if resp.status_code == 200:
                data = resp.json()
                print(f"Backend ready: {data.get('devices', 0)} devices, KB loaded")
                return True
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        if attempt < 9:
            print(f"Waiting for backend... (attempt {attempt+1}/10)")
            await asyncio.sleep(2)
    print(f"WARNING: Backend at {SERVER_URL} not reachable after 10 attempts")
    return False

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
    print("eNSP MCP Server starting...")
    print(f"Backend target: {SERVER_URL}")
    asyncio.run(check_backend_health())


