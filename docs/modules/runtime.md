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

## 知识成长接入

每个配置命令执行后，`ExperimentResult.execution_log` 会保留完整设备输出、从末尾提示符提取的视图、设备路径、节点标识和命令成败；节点结果中的输出摘要仍保持原有的 200 字符限制。

运行时可选接收 `device_scanner` 和 `topology_provider`。前者用于按设备路径提供型号、角色和版本，后者提供拓扑摘要；缺少型号或 IP 信息时，知识成长模块会使用安全默认值或通用参数化。

`execute_task()` 的收尾阶段独立执行下列非阻塞操作：

- 成功任务调用蓝图学习器，以实验标识、执行日志、设备与拓扑上下文学习配置蓝图。
- 失败任务逐条分类失败的配置命令，更新设备约束或蓝图视图前置条件。
- 仅在错误记录包含完整约束，以及调用方明确提供可执行的 `alternative_command` 时，为设备不支持或环境错误生成真实设备回归测试。

上述所有调用均有独立异常隔离，只写入警告日志，不改变任务成功、失败或清理流程。

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
