# Exceptions（统一异常体系）

## 位置
`mcpensp1/exceptions.py`

## 职责
定义 eNSP-MCP 全项目统一异常层次，消除 30+ 处 `except Exception: pass` 静默吞错。
所有异常分类捕获、记录日志、返回原因、支持恢复。

## Web 与 MCP 边界
`ENSPMCPError` 是统一业务异常基类，包含 `message`、`code`、`details`。`DeviceConnectionError`、`CommandExecutionError`、`KnowledgeNotFoundError`、`TopologyError`、`ExperimentError` 和 `AgentError` 用于领域失败。Flask 在应用边界转换为 JSON 响应，MCP 在工具边界转换为文本错误；既有 `ENSPError` 保持兼容并继承该基类。

## 异常层次

```
Exception
└── ENSPError（基类）
    ├── NetworkError          # 网络/Telnet 连接异常
    ├── CommandError          # 命令执行异常
    ├── ValidationError       # 校验失败（视图/规则/参数）
    ├── KnowledgeError        # 知识库异常
    ├── ExecutionError        # 执行流程异常
    ├── CapabilityNotSupported # 设备能力不支持（Step2）
    ├── PlanReviewRejected    # 计划审核被拒（Step5）
    └── TransactionRollbackFailed # 事务回滚失败（Step4，下一批次）
```

## 设计原则

1. **向后兼容**：所有异常继承 ENSPError → Exception，现有 `except Exception` 仍能捕获
2. **携带上下文**：每个异常含 message + context dict（device_path/command/reason 等）
3. **可序列化**：`to_dict()` 供 API 返回 / 结构化日志
4. **可读 __str__**：自动拼接 message + 非空 context

## 核心 API

| API | 说明 |
|-----|------|
| `ENSPError(message, context=None)` | 基类，所有异常的父 |
| `NetworkError(message, device_path="", **kwargs)` | 网络异常 |
| `CommandError(message, device_path="", command="", **kwargs)` | 命令异常 |
| `ValidationError(message, rule="", **kwargs)` | 校验异常 |
| `PlanReviewRejected(message, issues=[], score=0.0, **kwargs)` | 计划审核被拒 |
| `CapabilityNotSupported(message, model="", protocol="", **kwargs)` | 能力不支持 |
| `is_recoverable(error) -> bool` | 判断异常是否可重试 |
| `classify_exception(error) -> str` | 将任意异常分类为标准类型名 |

## 使用示例

```python
from exceptions import CommandError, NetworkError

# 抛出（携带上下文）
raise CommandError('命令执行失败', device_path=path, command=cmd)

# 捕获（分类处理）
try:
    send_command(...)
except NetworkError as e:
    logger.error('网络异常: %s (device=%s)', e, e.device_path)
    return {'success': False, 'error': str(e), 'error_type': 'NetworkError'}
except CommandError as e:
    logger.error('命令异常: %s', e)
    return {'success': False, 'error': str(e), 'error_type': 'CommandError'}

# 向后兼容（旧代码仍工作）
try:
    ...
except Exception as e:  # 仍能捕获 ENSPError
    ...
```

## 依赖
- 无外部依赖（纯 Python 标准库）

## 禁止事项
- ❌ 不允许异常继承非 Exception 的基类（必须向后兼容 `except Exception`）
- ❌ 不允许静默吞错（`except: pass`），必须至少 log
- ❌ 不允许异常丢失原始 context（必须保留 device/command 等信息）

## v3.3 引入（第四阶段 Step8）
- 新建本模块，建立统一异常体系
- 当前批次：定义异常类 + 辅助函数，未强制替换现有 `except Exception`（渐进式迁移）
- 后续：逐模块将 `except Exception: pass` 替换为分类异常 + 日志

## 迁移策略（渐进式）
1. 旧代码 `except Exception` 仍能捕获新异常（ENSPError 继承 Exception）
2. 新代码逐步改用具体异常类型，配合日志而非静默 pass
3. 不强制一次性替换所有 except，按模块分批迁移（connection.py 8 处、app.py 24 处等）
