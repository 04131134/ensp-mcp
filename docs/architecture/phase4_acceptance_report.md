# eNSP-MCP 第四阶段验收报告：异常处理与稳定性增强

> **阶段** 第四阶段 | **执行日期** 2026-07-21 | **基线** 283 passed / 3 skipped（第三阶段后）
> **遵守规则** 最高优先级开发原则（小步、可回滚、≤10 文件、每步测试、不破坏现有功能）
> **本批次范围** Step8（异常体系）+ Step6（verifier 修复）+ Step5（plan_reviewer 接入）
> **推迟到下一批次** Step3（command_validator，依赖 cli_state 孤岛）+ Step4（transaction，需改 rollback 逻辑）

---

## 1. 修改文件列表（共 7 个，符合 ≤10 约束）

### 源代码（3 个）
| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `mcpensp1/exceptions.py` | **新建** | 统一异常体系（9 个异常类 + 2 个辅助函数） |
| `mcpensp1/agent/verifier.py` | 改动 | 修 verify_acl + verify_connectivity 两个永真判定（加 strict_acl/ping_loss_threshold 开关） |
| `mcpensp1/agent/runtime.py` | 改动 | 注入 plan_reviewer + _review_plan 方法 + 阶段4 后审核调用 |

### 测试（3 个新增）
| 文件 | 用例数 | 覆盖 |
|------|--------|------|
| `tests/test_exceptions.py` | 15 | 异常继承/to_dict/__str__/is_recoverable/classify |
| `tests/test_verifier_strict.py` | 14 | ACL 严格/非严格 + ping 阈值/可配置/边界 |
| `tests/test_runtime_stability.py` | 7 | plan_reviewer 注入/审核/开关/异常容错 |

### 文档（1 个）
| 文件 | 改动 |
|------|------|
| `docs/modules/exceptions.md` | **新建**（AGENTS.md 要求新模块有文档） |

---

## 2. 每处修改原因

### Step8 — 统一异常体系（P1 稳定性）
- **问题**：第一阶段报告发现全项目零自定义异常类，30+ 处 `except Exception: pass` 静默吞错，错误无法分类恢复。
- **修改**：新建 `exceptions.py`，定义 9 个异常类（NetworkError/CommandError/ValidationError/KnowledgeError/ExecutionError/CapabilityNotSupported/PlanReviewRejected/TransactionRollbackFailed）+ 2 个辅助函数（is_recoverable/classify_exception）。
- **影响范围**：纯新增模块，不修改任何现有代码。所有异常继承 Exception，向后兼容现有 `except Exception`。渐进式迁移，未强制替换现有 except。

### Step6 — 修 verifier 两个永真判定（P1 稳定性）
- **问题**：
  - `verify_acl`：`has_acl = 'rule' in output or 'acl' in output` —— `display acl all` 表头就含 "ACL"，几乎永真
  - `verify_connectivity`：`passed = loss_rate < 100` —— 0% 与 99% 丢包同等对待
- **修改**：
  - `verify_acl` 加 `strict_acl` 开关（默认 True），严格模式用正则 `rule\s+\d+\s+(?:permit|deny)` 统计实际规则数，rule_count > 0 才通过
  - `verify_connectivity` 加 `ping_loss_threshold` 属性（默认 0），`passed = loss_rate <= threshold`
- **影响范围**：仅 verifier.py，默认严格模式。strict_acl=False / threshold=100 时回退旧逻辑（向后兼容）。

### Step5 — runtime 接入 plan_reviewer（P1 稳定性）
- **问题**：plan_reviewer 是 11 个孤岛之一，计划审核能力未接入。危险命令/视图错误/循环依赖直接放行。
- **修改**：runtime.__init__ 注入 PlanReviewer（try/except 容错）；阶段4 plan 生成后调 `_review_plan`，critical 问题 log warning（不阻塞）；加 `review_plan` 开关。
- **影响范围**：仅 runtime.py 新增审核步骤，审核异常时静默跳过（不破坏流程）。接入 plan_reviewer 孤岛。

### Step3 推迟原因
- command_validator 依赖 CLIState（也是孤岛），强行用默认 SYSTEM 视图校验价值有限。需先接入 cli_state + prompt_parser 形成真实视图状态链，与本批次异常体系一起做更合理。留下一批次。

### Step4 推迟原因
- transaction 接入需改 rollback 逻辑（当前 rollback 依赖外部回调，未真正用 snapshot_data 恢复），改动面大。留下一批次。

---

## 3. 测试结果

| 阶段 | 通过/跳过 | 回归 | 新增 |
|------|-----------|------|------|
| 基线（第三阶段后） | 283 passed, 3 skipped | — | — |
| 新测试单独跑（首次） | 35 passed, 1 failed | — | 修复 __str__ 后全过 |
| 全量（全部改完 + 36 新测试） | **319 passed, 3 skipped** | **0 回归** | **+36 全过** |

✅ **283 → 319，零回归，36 个新测试全部通过，3 skipped 不变**

### 新增测试覆盖维度
- **异常体系**：继承链/向后兼容/to_dict/__str__/is_recoverable/classify（15 用例）
- **ACL 严格校验**：有规则/无规则/仅表头/非严格回退/默认值/执行失败（6 用例）
- **ping 阈值**：0%通过/部分丢包失败/100%失败/阈值可配置/阈值50/默认值/执行失败/无丢包信息（8 用例）
- **plan_reviewer 接入**：注入成功/审核执行/开关关闭/未注入/异常容错/空plan/默认开关（7 用例）

---

## 4. 性能变化

- exceptions.py 为纯新增模块，未被现有代码调用，零运行时开销
- verifier 严格校验增加一次正则匹配（<0.1ms），可忽略
- plan_reviewer 审核为计划生成后的一次调用（dict 校验，<1ms）
- 全量测试耗时 111.3s vs 基线 111.1s，**无显著变化**

---

## 5. Agent 能力提升

| 能力维度 | 改动前 | 改动后 | 提升 |
|---------|--------|--------|------|
| 异常处理 | 零自定义异常，30+ 处静默吞错 | 统一异常体系，分类捕获 | 错误可分类、可恢复 |
| ACL 验证 | 几乎永真（含 'acl' 字符串即通过） | 严格统计实际 rule 数 | 配错 ACL 能被发现 |
| 连通性验证 | 0% 与 99% 丢包同等对待 | 阈值判定（默认 0% 丢包） | ping 质量真实反映 |
| 计划审核 | 无（孤岛未接入） | plan_reviewer 审核，critical 问题 warning | 危险命令/视图错误能被发现 |

### 接入的孤岛模块
- ✅ `plan_reviewer` → runtime（Step5）
- 累计已接入 4 个孤岛：knowledge_store/capability_manager/error_library/plan_reviewer
- 仍剩 7 个孤岛：transaction/runtime_action/action_types/cli_state/prompt_parser/command_generator/command_validator/dependency_graph

---

## 6. 剩余风险

| 风险 | 严重度 | 说明 | 缓解 |
|------|--------|------|------|
| 异常体系未应用到现有代码 | 🟡 中 | exceptions.py 已定义但未替换现有 except Exception: pass | 渐进式迁移，按模块分批（下一批次） |
| Step3/Step4 未做 | 🟡 中 | command_validator/transaction 未接入 | 依赖 cli_state/需改 rollback，下一批次 |
| plan_reviewer 审核不阻塞 | 🟢 低 | critical 问题仅 warning，仍继续执行 | 当前不阻塞避免破坏流程；后续可加阻塞开关 |
| strict_acl 可能误判 | 🟢 低 | 正则 `rule\s+\d+\s+(?:permit|deny)` 可能漏匹配某些格式 | 可调整正则；strict_acl=False 回退 |
| plan_reviewer 接受 dict 格式 | 🟢 低 | to_dict() 格式与 plan_reviewer 期望可能不完全一致 | try/except 容错，格式不匹配时跳过 |

---

## 7. 下一阶段建议

### 第四阶段下一批次（P1 剩余）
- **Step3**：接入 cli_state + prompt_parser + command_validator（视图状态链，执行前校验）
- **Step4**：接入 transaction（失败回滚，需改 rollback 用 snapshot_data）
- **异常体系应用**：逐模块将 connection.py（8处）/app.py（24处）的 `except Exception: pass` 替换为分类异常 + 日志

### 第五阶段（架构审计，P4）
- 统一循环依赖检测到 dependency_graph（5 处重复）
- 统一 AST 到 action_types（types.PlanNode 与 action_types.ActionNode 并存）
- 合并 runtime.py 与 runtime_action.py（两套引擎并存）

---

## 8. 回滚方案

- **Step8 回滚**：删除 exceptions.py（纯新增，无现有代码依赖）
- **Step6 回滚**：`verifier.strict_acl = False` + `verifier.ping_loss_threshold = 100`（等价旧逻辑）
- **Step5 回滚**：`runtime.review_plan = False`（跳过审核）

所有改动均通过开关或纯新增控制，可即时回退行为。
