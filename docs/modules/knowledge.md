# 知识层 (KnowledgeBase) 模块文档 v3.0

## 概述
`KnowledgeBase` 定义在 `mcpensp1/knowledge.py`，是命令 / 经验 / 最佳实践 / 排错案例的**结构化知识库**。

- 由 `services.py` 实例化为模块级 `kb`，供 MCP 工具（`mcp_server.py`）调用。
- Flask Web 层（`app.py`）通过 `from services import kb` **复用同一实例**，自身不再重复定义 `KnowledgeBase`。
- v2.4 起 `record_experience` 简化（仅记录 topic + device_type + commands + lessons），自动归纳逻辑收敛到 `_auto_record_knowledge`。

## 数据文件
- **设备历史**：`kb/devices_kb.json` —— 每台设备执行过 / 失败过的命令
- **全局命令**：`kb/global_kb.json` —— 全量命令使用记录
- **结构化命令库**：`kb/structured_commands_kb.json` —— 用户/系统视图命令、最佳实践、经验、排错案例
- **配置方法**：`kb/config_methods/*.json` —— 标准配置流程

## 与 Agent 知识库的关系
`agent/knowledge_store.py` 的 `KnowledgeStore` 是 **Agent 学习 / 记录库**（记录式增长数据，方法为 search / get_stats / export_for_sharing / import_shared），与本文的 `KnowledgeBase`（结构化命令知识库）**数据模型与方法均不同**，是两套独立系统，**不合并**。

## 主要方法

| 方法 | 返回 | 说明 |
|------|--------|-----------|
| `record_command(cmd, output, ...)` | `None` | 记录命令执行结果到 devices_kb + global_kb |
| `record_experience(data)` | `{"success": bool}` | **v2.4 简化**：仅 topic + device_type + commands + lessons |
| `_auto_record_knowledge(...)` | `None` | **v2.4 简化**：自动归纳配置意图 |
| `get_stats()` | `{"total": int, ...}` | 统计 |
| `get_experiences(experiment)` | `List[Dict]` | 读取经验 |
| `get_device_history(path)` | `List[Dict]` | 设备命令历史 |
| `get_device_capabilities(path)` | `Dict` | 设备能力（verified/supported/failed/unsupported） |
| `get_global_commands(...)` | `List[Dict]` | 全局命令（可按 category/device_type/risk 过滤） |
| `get_command_catalog(...)` | `Dict` | 命令目录（来自 COMMAND_CATALOG） |
| `search_experiences(query)` | `List[Dict]` | 搜索经验 |
| `get_best_practices(...)` | `List[Dict]` | 最佳实践 |
| `get_structured_kb(...)` | `Dict` | 结构化命令库（按视图/型号过滤） |
| `get_troubleshooting_cases(query)` | `List[Dict]` | 排错案例 |
| `detect_view_mode(prompt)` | `str` | 识别用户视图 `< >` / 系统视图 `[ ]` |
| `suggest_commands(model)` | `Dict` | 按型号建议命令 |
| `scan_device_commands(path)` | `Dict` | 扫描设备并建议命令 |
| `reload_structured_kb()` / `load_structured_kb()` | `Dict/bool` | 加载结构化库 |

## v2.4 已废弃（已删除）
- ~~`get_config_guidance(topic)`~~ —— 已从 `knowledge.py` 移除
- ~~`app.py` 中的 `KnowledgeBase` 重复定义~~ —— 已从 `app.py` 移除，统一使用 `knowledge.py` 的单一来源

## 架构
```
mcp_server.py → services.py → KnowledgeBase (knowledge.py，唯一来源)
app.py        → 通过 from services import kb 复用同一实例（不再重复定义）
    record_command        → devices_kb.json + global_kb.json
    record_experience     → structured_commands_kb.json
    get_*                 → 读取各 JSON
```

## 另见
- `docs/modules/knowledge_store.md` —— Agent 知识库
- `docs/modules/config_method_store.md` —— 配置方法库
- `docs/modules/web_api.md` —— Flask Web API（HTTP 路由 + SocketIO 事件）
