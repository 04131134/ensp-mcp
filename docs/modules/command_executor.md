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
| `send_command(path, command)` | `{"success": true/false, "path": str, "output": str, "response_time": float, "cmd_success": bool, "error"?: str}` |
| `batch_command(path, commands, wait, auto_view, auto_undo_tm)` | `{"success": true/false, "path": str, "results": [{"command": str, "success": bool, "output": str, "response_time": float}], "total": int, "success_count": int}` |
| `send_command_to_group(paths, command)` | `{"success": true, "results": [{"path": str, "success": bool, "output": str, ...}]}` |

## 核心特性

- **prompt 驱动读取**：基于提示符 `<NAME>`/`[NAME]` 检测命令输出结束
- **命令分类**：display(15s) / diagnostic(30s) / config(5s) / interactive(60s)
- **翻页处理**：自动检测 `---- More ----` 并发送空格
- **危险命令处理**：命令拦截功能已在 v2.4 移除，`CommandExecutor` 不再拦截命令；危险命令告警由 `PlanReviewer._check_dangerous()` 基于关键词负责
- **视图切换**：`auto_view=True` 时自动进入/退出系统视图
- **undo t m**：`auto_undo_tm=True` 时自动管理 `undo terminal monitor`

## 依赖
- `device_manager.DeviceManager` — 获取连接
- `connection.TelnetConnection` — 发送/接收
- `knowledge.KnowledgeBase` — 自动记录（可选）

## 禁止事项
- ❌ 不允许在未连接设备时发送命令
- ❌ 不允许修改命令分类规则而不更新对应测试

## 调用关系
```
mcp_server (send_command/batch_command/group_command)
    → services.py
    → CommandExecutor
        ├── DeviceManager.get(path) → TelnetConnection
        └── TelnetConnection.send_cmd()（批量发送为循环调用）
```
