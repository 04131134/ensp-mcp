# CapabilityManager（设备能力管理器）

> ⚠️ **状态：未接入运行链路（实验性 / 候选能力）**
> 本模块代码已实现，但 `AgentRuntime`（`mcpensp1/agent/runtime.py`）在初始化与 `execute_task` 中**并未实例化或调用 `CapabilityManager`**。因此文档中“Planner 必须先查询 Capability”**当前并未生效**——`DAGPlanner` 不查询设备能力即可生成计划。本文档描述的是设计意图，非已上线功能。如需启用，须在 `bootstrap.py` / `runtime.py` 中注入 `CapabilityManager`（属于架构增强，非缺陷修复）。

## 位置
`mcpensp1/agent/capability_manager.py`

## 职责
执行前检查设备型号、支持协议、支持命令。Planner 必须先查询 Capability。

## 支持的型号
S5700 / S3700 / AR2220 / USG6000V / AC6605 / AP4050DN

## 核心接口
| 方法 | 说明 |
|------|------|
| `check_protocol(model, protocol)` | 检查设备是否支持某协议 |
| `check_commands(model, commands)` | 批量检查命令是否被支持 |
| `get_model_capabilities(model)` | 获取设备完整能力 |
| `suggest_model_for_protocol(protocol)` | 推荐支持协议的设备型号 |

## 依赖
- `PlanReviewer._check_dangerous` — 危险命令关键词告警（命令拦截已在 v2.4 移除，本模块仅做能力校验）

## 禁止事项
- 不允许在未知型号上静默执行（明确返回 error）
