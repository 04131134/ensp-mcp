# CommandValidator（命令验证器）

## 位置
`mcpensp1/agent/command_validator.py`

## 职责
命令执行前验证当前视图是否允许执行该命令。不允许时返回修正建议。

## 核心接口
| 方法 | 说明 |
|------|------|
| `validate(state, command)` | 单条命令验证 → {allowed, suggestion, correction_cmds} |
| `validate_batch(state, commands)` | 批量验证（追踪状态变化） |

## 验证类型
- 危险命令检测（is_blocked_command）
- 视图权限检查（基于 view_rules.json）
- system-view/quit/return 特殊处理
- 全局命令白名单（display/undo）

## 依赖
- `cli_state.CLIState` — 视图状态
- `kb/cli/view_rules.json` — 命令-视图映射规则

## 禁止事项
- 不允许绕开验证直接发送命令
