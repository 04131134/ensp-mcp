# DAGPlanner 任务规划器

## 概述

`DAGPlanner`（`mcpensp1/agent/planner.py`）将自然语言实验目标转换为有向无环图（DAG）执行计划。它是 Agent 闭环实验的第一步。

## 核心流程

```
plan_from_goal(goal)
    │
    ├── 1. 解析目标 → TaskGoal (features, protocol, device_type)
    │
    ├── 2. 模板匹配（_match_template）
    │   ├── 命中 → _plan_from_template() → 展开模板为 PlanNode 列表
    │   └── 未命中 → _plan_from_analysis() → 关键词驱动的任务分解
    │
    ├── 3. 构建 DAG（拓扑排序，无环检测）
    │
    ├── 4. _add_verification_nodes() → 为每个 ConfigNode 追加 VerifyNode
    │
    └── 5. _set_recovery_strategies() → 每个节点绑定恢复策略
```

## 支持的模板

内置模板覆盖常见网络实验：

- VLAN 配置 + 验证
- OSPF 基础 + 验证
- 静态路由 + 验证
- DHCP Server + 验证
- AC/AP 无线 + 验证
- STP/RSTP + 验证

## 核心接口

| 方法 | 说明 |
|------|------|
| `plan_from_goal(goal, device_paths, experiment_type)` | 生成执行计划 |
| `update_plan_after_failure(plan, node, error)` | 失败后更新计划 |
| `get_plan_summary(plan)` | 计划概要 |
| `_extract_protocols(description)` | 从文本提取协议关键词 |
| `_extract_variables(description)` | 从文本提取变量（VLAN ID、IP 等） |

## 数据结构

```python
class ExecutionPlan:
    nodes: List[PlanNode]         # DAG 节点
    edges: List[Tuple[str,str]]   # 依赖边 (from_id, to_id)

class PlanNode:
    id: str            # 唯一标识
    type: str          # config / verify
    device: str        # 设备路径
    commands: List[str] # 命令列表
    verify: Dict       # 验证规则
    depends_on: List[str] # 前驱节点
    recovery: str      # retry / skip / abort
```

## 禁止事项

- ❌ 不允许在 DAG 中产生环路（有 `_has_circular_dependency` 检测）
- ❌ 不允许 ConfigNode 没有对应的 VerifyNode
- ❌ 不允许直接修改模板数据结构而不更新测试
