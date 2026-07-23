# Planner Knowledge Integration Design

> **版本** v1.0 | **日期** 2026-07-21 | **状态** 设计稿，待确认后实施
> **前置审计** command_generator_knowledge_audit.md
> **设计原则** 不删除 COMMAND_TEMPLATES、不改知识库接口签名、≤5 文件/批次

---

## 1. 当前调用链（审计确认）

```
runtime.execute_task()
  │
  ├─ 阶段2.5: config_methods.search_methods()
  │   └─ get_method_commands(method_id)   ← 查询了但只 log，丢弃
  │
  ├─ 阶段3: knowledge.query_for_task()
  │   └─ 传给 planner 作 knowledge_context  ← planner 只用作变量合并
  │
  ├─ 阶段4: planner.plan_from_goal(goal, knowledge_context, devices=None)
  │   ├─ _extract_variables()     → 正则提取 IP/VLAN/端口
  │   ├─ _match_template()        → campus/ospf_area/bgp/vpn/basic_routing
  │   ├─ _resolve_commands()      → COMMAND_TEMPLATES 硬编码 ← 命令唯一来源
  │   ├─ _apply_experience()      → knowledge_store 成功经验覆盖（第二阶段）← 唯一知识源
  │   ├─ _add_verification_nodes()
  │   └─ _check_capabilities()    → devices 为 None，跳过
  │
  └─ 阶段6: _execute_config_node()
      └─ self._exec_cmd(path, cmd)  ← 直接发 node.commands
```

### 断点位置

| 断点 | 位置 | 可用数据源 | 当前状态 |
|------|------|-----------|---------|
| A | planner 命令生成 | structured_commands_kb（176条） | ❌ 不查询 |
| B | runtime 阶段2.5 | config_methods（18个方法） | ❌ 查询后丢弃 |
| C | planner 能力校验 | capability_manager | ⚠ 注入了但 devices=None |
| D | planner 设备感知 | device_manager 已连接设备型号 | ❌ 不传递 |

---

## 2. 改造方案

### 2.1 总体架构

```
用户任务 "S5700 创建VLAN10"
    │
    ▼
runtime.execute_task()
    ├─ 阶段0: 获取已连接设备型号
    │   └─ device_manager.get_connected_summary() → [{path, device_type, model}, ...]
    │
    ├─ 阶段2.5: config_methods.search_methods(keyword)
    │   └─ best_method.commands → 传给 planner 作 config_method_commands
    │
    ├─ 阶段3: knowledge.query_for_task(description)
    │   ├─ knowledge_store 经验 → 传给 planner
    │   └─ suggest_commands(model, type) → structured KB 命令  ← 新增
    │
    ▼
planner.plan_from_goal(goal, knowledge_context, devices, config_method_commands=None)
    │
    ├─ 1. suggest_commands(device_model, 'system_view')  ← 新增：结构化命令库
    │      命中 → 用结构化命令覆盖对应协议节点的 commands
    │
    ├─ 2. config_method_commands                         ← 新增：配置方法库
    │      命中 → 补充到对应协议节点的 commands
    │
    ├─ 3. knowledge_store 成功经验                       ← 已有（第二阶段）
    │      命中 → 覆盖对应协议节点的 commands
    │
    ├─ 4. COMMAND_TEMPLATES 硬编码                        ← 兜底
    │      以上均未命中 → 用模板生成
    │
    └─ 5. capability_manager.check_protocol               ← 已有（需 devices）
           不支持的协议 → log warning
    │
    ▼
PlanNode {commands, device_model, knowledge_source, ...}
    │
    ▼
runtime._execute_config_node()
    └─ self._exec_cmd(path, cmd)
```

### 2.2 命令生成优先级（修复后）

```
优先级  来源                    覆盖场景                 命中条件
─────────────────────────────────────────────────────────────
  P1    structured_commands_kb  设备型号+协议精确匹配       suggest_commands 返回非空
  P2    config_methods          用户描述命中配置方法名      search_methods 返回结果
  P3    knowledge_store 经验    历史成功实验的命令序列      query_for_task 有 success_case
  P4    COMMAND_TEMPLATES       兜底                       以上均未命中
  P5    LLM（未来）             知识库无匹配的自由格式需求   暂不实现
```

### 2.3 数据流设计

#### A. 设备型号传递

```
device_manager (已连接设备)
  → dm.get_connected_summary()
  → [{path: '127.0.0.1:2000', name: 'S5700-1', device_type: 'S5700'}, ...]
  → runtime 提取 device_type
  → 传给 planner.plan_from_goal(devices={'model': 'S5700'})
```

**关键约束**：设备必须先 `connect_device` 才能获取型号。对于未连接设备的场景，model 为 None，知识库查询跳过，回退 COMMAND_TEMPLATES（与当前行为一致）。

#### B. PlanNode 扩展

```python
@dataclass
class PlanNode:
    # 现有字段（不变）
    node_id: str
    label: str
    node_type: NodeType
    commands: List[str]
    device_path: str
    dependencies: List[str]
    verify_commands: List[str]
    ...

    # 新增字段（默认值保证向后兼容）
    device_model: str = ""           # 目标设备型号（如 "S5700"）
    required_view: str = ""          # 命令需要的视图（"system_view"/"user_view"）
    knowledge_source: str = ""       # 命令来源（"template"/"structured_kb"/"config_method"/"experience"）
    capability_checked: bool = False # 是否通过能力校验
```

#### C. planner 接口变更

```python
class DAGPlanner:
    # 新增 setter（第二阶段已有 knowledge_store / capability_manager）
    # 新增 setter
    def set_knowledge_base(self, kb) -> None:
        """注入 KnowledgeBase 实例（用于 suggest_commands 查询）。"""
        self._knowledge_base = kb

    # plan_from_goal 签名不变（devices 参数已存在，但从未被有效使用）
    def plan_from_goal(
        self, goal: TaskGoal,
        knowledge_context: Optional[Dict] = None,
        devices: Optional[Dict] = None,               # 现有参数，现在真正使用
    ) -> ExecutionPlan:
        # ... 现有逻辑 ...
        # 新增：结构化命令库查询
        self._enrich_with_structured_kb(plan, devices)
        # ... 继续现有逻辑 ...
```

### 2.4 核心方法设计

#### `_enrich_with_structured_kb(plan, devices)`

```python
def _enrich_with_structured_kb(self, plan, devices):
    """用 structured_commands_kb 的命令覆盖模板命令（优先级 P1）。
    
    查询 suggest_commands(device_model, 'system_view') 获取设备型号对应的配置命令，
    按 function 名称匹配 plan 节点的 protocol/experiment_type，
    命中则用结构化命令覆盖 COMMAND_TEMPLATES。
    
    开关: use_structured_kb=True（新增）
    未注入 kb / 无设备型号 / 查询无结果 → 静默跳过
    """
    if not self.use_structured_kb or not self._knowledge_base:
        return
    device_model = devices.get('model') if devices else None
    if not device_model:
        return
    
    result = self._knowledge_base.suggest_commands(device_model, 'system_view')
    sv_cmds = result.get('system_view', [])
    # 按 function 分组: {function_name: [{cmd, desc, ...}]}
    func_cmds = {}
    for c in sv_cmds:
        fn = c.get('group', '')
        if fn not in func_cmds:
            func_cmds[fn] = []
        func_cmds[fn].append(c.get('cmd', ''))
    
    # 匹配 plan 节点：节点 protocol 对应 function 名称
    applied = 0
    for node in plan.nodes.values():
        if node.node_type != NodeType.CONFIG:
            continue
        # 匹配规则: node_id/protocol 名与 function 名模糊匹配
        for fn_name, cmds in func_cmds.items():
            if _fuzzy_match(node.node_id, fn_name) or _fuzzy_match(node.label, fn_name):
                node.commands = list(cmds)
                node.device_model = device_model
                node.knowledge_source = 'structured_kb'
                applied += 1
                break
    if applied:
        logger.info('[Planner] structured_kb 覆盖 %d 个节点', applied)
```

#### `_enrich_with_config_methods(plan, config_method_commands)`

```python
def _enrich_with_config_methods(self, plan, config_method_commands):
    """用 config_methods 的命令补充模板命令（优先级 P2）。
    
    仅补充未从 P1 获取命令的节点。config_method_commands 是按步骤排列的命令列表。
    
    开关: use_config_methods=True（新增）
    """
    if not self.use_config_methods or not config_method_commands:
        return
    # 从未被 P1 覆盖的 config 节点
    unmatched = [n for n in plan.nodes.values()
                 if n.node_type == NodeType.CONFIG and n.knowledge_source != 'structured_kb']
    if unmatched:
        # 将 config_method_commands 分配给第一个未匹配节点
        unmatched[0].commands = list(config_method_commands)
        unmatched[0].knowledge_source = 'config_method'
        logger.info('[Planner] config_methods 覆盖节点 %s', unmatched[0].node_id)
```

### 2.5 runtime 改动

```python
class AgentRuntime:
    def __init__(self, ...):
        # 现有注入...
        
        # 新增: planner 注入 KnowledgeBase（查询 structured_commands_kb）
        try:
            from knowledge import KnowledgeBase
            kb_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'kb')
            self._kb = KnowledgeBase(kb_folder=kb_folder)
            self.planner.set_knowledge_base(self._kb)
            logger.info('[Runtime] KnowledgeBase 已注入 planner')
        except Exception as e:
            logger.warning('[Runtime] KnowledgeBase 注入失败: %s', e)
    
    def execute_task(self, ...):
        # ...
        
        # 阶段0: 获取已连接设备型号（新增）
        device_models = self._get_device_models()
        
        # 阶段2.5: config_methods 查询（改进：结果传给 planner）
        config_cmds = self._query_config_methods(request)
        
        # 阶段4: planner 生成计划（改进：传入型号和配置方法）
        plan = self.planner.plan_from_goal(
            goal=goal,
            knowledge_context=knowledge_context,
            devices=device_models,  # 新增：传设备型号
            config_method_commands=config_cmds,  # 新增：传配置方法命令
        )
    
    def _get_device_models(self):
        """从已连接设备获取型号映射。"""
        summary = dm.get_connected_summary()  # 需从 services 获取 dm 引用
        return {'model': summary[0].get('device_type')} if summary else None
    
    def _query_config_methods(self, request):
        """查询配置方法库并提取命令序列。"""
        results = self.config_methods.search_methods(request)
        if results:
            return self.config_methods.get_method_commands(results[0].get('id'))
        return None
```

---

## 3. 涉及文件（分批次）

### 批次1（P0 核心）：planner 接入 structured_commands_kb

| 文件 | 改动 | 风险 |
|------|------|------|
| `agent/planner.py` | + `set_knowledge_base` + `_enrich_with_structured_kb` + `use_structured_kb` 开关 | 低（新增方法，不修改现有签名） |
| `agent/types.py` | PlanNode 新增 device_model/knowledge_source/required_view 字段（带默认值） | 低（dataclass 默认值向后兼容） |
| `agent/runtime.py` | 注入 KnowledgeBase + 传设备型号 | 中（需访问 device_manager 获取已连接设备型号） |
| `tests/test_planner_structured_kb.py` | 新增测试 | — |

**4 文件，符合 ≤5。**

### 批次2（P1 补充）：config_methods 接入

| 文件 | 改动 | 风险 |
|------|------|------|
| `agent/planner.py` | + `_enrich_with_config_methods` + `use_config_methods` 开关 | 低（新增方法） |
| `agent/runtime.py` | 阶段2.5 结果传给 planner | 低（传参，不影响现有流程） |
| `tests/test_planner_config_methods.py` | 新增测试 | — |

**3 文件，符合 ≤5。**

### 批次3（P2 完善）：设备型号获取 + 运行时增强

| 文件 | 改动 | 风险 |
|------|------|------|
| `agent/runtime.py` | `_get_device_models` 完善（从 dm 获取真实型号） | 中（依赖 dm 接口） |
| `tests/test_runtime_device_model.py` | 新增测试 | — |

**2 文件。**

---

## 4. 风险分析

| 风险 | 严重度 | 触发条件 | 缓解措施 |
|------|--------|---------|---------|
| 设备未连接时型号为空 | 🟡 中 | 用户未先 connect_device | model=None 时跳过多源查询，回退 COMMAND_TEMPLATES（与当前行为一致） |
| suggest_commands 返回空 | 🟢 低 | 设备型号在 structured_kb 中无匹配 | 降级到 config_methods → 经验 → 模板 |
| function 名与 protocol 名不匹配 | 🟡 中 | structured_kb 的 function 名（如"VLAN端口"）与 planner protocol（vlan）不一致 | `_fuzzy_match` 做关键词子串匹配 |
| PlanNode 新字段改变序列化 | 🟢 低 | 旧 API 消费者依赖 to_dict() 返回的特定键集 | 新字段带默认值不破坏反序列化；to_dict() 自动包含 |
| knowledge.py 循环导入 | 🟢 低 | planner 导入 knowledge，knowledge 不导入 planner | 无循环依赖 |
| struct_kb 命令优先级过高 | 🟡 中 | structured_kb 的命令不适用于当前拓扑（如接口名不同） | 仅在 function 名称精确匹配时才覆盖；`use_structured_kb` 开关可关闭 |

### function 名称模糊匹配策略

```python
def _fuzzy_match(node_key: str, func_name: str) -> bool:
    """模糊匹配 plan 节点标识与 structured_kb function 名。
    
    示例:
        node_key='vlan', func_name='VLAN'        → True
        node_key='ospf', func_name='OSPF路由'     → True
        node_key='interface', func_name='接口配置' → True
        node_key='bgp', func_name='BGP路由'       → True
    """
    nk = node_key.lower()
    fn = func_name.lower()
    return nk in fn or fn in nk
```

---

## 5. 分阶段实施计划

| 阶段 | 批次 | 改动 | 预期测试增量 | 验收标准 |
|------|------|------|------------|---------|
| 1 | 批次1 | planner 接入 structured_commands_kb | +8 用例 | S5700 VLAN 查询到结构化命令；USG6000V NAT 命令正确 |
| 2 | 批次2 | config_methods 接入 | +4 用例 | "配置 OSPF" 命中 ospf_basic 方法并获取步骤命令 |
| 3 | 批次3 | 设备型号运行时获取 | +3 用例 | connect_device 后 planner 自动感知型号 |

### 阶段1 验收场景

当前（修复前）：
```python
goal = TaskGoal(description='USG6000V NAT', ...)
plan = planner.plan_from_goal(goal)
plan.nodes['nat'].commands
# → ['interface GE0/0/0', 'nat outbound 3001', 'quit']  ← 错误！
```

修复后（批次1）：
```python
planner.set_knowledge_base(kb)
goal = TaskGoal(description='USG6000V NAT', ...)
plan = planner.plan_from_goal(goal, devices={'model': 'USG6000V'})
plan.nodes['nat'].commands
# → ['nat-policy', 'source-zone trust', 'destination-zone untrust', 'action source-nat easy-ip']  ← 正确！
```

---

## 6. 向后兼容性保证

| 改动 | 兼容措施 |
|------|---------|
| PlanNode 新字段 | 默认值 "" / False，现有构造不传值行为不变 |
| planner 新方法 | setter 可选注入，未注入时跳过 |
| planner 新开关 | 默认 True 但未注入时自动降级 |
| runtime 传 devices | devices 为 None 时 planner 行为与当前完全一致 |
| config_methods 传参 | 参数默认 None，不传时行为不变 |

---

## 7. 设计决策记录

### 为什么不在 plan_from_goal 签名上加新参数？

planner.plan_from_goal 已有 `devices` 参数但从未被有效使用。本设计复用该参数传递设备型号信息（`{'model': 'S5700'}`），无需新增签名参数。config_method_commands 作为 `knowledge_context` dict 的一个 key 传递（如 `knowledge_context['config_method_commands']`），也无需新参数。

### 为什么 KnowledgeBase 通过 setter 注入而非 import？

- 解耦：planner.py 不硬依赖 knowledge.py
- 可测试：单元测试可注入 mock kb
- 可回滚：set_knowledge_base(None) 关闭结构化命令查询

### 为什么 function 匹配用模糊而非精确？

structured_kb 的 function 名是中文描述（如"VLAN端口"、"OSPF路由"），planner 的 protocol 是英文（如"vlan"、"ospf"）。精确匹配会大量漏匹配。模糊匹配 `nk in fn or fn in nk` 覆盖中英文对应场景。

### 为什么不把 config_methods 优先级排在 structured_kb 之前？

config_methods 是按实验目标组织的完整步骤序列（如"OSPF基础配置"的 5 步），而 structured_kb 是按设备型号整理的单条命令。对于"配置 XXX"这种任务，完整步骤序列比单条命令更适合直接使用。但 structured_kb 的优势在于精确匹配设备型号（USG6000V 的 NAT 命令与 S5700 完全不同），因此本设计将 structured_kb 排 P1、config_methods 排 P2，config_methods 补充未被 P1 覆盖的节点。

---

## 8. 总结

本设计只需 **≤4 文件/批次**，不删除 COMMAND_TEMPLATES，不改变现有 API 签名，所有增强通过 setter 注入 + 开关控制，可随时回退。核心改动：planner 增加 `_enrich_with_structured_kb` 方法调用 `suggest_commands` + runtime 传递设备型号给 planner。修复后 USG6000V NAT 场景从"生成错误命令"变为"从结构化 KB 获取正确防火墙 NAT 命令"。
