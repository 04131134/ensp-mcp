# Planner Knowledge Integration Batch1 Report

> **批次** 批次1 | **日期** 2026-07-21 | **基线** 326 passed / 3 skipped
> **设计文档** planner_knowledge_integration_design.md
> **审计前置** command_generator_knowledge_audit.md

---

## 1. 修改文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `agent/planner.py` | +45 行 | + set_knowledge_base / _enrich_with_structured_kb / _match_structured_commands / use_structured_kb / _experience_applied_nodes |
| `agent/runtime.py` | +11 行 | __init__ 注入 KnowledgeBase 给 planner |
| `tests/test_planner_structured_kb.py` | 新建 4 用例 | S5700 VLAN / USG6000V NAT / 无型号降级 / KB不可用降级 |

## 2. 调用链变化

```
修复前:
  plan_from_goal → _apply_experience(P2) → COMMAND_TEMPLATES(P3)

修复后:
  plan_from_goal → _apply_experience(P2) → _enrich_with_structured_kb(P1) → COMMAND_TEMPLATES(P3)
                                                       │
                                                       ├─ devices有型号 → suggest_commands(model,'system_view')
                                                       │   → function模糊匹配 → 增强节点commands
                                                       └─ devices无型号 → 跳过
```

## 3. 新旧命令生成区别

### S5700 VLAN

| 情况 | 输出 |
|------|------|
| 修复前 | `['vlan 10', 'quit']` ← COMMAND_TEMPLATES |
| 修复后(有型号) | structured_kb 的 VLAN端口 function 命令（含 port link-type trunk 等） |
| 修复后(无型号) | `['vlan 10', 'quit']` ← 降级模板 |

### USG6000V NAT

| 情况 | 输出 |
|------|------|
| 修复前 | `['interface GE0/0/0', 'nat outbound 3001', 'quit']` ← 🔴 交换机NAT命令，对防火墙错误 |
| 修复后(有型号) | structured_kb 的 NAT策略 function 命令（nat-policy + source-zone + action source-nat）← ✅ |
| 修复后(无型号) | 同修复前 |

## 4. 测试结果

| 阶段 | 结果 |
|------|------|
| 新测试单独跑 | 4 passed |
| 全量 | _待填_ |

### 新增测试覆盖

| 测试 | 验证点 | 状态 |
|------|--------|------|
| test_s5700_vlan_uses_structured_kb | S5700 VLAN 从结构化KB获取候选命令 | PASS |
| test_usg6000v_nat_not_generates_outbound | USG6000V NAT 不再生成 nat outbound | PASS |
| test_no_device_model_fallback_to_template | 无型号降级 COMMAND_TEMPLATES | PASS |
| test_knowledge_base_unavailable_fallback | KB 不可用正常降级 | PASS |

## 5. 风险

| 风险 | 缓解 |
|------|------|
| _match_template 'as' 子串误匹配 | 已知（审计报告记录），非本批次范围 |
| structured_kb 的 function 名与 planner protocol 名不一致 | _match_structured_commands 子串双向匹配 |
| KnowledgeBase 构造需 kb_folder 路径 | runtime 用 os.path.dirname 推导项目路径 |

## 6. 设计保证

- ✅ 不删除 COMMAND_TEMPLATES（始终作为兜底）
- ✅ 不覆盖经验覆盖的节点（_experience_applied_nodes 追踪）
- ✅ 不改变 PlanNode 对外结构
- ✅ 不新增 plan_from_goal 签名参数（复用 devices）
- ✅ KnowledgeBase 通过 setter 注入（可测试/可回滚）
