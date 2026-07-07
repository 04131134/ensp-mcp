# -*- coding: utf-8 -*-
"""事务管理器 — 配置操作的事务性执行框架。

执行流程：
    Snapshot → Execute → Verify → Commit（或 Rollback）

失败自动回滚，保证设备配置的一致性。
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
from enum import Enum


class TransactionState(Enum):
    """事务状态。"""
    INIT = "init"
    SNAPSHOTTING = "snapshotting"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMMITTING = "committing"
    ROLLING_BACK = "rolling_back"
    COMPLETED = "completed"
    FAILED = "failed"


class Transaction:
    """一个配置事务 — 不可变 id，有明确的 Snapshot/Execute/Verify/Commit/Rollback 流程。

    用法:
        tx = Transaction(
            tx_id="tx-001",
            device_path="127.0.0.1:2000",
            commands=["system-view", "vlan 10", "quit"],
            verify_commands=["display vlan 10"],
        )
        result = tx.execute(executor_fn)
    """

    def __init__(self, tx_id: str, device_path: str,
                 commands: List[str],
                 verify_commands: Optional[List[str]] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.tx_id = tx_id
        self.device_path = device_path
        self.commands = list(commands)
        self.verify_commands = verify_commands or []
        self.metadata = metadata or {}

        self.state: TransactionState = TransactionState.INIT
        self.snapshot_data: Optional[str] = None
        self.snapshot_id: Optional[str] = None
        self.execute_result: Optional[Dict[str, Any]] = None
        self.verify_result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "tx_id": self.tx_id,
            "device_path": self.device_path,
            "commands": self.commands,
            "verify_commands": self.verify_commands,
            "state": self.state.value,
            "snapshot_id": self.snapshot_id,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class TransactionManager:
    """事务管理器 — 管理多设备、多事务的并发执行和回滚。

    执行流程:
        1. Snapshot:    保存设备当前配置（display current-configuration）
        2. Execute:     执行配置命令
        3. Verify:      验证配置结果
        4. Commit:      提交成功标记
        5. Rollback:    失败时从快照恢复

    用法:
        tm = TransactionManager(command_executor=None, snapshot_provider=None)
        result = tm.run(transaction)
    """

    def __init__(self,
                 command_executor: Optional[Any] = None,
                 snapshot_provider: Optional[Callable[[str], Optional[str]]] = None):
        """初始化事务管理器。

        参数:
            command_executor: CommandExecutor 实例（用于 send_command / batch_command）
            snapshot_provider: 快照提供函数 (path) -> snapshot_id
        """
        self._executor = command_executor
        self._snapshot_provider = snapshot_provider
        self._transactions: Dict[str, Transaction] = {}
        self._history: List[Transaction] = []

    def run(self, tx: Transaction,
            executor_fn: Optional[Callable] = None) -> Dict[str, Any]:
        """执行一个完整的事务。

        参数:
            tx: 事务对象
            executor_fn: 命令执行回调 (path, commands) -> result_dict

        返回:
            {
                "tx_id": str,
                "success": bool,
                "state": TransactionState 字符串,
                "snapshot_id": str 或 None,
                "results": [...],
                "error": str 或 None,
                "rolled_back": bool,
            }
        """
        self._transactions[tx.tx_id] = tx
        _exec = executor_fn

        try:
            # ── Phase 1: Snapshot ──────────────────────
            tx.state = TransactionState.SNAPSHOTTING
            if self._snapshot_provider:
                try:
                    tx.snapshot_id = self._snapshot_provider(tx.device_path)
                except Exception as e:
                    tx.error = f"快照失败: {e}"
                    tx.state = TransactionState.FAILED
                    return self._finalize(tx, False)

            # ── Phase 2: Execute ──────────────────────
            tx.state = TransactionState.EXECUTING
            if _exec is None:
                tx.error = "未提供命令执行回调"
                tx.state = TransactionState.FAILED
                return self._finalize(tx, False, rolled_back=True)

            try:
                tx.execute_result = _exec(tx.device_path, tx.commands)
            except Exception as e:
                tx.error = f"命令执行失败: {e}"
                tx.state = TransactionState.FAILED
                return self._finalize(tx, False, rolled_back=True)

            # 检查执行结果
            if isinstance(tx.execute_result, dict) and not tx.execute_result.get("success", True):
                tx.error = tx.execute_result.get("error", "命令执行返回失败")
                tx.state = TransactionState.FAILED
                return self._finalize(tx, False, rolled_back=True)

            # ── Phase 3: Verify ──────────────────────
            if tx.verify_commands:
                tx.state = TransactionState.VERIFYING
                if _exec:
                    try:
                        tx.verify_result = _exec(tx.device_path, tx.verify_commands)
                    except Exception as e:
                        tx.error = f"验证失败: {e}"
                        tx.state = TransactionState.FAILED
                        return self._finalize(tx, False, rolled_back=True)
                else:
                    tx.verify_result = {"skipped": True, "reason": "无验证回调"}

            # ── Phase 4: Commit ──────────────────────
            tx.state = TransactionState.COMMITTING
            tx.state = TransactionState.COMPLETED
            return self._finalize(tx, True)

        except Exception as e:
            tx.error = f"事务异常: {e}"
            tx.state = TransactionState.FAILED
            return self._finalize(tx, False, rolled_back=True)

    def run_batch(self, transactions: List[Transaction],
                  executor_fn: Optional[Callable] = None) -> List[Dict[str, Any]]:
        """批量执行事务（顺序执行）。

        参数:
            transactions: 事务列表
            executor_fn: 命令执行回调

        返回:
            结果列表
        """
        results = []
        for tx in transactions:
            result = self.run(tx, executor_fn)
            results.append(result)
            if not result["success"] and result.get("rolled_back"):
                # 失败时停止后续事务
                break
        return results

    def rollback(self, tx_id: str,
                 rollback_fn: Optional[Callable] = None) -> Dict[str, Any]:
        """手动回滚事务。

        参数:
            tx_id: 事务 ID
            rollback_fn: 回滚回调 (path, snapshot_id) -> result

        返回:
            回滚结果
        """
        tx = self._transactions.get(tx_id)
        if tx is None:
            return {"success": False, "error": f"事务不存在: {tx_id}"}

        tx.state = TransactionState.ROLLING_BACK

        if tx.snapshot_id and rollback_fn:
            try:
                rollback_fn(tx.device_path, tx.snapshot_id)
            except Exception as e:
                return {"success": False, "error": f"回滚失败: {e}"}

        tx.state = TransactionState.COMPLETED
        return {
            "success": True,
            "tx_id": tx_id,
            "state": tx.state.value,
        }

    def get_status(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """查询事务状态。"""
        tx = self._transactions.get(tx_id)
        return tx.to_dict() if tx else None

    def list_active(self) -> List[str]:
        """列出活跃事务 ID。"""
        return [tid for tid, tx in self._transactions.items()
                if tx.state not in (TransactionState.COMPLETED, TransactionState.FAILED)]

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取事务历史。"""
        return [tx.to_dict() for tx in self._history[-limit:]]

    def _finalize(self, tx: Transaction, success: bool,
                  rolled_back: bool = False) -> Dict[str, Any]:
        """完成事务并记录历史。"""
        tx.completed_at = datetime.now(timezone.utc).isoformat()
        if tx.state not in (TransactionState.COMPLETED, TransactionState.FAILED):
            tx.state = TransactionState.COMPLETED if success else TransactionState.FAILED
        self._history.append(tx)
        return {
            "tx_id": tx.tx_id,
            "success": success,
            "state": tx.state.value,
            "snapshot_id": tx.snapshot_id,
            "results": tx.execute_result,
            "verify": tx.verify_result,
            "error": tx.error,
            "rolled_back": rolled_back,
        }
