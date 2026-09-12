# eNSP-MCP MCP 工具参考 (v3.0)

> 本文件由代码 `mcp_server.py` 自动提取生成，覆盖全部 **47 个**已实现的 MCP 工具。

> 文档随版本 3.0 发布。每个工具含：**参数表 + 调用示例 + 依赖说明**。所有工具统一以 JSON 文本返回（见「返回格式」）。


## 调用前置条件

- **MCP Server**：`cd mcpensp1 && python mcp_server.py`（stdio 模式，无需 Flask 即可启动）。
- **设备路径格式**：`127.0.0.1:<telnet_port>`（例如 `127.0.0.1:2001`）。先用 `scan_devices` 发现端口，再用 `connect_device` 建立连接，之后所有设备操作均用该 path 定位。
- **依赖形态**：全部工具均为**直连型**，在 MCP Server 进程内直接操作设备/知识库/拓扑。
  历史版本的 HTTP 代理模式（「后端型」）已按 ADR-002 移除，`mcp_req` 仅作为抛异常的兼容占位。
- Flask（`python app.py`）只服务于 Web 控制台，MCP Server 的启动不依赖它。


## 返回格式（通用）

所有工具返回统一的 JSON 字符串（封装在 MCP `TextContent` 中）：

- **直连型**：返回结构因工具而异，常见为 `{"success": true, ...}` 或数据对象；失败返回 `{"error": "..."}`。
- 调用方应解析该 JSON 文本获取字段。


## 工具总览（47 个）

| 分类 | 数量 | 工具 |
|---|---|---|
| 设备连接 | 7 | `scan_devices`、`connect_device`、`send_command`、`disconnect_device`、`get_connected_devices`、`rename_device`、`fetch_device_name` |
| 批量命令 | 2 | `batch_command`、`group_command` |
| 知识库 | 18 | `get_command_catalog`、`get_device_capabilities`、`get_device_history`、`get_kb_commands`、`get_kb_stats`、`get_structured_kb`、`suggest_commands`、`scan_device_commands`、`get_best_practices`、`get_experiences`、`record_experience`、`detect_device_view`、`get_troubleshooting_kb`、`reload_kb`、`generate_lab_report`、`auto_record_experience`、`search_kb`、`get_command_help` |
| 拓扑 | 4 | `get_topology`、`save_topology`、`find_topology_path`、`get_topology_device` |
| 配置方法 | 6 | `config_method_list`、`config_method_get`、`config_method_search`、`config_method_add`、`config_method_steps`、`config_method_update` |
| Agent 工具 | 10 | `agent_memory_query`、`agent_memory_lessons`、`agent_memory_stats`、`agent_knowledge_search`、`agent_knowledge_best_practices`、`agent_knowledge_troubleshooting`、`agent_plan`、`agent_execute`、`agent_status`、`agent_daily_review` |


---

## 设备连接

### `scan_devices`

**说明**：扫描指定端口范围的 eNSP 设备

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `start` | integer | — | `2000` |  |
| `end` | integer | — | `2050` |  |


**调用示例**：

```json
{
  "tool": "scan_devices",
  "arguments": {
    "start": 2000,
    "end": 2050
  }
}
```

### `connect_device`

**说明**：连接 eNSP 设备，自动识别设备型号和获取主机名

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `port` | integer | ✅ | — | 端口(1-65535) |


**调用示例**：

```json
{
  "tool": "connect_device",
  "arguments": {
    "port": 0
  }
}
```

### `send_command`

**说明**：向设备发送命令，自动记录知识库并关注错误信息

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | ✅ | — | 设备路径 |
| `command` | string | ✅ | — | (最多1024字符) |


**调用示例**：

```json
{
  "tool": "send_command",
  "arguments": {
    "path": "<path>",
    "command": "<command>"
  }
}
```

### `disconnect_device`

**说明**：断开设备连接

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | ✅ | — |  |


**调用示例**：

```json
{
  "tool": "disconnect_device",
  "arguments": {
    "path": "<path>"
  }
}
```

### `get_connected_devices`

**说明**：获取当前已连接设备列表及其状态

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

_无参数_


**调用示例**：

```json
{
  "tool": "get_connected_devices",
  "arguments": {}
}
```

### `rename_device`

**说明**：重命名指定设备

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | ✅ | — |  |
| `name` | string | ✅ | — |  |


**调用示例**：

```json
{
  "tool": "rename_device",
  "arguments": {
    "path": "<path>",
    "name": "<name>"
  }
}
```

### `fetch_device_name`

**说明**：从设备获取真实主机名

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | ✅ | — |  |


**调用示例**：

```json
{
  "tool": "fetch_device_name",
  "arguments": {
    "path": "<path>"
  }
}
```


---

## 批量命令

### `batch_command`

**说明**：批量发送命令到设备，自动切换视图、自动 undo t m，一次最多 200 条

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | ✅ | — |  |
| `commands` | array | ✅ | — |  |
| `wait` | number | — | `0.1` |  |
| `auto_view` | boolean | — | `True` |  |
| `auto_undo_tm` | boolean | — | `True` |  |


**调用示例**：

```json
{
  "tool": "batch_command",
  "arguments": {
    "path": "<path>",
    "commands": [],
    "wait": 0.1,
    "auto_view": true,
    "auto_undo_tm": true
  }
}
```

### `group_command`

**说明**：对多台设备发送相同命令

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `paths` | array | ✅ | — |  |
| `command` | string | ✅ | — |  |


**调用示例**：

```json
{
  "tool": "group_command",
  "arguments": {
    "paths": [],
    "command": "<command>"
  }
}
```


---

## 知识库

### `get_command_catalog`

**说明**：获取命令目录，包括支持的命令、参数说明、风险等级及支持设备类型。AI agent 用此了解整体能力

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `category` | string | — | — | : display/config/verify/diagnostic |
| `device_type` | string | — | — | 设备类型: huawei/h3c/cisco/juniper |
| `risk` | string | — | — | : safe/low/medium/high |


**调用示例**：

```json
{
  "tool": "get_command_catalog",
  "arguments": {}
}
```

### `get_device_capabilities`

**说明**：获取设备能力：哪些命令可执行、哪些功能、哪些已验证成功。AI agent用此了解特定设备能力

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | — | — | 设备路径 |


**调用示例**：

```json
{
  "tool": "get_device_capabilities",
  "arguments": {}
}
```

### `get_device_history`

**说明**：获取设备执行历史：该设备成功/失败执行过哪些命令，用于结果预测

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | — | — | 设备路径 |


**调用示例**：

```json
{
  "tool": "get_device_history",
  "arguments": {}
}
```

### `get_kb_commands`

**说明**：查询知识库中已记录的命令（全局），支持使用过滤条件

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `category` | string | — | — |  |
| `device_type` | string | — | — |  |
| `risk` | string | — | — |  |
| `limit` | integer | — | `50` |  |


**调用示例**：

```json
{
  "tool": "get_kb_commands",
  "arguments": {
    "limit": 50
  }
}
```

### `get_kb_stats`

**说明**：知识库统计信息

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

_无参数_


**调用示例**：

```json
{
  "tool": "get_kb_stats",
  "arguments": {}
}
```

### `get_structured_kb`

**说明**：获取结构化知识库（按拓扑视图/设备型号分类），可按 model 和 view_type 过滤

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | — | — | 型号: S5700/S3700/USG6000V/AR2220/AC6605 |
| `view_type` | string | — | — | 视图: user_view/system_view |


**调用示例**：

```json
{
  "tool": "get_structured_kb",
  "arguments": {}
}
```

### `suggest_commands`

**说明**：根据设备名称或型号推荐合适命令。参数为设备名如 LSW1/FW1/AR1/AC1 可自动匹配型号，不重复推荐型号

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | ✅ | — | 型号: LSW1/S5700/FW1/AR1/AC1 |
| `view_type` | string | — | — | 可选: user_view/system_view |


**调用示例**：

```json
{
  "tool": "suggest_commands",
  "arguments": {
    "model": "<model>"
  }
}
```

### `scan_device_commands`

**说明**：扫描历史已连设备，自动识别型号，返回该型号下所有可用命令建议。连接设备前推荐使用

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | ✅ | — | 设备 127.0.0.1:2012 |


**调用示例**：

```json
{
  "tool": "scan_device_commands",
  "arguments": {
    "path": "<path>"
  }
}
```

### `get_best_practices`

**说明**：获取最佳实践规范（当前指定视图下：退出、信息中心、undo t m 等公共规范）

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `priority` | string | — | — | : critical/high/medium |
| `applies_to` | string | — | — | 型号 |


**调用示例**：

```json
{
  "tool": "get_best_practices",
  "arguments": {}
}
```

### `get_experiences`

**说明**：获取实验经验记录：每个实验的目标、命令、教训、注意事项

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `experiment` | string | — | — | 实验 |


**调用示例**：

```json
{
  "tool": "get_experiences",
  "arguments": {}
}
```

### `record_experience`

**说明**：记录实验经验（目标+命令+教训+注意事项），可自动归约到知识库

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `experiment` | string | ✅ | — |  |
| `date` | string | — | — |  |
| `topology` | string | — | — |  |
| `features_implemented` | array | — | — |  |
| `new_commands_learned` | array | — | — |  |
| `lessons_learned` | array | — | — |  |
| `troubleshooting_cases` | array | — | — |  |


**调用示例**：

```json
{
  "tool": "record_experience",
  "arguments": {
    "experiment": "<experiment>"
  }
}
```

### `detect_device_view`

**说明**：探测设备当前视图类型：< > 用户视图，[ ] 系统视图。命令执行前先探测

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `prompt` | string | ✅ | — | 示例<LSW1>[LSW1] |


**调用示例**：

```json
{
  "tool": "detect_device_view",
  "arguments": {
    "prompt": "<prompt>"
  }
}
```

### `get_troubleshooting_kb`

**说明**：获取排错知识库（故障现象+原因+解决方案）

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `symptom` | string | — | — | 症状 |


**调用示例**：

```json
{
  "tool": "get_troubleshooting_kb",
  "arguments": {}
}
```

### `reload_kb`

**说明**：重新加载结构化知识库（知识库文件外部修改后用）

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

_无参数_


**调用示例**：

```json
{
  "tool": "reload_kb",
  "arguments": {}
}
```

### `generate_lab_report`

**说明**：自动生成实验报告：包含已连接设备与知识库统计，"markdown" 字段为 Markdown 正文

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | string | — | — | 实验 |
| `paths` | array | — | — | 设备列表 |


**调用示例**：

```json
{
  "tool": "generate_lab_report",
  "arguments": {}
}
```

### `auto_record_experience`

**说明**：自动提取知识库中已记录的该设备命令序列，识别关键配置意图（AC/WLAN、OSPF、VLAN等）并归纳为实验记录

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | ✅ | — | 设备路径 |


**调用示例**：

```json
{
  "tool": "auto_record_experience",
  "arguments": {
    "path": "<path>"
  }
}
```

### `search_kb`

**说明**：知识库全文搜索：命令、排错经验、实验记录

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `q` | string | ✅ | — |  |
| `limit` | integer | — | `20` |  |


**调用示例**：

```json
{
  "tool": "search_kb",
  "arguments": {
    "q": "<q>",
    "limit": 20
  }
}
```

### `get_command_help`

**说明**：查询特定命令的帮助信息，从知识库返回用法和示例

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `cmd` | string | ✅ | — |  |


**调用示例**：

```json
{
  "tool": "get_command_help",
  "arguments": {
    "cmd": "<cmd>"
  }
}
```


---

## 拓扑

### `get_topology`

**说明**：获取拓扑摘要

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

_无参数_


**调用示例**：

```json
{
  "tool": "get_topology",
  "arguments": {}
}
```

### `save_topology`

**说明**：保存/更新拓扑数据

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `data` | object | — | — | nodeslinksJSON |


**调用示例**：

```json
{
  "tool": "save_topology",
  "arguments": {}
}
```

### `find_topology_path`

**说明**：查找两个设备间最短路径

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `start` | string | ✅ | — |  |
| `end` | string | ✅ | — |  |


**调用示例**：

```json
{
  "tool": "find_topology_path",
  "arguments": {
    "start": "<start>",
    "end": "<end>"
  }
}
```

### `get_topology_device`

**说明**：获取设备的连接和端口信息

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `node_id` | string | ✅ | — |  |


**调用示例**：

```json
{
  "tool": "get_topology_device",
  "arguments": {
    "node_id": "<node_id>"
  }
}
```


---

## 配置方法

### `config_method_list`

**说明**：列出所有配置方法（按类别组织的标准流程）

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `category` | string | — | — | 可选: routing/switching/security/wireless/services/management |


**调用示例**：

```json
{
  "tool": "config_method_list",
  "arguments": {}
}
```

### `config_method_get`

**说明**：获取指定配置方法的详细信息：包含步骤、验证命令、注意事项等

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `method_id` | string | ✅ | — | ID ospf_basicvlan_config |


**调用示例**：

```json
{
  "tool": "config_method_get",
  "arguments": {
    "method_id": "<method_id>"
  }
}
```

### `config_method_search`

**说明**：搜索配置方法

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `keyword` | string | ✅ | — | 关键词 |


**调用示例**：

```json
{
  "tool": "config_method_search",
  "arguments": {
    "keyword": "<keyword>"
  }
}
```

### `config_method_add`

**说明**：添加新的配置方法到知识库

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `method_data` | object | ✅ | — | 包含 id/name/category/steps 等字段 |


**调用示例**：

```json
{
  "tool": "config_method_add",
  "arguments": {
    "method_data": {}
  }
}
```

### `config_method_steps`

**说明**：获取配置方法的步骤命令列表，可直接执行的命令序列

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `method_id` | string | ✅ | — | ID |


**调用示例**：

```json
{
  "tool": "config_method_steps",
  "arguments": {
    "method_id": "<method_id>"
  }
}
```

### `config_method_update`

**说明**：更新配置方法：添加成功经验、更新成功率等

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `method_id` | string | ✅ | — | ID |
| `updates` | object | ✅ | — | 需要更新的字段 |


**调用示例**：

```json
{
  "tool": "config_method_update",
  "arguments": {
    "method_id": "<method_id>",
    "updates": {}
  }
}
```


---

## Agent 工具

### `agent_memory_query`

**说明**：[Memory Query] Query Agent long-term memory

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | — | — |  |
| `category` | string | — | — |  |
| `limit` | integer | — | `20` |  |


**调用示例**：

```json
{
  "tool": "agent_memory_query",
  "arguments": {
    "limit": 20
  }
}
```

### `agent_memory_lessons`

**说明**：[Lessons] Get lessons from experiments

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

_无参数_


**调用示例**：

```json
{
  "tool": "agent_memory_lessons",
  "arguments": {}
}
```

### `agent_memory_stats`

**说明**：[Memory Stats] Memory statistics

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

_无参数_


**调用示例**：

```json
{
  "tool": "agent_memory_stats",
  "arguments": {}
}
```

### `agent_knowledge_search`

**说明**：[Knowledge Search] Search growing knowledge base

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | — | — |  |
| `category` | string | — | — |  |
| `device_type` | string | — | — |  |
| `limit` | integer | — | `20` |  |


**调用示例**：

```json
{
  "tool": "agent_knowledge_search",
  "arguments": {
    "limit": 20
  }
}
```

### `agent_knowledge_best_practices`

**说明**：[Best Practices] Network config best practices

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

_无参数_


**调用示例**：

```json
{
  "tool": "agent_knowledge_best_practices",
  "arguments": {}
}
```

### `agent_knowledge_troubleshooting`

**说明**：[Troubleshooting] Historical troubleshooting cases

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | — | — |  |


**调用示例**：

```json
{
  "tool": "agent_knowledge_troubleshooting",
  "arguments": {}
}
```

### `agent_plan`

**说明**：[Smart Planning] Generate DAG execution plan. USE BEFORE config.

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `goal` | string | ✅ | — |  |
| `experiment_type` | string | — | — |  |


**调用示例**：

```json
{
  "tool": "agent_plan",
  "arguments": {
    "goal": "<goal>"
  }
}
```

### `agent_execute`

**说明**：[Full Experiment] One-click closed-loop experiment. RECOMMENDED.

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `request` | string | ✅ | — |  |
| `device_paths` | array | — | — |  |
| `experiment_type` | string | — | — |  |
| `constraints` | array | — | — |  |


**调用示例**：

```json
{
  "tool": "agent_execute",
  "arguments": {
    "request": "<request>"
  }
}
```

### `agent_status`

**说明**：[Agent Status] Runtime status and stats

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

_无参数_


**调用示例**：

```json
{
  "tool": "agent_status",
  "arguments": {}
}
```

### `agent_daily_review`

**说明**：[Daily Review] Memory review and optimization

**依赖**：**直连型** —— 仅 MCP Server 即可


**参数**：

_无参数_


**调用示例**：

```json
{
  "tool": "agent_daily_review",
  "arguments": {}
}
```

