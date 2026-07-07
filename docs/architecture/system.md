# 系统架构概述

## 项目定位

eNSP-MCP 是一个面向华为 eNSP 网络仿真平台的 AI 网络自动化工具。它通过 MCP（Model Context Protocol）协议暴露 52+ 工具，使 AI Agent 能够自动化完成网络拓扑配置、验证、排错等任务。

## 技术栈

| 层级 | 技术 |
|------|------|
| 协议层 | MCP（Model Context Protocol） |
| Web 层 | Flask + SocketIO |
| 连接层 | Telnet（asyncio + threading） |
| AI Agent | 自研 DAGPlanner + AgentRuntime + SemanticVerifier |
| 知识层 | JSON 知识库 + MemoryStore + KnowledgeStore |
| 测试 | pytest（97 条测试） |

## 核心架构图

```
+----------------------------------------------------+
|                   AI Client (Claude/Codex)          |
|                       ↓ MCP 协议                     |
+----------------------------------------------------+
|                  mcp_server.py                      |
|          (52+ tools: scan/connect/send/batch/...)   |
|                       ↓                             |
|   +-----------+  +-----------+  +----------------+  |
|   |  Flask    |  | Agent     |  | Knowledge &    |  |
|   |  Web API  |  | Runtime   |  | Config Methods |  |
|   +-----+-----+  +-----+-----+  +-------+--------+  |
|         |               |                |           |
|   +-----v-----+   +-----v-----+   +------v-------+  |
|   | Device    |   | Planner   |   | KB (JSON/   |  |
|   | Manager   |   | Verifier  |   | MemoryStore)|  |
|   +-----+-----+   +-----------+   +--------------+  |
|         |                                            |
|   +-----v-----+                                      |
|   | Command   |                                      |
|   | Executor  |                                     |
|   +-----+-----+                                      |
|         |                                            |
|   +-----v-----+                                      |
|   | Telnet    |                                      |
|   | Connection|                                      |
|   +-----------+                                      |
+----------------------------------------------------+
|                  eNSP 仿真设备                        |
|     (路由器/交换机/防火墙/AC 通过 localhost:2000+)     |
+----------------------------------------------------+
```

## 数据流

### 命令执行流

```
AI Client → mcp_server (send_command) → CommandExecutor → TelnetConnection → eNSP 设备
                                                                                ↓
AI Client ← mcp_server ← CommandExecutor ← TelnetConnection ← 命令输出
```

### Agent 闭环实验流

```
AI Client → mcp_server (agent_execute) → AgentRuntime
                                            ├── DAGPlanner (制定执行计划)
                                            ├── CommandExecutor (执行命令)
                                            ├── SemanticVerifier (验证结果)
                                            ├── ReflectionEngine (反思&学习)
                                            └── MemoryStore / KnowledgeStore (记录)
                                         → 返回 ExperimentResult
```

## 模块依赖图

```
mcp_server.py ──→ services.py ──→ device_manager.py
     │                │                 │
     │                ├──→ knowledge.py │
     │                │                 │
     ├──→ command_executor.py ←────────┘
     │         │
     │         └──→ connection.py (TelnetConnection)
     │
     ├──→ heartbeat.py ←── device_manager.py
     │
     ├──→ topology.py
     │
     ├──→ agent/
     │    ├── cli_state.py          # CLI 视图栈状态机
     │    ├── prompt_parser.py      # Prompt 解析
     │    ├── command_validator.py  # 命令验证
     │    ├── command_generator.py  # 命令生成
     │    ├── error_library.py      # 错误查询
     │    ├── capability_manager.py # 能力矩阵
     │    ├── plan_reviewer.py      # 计划审核
     │    ├── transaction.py        # 事务管理
     │    ├── action_types.py       # AST 数据结构
     │    ├── dependency_graph.py   # 依赖图
     │    └── runtime_action.py     # Action 驱动 Runtime
           ├── runtime.py
           │    ├── planner.py (DAGPlanner)
           │    ├── verifier.py (SemanticVerifier)
           │    └── reflection.py (ReflectionEngine)
           ├── memory.py (MemoryStore)
           ├── knowledge_store.py (KnowledgeStore)
           └── learning.py
```

## 关键设计决策

1. **MCP 作为唯一外部协议**：所有 AI 交互通过 MCP，不暴露 REST API 给 AI
2. **直连模式**：工具函数直接调用 Python 模块，不经过 HTTP 转发（已从 45+ HTTP 调用降至 ~10）
3. **DeviceManager 单例**：全局唯一的设备连接池，线程安全
4. **Telnet prompt 驱动**：基于 prompt 检测的命令读取，支持分页和超时
5. **CLI 状态机**：基于视图栈的 CLI 状态管理，命令执行前验证视图权限
6. **安全执行框架**：计划审核 → 事务管理 → 错误库驱动的自动恢复
7. **Action 驱动架构**：Planner 输出结构化 Action，CLI 由 Generator 生成
