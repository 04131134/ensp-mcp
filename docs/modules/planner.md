# Planner（DAGPlanner）

## 位置
`mcpensp1/agent/planner.py`

## 职责
将自然语言实验目标（如"配置VLAN 10和VLAN 20"）转换为结构化的 DAG 执行计划。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `goal` | `TaskGoal` | 实验目标描述 |
| `device_paths` | `List[str]` | 目标设备路径列表 |
| `experiment_type` | `str` | 实验类型（vlan/ospf/...） |
| `constraints` | `List[str]` | 约束条件 |
| `knowledge_context` | `Dict` | 知识库上下文 |

## 输出
```python
ExecutionPlan:
    nodes: List[PlanNode]          # DAG 节点
    edges: List[Tuple[str,str]]    # 依赖关系
    metadata: Dict                 # 元信息
```

## 依赖
- `agent/types.py` — 数据结构定义
- 内置模板字典（协议→命令映射）

## 禁止事项
- ❌ 不允许生成包含环路的 DAG
- ❌ 不允许 ConfigNode 没有对应的 VerifyNode
- ❌ 不允许修改模板数据结构而不更新对应测试

## 调用关系
```
AgentRuntime → DAGPlanner.plan_from_goal() → ExecutionPlan
                  ├── _match_template() → 模板匹配
                  ├── _plan_from_template() → 模板展开
                  ├── _plan_from_analysis() → 自由分析
                  ├── _add_verification_nodes() → 追加验证节点
                  └── _set_recovery_strategies() → 绑定恢复策略
```
