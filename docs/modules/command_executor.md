# CommandExecutor

## 位置
`mcpensp1/command_executor.py`

## 职责
命令执行引擎：通过 DeviceManager 获取 TelnetConnection，向 eNSP 设备发送命令并返回结果。支持单条命令、批量命令、多设备组命令三类模式。

## 输入
| 参数 | 类型 | 说明 |
|------|------|------|
| `knowledge_base` | `KnowledgeBase` | 可选，用于自动记录命令 |

## 输出

| 方法 | 返回值 |
|------|--------|
| `send_command(path, command)` | `{"status": "ok"/"error", "output": str, ...}` |
| `batch_command(path, commands, wait, auto_view, auto_undo_tm)` | `{"status": "ok", "results": [...]}` |
| `send_command_to_group(paths, command)` | `{"status": "ok"/"partial", "results": {...}}` |

## 核心特性

- **prompt 驱动读取**：基于提示符 `<NAME>`/`[NAME]` 检测命令输出结束
- **命令分类**：display(15s) / diagnostic(30s) / config(5s) / interactive(60s)
- **翻页处理**：自动检测 `---- More ----` 并发送空格
- **危险命令拦截**：`is_blocked_command()` 过滤 `reboot`/`format` 等
- **视图切换**：`auto_view=True` 时自动进入/退出系统视图
- **undo t m**：`auto_undo_tm=True` 时自动管理 `undo terminal monitor`

## 依赖
- `device_manager.DeviceManager` — 获取连接
- `connection.TelnetConnection` — 发送/接收
- `knowledge.KnowledgeBase` — 自动记录（可选）

## 禁止事项
- ❌ 不允许绕开危险命令检测
- ❌ 不允许在未连接设备时发送命令
- ❌ 不允许修改命令分类规则而不更新对应测试

## 调用关系
```
mcp_server (send_command/batch_command/group_command)
    → services.py
    → CommandExecutor
        ├── DeviceManager.get(path) → TelnetConnection
        ├── is_blocked_command() → 安全检查
        └── TelnetConnection.send_cmd() / send_cmd_batch()
```
