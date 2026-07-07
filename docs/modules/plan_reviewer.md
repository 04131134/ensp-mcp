# PlanReviewer（计划审核器）

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
