# DependencyGraph（依赖图）

## 位置
`mcpensp1/agent/dependency_graph.py`

## 职责
管理 Action 间的依赖关系。支持拓扑排序、循环检测、失败节点重试、局部恢复。

## 核心能力
- **拓扑排序**：按依赖顺序输出可执行序列
- **循环检测**：防止无限等待
- **局部恢复**：不因一个节点失败而重跑整个实验
- **重试机制**：可配置最大重试次数

## 核心接口
| 方法 | 说明 |
|------|------|
| `topological_sort()` | 拓扑排序 |
| `has_cycle()` | 循环检测 |
| `get_next_ready()` | 获取就绪节点 |
| `retry_action()` | 重试失败节点 |
| `get_subgraph_for_recovery()` | 局部恢复子集 |

## 依赖
- `action_types.ActionNode` / `ActionPlan`

## 禁止事项
- 不允许在有环的图上执行
