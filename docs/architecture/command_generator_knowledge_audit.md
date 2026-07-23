# CommandGenerator Knowledge Integration Audit

> **审计 ID** | **日期** 2026-07-21 | **范围** command_generator.py / planner.py / runtime.py / knowledge.py
> **方法** 代码审查 + 三个真实场景端到端追踪（S5700 VLAN / AR2220 OSPF / USG6000V NAT）
> **状态** 只读审计，未修改代码

---

## 1. 调用链图

### 实际调用链（当前生效）

```
用户需求 "配置VLAN"
    │
    ▼
runtime.execute_task()
    ├─ 阶段2.5: config_methods.search_methods()  ← 只 log，不传给 planner
    ├─ 阶段3:   knowledge.query_for_task()       ← 传给 planner 作 knowledge_context
    │
    ▼
planner.plan_from_goal()
    ├─ _match_template() → 匹配到 campus/ospf_area/bgp/vpn/basic_routing 模板
    ├─ _extract_protocols() → 关键词匹配协议
    ├─ _resolve_commands() → COMMAND_TEMPLATES 硬编码 VRP 命令  ← 主来源
    ├─ _apply_experience() → knowledge_store 成功经验覆盖        ← 第二阶段加入
    ├─ _add_verification_nodes() → 拼 display/ping 命令
    └─ _check_capabilities() → device 为 None，跳过
    │
    ▼ PlanNode.commands = ['vlan 10', 'quit']
    │
    ▼
runtime._execute_config_node()
    └─ self._exec_cmd(device_path, cmd)  ← 直接发命令，不经 CommandGenerator
```

### CommandGenerator 孤岛链（未接入）

```
[未接入]
runtime_action.py (孤岛)
    → DAGPlanner  → ActionPlan (新 AST)
    → CommandGenerator.generate(state, action)  ← 视图导航 + 命令组装
        ├─ 查 ACTION_VIEW_MAP（目标视图映射）← 硬编码
        ├─ _get_enter_command（进入视图命令） ← 硬编码模板
        └─ _get_core_commands（从 action.params 取命令）← 命令来源在上游
```

### 理想调用链（设计意图，未实现）

```
用户需求 → Planner（查 suggest_commands + knowledge_store + capability）
         → PlanNode（含 device/model/view_type 元信息）
         → CommandValidator（视图校验）
         → CommandGenerator（根据 CLIState + 结构化命令库生成完整序列）
         → CommandExecutor（执行）
```

---

## 2. 实际调用文件与引用关系

### command_generator.py（282 行）

| 检查项 | 结果 |
|--------|------|
| 是否 import knowledge.py | ❌ 无 |
| 是否调用 suggest_commands | ❌ 无 |
| 是否查询 system_view | ❌ 无 |
| 是否使用设备型号 | ❌ 无（仅处理 CLIView 枚举） |
| 命令来源 | `action.params["commands"]`（上游传入） |
| 知识调用 | 0 处 |
| 在 runtime.py 中是否使用 | ❌ **runtime.py 不 import CommandGenerator** |

**结论**：CommandGenerator 本身不负责命令生成——它只是视图导航器。真正的命令来源于 planner.COMMAND_TEMPLATES。

### planner.py（480 → 约 540 行，第二阶段扩充后）

| 检查项 | 结果 |
|--------|------|
| 是否 import knowledge.py | ❌ 无 |
| 是否调用 suggest_commands | ❌ 无 |
| 是否调用 get_structured_kb | ❌ 无 |
| 是否使用 knowledge_store | ✅ 第二阶段 `_apply_experience`（仅运行时，需 runtime 注入） |
| 是否使用 capability_manager | ✅ 第二阶段 `_check_capabilities`（仅运行时，需 runtime 注入 + devices 参数） |
| PlanNode 是否含 device 信息 | ❌ `PlanNode.device_path` 默认为 "" |
| PlanNode 是否含 view_type | ❌ 无此字段 |
| 命令主要来源 | `COMMAND_TEMPLATES` 模块级硬编码常量 |

**PlanNode 携带的字段**：node_id、label、node_type、commands、dependencies、verify_commands。**不携带** device/device_model/view_type/required_view。

### runtime.py（约 490 行，第二阶段扩充后）

| 检查项 | 结果 |
|--------|------|
| 是否 import CommandGenerator | ❌ 无 |
| 是否调用 suggest_commands | ❌ 无 |
| 阶段 2.5 config_methods 查询结果 | ❌ **只 log，不传给 planner**（L150-157） |
| 阶段 3 knowledge_context 查询 | ✅ 传给 planner，但 planner 只用作变量合并 |
| 执行前是否有知识校验 | ❌ 无（_execute_config_node 直接发 node.commands） |
| 执行前是否有视图校验 | ❌ 无（command_validator 仍在孤岛状态） |

---

## 3. 知识库使用情况

### 三层知识源现状

| 知识源 | 存储位置 | 是否被命令生成链路使用 | 说明 |
|--------|---------|---------------------|------|
| **knowledge_store**（经验） | agent/knowledge_store.py | ✅ 第二阶段接入了（_apply_experience） | runtime 注入后 planner 可用 |
| **structured_commands_kb**（结构化命令） | kb/structured_commands_kb.json | ❌ **完全不使用** | 刚修复了路径 bug，但无调用方 |
| **config_methods**（配置方法） | kb/config_methods/ | ❌ 阶段2.5查询但只 log 不用 | 18 个方法、完整步骤命令 |
| **best_practices** | kb/best_practices.json | ❌ 不查询 | 12 条实战规则 |
| **troubleshooting_cases** | kb/troubleshooting_cases.json | ❌ 不查询 | 12 个排障案例 |

### 命令生成优先级（实际情况 vs 期望）

| 实际优先级 | 期望优先级 |
|-----------|-----------|
| 1. COMMAND_TEMPLATES 硬编码 | 1. knowledge_store 成功经验 |
| 2. knowledge_store 经验覆盖（第二阶段后） | 2. structured_commands_kb 结构化命令库 |
| 3. （无更多层级） | 3. config_methods 配置方法 |
| | 4. COMMAND_TEMPLATES 规则模板（兜底） |

**差距**：缺乏 structured_commands_kb 和 config_methods 的接入，命令生成实际只有两层（模板 + 经验覆盖）。

### config_methods 查询被忽略的实证

```python
# runtime.py L150-157（当前代码）
if config_method_results:
    logger.info('[阶段2.5] 配置方法库命中: %d 个方法', ...)
    best_method = config_method_results[0]
    standard_commands = self.config_methods.get_method_commands(best_method.get('id'))
    logger.info('[阶段2.5] 标准命令序列: %s', standard_commands[:5])
    # ⚠ 仅 log，不传给 planner！
else:
    logger.info('[阶段2.5] 配置方法库无命中，将查询知识库')
```

---

## 4. 三个真实场景追踪

### 场景1：S5700 VLAN 配置

```
输入: "VLAN配置 S5700 创建VLAN10"
输出: config[vlan]: ['vlan 10', 'quit']
      verify[final_verify]: ['display ip interface brief', 'display ip routing-table', 'ping 192.168.20.1']
```

| 维度 | 评估 |
|------|------|
| 命令来源 | COMMAND_TEMPLATES['vlan'] |
| 是否正确 | ✅ 基本正确（vlan 10, quit） |
| 是否考虑设备型号 | ❌ S5700 信息被忽略 |
| 是否查询 structured_commands_kb | ❌ 未查询（S5700 system_view 有 59 条命令含 VLAN端口/VLANIF接口） |
| 缺少的命令 | port link-type access、port default vlan（access 节点但未匹配到 S5700 的 VLAN端口 function） |
| 经验覆盖可用性 | ⚠ 第二阶段后，若有历史 VLAN 成功实验可覆盖 |

### 场景2：AR2220 OSPF 配置

```
输入: "AR2220 OSPF路由配置 area 0 network 192.168.1.0"
输出: config[interface]: ['interface GE0/0/1', 'ip address 192.168.1.0 255.255.255.0', 'quit']
      config[ospf]: ['ospf 1 router-id 1.1.1.1', 'area 0', 'network 192.168.10.0 0.0.0.255', 'quit', 'quit']
```

| 维度 | 评估 |
|------|------|
| 命令来源 | COMMAND_TEMPLATES['ospf'] |
| 是否正确 | ⚠ 部分正确（ospf/router-id/area/network 结构对） |
| 变量提取问题 | 提取了 `192.168.1.0` 作为 ip，但 **network 声明用了默认值 192.168.10.0**（`_extract_variables` 只取第一个 IP 给 gateway，第二个 IP 给 target_ip，没给 network） |
| Router-ID 默认值 | `1.1.1.1` 硬编码，未从用户输入推断 |
| 是否查询 structured_commands_kb | ❌ 未查询（AR2220 system_view 有 OSPF路由/BGP路由 等 15 条命令） |
| 经验覆盖可用性 | ⚠ AR2220 OSPF 在 AR2220 的 `经验积累` function 下有经验命令 |

### 场景3：USG6000V NAT 配置 🔴

```
输入: "USG6000V NAT配置 Easy-IP"
输出: config[interface]: ['interface GE0/0/1', 'ip address 10.0.0.1 255.255.255.0', 'quit']
      config[nat]: ['interface GE0/0/0', 'nat outbound 3001', 'quit']
```

| 维度 | 评估 |
|------|------|
| 命令来源 | COMMAND_TEMPLATES['nat'] |
| 是否正确 | 🔴 **完全错误** |
| 问题 | `nat outbound 3001` 是交换机/路由器的 NAT 命令。**USG6000V 防火墙的 NAT 命令完全不同**：应为 `nat-policy` + `source-zone trust` + `destination-zone untrust` + `action source-nat easy-ip` |
| 根本原因 | COMMAND_TEMPLATES 只有一套 VRP 交换/路由 NAT 命令，无防火墙版本 |
| 是否查询 structured_commands_kb | ❌ 未查询（USG6000V system_view 有 NAT策略 function，含正确命令） |
| device_model 传递 | ❌ **planner 完全不知道设备是 USG6000V** —— description 里的型号信息被 _extract_variables 忽略 |

---

## 5. 存在的问题（按严重度排序）

### P0 — 命令生成不感知设备型号

**影响**：所有场景都受影响。planner 不区分 S5700/USG6000V，用同一套 COMMAND_TEMPLATES 生成命令。场景3（USG6000V NAT）为典型案例——生成了完全错误的命令。

**根因**：
- `PlanNode` 无 device/device_model 字段
- `planner.plan_from_goal` 的 `devices` 参数从未被有效使用
- `runtime.execute_task` 的 `device_paths` 是 IP:Port 形式（如 `127.0.0.1:2000`），不含型号信息

### P0 — structured_commands_kb 查询通路完全断开

**影响**：刚修复的 176 条 system_view 配置命令、48 条 user_view 查看命令无法被命令生成链路使用。

**根因**：
- `planner.py`：不 import knowledge，不调 suggest_commands/get_structured_kb
- `runtime.py`：不调任何 structured_commands_kb 相关方法
- `command_generator.py`：孤岛状态，不调 knowledge

### P1 — config_methods 查询结果被丢弃

**影响**：18 个配置方法的完整命令序列只用于日志打印，不传给命令生成链路。

**根因**：runtime L150-157 查询了配置方法库但只 log，不传给 planner。

### P1 — 命令生成缺乏多源融合

**实际流程**：
```
COMMAND_TEMPLATES 硬编码 → (可选) 经验覆盖 → 直接执行
```

**缺少的层级**：
```
suggest_commands(device_model, 'system_view')  ← 刚修复但无人调用
config_methods.get_method_commands(id)         ← 查询了但丢弃了
capability_manager.check_protocol(model, proto) ← 注入了但 devices 为空
```

### P2 — PlanNode 缺乏视图/能力元信息

**缺失字段**：
- `device_model`: str — 设备型号
- `required_view`: str — 命令需要的视图（system_view/user_view/interface_view）
- `capability_check`: bool — 是否通过能力校验
- `knowledge_source`: str — 命令来源（template/experience/structured_kb/config_method）

### P2 — CommandGenerator 孤岛

CommandGenerator 代码已写完（282 行），但 runtime.py 不用它。即使 CommandGenerator 接入，它也不查知识库——它只是视图导航器 + 命令组装器。真正的知识调用需要在 Planner 层完成。

---

## 6. 优化建议

### 立即可做（不改架构，打通已有数据源）

| 优先级 | 改动 | 文件 | 预期效果 |
|--------|------|------|---------|
| P0 | planner 增加 `suggest_commands` 查询，按设备型号取结构化命令覆盖 COMMAND_TEMPLATES | planner.py | 场景3 NAT 命令从错误→正确 |
| P0 | runtime 传递 device_model 给 planner（从 device_manager 或 scan_devices 获取型号） | runtime.py | 命令生成感知设备型号 |
| P1 | runtime 阶段2.5 config_methods 结果传给 planner 作为命令备选 | runtime.py | config_methods 不再白查 |
| P1 | PlanNode 增加 device_model/required_view 字段 | types.py | 元信息沿链路传递 |

### 渐进式（小步接入孤岛模块）

| 优先级 | 改动 | 说明 |
|--------|------|------|
| P1 | runtime 接入 CommandGenerator（用 suggest_commands 的输出构造 Action） | CommandGenerator 从孤岛变活跃 |
| P2 | 接入 command_validator（执行前校验视图） | 需先接入 cli_state |

### 命令生成优先级（修复后目标）

```
1. knowledge_store 成功经验（已接入，第二阶段）
2. structured_commands_kb suggest_commands（未接入 ← 本次建议）
3. config_methods get_method_commands（查询了但丢弃 ← 本次建议）
4. COMMAND_TEMPLATES 硬编码模板（兜底）
```

### 不需要的：LLM 生成

当前架构中 LLM 不直接生成命令（planner 的 _extract_variables 只做变量提取，不确定命令语法）。如未来引入 LLM 生成，应排在结构化知识库之后作为最终兜底。

---

## 7. 总结

**核心结论**：CommandGenerator 知识调用链处于"知识数据已就绪、但查询通路完全断开"的状态。刚修复的 structured_commands_kb（176 条 system_view 命令）和 config_methods（18 个配置方法）在命令生成链路中完全未被使用。planner 仍依赖纯硬编码 COMMAND_TEMPLATES，导致设备型号不感知（场景3 USG6000V NAT 命令完全错误）。

**建议优先修 P0 两项**：planner 增加 suggest_commands 查询 + runtime 传递 device_model。这两个改动 ≤3 文件，即可让刚修复的 176 条结构化命令生效。
