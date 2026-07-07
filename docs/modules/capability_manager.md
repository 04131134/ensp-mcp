# CapabilityManager（设备能力管理器）

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
- `command_executor.is_blocked_command` — 危险命令检查

## 禁止事项
- 不允许在未知型号上静默执行（明确返回 error）
