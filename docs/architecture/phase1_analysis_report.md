# eNSP-MCP 项目架构分析报告（第一阶段）

> **版本** v3.0.0 | **分析日期** 2026-07-20 | **阶段** 第一阶段（只读分析，未修改任何代码）
> **基线测试** README 记录 236 passed / 3 skipped；AGENTS.md 记录 223 passed / 3 skipped；`docs/architecture/system.md` 记录 224 条 —— **三处数字不一致，本身就是待修风险**
> **分析方法** 通读 README/AGENTS/pyproject + 全量扫描 `mcpensp1/agent/` 23 个文件 + 12 个核心模块 + `kb/` 知识库 + 15 个测试文件

---

## 0. 执行摘要（先看这段）

项目目标宏大——"理解网络实验目标、自主规划、自动配置、错误诊断恢复、经验学习"——但当前实现与目标之间存在**结构性差距**，核心矛盾集中在三处：

1. **"已实现但未接入"的孤岛子系统**：`agent/` 目录 23 个文件中，**11 个模块（capability_manager / plan_reviewer / transaction / runtime_action / action_types / cli_state / prompt_parser / command_generator / command_validator / dependency_graph / error_library）代码已写完、有测试覆盖，但 `AgentRuntime.execute_task` 从未实例化或调用它们**。`docs/architecture/system.md:112` 官方确认这一点。这意味着"Planner 先查能力矩阵"、"计划必须审核"、"事务回滚"、"Action 驱动引擎"、"命令执行前校验"等关键能力**当前全部未生效**，所谓闭环 Agent 实际只是 `planner → executor → verifier → reflection → learning` 五段直线流程。

2. **命令生成仍为规则驱动，非经验驱动**：`planner.py` 的 `COMMAND_TEMPLATES` 全部硬编码华为 VRP 命令与默认变量（甚至含弱口令 `psk='Admin@123'`），`_extract_variables` 用简单正则，**不查询 capability_manager、不读取 knowledge_store 的成功经验、不感知当前 CLI 状态**。`knowledge_store.search` 的评分函数硬编码权重，`_find_similar` 用 `md5[:12]` 精确匹配——语义相似但格式微差的经验无法去重也无法被检索复用。"从规则驱动 Agent 提升到经验驱动 Agent" 这一目标尚未起步。

3. **接口映射依赖硬编码经验规则，无自动推理**：`srcIndex → G0/0/N` 的映射在 `app.py:174-194` 和 `knowledge.py:586-606` 各有一份（后者是死代码），规则固定拼 `{name}0/0/{idx}`，**无法区分盒式设备（S5700 的 `0/0/1` 起始）与子卡设备（AR 路由器的 `0/0/0` 起始）**。无 `display interface` / LLDP / 邻居 MAC 回填机制，纯靠 `.topo` 文件解析。这与工作记忆中"永远不信任 .topo 的 srcIndex"的实战教训直接冲突。

其余风险：`app.py` 1699 行胖文件 + 双重设备状态源、47 个 MCP 工具一半直连一半 HTTP 绕行 Flask、全项目零自定义异常类、`except Exception: pass` 静默吞错 30+ 处、循环依赖检测在 5 个文件重复实现。

---

## A. 当前系统架构图

### A.1 分层架构（含孤岛标注）

```
+--------------------------------------------------------------+
|  AI Client (Codex / Claude / Cursor)                         |
|              ↓ MCP stdio                                      |
+--------------------------------------------------------------+
|  mcp_server.py  (47 tools)                                   |
|   ├── 32 个直连本地单例                                       |
|   └── 15 个经 HTTP 绕回 Flask (10 Agent + 5 KB)  ⚠ 强耦合双进程 |
+--------------------------------------------------------------+
|  Flask app.py (1699 行, 74 端点)   |   直连模块层              |
|   ├── 设备/拓扑/实验 HTTP 端点     |   device_manager (连接池) |
|   ├── 拓扑解析 (含死代码副本)       |   command_executor       |
|   └── 模块级 devices/dict ⚠ 双源   |   topology.py (53 行)    |
|                                    |   knowledge.py (607 行)  |
|                                    |   view_router / heartbeat |
+--------------------------------------------------------------+
|  Agent Runtime (agent/runtime.py, 437 行)                    |
|  ┌─────────────── 已接入 (7) ──────────────┐ ┌── 孤岛 (11, 未接入) ──┐
|  │ planner  runtime  verifier              │ │ capability_manager    │
|  │ reflection  learning  memory            │ │ plan_reviewer         │
|  │ knowledge_store                          │ │ transaction           │
|  └──────────────────────────────────────────┘ │ runtime_action        │
|                                                │ action_types          │
|                                                │ cli_state             │
|                                                │ prompt_parser         │
|                                                │ command_generator     │
|                                                │ command_validator     │
|                                                │ dependency_graph      │
|                                                │ error_library         │
|                                                └───────────────────────┘
+--------------------------------------------------------------+
|  TelnetConnection (434 行, 8 处静默 except)                  |
+--------------------------------------------------------------+
|  eNSP 仿真设备 (localhost:2000+)                              |
+--------------------------------------------------------------+
```

### A.2 数据流真相

| 流向 | 实际路径 | 设计意图 | 差距 |
|------|---------|---------|------|
| AI → 设备 | `mcp_server.send_command → dm.get → conn.send_cmd_async` | 直连 | ✅ 符合 |
| AI → Agent | `mcp_server.agent_execute → HTTP /api/agent/execute → AgentRuntime` | 应直连 | ⚠ 同进程 HTTP 往返，30s 超时风险 |
| Agent → 设备 | `AgentRuntime → command_executor → telnet` | 经 command_validator/transaction | ❌ **直接执行，无校验、无事务、无回滚** |
| Agent → 知识 | `planner.plan_from_goal` | 应查 knowledge_store 经验 | ❌ **不查，纯用硬编码 COMMAND_TEMPLATES** |
| 失败 → 恢复 | `recovery.attempt_recovery → 重跑 node.commands` | 应联动 transaction 回滚 | ❌ **无回滚，错误视图上重复执行** |

---

## B. Agent 执行流程

### B.1 当前实际流程（5 段直线）

```
agent_execute(request)
  │
  ├─ 1. PLANNING     planner.plan_from_goal(goal, knowledge_context, devices)
  │                   └─ 用硬编码 COMMAND_TEMPLATES 拼命令
  │                   └─ ❌ 不查 capability_manager
  │                   └─ ❌ 不查 knowledge_store 成功经验
  │                   └─ ❌ 不调 plan_reviewer 审核
  │
  ├─ 2. EXECUTING    _execute_plan_loop → _execute_config_node
  │                   └─ command_executor.batch_command
  │                   └─ ❌ 不经 command_validator 校验视图
  │                   └─ ❌ 不开 transaction（无快照、无回滚）
  │                   └─ ❌ _select_device 只取 device_paths[0]，多设备实验打同一台
  │
  ├─ 3. VERIFYING    verifier.verify_all(device_path)
  │                   └─ 自己发 display 命令（绕过 command_validator）
  │                   └─ ⚠ 解析全靠正则 + split()，版本脆弱
  │                   └─ ⚠ verify_acl 仅判输出含 'rule'/'acl' 字符串（几乎永真）
  │                   └─ ⚠ verify_connectivity ping 丢包<100% 即判通过
  │
  ├─ 4. 失败分支     recovery.analyze_failure + attempt_recovery
  │                   └─ ❌ 重跑 node.commands 不回滚（与 transaction 未联动）
  │                   └─ ❌ ERROR_PATTERNS 与 error_library 重复定义但未调用
  │                   └─ 最多 3 轮，无部分提交策略
  │
  ├─ 5. REFLECTING   reflection.reflect(result)
  │                   └─ ⚠ 纯字符串拼接，无因果分析
  │                   └─ _suggest_knowledge_updates 生成建议但不落库
  │
  └─ 6. LEARNING     learning.learn_from_experiment(result, reflection)
                      └─ ❌ device_type 全硬编码 'huawei'
                      └─ ❌ record_verify_method 传 commands=[]（数据缺失）
                      └─ ⚠ _suggest_template 未真正模板化
```

### B.2 理想流程（设计意图，当前未实现）

```
agent_execute
  ├─ 0. GOAL_PARSE      prompt_parser 理解自然语言目标
  ├─ 1. CAPABILITY      capability_manager 查设备能力矩阵
  ├─ 2. PLAN            planner + knowledge_store 经验检索 → ActionPlan
  ├─ 3. VALIDATE_PLAN   plan_reviewer 审核（危险命令/视图/循环/能力）
  ├─ 4. TRANSACTION     transaction 开快照
  ├─ 5. VALIDATE_CMD    command_validator 逐条校验视图权限
  ├─ 6. GENERATE        command_generator 基于 CLIState 生成完整序列
  ├─ 7. EXECUTE         command_executor 执行
  ├─ 8. VERIFY          verifier 语义验证
  ├─ 9. FAIL→RECOVER    recovery 分析 + transaction 回滚 + 重试
  ├─ 10. REFLECT        reflection 因果分析
  └─ 11. LEARN          learning 落库 memory + knowledge_store
```

**差距清单（11 步理想 vs 6 步实际）**：缺失 0/1/3/4/5/6/9 五个阶段；第 2/7/8/10/11 步虽存在但均有缺陷。

### B.3 状态机（当前实现）

```
IDLE → PLANNING → EXECUTING → VERIFYING → COMPLETED
                    ↑              │
                    │       ┌──────┘
                    │       ↓
                    └── RECOVERING (max 3 轮) → FAILED
```

`TaskPhase` 枚举定义在 `types.py`，`runtime._update_phase` 驱动。

---

## C. 模块职责分析

### C.1 已接入运行链路的 7 个模块

| 模块 | 行数 | 输入 | 输出 | 职责 | 主要隐患 |
|------|------|------|------|------|---------|
| `planner.py` | 480 | TaskGoal, knowledge_context | ExecutionPlan | DAG 规划 + 硬编码命令模板 | COMMAND_TEMPLATES 含弱口令；不查能力矩阵；不查经验 |
| `runtime.py` | 437 | NL request, device_paths | ExperimentResult | 11 阶段闭环编排 | `sys.path.insert` 污染；execute_task 130 行巨型函数；_select_device 只取 [0] |
| `verifier.py` | 381 | device_path, executor | VerificationResult[] | 发 display 命令 + 正则解析 | verify_acl 几乎永真；verify_connectivity 0% 与 99% 丢包同等对待 |
| `reflection.py` | 166 | ExperimentResult | ReflectionEntry | 经验总结 | 纯字符串拼接无因果；与 learning 边界模糊 |
| `learning.py` | 179 | result + reflection | 计数 + 落库 | 写 memory/knowledge | device_type 硬编码 'huawei'；verify_method 传空 commands |
| `memory.py` | 286 | MemoryEntry | 记忆列表 | 长期记忆 + 衰减 | md5[:8] 去重过严；recall 中 touch() 锁外修改 |
| `knowledge_store.py` | 383 | KnowledgeRecord | 知识列表 | 增长知识库 | search 评分硬编码权重；md5[:12] 去重过严；未被 planner 调用 |

### C.2 孤岛模块（11 个，已实现未接入）

| 模块 | 行数 | 设计职责 | 未接入后果 | 接入难度 |
|------|------|---------|-----------|---------|
| `capability_manager.py` | 244 | 设备能力矩阵查询 | planner 不校验协议支持，对不支持设备也生成命令 | 低（硬编码 6 款设备表，需扩数据） |
| `plan_reviewer.py` | 293 | 计划安全审核 | 危险命令/视图错误/循环依赖直接放行 | 中（接受 dict 而非 ActionPlan，类型需统一） |
| `transaction.py` | 259 | 快照-执行-验证-回滚 | 失败无法回滚，错误状态残留设备 | 中（rollback 未真正用 snapshot_data） |
| `runtime_action.py` | 412 | Action 驱动新引擎（14 步） | 与 runtime.py 大量重复，未替换 | 高（两套并存，需二选一或合并） |
| `action_types.py` | 194 | 新 AST（Action/ActionPlan） | 与 types.PlanNode 两套并行 AST | 高（牵一发动全身） |
| `cli_state.py` | 256 | CLI 视图栈状态机 | 命令执行不感知当前视图 | 中（与 command_generator 重复导航逻辑） |
| `prompt_parser.py` | 192 | prompt → 视图解析 | cli_state 无法更新，视图漂移 | 中（_extract_params 空 except 吞错） |
| `command_generator.py` | 282 | Action+CLIState → CLI 序列 | 命令生成不基于状态 | 中（与 planner.COMMAND_TEMPLATES 平行） |
| `command_validator.py` | 283 | 执行前视图校验 | 错误视图命令直接发往设备 | 中（_simulate_execution 与 cli_state 重复） |
| `dependency_graph.py` | 251 | Action 依赖图 + 恢复子图 | 循环检测在 5 处重复实现 | 中（与 types.ExecutionPlan._recompute_order 重复） |
| `error_library.py` | 136 | 华为 CLI 错误查询 | recovery 不查库，用本地 ERROR_PATTERNS | 低（lookup 关键词截断 15 字符） |

**孤岛接入收益估算**：接入 `capability_manager + plan_reviewer + command_validator + transaction + error_library` 这 5 个低中难度模块，即可补齐"执行前校验"和"失败回滚"两大缺口；接入 `cli_state + prompt_parser` 可解决命令生成不感知状态的核心问题。

### C.3 非 agent 模块的核心组件

| 模块 | 行数 | 职责 | 主要隐患 |
|------|------|------|---------|
| `mcp_server.py` | 532 | 47 工具注册 + dispatch | 9 处 except Exception；15 个工具 HTTP 绕行 |
| `app.py` | **1699** | Flask + 拓扑解析 + 设备操作 + 实验 | **胖文件**；24 处 except；模块级 devices dict 与 dm 双源；本地 TopologyEngine 死代码副本 |
| `topology.py` | 53 | 拓扑引擎（被动接收 dict） | **无主动发现**；无 srcIndex 推理 |
| `device_manager.py` | 163 | 连接池 + 保活 | 3 处静默 |
| `command_executor.py` | 129 | 命令发送 + 解析 | 1 处静默 |
| `view_router.py` | 137 | 视图感知路由 + VRP 冷却 | 2 处 except |
| `connection.py` | 434 | Telnet + 缓冲 + 超时 | **8 处静默 except**；防火墙登录失败无法区分原因 |
| `knowledge.py` | 607 | 配置方法 CRUD + 经验积累 | 9 处 except；含死代码 `_build_interface_map` 副本 |
| `services.py` | 20 | 服务聚合 | 无隐患 |
| `heartbeat.py` | 150 | 心跳 + 保活 | 1 处静默 |
| `config_method_store.py` | 347 | 配置方法 JSON 存储 | 5 处 except |

### C.4 知识库结构（`mcpensp1/kb/`）

| 子库 | 文件 | 状态 |
|------|------|------|
| `config_methods/` | 18 个 JSON（VLAN/OSPF/DHCP/static_route/ACL/NAT/BGP/VRRP/STP/Eth-Trunk/RIP/防火墙3个/接口/远程管理/VRP文件系统/AC无线） + `_index.json` | ✅ 完整，覆盖主流实验 |
| `errors/huawei_errors.json` | 1 个 | ✅ 有库，但 `error_library.lookup` 关键词截断 15 字符，匹配脆弱 |
| `cli/view_rules.json` | 1 个 | ✅ 有规则，但 `command_validator` 默认规则可能与之不一致 |
| `best_practices.json` | 1 个 | ✅ 可用 |
| `troubleshooting_cases.json` | 1 个 | ✅ 可用 |
| `structured_commands_kb.json` | 1 个 | ⚠ bootstrap 迁移源，迁移后用途不明 |
| `global_kb.json` / `devices_kb.json` | 2 个 + 2 个 `_backup_` | ⚠ 遗留，`knowledge.py:9-13` 仍 forward ref |
| `ap_online_flow.md` / `campus_network_experiment.md` / `ensp_command_reference.md` | 3 个 md | ✅ 文档型知识 |

**知识库调用现状**：`planner.py` **不查** knowledge_store；`recovery.py` 查了但 `except Exception: pass` 静默吞；`learning.py` 写入但数据质量差（device_type 硬编码、verify_method 空 commands）。**"经验驱动"目标在数据层有基础设施，在调用层完全断开**。

### C.5 测试覆盖（15 文件 / 2744 行 / ~268 用例）

| 测试文件 | 行数 | 用例数 | 覆盖范围 | 评估 |
|---------|------|--------|---------|------|
| `test_smoke.py` | 425 | 32 | 端到端冒烟 | ⚠ 需真实 eNSP，skip |
| `test_safety_framework.py` | 409 | 41 | 安全框架 | ✅ 充分 |
| `test_cli_state_machine.py` | 611 | 60 | CLI 状态机（孤岛模块） | ✅ 充分，但测的是未接入模块 |
| `test_action_architecture.py` | 284 | 26 | Action 架构（孤岛模块） | ✅ 充分，但测的是未接入模块 |
| `test_unit.py` | 257 | 25 | 单元 | ✅ |
| `test_regression.py` | 143 | 13 | 回归 | ✅ |
| `test_agent_runtime.py` | 157 | **10** | Agent 闭环 | ❌ **严重不足**，11 阶段仅 10 用例 |
| `test_agent_tools_proxy.py` | 93 | **2** | Agent MCP 代理 | ❌ **几乎没测** |
| 其余 7 个 | 365 | 59 | 各专项 | ✅ |

**关键缺口**：
- Agent 闭环执行（`runtime.execute_task`）仅 10 用例，且大部分是 happy path
- 命令生成准确率**无专项测试**（planner.COMMAND_TEMPLATES 输出无校验）
- 接口映射（`_build_interface_map` / `_resolve_interface`）**无测试**
- 失败恢复 + 事务回滚**无测试**（transaction 模块未接入）
- 知识库学习闭环（learning → knowledge_store → planner 检索）**无端到端测试**

---

## D. 潜在风险（按用户 P0-P5 优先级分级）

### P0 — 命令生成准确率（最高优先级）

| 风险 | 位置 | 影响 | 严重度 |
|------|------|------|--------|
| `COMMAND_TEMPLATES` 全硬编码，含弱口令 `psk='Admin@123'` | `planner.py` 模块级 | 命令生成不基于拓扑/型号/状态/经验；安全风险 | 🔴 严重 |
| `_extract_variables` 用简单正则提 IP/掩码/端口 | `planner.py` | IP/掩码/端口易错配 | 🔴 严重 |
| planner 不查 `knowledge_store` 成功经验 | `planner.py:plan_from_goal` | "经验驱动"目标未起步 | 🔴 严重 |
| planner 不查 `capability_manager` | `planner.py:plan_from_goal` | 对不支持设备也生成命令 | 🟠 高 |
| 命令生成不感知 `CLIState` | `planner.py` vs `command_generator.py` | 视图错误命令直接发出 | 🟠 高 |
| 接口映射 `_build_interface_map` 硬编码 `0/0/{idx}` | `app.py:174-194` | 无法区分 0 起始 vs 1 起始设备 | 🔴 严重 |
| 接口映射死代码副本 | `knowledge.py:586-606` | 维护改错风险 | 🟡 中 |

### P1 — 执行稳定性

| 风险 | 位置 | 影响 | 严重度 |
|------|------|------|--------|
| 11 个孤岛模块未接入，校验/事务/回滚全缺位 | `agent/runtime.py` | 错误命令直接发设备，失败无回滚 | 🔴 严重 |
| `_select_device` 只取 `device_paths[0]` | `runtime.py` | 多设备实验全打到同一台 | 🔴 严重 |
| `recovery.attempt_recovery` 重跑不回滚 | `recovery.py` | 错误视图重复执行放大故障 | 🟠 高 |
| `verifier.verify_acl` 几乎永真 | `verifier.py` | ACL 配错也能"通过" | 🟠 高 |
| `verifier.verify_connectivity` 0% 与 99% 丢包同等 | `verifier.py` | ping 几乎全丢也算通过 | 🟠 高 |
| `connection.py` 8 处静默 except | `connection.py` | 防火墙登录失败无法区分原因 | 🟠 高 |
| `app.py` 模块级 devices dict 与 dm 双源 | `app.py:74-82` | 状态不一致 | 🟡 中 |
| 全项目零自定义异常类 | 全仓 | 错误无法分类恢复 | 🟡 中 |
| `except Exception: pass` 静默吞错 30+ 处 | 分布 12 个文件 | NameError/RuntimeError 被隐藏 | 🟡 中 |

### P2 — Agent 智能能力

| 风险 | 位置 | 影响 | 严重度 |
|------|------|------|--------|
| `reflection.reflect` 纯字符串拼接无因果分析 | `reflection.py` | 反思无信息量 | 🟠 高 |
| `learning` device_type 硬编码 'huawei' | `learning.py` | 学习数据失真 | 🟠 高 |
| `learning.record_verify_method` 传 `commands=[]` | `learning.py` | 验证方法学不到 | 🟠 高 |
| `knowledge_store.search` 评分硬编码权重 | `knowledge_store.py` | 检索质量不可调 | 🟡 中 |
| `knowledge_store._find_similar` md5[:12] 精确匹配 | `knowledge_store.py` | 语义相似经验无法去重 | 🟡 中 |
| `recovery.ERROR_PATTERNS` 与 `error_library` 重复 | `recovery.py` vs `error_library.py` | 两份错误定义易漂移 | 🟡 中 |
| `runtime.py` 与 `runtime_action.py` 两套引擎并存 | `agent/` | 维护成本翻倍 | 🟡 中 |

### P3 — 代码质量

| 风险 | 位置 | 影响 | 严重度 |
|------|------|------|--------|
| `app.py` 1699 行胖文件 | `app.py` | 路由+业务+拓扑+设备混在一起 | 🟠 高 |
| 循环依赖检测在 5 处重复实现 | `types/dependency_graph/plan_reviewer/runtime/runtime_action` | 维护噩梦 | 🟡 中 |
| `bootstrap._migrate_legacy_kb` 引用未定义 logger | `bootstrap.py:21` | 运行时靠加载顺序兜底 | 🟡 中 |
| `routes._rate_calls` 字典永不清理 | `routes.py` | 长期内存泄漏 | 🟡 中 |
| `sys.path.insert(0, ...)` 运行时污染 | `runtime.py` | 模块空间污染 | 🟡 中 |
| README/AGENTS/docs 测试数字三处不一致 | 文档 | 基线不可信 | 🟢 低 |

### P4 — 架构边界

| 风险 | 位置 | 影响 | 严重度 |
|------|------|------|--------|
| 15 个 MCP 工具同进程 HTTP 绕行 Flask | `mcp_server.py` | 30s 超时 + 序列化损失 | 🟠 高 |
| `app.py` 本地 `TopologyEngine` 死代码副本 | `app.py:196-229` | 改错一份风险 | 🟡 中 |
| `action_types.ActionPlan` vs `types.ExecutionPlan` 两套 AST | `agent/` | 新旧并存 | 🟠 高 |
| `command_generator` 与 `planner.COMMAND_TEMPLATES` 命令生成逻辑未统一 | `agent/` | 双源 | 🟡 中 |

### P5 — 文档

| 风险 | 位置 | 影响 |
|------|------|------|
| README 说 agent/ 7 个文件，实际 23 个 | `README.md` | 误导 |
| `docs/architecture/system.md` 测试数 224，README 236，AGENTS 223 | 文档 | 基线不可信 |
| 11 个孤岛模块的 docs 标注"未接入"但 README 宣传为已实现能力 | `README.md` | 能力宣传与实际不符 |

---

## E. 优化路线图

### 总原则（遵守 AGENTS.md）

- 每次修改 ≤10 文件，必须运行 `pytest tests/`
- 不删除公开 API，不修改签名
- 渐进式重构，先建安全网（分支 + 测试基线）
- 修改前先读 `docs/modules/`，修改后同步更新

### 阶段映射（对应用户的第二/三/四/五阶段）

| 阶段 | 用户主题 | 对应本报告风险 | 建议交付物 | 文件改动量 |
|------|---------|---------------|-----------|-----------|
| 第二阶段 | Agent 智能增强 | P0 命令生成 + P2 反思/学习 | planner 接入 knowledge_store 检索；learning 修 device_type/verify_method；reflection 加因果分析 | ~6 文件 |
| 第三阶段 | 接口映射优化 | P0 接口映射硬编码 | 新建 `interface_resolver.py` 集成拓扑+设备型号+`display interface`+邻居 MAC+历史经验；删除 knowledge.py 死代码副本 | ~5 文件 |
| 第四阶段 | 稳定性增强 | P1 异常体系 + 静默吞错 | 新建 `exceptions.py` 统一异常体系（NetworkError/CommandError/ValidationError/KnowledgeError/ExecutionError）；逐文件替换 `except Exception: pass` 为分类异常 + 日志 | ~8 文件（分批） |
| 第五阶段 | 架构审计 | P4 职责重叠 | 输出模块职责矩阵；统一循环依赖检测到 `dependency_graph`；统一 AST 到 `action_types`；接入 5 个低中难度孤岛模块 | ~10 文件（分批） |

### 详细路线（按依赖排序，每步可独立验证可回滚）

#### Step 1 — 接入 knowledge_store 到 planner（P0，第二阶段起步）
- **改动**：`planner.plan_from_goal` 增加 `knowledge_store.query_for_task` 调用，命中经验则用经验命令覆盖 `COMMAND_TEMPLATES`
- **测试**：新增 `test_planner_uses_experience.py`，构造一条成功经验，验证 planner 输出与经验一致
- **风险**：knowledge_store 检索质量差（md5 去重），但作为冷启动可接受
- **回滚**：planner 增加 `use_experience=True` 开关，默认 True，失败回退原模板

#### Step 2 — 接入 capability_manager 到 planner（P0）
- **改动**：`planner.plan_from_goal` 开头调 `capability_manager.check_protocol`，不支持则抛 `CapabilityNotSupported`
- **测试**：新增 `test_planner_capability_check.py`
- **风险**：`_MODEL_CAPABILITIES` 仅 6 款设备，需先扩数据（S5700/S3700/AR3260/AR2220/AC6605/USG6000V 已有，补 AR1200/S2700 等）
- **回滚**：开关 `check_capability=True`

#### Step 3 — 接入 command_validator + cli_state 到 runtime（P1）
- **改动**：`runtime._execute_config_node` 执行前调 `command_validator.validate_batch`，不通过则跳过并记录
- **测试**：新增 `test_runtime_validates_before_execute.py`
- **风险**：command_validator 默认规则与 `view_rules.json` 可能不一致，需先校准
- **回滚**：开关 `validate_before_execute=True`

#### Step 4 — 接入 transaction 到 runtime（P1，关键）
- **改动**：`runtime._execute_plan_loop` 包裹 `transaction.run_batch`，失败时 `transaction.rollback`
- **测试**：新增 `test_runtime_transaction_rollback.py`
- **风险**：transaction.rollback 当前依赖外部回调，需先补 `snapshot_data` 真正恢复逻辑
- **回滚**：开关 `use_transaction=True`

#### Step 5 — 接入 plan_reviewer 到 planner（P1）
- **改动**：planner 输出后调 `plan_reviewer.review`，不通过则抛 `PlanReviewRejected`
- **测试**：新增 `test_plan_reviewer_integration.py`
- **风险**：plan_reviewer 接受 dict 而非 ActionPlan，需先统一类型（用 `ExecutionPlan.to_dict()`）
- **回滚**：开关 `review_plan=True`

#### Step 6 — 修 verifier 的两个永真判定（P1）
- **改动**：`verify_acl` 改为解析 `display acl` 规则计数；`verify_connectivity` 改为要求丢包率 < 阈值（默认 0%）
- **测试**：新增 `test_verifier_strict.py`
- **风险**：现有依赖宽松判定的实验可能"突然失败"，需调研历史实验
- **回滚**：阈值参数化，`strict_acl=False` / `ping_loss_threshold=1.0`

#### Step 7 — 接口映射自动推理（P0，第三阶段核心）
- **改动**：新建 `interface_resolver.py`，输入 `{topology, device_model, display_interface_brief, lldp_neighbor, mac_table, history}`，输出真实接口名；删除 `knowledge.py:586-606` 死代码；`app.py:_resolve_interface` 改为调新模块
- **测试**：新增 `test_interface_resolver.py`，覆盖 S5700/S3700/AR3260/USG6000V 四类设备的 srcIndex 推理
- **风险**：`display interface brief` 需设备已连接，冷启动时仍需回退到经验规则
- **回滚**：保留旧 `_resolve_interface` 作为 fallback

#### Step 8 — 统一异常体系（P1，第四阶段）
- **改动**：新建 `mcpensp1/exceptions.py` 定义 `NetworkError/CommandError/ValidationError/KnowledgeError/ExecutionError/CapabilityNotSupported/PlanReviewRejected/TransactionRollbackFailed`；逐文件替换 `except Exception: pass` 为分类捕获 + 日志
- **测试**：新增 `test_exceptions.py`
- **风险**：替换面广，必须分批（每次 ≤10 文件）
- **回滚**：异常类继承 `Exception`，旧代码 `except Exception` 仍能兜底

#### Step 9 — reflection 加因果分析（P2）
- **改动**：`reflection.reflect` 调 `error_library.lookup` 关联错误原因，输出结构化因果链而非字符串拼接
- **测试**：新增 `test_reflection_causal.py`
- **风险**：error_library 匹配脆弱（关键词截断 15 字符），需先修 lookup
- **回滚**：开关 `causal_reflection=True`

#### Step 10 — 架构审计与去重（P4，第五阶段）
- **改动**：统一循环依赖检测到 `dependency_graph.has_cycle`，删除 `types._recompute_order` / `runtime._has_circular_dependency` / `plan_reviewer._check_circular_dependency` 三处重复；统一 AST 到 `action_types`，`types.PlanNode` 标记 deprecated
- **测试**：全量回归
- **风险**：改动面大，必须每步跑测试
- **回滚**：保留旧函数为 thin wrapper

### 验收基线（每步必须满足）

- `pytest tests/` 通过数 **不低于当前基线**（需先统一基线数字，建议跑一次确认实际数）
- 新增测试全部通过
- 无新增 `except Exception: pass`
- 无新增硬编码命令模板
- 文档同步更新

---

## F. 结论

eNSP-MCP v3.0.0 在"工具层"已相当完整（47 个 MCP 工具、18 个配置方法、知识库基础设施齐全），但在"智能层"存在**结构性断口**：11 个 Agent 子模块写完却没有接入主流程，导致闭环 Agent 实际只是 5 段直线执行；命令生成仍是硬编码规则驱动，知识库有基础设施却无人调用；接口映射靠经验规则无自动推理。

**优先级建议**：先做 Step 1-2（planner 接入经验 + 能力矩阵）——这是"经验驱动 Agent"目标的最低门槛，改动小、收益大；再做 Step 3-5（接入校验/事务/审核三个孤岛）——补齐执行稳定性；Step 7（接口映射）独立可做，不依赖前序。

**不建议**：在 Step 1-5 完成前动 `runtime_action.py` 与 `runtime.py` 的合并（P4 的 AST 统一），因为两套引擎并存是当前最大的维护债，但合并风险高，应在闭环跑通后再做。

报告完毕，等待确认后进入第二阶段实施。
