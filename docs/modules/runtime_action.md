# ActionDrivenRuntime（Action 驱动执行引擎）

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
