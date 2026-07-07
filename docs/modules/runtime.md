# Runtime（AgentRuntime）

## 位置
`mcpensp1/agent/runtime.py`

## 职责
闭环实验执行引擎：接收执行计划，协调 Planner、CommandExecutor、Verifier、ReflectionEngine 完成自动化实验并记录结果。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `request` | `str` | 自然语言实验请求 |
| `device_paths` | `List[str]` | 目标设备路径 |
| `experiment_type` | `str` | 实验类型 |
| `constraints` | `List[str]` | 约束条件 |

## 输出
```python
ExperimentResult:
    experiment_id: str
    status: TaskPhase (COMPLETED/FAILED/...)
    nodes: List[NodeResult]
    reflection: ReflectionEntry
    summary: str
```

## 依赖
- `planner.DAGPlanner` — 生成执行计划
- `verifier.SemanticVerifier` — 验证结果
- `reflection.ReflectionEngine` — 经验反思
- `memory.MemoryStore` — 记忆写入
- `knowledge_store.KnowledgeStore` — 知识写入
- `command_executor.CommandExecutor` — 命令执行

## 禁止事项
- ❌ 不允许跳过验证直接标记成功
- ❌ 不允许超过 max_rounds 后继续重试
- ❌ 不允许在有环 DAG 上执行

## 调用关系
```
MCP agent_execute → AgentRuntime.execute_task()
    └── _execute_plan_loop() → 遍历 DAG 节点
        ├── ConfigNode → _execute_config_node() → CommandExecutor
        ├── VerifyNode → _execute_verify_node() → SemanticVerifier
        └── 失败 → 恢复策略 → retry/skip/abort
    └── ReflectionEngine.reflect()
    └── MemoryStore/KnowledgeStore 写入
```
