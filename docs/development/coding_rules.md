# 编码规范

## Python 版本

- 目标版本：Python 3.10+
- 当前开发版本：Python 3.14

## 代码风格

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块 | 小写下划线 | `command_executor.py` |
| 类 | 大驼峰 | `DeviceManager`, `DAGPlanner` |
| 函数/方法 | 小写下划线 | `send_command()`, `plan_from_goal()` |
| 常量 | 大写下划线 | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| 私有方法 | 下划线前缀 | `_parse_ip_brief()`, `_guess_cat()` |

### 类型注解

所有公开接口必须包含类型注解：

```python
def send_command(self, path: str, command: str) -> dict:
    ...
```

### 文档字符串

公开方法使用 docstring 说明用途、参数、返回值：

```python
def batch_command(self, path: str, commands: List[str],
                  wait: float = 0.1) -> dict:
    """批量发送命令到设备。

    参数:
        path: 设备路径，格式 "127.0.0.1:PORT"
        commands: 命令列表
        wait: 命令间等待时间（秒）

    返回:
        {"status": "ok", "results": [...], "summary": {...}}
    """
```

### 导入顺序

```python
# 1. 标准库
from __future__ import annotations
import asyncio
import json

# 2. 第三方库
from flask import Flask

# 3. 本地模块
from mcpensp1.device_manager import DeviceManager
```

## 错误处理

- 使用 `try/except` 包裹外部调用（Telnet、文件 I/O）
- 返回 dict 结构包含 `"error"` 字段，不抛异常给调用方
- 日志使用 `logging` 模块，不直接打印

```python
try:
    output = conn.send_cmd(command)
    return {"status": "ok", "output": output}
except Exception as e:
    logger.error("命令执行失败: %s", e)
    return {"status": "error", "error": str(e)}
```

## MCP 工具编写规范

```python
Tool(
    name="tool_name",              # snake_case
    description="中文描述",         # 面向 AI Agent 的清晰描述
    inputSchema={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数说明"},
        },
        "required": ["param1"],
    },
)
```

## 测试规范

- 测试文件命名：`test_<模块>.py`
- 测试类命名：`Test<Feature>`
- 测试方法命名：`test_<what>_<expected>`
- 每个新工具至少 1 条冒烟测试
- 关键路径至少 1 条回归测试

## 禁止事项

- ❌ 使用裸 `except:` 不指定异常类型
- ❌ 在公开接口中不返回 dict 结构
- ❌ 在循环中进行阻塞 I/O（应使用 asyncio）
- ❌ 硬编码路径（应使用 `os.path.join`）
- ❌ 在 MCP tool 描述中使用英文（面向中文 AI Agent）
