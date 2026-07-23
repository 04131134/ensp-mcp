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
                  ├── _apply_experience() → 经验驱动覆盖命令（v3.1，第二阶段 Step1）
                  ├── _add_verification_nodes() → 追加验证节点
                  ├── _set_recovery_strategies() → 绑定恢复策略
                  └── _check_capabilities() → 设备能力校验（v3.1，第二阶段 Step2，不阻塞）
```

## v3.1 增强（第二阶段：经验/能力驱动）

### 新增接口（向后兼容，可选注入）

| 接口 | 说明 | 默认 |
|------|------|------|
| `set_knowledge_store(store)` | 注入 KnowledgeStore，启用经验驱动命令生成 | None（回退模板） |
| `set_capability_manager(cm)` | 注入 CapabilityManager，启用设备能力校验 | None（跳过校验） |
| `use_experience: bool` | 开关：是否用成功经验覆盖模板命令 | True |
| `check_capability: bool` | 开关：是否校验设备协议支持 | True |

### 经验驱动流程（Step1）
`plan_from_goal` 在生成计划后、追加验证节点前调用 `_apply_experience`：
1. 检索 `knowledge_store.query_for_task(goal.description)` 的 `success_cases`
2. 建立 `experiment_type → 经验命令` 映射
3. 命中则用经验命令覆盖对应 ConfigNode 的 `commands`
4. 任一步异常静默回退模板行为（不破坏流程）

### 能力校验流程（Step2）
`plan_from_goal` 末尾调用 `_check_capabilities`：
1. 需 `devices` 参数含型号（`{'model': 'S5700'}` 或 `{'models': [...]}`）
2. 对每个协议调 `capability_manager.check_protocol(model, proto)`
3. 不支持仅 log warning，**不抛异常、不阻塞**
4. 当前 runtime 未传 devices，故默认跳过；未来 runtime 传入型号后自动生效
