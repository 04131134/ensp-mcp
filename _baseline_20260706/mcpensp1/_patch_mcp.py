import pathlib, base64, re
path = pathlib.Path(r'E:/eNSP-MCP/mcpensp1/mcp_server.py')
text = path.read_text(encoding='utf-8')
if 'create_experiment' not in text:
    tool_block = '''        Tool(
            name="create_experiment",
            description="创建实验状态实例，用于持续跟踪拓扑、设备、接口、协议与验证结果。",
            inputSchema={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "name": {"type": "string"},
                    "goal": {"type": "string"},
                    "devices": {"type": "array", "items": {"type": "object"}},
                    "topology": {"type": "object"},
                    "constraints": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["experiment_id", "name"]
            }
        ),
        Tool(
            name="get_experiment",
            description="获取实验快照，包含当前状态、历史阶段和验证结果。",
            inputSchema={"type": "object", "properties": {"experiment_id": {"type": "string"}}, "required": ["experiment_id"]}
        ),
        Tool(
            name="update_experiment_device",
            description="更新实验中的设备状态（连接状态、型号、标签等）。",
            inputSchema={"type": "object", "properties": {"experiment_id": {"type": "string"}, "path": {"type": "string"}, "name": {"type": "string"}, "device_type": {"type": "string"}, "model": {"type": "string"}, "connected": {"type": "boolean"}}, "required": ["experiment_id", "path"]}
        ),
        Tool(
            name="update_experiment_interface",
            description="更新实验中的接口状态或 IP 信息。",
            inputSchema={"type": "object", "properties": {"experiment_id": {"type": "string"}, "path": {"type": "string"}, "interface": {"type": "string"}, "status": {"type": "string"}, "ip": {"type": "string"}, "mask": {"type": "string"}}, "required": ["experiment_id", "path", "interface"]}
        ),
        Tool(
            name="record_experiment_protocol",
            description="记录协议层状态（OSPF 邻居、VLAN 列表、路由摘要等）。",
            inputSchema={"type": "object", "properties": {"experiment_id": {"type": "string"}, "path": {"type": "string"}, "protocol": {"type": "string"}, "state": {}}, "required": ["experiment_id", "path", "protocol"]}
        ),
        Tool(
            name="add_experiment_link",
            description="记录实验拓扑链路信息。",
            inputSchema={"type": "object", "properties": {"experiment_id": {"type": "string"}, "source": {"type": "string"}, "target": {"type": "string"}, "source_interface": {"type": "string"}, "target_interface": {"type": "string"}}, "required": ["experiment_id", "source", "target"]}
        ),
        Tool(
            name="execute_experiment_phase",
            description="执行单个实验阶段并自动进行前置条件检查与执行后验证。",
            inputSchema={"type": "object", "properties": {"experiment_id": {"type": "string"}, "phase_id": {"type": "string"}, "auto_verify": {"type": "boolean"}, "dry_run": {"type": "boolean"}}, "required": ["experiment_id", "phase_id"]}
        ),
        Tool(
            name="execute_experiment_plan",
            description="执行整套实验计划（含依赖顺序），失败时自动触发恢复策略。",
            inputSchema={"type": "object", "properties": {"experiment_id": {"type": "string"}, "ordered_phases": {"type": "array", "items": {"type": "string"}}, "context": {"type": "object"}, "auto_verify": {"type": "boolean"}, "max_retries": {"type": "integer"}}, "required": ["experiment_id", "ordered_phases"]}
        ),
        Tool(
            name="verify_experiment_device",
            description="对实验中某台设备执行验证检查（接口、OSPF、路由、连通性等）。",
            inputSchema={"type": "object", "properties": {"experiment_id": {"type": "string"}, "path": {"type": "string"}, "checks": {"type": "array", "items": {"type": "string"}}, "target_ip": {"type": "string"}}, "required": ["experiment_id", "path"]}
        ),
        Tool(
            name="get_experiment_phases",
            description="获取全部可用实验阶段定义。",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_experiment_dependency_graph",
            description="获取实验阶段依赖关系图。",
            inputSchema={"type": "object", "properties": {}}
        ),
'''
    text = text.replace('        Tool(\n            name="group_command",', tool_block + '        Tool(\n            name="group_command",', 1)
old = '        # ---- 批量 ----\n        elif name == "group_command":'
new = '''        # ---- 实验状态 ----
        elif name == "create_experiment":
            text = await mcp_req("POST", "/api/experiments", json_data=arguments)
        elif name == "get_experiment":
            text = await mcp_req("GET", f"/api/experiments/{quote(str(arguments['experiment_id']), safe='')}")
        elif name == "update_experiment_device":
            text = await mcp_req("POST", f"/api/experiments/{quote(str(arguments['experiment_id']), safe='')}/device", json_data=arguments)
        elif name == "update_experiment_interface":
            text = await mcp_req("POST", f"/api/experiments/{quote(str(arguments['experiment_id']), safe='')}/interface", json_data=arguments)
        elif name == "record_experiment_protocol":
            text = await mcp_req("POST", f"/api/experiments/{quote(str(arguments['experiment_id']), safe='')}/protocol", json_data=arguments)
        elif name == "add_experiment_link":
            text = await mcp_req("POST", f"/api/experiments/{quote(str(arguments['experiment_id']), safe='')}/link", json_data=arguments)
        elif name == "execute_experiment_phase":
            text = await mcp_req("POST", f"/api/experiments/{quote(str(arguments['experiment_id']), safe='')}/execute", json_data=arguments)
        elif name == "execute_experiment_plan":
            text = await mcp_req("POST", f"/api/experiments/{quote(str(arguments['experiment_id']), safe='')}/plan", json_data=arguments)
        elif name == "verify_experiment_device":
            text = await mcp_req("POST", f"/api/experiments/{quote(str(arguments['experiment_id']), safe='')}/verify", json_data=arguments)
        elif name == "get_experiment_phases":
            text = await mcp_req("GET", "/api/experiments/phases")
        elif name == "get_experiment_dependency_graph":
            text = await mcp_req("GET", "/api/experiments/dependency-graph")
        # ---- 批量 ----
        elif name == "group_command":'''
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('patched')
