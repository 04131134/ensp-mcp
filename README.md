# eNSP-MCP 基于 eNSP 模拟器的 AI 网络实验平台 v3.0

> **版本** v3.0 | **更新日期** 2026-07-19 | **分支** `codex/version-3.0`

让 AI（Codex/Claude/Cursor 等）通过 Telnet 驱动本地 eNSP 模拟器，完成 20+ 种网络实验的自动化配置。

---

## 架构总览

```
AI / AI Agent
     |  MCP (stdio)
     v
MCP Server (mcp_server.py, 47 个工具)
     |  部分 Agent 工具经 HTTP 调用后端 Flask
     +---> DeviceManager (dm)       设备连接池管理
     +---> KnowledgeBase (kb)       配置知识库（只记配置方法）
     +---> TopologyEngine           拓扑引擎
     +---> ConfigMethodStore        配置方法库
     +---> ViewRouter (v3.0)   命令视图感知路由 + VRP 冷却保护
     +---> TelnetConnection          Telnet 连接层
     |
     4 个 Agent Runtime 模块经 HTTP 调 Flask
     v
Flask Web UI (app.py + web/ 蓝图, 59 个 HTTP 端点, 另 7 个 SocketIO 事件)
     +---> Agent Runtime v3.0 (planner/runtime/verifier/reflection/learning)
```

**v3.0 版本说明**
v3.0 为「版本与文档统一」版本：**不新增功能**，仅把此前分散在代码（Agent Runtime 已标 `v3.0`）、`pyproject.toml`（旧 `3.1.0`）与旧 README（旧 `v2.4`）中的版本号统一收敛为 **3.0**，并补全全部 **47 个** MCP 工具的使用说明（见 [`docs/api/mcp_tools_reference.md`](docs/api/mcp_tools_reference.md)）。已实现的稳定能力包括：

- `view_router.py`：命令视图感知路由 + VRP 冷却保护
- 设备操作已收敛，移除 `reboot`/`reset` 等高危占位
- 知识库精简为「只记配置方法」，模板/快照/配置向导类工具已移除
- 心跳监控含设备保活（keepalive）
- 命令发送统一 `120` 字符 `\r\n` 缓冲
- 47 个 MCP 工具全部可用，含 Agent Runtime 闭环实验（`agent_execute` 推荐）

---

## 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **DeviceManager** | `device_manager.py` | 设备连接池 / 连接 / 断开 / 保活 |
| **CommandExecutor** | `command_executor.py` | 命令发送 / 结果解析 |
| **ViewRouter** | `view_router.py` | 命令视图感知路由 + VRP 冷却保护（v3.0） |
| **KnowledgeBase** | `knowledge.py` | 配置方法 CRUD + 经验积累（v3.0：只记配置方法） |
| **Services** | `services.py` | kb / topo_engine / config_methods 服务聚合 |
| **TopologyEngine** | `topology.py` | 拓扑发现 / 路径 / 设备关系 |
| **HeartbeatMonitor** | `heartbeat.py` | 心跳监控 + 设备保活（v3.0 keepalive） |
| **TelnetConnection** | `connection.py` | Telnet 连接层 + 缓冲 + 超时控制 |
| **ConfigMethodStore** | `config_method_store.py` | 配置方法 JSON 存储 |
| **Memory** | `agent/memory.py` | 长期记忆 |
| **DAGPlanner** | `agent/planner.py` | DAG 任务规划 |
| **SemanticVerifier** | `agent/verifier.py` | 语义验证器 |
| **AgentRuntime** | `agent/runtime.py` | 闭环执行引擎 |

> 注：`mcpensp1/knowledge_store.py`（旧别名垫片）已在清理中删除；增长知识库现为 `agent/knowledge_store.py`（独立的 Agent 学习库，不与 `KnowledgeBase` 合并）。

---

## MCP 工具清单

共 **47 个工具**，均已实现，且全部为**直连型**（在 MCP Server 进程内执行，不依赖 Flask）。

> 📘 **完整工具使用说明（参数 / 示例 / 依赖）见 [`docs/api/mcp_tools_reference.md`](docs/api/mcp_tools_reference.md)**，这是调用本工具时的主要参考。

### 设备连接 7 个
`scan_devices` `connect_device` `send_command` `disconnect_device` `get_connected_devices` `rename_device` `fetch_device_name`

### 批量命令 2 个
`batch_command` `group_command` —— 批量命令经 view_router 路由

### 知识库 18 个
`get_command_catalog` `get_device_capabilities` `get_device_history` `get_kb_commands` `get_kb_stats` `get_structured_kb` `suggest_commands` `scan_device_commands` `get_best_practices` `get_experiences` `record_experience` `detect_device_view` `get_troubleshooting_kb` `reload_kb` `generate_lab_report` `auto_record_experience` `search_kb` `get_command_help`

### 拓扑 4 个
`get_topology` `save_topology` `find_topology_path` `get_topology_device`

### 配置方法 6 个
`config_method_list` `config_method_get` `config_method_search` `config_method_add` `config_method_steps` `config_method_update`

### Agent 工具 10 个
`agent_memory_query` `agent_memory_lessons` `agent_memory_stats` `agent_knowledge_search` `agent_knowledge_best_practices` `agent_knowledge_troubleshooting` `agent_plan` `agent_execute` `agent_status` `agent_daily_review`

### 已移除工具（历史） 12 个
~~配置模板类~~ `generate_config_template` `list_templates` ~~~~ ~~配置快照类~~ `snapshot_config` `list_snapshots` `get_snapshot` `diff_snapshots` `rollback_config` ~~~~ ~~配置向导类~~ `get_config_guidance` `suggest_next_steps` `get_config_order` `config_summary` `config_record_experience` ~~~~

---

## 环境要求

| 项 | 要求 |
|------|------|
| **系统** | Windows + eNSP 模拟器 |
| **Python** | 3.12+ |
| **eNSP** | 已安装并能启动设备 |

---

## 快速开始

### 1. 启动 MCP Server（stdio）

```bash
cd mcpensp1
python mcp_server.py
```

MCP Server 通过 stdio 与 AI 客户端通信，不单独启动 Flask。

### 2. 启动 Flask Web 界面

```bash
python app.py
```

默认访问 `http://127.0.0.1:5000`。

### 3. 接入 MCP 客户端

```json
{
  "mcpServers": {
    "ensp": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "e:/eNSP-MCP/mcpensp1"
    }
  }
}
```

---

## 项目结构

```
eNSP-MCP/
├── mcpensp1/
│   ├── app.py                  # Flask 应用装配（创建 app/SocketIO、注册蓝图）
│   ├── web/                    # Web 蓝图 + SocketIO 事件（devices/commands/knowledge/
│   │                           #   topology/experiments/agent，共 59 个 HTTP 端点）
│   ├── mcp_server.py           # MCP Server（47 个工具）
│   ├── connection.py           # Telnet 连接层（缓冲 + 超时）
│   ├── device_manager.py       # 设备连接池（保活）
│   ├── command_executor.py     # 命令执行引擎
│   ├── view_router.py          # 命令视图感知路由 + VRP 冷却（v3.0）
│   ├── knowledge.py            # 配置知识库（v3.0：只记配置方法）
│   ├── services.py             # kb/topo/config 服务聚合
│   ├── topology.py             # 拓扑引擎
│   ├── heartbeat.py            # 心跳监控 + 保活（v3.0 keepalive）
│   ├── config_method_store.py  # 配置方法库
│   ├── experiment_engine.py    # 实验引擎
│   ├── requirements.txt
│   ├── mcp.json
│   ├── protocols/              # 协议模板（VLAN/OSPF/BGP/ACL）
│   ├── prompts/v3/system.md    # Agent System Prompt
│   ├── agent/                  # AI Agent 子系统
│   │   ├── planner.py          # DAG 任务规划
│   │   ├── runtime.py          # 闭环执行引擎
│   │   ├── verifier.py         # 语义验证器
│   │   ├── reflection.py       # 反思引擎
│   │   ├── learning.py         # 学习引擎
│   │   ├── memory.py           # 长期记忆
│   │   └── knowledge_store.py  # 增长知识库
│   ├── kb/                     # 静态知识库数据
│   │   └── config_methods/     # 配置方法 JSON（VLAN/OSPF/DHCP/static_route）
│   ├── static/                 # Web 静态资源
│   └── templates/              # Web 模板
├── tests/                      # 测试（380 passed, 3 skipped）
│   ├── test_smoke.py           # 冒烟（需真实 eNSP 设备，skip）
│   ├── test_regression.py      # 回归
│   ├── test_agent_runtime.py   # Agent 运行时
│   └── test_safety_framework.py # 安全框架
└── docs/                       # 项目文档
    ├── architecture/           # 架构文档
    ├── development/            # 开发规范
    ├── modules/                # 模块文档
    ├── api/                    # API 文档
    ├── best_practices/         # 最佳实践
    ├── troubleshooting/        # 排错指南
    └── adr/                    # 架构决策记录
```

---

## 测试

```bash
cd eNSP-MCP
python -m pytest tests/ -q
# 380 passed, 3 skipped
```

---

MIT License
