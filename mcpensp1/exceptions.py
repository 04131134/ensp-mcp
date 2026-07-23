# -*- coding: utf-8 -*-
"""eNSP-MCP 统一异常体系（第四阶段 Step8）

目标：消除全项目 30+ 处 `except Exception: pass` 静默吞错，
所有异常分类捕获、记录日志、返回原因、支持恢复。

设计原则：
- 所有自定义异常继承 ENSPError（最终继承 Exception），向后兼容现有 `except Exception`
- 按职责分层：网络/命令/校验/知识/执行/能力/计划/事务
- 每个异常携带可读 message + 可选 context（设备/命令/原因）

使用示例：
    try:
        raise CommandError(f'命令执行失败: {cmd}', device_path=path, command=cmd)
    except CommandError as e:
        logger.error('%s (device=%s, cmd=%s)', e, e.device_path, e.command)
        return {'success': False, 'error': str(e), 'error_type': 'CommandError'}

迁移策略（渐进式）：
- 旧代码 `except Exception` 仍能捕获新异常（因 ENSPError 继承 Exception）
- 新代码逐步改用具体异常类型，配合日志而非静默 pass
- 不强制一次性替换所有 except，按模块分批迁移
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class ENSPError(Exception):
    """所有 eNSP-MCP 自定义异常的基类。

    Attributes:
        message: 错误描述
        context: 附加上下文（device_path/command/reason 等）
    """

    def __init__(self, message: str = "", context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = context or {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化字典（供 API 返回 / 日志结构化）。"""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'context': self.context,
        }

    def __str__(self) -> str:
        if self.context:
            ctx_str = ', '.join(f'{k}={v}' for k, v in self.context.items() if v not in (None, '', []))
            return f'{self.message} [{ctx_str}]' if ctx_str else self.message
        return self.message


# ==================== 网络层异常 ====================

class NetworkError(ENSPError):
    """网络/Telnet 连接异常。

    用于：设备连接失败、Telnet 超时、连接断开、端口不可达等。
    替代 connection.py 中 8 处静默 except 的泛化返回。
    """

    def __init__(self, message: str = "", device_path: str = "", **kwargs):
        ctx = {'device_path': device_path, **kwargs}
        super().__init__(message, ctx)
        self.device_path = device_path


# ==================== 命令执行层异常 ====================

class CommandError(ENSPError):
    """命令执行异常。

    用于：命令发送失败、CLI 报错、设备返回错误输出等。
    """

    def __init__(self, message: str = "", device_path: str = "", command: str = "", **kwargs):
        ctx = {'device_path': device_path, 'command': command, **kwargs}
        super().__init__(message, ctx)
        self.device_path = device_path
        self.command = command


# ==================== 校验层异常 ====================

class ValidationError(ENSPError):
    """校验失败异常。

    用于：命令视图校验不通过、参数校验失败、格式校验失败等。
    """

    def __init__(self, message: str = "", rule: str = "", **kwargs):
        ctx = {'rule': rule, **kwargs}
        super().__init__(message, ctx)
        self.rule = rule


# ==================== 知识层异常 ====================

class KnowledgeError(ENSPError):
    """知识库异常。

    用于：知识库加载失败、检索异常、记录写入失败等。
    """

    def __init__(self, message: str = "", store: str = "", **kwargs):
        ctx = {'store': store, **kwargs}
        super().__init__(message, ctx)
        self.store = store


# ==================== 执行流程异常 ====================

class ExecutionError(ENSPError):
    """执行流程异常。

    用于：Agent 执行流程错误、计划执行异常、状态机错误等。
    """

    def __init__(self, message: str = "", experiment_id: str = "", **kwargs):
        ctx = {'experiment_id': experiment_id, **kwargs}
        super().__init__(message, ctx)
        self.experiment_id = experiment_id


# ==================== Agent 智能层异常 ====================

class CapabilityNotSupported(ENSPError):
    """设备能力不支持异常。

    用于：planner 检测到设备不支持目标协议时抛出。
    Step2 接入 capability_manager 后使用。
    """

    def __init__(self, message: str = "", model: str = "", protocol: str = "", **kwargs):
        ctx = {'model': model, 'protocol': protocol, **kwargs}
        super().__init__(message, ctx)
        self.model = model
        self.protocol = protocol


class PlanReviewRejected(ENSPError):
    """计划审核被拒异常。

    用于：plan_reviewer 审核不通过时抛出（critical 级别问题）。
    Step5 接入 plan_reviewer 后使用。
    """

    def __init__(self, message: str = "", issues: Optional[list] = None, score: float = 0.0, **kwargs):
        ctx = {'issues': issues or [], 'score': score, **kwargs}
        super().__init__(message, ctx)
        self.issues = issues or []
        self.score = score


class TransactionRollbackFailed(ENSPError):
    """事务回滚失败异常。

    用于：transaction.rollback 失败时抛出。
    Step4 接入 transaction 后使用（下一批次）。
    """

    def __init__(self, message: str = "", transaction_id: str = "", **kwargs):
        ctx = {'transaction_id': transaction_id, **kwargs}
        super().__init__(message, ctx)
        self.transaction_id = transaction_id


# ==================== 便捷函数 ====================

def is_recoverable(error: Exception) -> bool:
    """判断异常是否可恢复（重试可能成功）。

    NetworkError/CommandError 通常可重试；
    ValidationError/CapabilityNotSupported/PlanReviewRejected 不可重试（需修改输入）。
    """
    if isinstance(error, (NetworkError, CommandError)):
        return True
    if isinstance(error, (ValidationError, CapabilityNotSupported, PlanReviewRejected)):
        return False
    return True  # 默认可恢复


def classify_exception(error: Exception) -> str:
    """将任意异常分类为标准异常类型名（供日志/API）。"""
    if isinstance(error, ENSPError):
        return error.__class__.__name__
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return 'NetworkError'
    if isinstance(error, (ValueError, TypeError, KeyError)):
        return 'ValidationError'
    return 'ExecutionError'
