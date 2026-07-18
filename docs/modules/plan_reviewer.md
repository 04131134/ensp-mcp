# PlanReviewer（计划审核器）

> ⚠️ **状态：未接入运行链路（实验性 / 候选能力）**
> 本模块代码已实现，但 `AgentRuntime.execute_task` **从未调用 `PlanReviewer.review()`**。因此文档中“所有执行计划必须通过审核才能执行”**当前并未生效**——计划会直接执行，不经过审核。本文档描述的是设计意图，非已上线功能。如需启用，须在 `runtime.py` 的 `execute_task` 中接入审核步骤（属于架构增强，非缺陷修复）。

## 位置
`mcpensp1/agent/plan_reviewer.py`

## 职责
所有执行计划必须通过审核才能执行。审核失败禁止执行。

## 6 项审核检查
1. 危险命令检测
2. 视图权限错误
3. 循环依赖检测
4. 重复配置检测
5. 非法删除检测
6. 设备能力匹配

## 核心接口
| 方法 | 说明 |
|------|------|
| `review(plan, device_model)` | 审核完整计划 → {approved, score, issues, suggestions} |
| `review_commands(commands, device_model)` | 快速审核命令列表 |

## 依赖
- `command_validator.CommandValidator` — 视图验证
- `capability_manager.CapabilityManager` — 能力检查

## 禁止事项
- 不允许审核失败后继续执行
