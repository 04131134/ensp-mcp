# CLIState（CLI 视图栈状态机）

## 位置
`mcpensp1/agent/cli_state.py`

## 职责
维护设备当前 CLI 视图的视图栈。支持 10 种视图类型，提供 push/pop/return_to_user 操作。

## 支持的视图
USER / SYSTEM / INTERFACE / VLAN / OSPF / AREA / ACL / AAA / BGP / RIP

## 核心接口
| 方法 | 说明 |
|------|------|
| `push(view, params)` | 进入新视图 |
| `pop()` | 退出当前视图 |
| `return_to_user()` | 一键回到 USER |
| `current_view()` | 当前视图 |
| `sync_to_view(view, params)` | 直接同步到指定视图 |
| `update_from_prompt(prompt)` | 根据设备 prompt 更新状态 |

## 依赖
- `prompt_parser.PromptParser`（延迟导入，仅 update_from_prompt 中）

## 禁止事项
- 不允许在 USER 视图继续 pop
- 不允许绕过状态机直接操作视图栈

## 调用关系
```
command_validator → CLIState（验证时模拟）
command_generator → CLIState（生成导航命令）
runtime_action → CLIState（执行时追踪）
```
