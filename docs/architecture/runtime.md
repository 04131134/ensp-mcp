# Agent Runtime 执行引擎

## 概述

`AgentRuntime`（`mcpensp1/agent/runtime.py`）是 AI Agent 的闭环实验执行引擎。它接收自然语言目标，自动规划、执行、验证并反思实验结果。

## 核心流程

```
agent_execute(request)
    │
    ├── 1. Planner.plan_from_goal(goal) → ExecutionPlan (DAG)
    │
    ├── 2. 遍历 DAG 节点（拓扑序）:
    │   ├── ConfigNode → CommandExecutor.send_command / batch_command
    │   ├── VerifyNode → SemanticVerifier.verify_*
    │   └── 失败 → Recovery 策略 (retry/skip/abort)
    │
    ├── 3. ReflectionEngine.reflect(result) → 经验总结
    │
    └── 4. 写入 MemoryStore / KnowledgeStore
```

## 状态机

```
IDLE → PLANNING → EXECUTING → VERIFYING → COMPLETED
                       ↑            │
                       │     ┌──────┘
                       │     ↓
                       └── RECOVERING
                                 │
                            ┌────┴────┐
                            ↓         ↓
                        RETRY      FAILED
                            │
                            └──→ EXECUTING
```

## 关键参数

| 参数 | 说明 |
|------|------|
| `max_rounds` | 最大重试轮次（默认 3） |
| `experiment_type` | 实验类型（vlan/ospf/ac_wlan/...） |
| `device_paths` | 目标设备列表 |

## 恢复策略

- **retry**：重试当前节点（最多 max_rounds 次）
- **skip**：跳过当前节点继续
- **abort**：终止整个实验

## 依赖

- `planner.DAGPlanner` — 任务规划
- `verifier.SemanticVerifier` — 结果验证
- `reflection.ReflectionEngine` — 经验反思
- `memory.MemoryStore` — 长期记忆
- `knowledge_store.KnowledgeStore` — 知识库
- `command_executor.CommandExecutor` — 命令执行
