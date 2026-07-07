# eNSP Network Agent Runtime v3.1

> **版本：** v3.1 | **更新日期：** 2026-07-06 | **分支：** `refactor/p0`

一个能够自主完成网络实验、持续成长、共享知识、自动学习、自动规划、自动验证、自动修复的 **Network Agent Runtime**。

---
## 目录

- [系统架构](#系统架构)
- [Agent 工作流](#agent-工作流)
- [核心模块](#核心模块)
- [知识库架构](#知识库架构)
- [MCP 工具总览](#mcp-工具总览)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [重构记录](#重构记录)
- [兼容性说明](#兼容性说明)

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     用户 / AI Agent                         │
└─────────────────────────┬───────────────────────────────────┘
                          │ MCP (stdio)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              MCP Server (mcp_server.py, 58 个工具)           │
│                                                             │
│  ┌────────────────── 直接调用（无 HTTP 转发）─────────────┐ │
│  │  DeviceManager (dm)     │  CommandExecutor             │ │
│  │  KnowledgeBase (kb)     │  TopologyEngine              │ │
│  │  ConfigMethodStore      │  TelnetConnection (async)    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  仅 4 个 Agent Runtime 工具保留 HTTP → Flask 后端            │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP (仅 agent_plan/execute/status/daily_review)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│           Flask Web UI (app.py, 可选只读调试面板)            │
│                                                             │
│  ┌─────────────────── Agent Runtime v3.0 ─────────────────┐ │
│  │  Memory | KnowledgeStore | Planner | Runtime           │ │
│  │  Verifier | Recovery | Reflection | Learning           │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**关键变化（v3.0 → v3.1）：**
- MCP Server 直连核心模块，**HTTP 调用从 45+ 降至 10 个**
- 新增 `device_manager.py`、`command_executor.py`、`services.py` 独立模块
- `AGENT_SYSTEM_PROMPT` 外部化至 `prompts/v3/system.md`（UTF-8 可读）

---

## Agent 工作流

```
Receive Task
    ↓
Understand Goal（理解需求，识别协议/设备/拓扑）
    ↓
Load Memory（加载长期记忆，查询历史经验）
    ↓
Search Knowledge（搜索知识库：最佳实践/模板/排障案例）
    ↓
Planning（生成 DAG 执行计划，分析依赖，确定顺序）
    ↓
Check Dependencies（检查循环依赖，验证前置条件）
    ↓
Execute（按 DAG 顺序执行配置命令）
    ↓
Observe（观察命令输出和设备响应）
    ↓
Verify（语义化验证：接口/VLAN/OSPF/路由/连通性）
    ↓
Repair（验证失败 → 分析原因 → 重规划 → 重执行，最多 3 轮）
    ↓
Reflect（反思总结：成功/失败原因、优化建议）
    ↓
Update Memory（更新记忆和知识库：经验/命令/排障/模板）
    ↓
Finish
```

**关键约束：**
- 收到实验需求后，**禁止立即调用 Tool**
- 必须按上述流程逐步执行
- 知识库能回答时，**禁止外部搜索**

---

## 核心模块

### 模块清单

| 模块 | 文件 | 职责 |
|------|------|------|
| **DeviceManager** | `device_manager.py` | 设备连接/断开/命名/扫描（线程安全） |
| **CommandExecutor** | `command_executor.py` | 单条/批量命令执行、危险命令拦截 |
| **KnowledgeBase** | `knowledge.py` | 知识库 CRUD、搜索、统计（原有） |
| **KnowledgeStore** | `knowledge_store.py` | 知识库统一封装（桥接层） |
| **Services** | `services.py` | kb/topo_engine/config_methods 共享单例 |
| **TopologyEngine** | `topology.py` | 拓扑图加载/最短路径/设备连接查询 |
| **HeartbeatMonitor** | `heartbeat.py` | 设备存活检测/自动重连 |
| **TelnetConnection** | `connection.py` | Telnet 连接、同步/异步双接口 |
| **ConfigMethodStore** | `config_method_store.py` | 配置方法库（标准配置流程） |
| **Memory** | `agent/memory.py` | 长期记忆系统，跨会话持久化 |
| **KnowledgeStore** | `agent/knowledge_store.py` | Agent 专用可成长知识库 |
| **DAGPlanner** | `agent/planner.py` | DAG 执行计划生成 |
| **SemanticVerifier** | `agent/verifier.py` | 语义化验证引擎 |
| **RecoveryEngine** | `agent/recovery.py` | 自动恢复引擎 |
| **ReflectionEngine** | `agent/reflection.py` | 实验反思引擎 |
| **LearningEngine** | `agent/learning.py` | 自主学习引擎 |
| **AgentRuntime** | `agent/runtime.py` | 运行时编排器（闭环） |
| **Routes** | `agent/routes.py` | Agent API 路由（含认证） |

---

## MCP 工具总览

共 **58 个** MCP 工具。

### 直连工具（54 个，无 HTTP 转发）

**设备管理（7）：** `scan_devices`, `connect_device`, `send_command`, `disconnect_device`, `get_connected_devices`, `rename_device`, `fetch_device_name`

**命令执行（3）：** `batch_command`, `group_command`, `suggest_next_steps`

**知识库（16）：** `get_command_catalog`, `get_kb_commands`, `get_kb_stats`, `suggest_commands`, `scan_device_commands`, `get_best_practices`, `get_experiences`, `record_experience`, `search_kb`, `get_command_help`, `generate_config_template`, `list_templates`, `get_config_guidance`, `generate_lab_report`, `auto_record_experience`, `reload_kb`

**拓扑（4）：** `get_topology`, `save_topology`, `find_topology_path`, `get_topology_device`

**快照（4）：** `snapshot_config`, `list_snapshots`, `get_snapshot`, `diff_snapshots`, `rollback_config`

**配置方法（6）：** `config_method_list`, `config_method_get`, `config_method_search`, `config_method_add`, `config_method_steps`, `config_method_update`

**Agent 知识/内存（6）：** `agent_memory_query`, `agent_memory_lessons`, `agent_memory_stats`, `agent_knowledge_search`, `agent_knowledge_best_practices`, `agent_knowledge_troubleshooting`

**配置总结（3）：** `config_summary`, `config_record_experience`, `detect_device_view`

**其他（5）：** `get_device_capabilities`, `get_device_history`, `get_structured_kb`, `get_config_order`, `get_troubleshooting_kb`

### HTTP 转发工具（4 个）

`agent_plan`, `agent_execute`, `agent_status`, `agent_daily_review` — Agent Runtime 闭环逻辑驻留在 Flask 路由中。

---

## 环境要求

| 项目 | 要求 |
|------|------|
| **操作系统** | Windows（eNSP 依赖） |
| **Python** | 3.12+ |
| **eNSP** | 已安装且设备运行中 |
| **MCP 客户端** | TRAE / Claude Desktop / Cursor /Coedx等 |

---

## 快速开始

### 1. 启动 MCP Server（唯一必需组件）

```bash
cd mcpensp1
python mcp_server.py
```

MCP Server 现在**直连设备**，不依赖 Flask 后端。

### 2. （可选）启动 Flask Web 调试面板

```bash
python app.py
```

浏览器打开 `http://127.0.0.1:5000` 查看设备状态。

### 3. 配置 MCP 客户端

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

不再需要 `ENSP_SERVER_URL` 环境变量。

---

## 项目结构

```
eNSP-MCP/
├── mcpensp1/
│   ├── app.py                       # Flask Web UI (可选, ~3400行)
│   ├── mcp_server.py                # MCP Server (544行, 58个工具)
│   ├── connection.py                # Telnet连接 (同步+异步双接口)
│   ├── device_manager.py            # 设备状态管理 (线程安全) ★新
│   ├── command_executor.py          # 命令执行器 ★新
│   ├── knowledge.py                 # 知识库 (原有, 修复import)
│   ├── knowledge_store.py           # 知识库统一封装 (桥接层) ★新
│   ├── services.py                  # kb/topo/config共享单例 ★新
│   ├── topology.py                  # 拓扑引擎
│   ├── heartbeat.py                 # 心跳监控
│   ├── config_method_store.py       # 配置方法库
│   ├── experiment_engine.py         # 实验引擎
│   ├── requirements.txt
│   ├── mcp.json
│   ├── prompts/v3/
│   │   └── system.md                # Agent System Prompt (UTF-8) ★新
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── types.py                 # 共享数据类型
│   │   ├── memory.py                # 长期记忆系统
│   │   ├── knowledge_store.py       # 可成长知识库
│   │   ├── planner.py               # DAG 执行规划器
│   │   ├── verifier.py              # 语义化验证引擎
│   │   ├── recovery.py              # 自动恢复引擎 (修复KeyError)
│   │   ├── reflection.py            # 实验反思引擎
│   │   ├── learning.py              # 自主学习引擎
│   │   ├── runtime.py               # 运行时编排器
│   │   ├── routes.py                # API 路由 (修复认证)
│   │   └── bootstrap.py             # 集成引导
│   ├── agent_data/                  # Agent 数据
│   ├── kb/                          # 知识库 JSON
│   ├── static/
│   └── templates/
├── tests/
│   └── test_smoke.py                # 34个冒烟测试 ★新
├── _baseline_20260706/              # Phase 0基线备份 ★新
├── REFACTOR_PLAN.md                 # 重构方案
└── README.md
```

---

## 重构记录

| Phase | Commit | 内容 |
|-------|--------|------|
| **P0** | `43b373d` | 安全网：分支/备份/34个冒烟测试 |
| **P1** | `4ba467f` | Bug修复：names→device_names、recovery KeyError、认证、裸except、Prompt外部化、乱码 |
| **P2** | `8865ff0` | 模块拆分：device_manager.py、command_executor.py、knowledge_store.py |
| **P2.5** | `deb7a6d` | async桥接：TelnetConnection.send_cmd_async() |
| **P3 B1** | `8a4e4dd` | 核心设备工具直连：scan/connect/send/batch/disconnect |
| **P3 B2** | `1507042` | KB/拓扑/快照/配置方法 ~22个工具直连 + services.py |
| **P3 B3** | `e5b73d5` | Agent Memory/Knowledge/Config 工具直连 |
| **P3 B3b** | `398ba8a` | KB/topo/detect/snapshot 剩余工具直连 |
| **复查** | `ab9e757` | config_methods共享单例 + topo_names同步dm |

**成果：HTTP调用 45+ → 10，冒烟测试 28/28 PASS。**

---

## 兼容性说明

### 向后兼容

- ✅ 所有原有 MCP Tool 完全兼容
- ✅ 所有原有 API 路径完全兼容
- ✅ 原有知识库 JSON 文件继续使用
- ✅ 前端和 WebSocket 事件不变
- ✅ Agent Runtime 加载失败不影响原有功能

### 新增能力

- ✅ MCP Server 直连设备（无 HTTP 转发延迟）
- ✅ 4 个新增核心模块（device_manager, command_executor, services, knowledge_store）
- ✅ TelnetConnection 异步接口
- ✅ `_require_auth` 认证生效
- ✅ AGENT_SYSTEM_PROMPT 外部可编辑

---

## 许可证

MIT License
