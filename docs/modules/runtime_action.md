# ActionDrivenRuntime（Action 驱动执行引擎）

> ⚠️ **状态：未启用（实验性 / 候选引擎）**
> 本模块代码已实现，但 `bootstrap.py` / `runtime.py` / `app.py` / `mcp_server.py` **均未 import 或启用 `ActionDrivenRuntime`**，全仓仅测试引用。因此文档中“与旧 AgentRuntime 共存，渐进迁移”**当前并未发生**——系统实际只运行 `AgentRuntime`。连同其依赖的 `action_types / cli_state / prompt_parser / command_generator / command_validator / dependency_graph / error_library` 共 9 个模块，目前均为“已编写但未接线”的摆设代码。本文档描述的是设计意图，非已上线功能。

## 位置
`mcpensp1/agent/runtime_action.py`

## 职责
Action 驱动的 14 步闭环执行引擎。与旧 AgentRuntime 共存，渐进迁移。

## 14 步闭环流程
Receive Task → Capability Check → Planner → Action Plan → Dependency Graph
→ Command Generator → CLI Validator → Executor → Prompt Parser → CLI State Update
→ Semantic Verify → Repair → Knowledge Update

## 核心接口
| 方法 | 说明 |
|------|------|
| `execute(task, device_paths, device_model)` | 执行完整 14 步流程 |

## 依赖
- `action_types.*` — AST 数据结构
- `dependency_graph.DependencyGraph` — 依赖管理
- `command_validator.CommandValidator` — 命令验证
- `command_generator.CommandGenerator` — CLI 生成
- `error_library.ErrorLibrary` — 错误查询
- `capability_manager.CapabilityManager` — 能力检查

## 禁止事项
- 不允许删除旧 AgentRuntime
- 不允许跳过 Capability Check 直接执行
