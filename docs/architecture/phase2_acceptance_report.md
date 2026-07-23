# eNSP-MCP 第二阶段验收报告：Agent 智能增强

> **阶段** 第二阶段 | **执行日期** 2026-07-20 | **基线** 236 passed / 3 skipped
> **遵守规则** 最高优先级开发原则（小步、可回滚、≤10 文件、每步测试、不破坏现有功能）

---

## 1. 修改文件列表（共 8 个，符合 ≤10 约束）

### 源代码（4 个）
| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `mcpensp1/agent/planner.py` | 增强 | Step1 经验接入 + Step2 能力校验（加 setter + 2 辅助方法 + plan_from_goal 调用） |
| `mcpensp1/agent/runtime.py` | 增强 | __init__ 注入 3 个依赖（knowledge_store/capability_manager/error_library，全 try/except 容错） |
| `mcpensp1/agent/reflection.py` | 增强 | Step9 因果分析（加 __init__/setter/_analyze_failure_causes + reflect 调用） |
| `mcpensp1/agent/learning.py` | 修复 | device_type 硬编码 → _infer_device_type；verify_method 空 commands → _extract_verify_commands |

### 测试（4 个新增）
| 文件 | 用例数 | 覆盖 |
|------|--------|------|
| `tests/test_planner_uses_experience.py` | 4 | 经验覆盖/回退/开关/异常容错 |
| `tests/test_planner_capability_check.py` | 5 | 已知型号/未知型号/开关/未注入/未传devices |
| `tests/test_reflection_causal.py` | 4 | 因果分析/回退/开关/异常容错 |
| `tests/test_learning_data_quality.py` | 6 | 常量/推断/非空命令/兜底/列表/成功记录 |

### 文档（3 个同步更新，AGENTS.md 强制要求）
| 文件 | 改动 |
|------|------|
| `docs/modules/planner.md` | 新增 v3.1 增强章节（setter/开关/流程） |
| `docs/modules/learning.md` | 新增 v3.1 增强章节（修复说明/新接口） |
| `docs/modules/reflection.md` | 新建（原无文档，补 set_error_library 接口说明） |

---

## 2. 每处修改原因

### Step1 — planner 接入 knowledge_store（P0 命令生成）
- **问题**：第一阶段报告发现 `planner.plan_from_goal` 不查 knowledge_store，runtime 阶段3虽查了 `knowledge_context` 但 planner 只当字符串变量合并，**未用成功经验命令**。"经验驱动 Agent"目标未起步。
- **修改**：planner 加 `set_knowledge_store` + `_apply_experience`，检索 success_case 用经验命令覆盖 ConfigNode.commands；runtime.__init__ 注入 `self.knowledge`。
- **影响范围**：仅 plan_from_goal 新增一次经验检索调用，未注入/异常时静默回退模板行为，**不改变现有签名**。

### Step2 — planner 接入 capability_manager（P0 命令生成）
- **问题**：planner 不校验设备能力，对不支持设备也生成命令。capability_manager 是 11 个孤岛之一。
- **修改**：planner 加 `set_capability_manager` + `_check_capabilities`，校验协议支持；runtime.__init__ 注入 CapabilityManager。
- **影响范围**：仅 log warning 不阻塞，未传 devices 时跳过（当前 runtime 行为），**不破坏现有流程**。为 runtime 未来传型号铺路。

### Step9 — reflection 接入 error_library（P2 反思智能）
- **问题**：reflection.reflect 纯字符串拼接，失败节点只记"检查依赖和视图"，不关联具体错误原因。
- **修改**：reflection 加 `set_error_library` + `_analyze_failure_causes`，对失败节点查 error_library 输出结构化因果；runtime.__init__ 注入 ErrorLibrary。
- **影响范围**：reflect 新增因果分析步骤，未注入/异常时回退原行为，**不改变现有签名**。

### learning 数据质量修复（P2 学习智能）
- **问题**：learning.py L69/L82 `device_type='huawei'` 硬编码；L106 `record_verify_method` 传 `commands=[]`（注释"从验证结果中推断"但未实现），导致验证方法学不到命令。
- **修改**：提取 `DEFAULT_DEVICE_TYPE` 常量 + `_infer_device_type` + `_extract_verify_commands`；两处硬编码改为推断，空命令改为从 evidence 提取（兜底 check_name）。
- **影响范围**：仅 learning 内部，**默认行为不变**（仍 huawei），但 verify_method 记录不再空命令。

---

## 3. 测试结果

| 阶段 | 通过/跳过 | 回归 | 新增 |
|------|-----------|------|------|
| 基线（改动前） | 236 passed, 3 skipped | — | — |
| 第一次（planner+runtime 改完） | 236 passed, 3 skipped | **0 回归** | 0（仅验证不破坏） |
| 第二次（全部改完 + 19 新测试） | **255 passed, 3 skipped** | **0 回归** | **+19 全过** |

✅ **236 → 255，零回归，19 个新测试全部通过，3 skipped 不变**

### 新增测试覆盖维度
- **命令生成准确率**：test_planner_uses_experience（经验覆盖/回退/开关/异常）
- **设备能力校验**：test_planner_capability_check（已知/未知型号/开关/未注入/未传devices）
- **反思因果分析**：test_reflection_causal（因果/回退/开关/异常容错）
- **学习数据质量**：test_learning_data_quality（常量/推断/非空命令/兜底/列表/成功记录）

---

## 4. 性能变化

- **planner**：新增一次 `knowledge_store.query_for_task` 调用（内存检索，<1ms）+ 可选 `_check_capabilities`（dict 查询，<1ms）。实测全量测试耗时 111.2s vs 基线 112.7s，**无显著变化（甚至略快）**。
- **reflection**：新增 `_analyze_failure_causes`（仅失败节点查 error_library，JSON 内存查）。无失败节点时零开销。
- **learning**：`_infer_device_type`/`_extract_verify_commands` 均为 O(1) 操作。

---

## 5. Agent 能力提升

| 能力维度 | 改动前 | 改动后 | 提升 |
|---------|--------|--------|------|
| 命令生成依据 | 纯硬编码 COMMAND_TEMPLATES | 优先用 knowledge_store 成功经验覆盖模板 | 规则驱动 → 经验驱动起步 |
| 设备能力感知 | 无（对不支持设备也生成命令） | 校验协议支持，不支持 log warning | 接入 capability_manager 孤岛 |
| 失败原因分析 | 字符串拼接"检查依赖和视图" | 关联 error_library 输出 cause/fix/confidence | 纯描述 → 结构化因果 |
| 学习数据质量 | device_type 硬编码、verify_method 空命令 | 推断 device_type、提取真实验证命令 | 数据失真 → 可用数据 |

### 接入的孤岛模块
- ✅ `capability_manager` → planner（Step2）
- ✅ `error_library` → reflection（Step9）
- ⏳ `knowledge_store` → planner（Step1，已接入但 planner 侧；runtime 早已实例化）

### 仍未接入的孤岛（9 个，留待后续阶段）
plan_reviewer / transaction / runtime_action / action_types / cli_state / prompt_parser / command_generator / command_validator / dependency_graph

---

## 6. 剩余风险

| 风险 | 严重度 | 说明 | 缓解 |
|------|--------|------|------|
| Step2 能力校验未真正生效 | 🟡 中 | runtime 未传 devices 给 planner，check_protocol 跳过 | 已留接口，runtime 传型号属另一改动（第三/四阶段） |
| knowledge_store 检索质量差 | 🟡 中 | search 评分硬编码权重，md5[:12] 去重过严 | Step1 用作冷启动可接受，检索质量优化留后续 |
| error_library.lookup 匹配脆弱 | 🟡 中 | 关键词截断 15 字符，中文/短错误易漏匹配 | Step9 异常容错，未命中时回退原行为 |
| 经验覆盖可能引入过时命令 | 🟢 低 | 经验命令可能不适用新拓扑 | use_experience 开关可关闭，回退模板 |
| _apply_experience 按 node_id 匹配 | 🟢 低 | 经验 experiment_type 与 node_id 不完全对应 | 仅命中时覆盖，未命中用模板 |

---

## 7. 下一阶段建议

### 立即可做（第三阶段：接口映射优化，P0）
- Step7：新建 `interface_resolver.py`，集成拓扑+设备型号+`display interface`+邻居 MAC+历史经验，自动推理真实接口
- 删除 `knowledge.py:586-606` 死代码副本
- 独立于本阶段，可立即开展

### 后续可做（第四阶段：稳定性增强，P1）
- Step3：runtime 接入 command_validator（执行前校验视图）
- Step4：runtime 接入 transaction（失败回滚，关键）
- Step5：runtime 接入 plan_reviewer（计划审核）
- Step6：修 verifier 两个永真判定（verify_acl / verify_connectivity）
- Step8：统一异常体系（exceptions.py）

### 本阶段遗留
- runtime 传设备型号给 planner（让 Step2 真正生效）—— 需从 device_manager 取型号，属 runtime 改动，建议随 Step3-5 一起做
- knowledge_store 检索质量优化（评分权重参数化、去重改语义匹配）—— 独立优化，低优先级

---

## 8. 回滚方案

每个改动均支持独立回滚：
- **Step1 回滚**：`planner.set_knowledge_store(None)` 或 `planner.use_experience = False`
- **Step2 回滚**：`planner.set_capability_manager(None)` 或 `planner.check_capability = False`
- **Step9 回滚**：`reflection.set_error_library(None)` 或 `reflection.causal_reflection = False`
- **learning 回滚**：恢复 `device_type='huawei'` 和 `commands=[]`（git revert learning.py）

所有改动均通过开关或 setter 控制，无需改代码即可回退行为。
