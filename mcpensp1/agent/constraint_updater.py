# -*- coding: utf-8 -*-
"""根据错误分类结果维护设备能力约束和配置蓝图。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from .constraint_store import ConstraintStore
from .knowledge_store import KnowledgeStore
from .memory import MemoryStore
from .types import MemoryEntry


class ConstraintUpdater:
    """将错误分类结果转为持久化约束、蓝图修正或统计记忆。"""

    def __init__(
        self,
        constraint_store: ConstraintStore,
        knowledge_store: KnowledgeStore,
        memory_store: MemoryStore,
    ):
        """初始化约束更新器。"""
        self._constraint_store = constraint_store
        self._knowledge_store = knowledge_store
        self._memory_store = memory_store

    def update_from_error(self, error_record: Mapping[str, Any]) -> Dict[str, Any]:
        """根据错误类型更新约束、蓝图或错误统计记忆。

        设备型号、任务标识与缺失视图信息可由调用方附加到错误记录的
        ``device_model``、``task_id``、``required_view`` 或
        ``view_entry_command`` 字段中。
        """
        error_type = str(error_record.get("error_type", ""))
        task_id = str(error_record.get("task_id", ""))
        device_model = self._device_model(error_record)
        result = {
            "error_type": error_type,
            "constraint_recorded": False,
            "blueprints_updated": 0,
            "memory_recorded": False,
        }

        if error_type == "device_not_supported":
            constraint = error_record.get("constraint")
            if isinstance(constraint, Mapping):
                self._constraint_store.add(constraint, task_id, device_model)
                result["constraint_recorded"] = True
                result["blueprints_updated"] = self._remove_unsupported_device(
                    str(constraint.get("command_pattern", "")), device_model
                )
            return result

        if error_type == "context_error":
            result["blueprints_updated"] = self._add_view_precondition(error_record)
            return result

        self._record_error_memory(error_record, task_id, device_model)
        result["memory_recorded"] = True
        return result

    def _remove_unsupported_device(self, command_pattern: str, device_model: str) -> int:
        """从受不支持命令影响的蓝图中移除当前设备型号。"""
        if not command_pattern or not device_model:
            return 0
        updated = 0
        for record in self._blueprint_records():
            if not self._sequence_contains(record.content, command_pattern):
                continue
            applicable_devices = record.content.get("applicable_devices", [])
            if device_model not in applicable_devices:
                continue
            record.content["applicable_devices"] = [
                model for model in applicable_devices if model != device_model
            ]
            record.content["last_used"] = datetime.now(timezone.utc).isoformat()
            self._knowledge_store.update(record)
            updated += 1
        return updated

    def _add_view_precondition(self, error_record: Mapping[str, Any]) -> int:
        """为命中蓝图补齐缺失视图进入命令和前置条件。"""
        command_pattern = str(
            error_record.get("failed_command")
            or error_record.get("command_pattern")
            or ""
        )
        entry_command = self._view_entry_command(error_record)
        if not command_pattern or not entry_command:
            return 0

        required_view = str(error_record.get("required_view") or entry_command)
        precondition = f"requires view: {required_view}"
        updated = 0
        for record in self._blueprint_records():
            sequence = record.content.get("command_sequence", [])
            position = self._command_position(sequence, command_pattern)
            if position is None:
                continue
            changed = False
            preconditions = record.content.setdefault("preconditions", [])
            if precondition not in preconditions:
                preconditions.append(precondition)
                changed = True
            if not self._has_preceding_entry(sequence, position, entry_command):
                sequence.insert(position, {
                    "command": entry_command,
                    "expected_view": self._entry_expected_view(entry_command),
                })
                changed = True
            if changed:
                record.content["last_used"] = datetime.now(timezone.utc).isoformat()
                self._knowledge_store.update(record)
                updated += 1
        return updated

    def _record_error_memory(
        self,
        error_record: Mapping[str, Any],
        task_id: str,
        device_model: str,
    ) -> None:
        """将非约束类错误记录为可统计的长期记忆。"""
        timestamp = datetime.now(timezone.utc).isoformat()
        content = json.dumps({
            "error_type": error_record.get("error_type", ""),
            "task_id": task_id,
            "device_model": device_model,
            "suggestion": error_record.get("suggestion", ""),
            "raw_output_summary": error_record.get("raw_output_summary", ""),
        }, ensure_ascii=False, sort_keys=True)
        self._memory_store.add(MemoryEntry(
            category="error",
            content=content,
            context={"recorded_at": timestamp, "task_id": task_id},
            tags=["constraint-updater", str(error_record.get("error_type", "unknown"))],
            importance=0.6,
            experiment_id=task_id,
        ))

    def _blueprint_records(self) -> List[Any]:
        """获取包含蓝图命令序列的模板记录。"""
        return [
            record for record in self._knowledge_store.search(category="template", limit=10000)
            if isinstance(record.content.get("command_sequence"), list)
        ]

    @staticmethod
    def _sequence_contains(template: Mapping[str, Any], command_pattern: str) -> bool:
        """判断蓝图命令序列是否包含指定的命令模式。"""
        return ConstraintUpdater._command_position(
            template.get("command_sequence", []), command_pattern
        ) is not None

    @staticmethod
    def _command_position(sequence: Any, command_pattern: str) -> Optional[int]:
        """返回命令模式首次出现的位置。"""
        normalized_pattern = " ".join(command_pattern.lower().split())
        if not normalized_pattern or not isinstance(sequence, list):
            return None
        for index, step in enumerate(sequence):
            command = step.get("command", "") if isinstance(step, Mapping) else ""
            normalized_command = " ".join(str(command).lower().split())
            if normalized_pattern in normalized_command:
                return index
        return None

    @staticmethod
    def _has_preceding_entry(
        sequence: List[Dict[str, Any]], position: int, entry_command: str
    ) -> bool:
        """判断目标命令之前是否已有相同的视图进入命令。"""
        normalized_entry = " ".join(entry_command.lower().split())
        return any(
            " ".join(str(step.get("command", "")).lower().split()) == normalized_entry
            for step in sequence[:position]
            if isinstance(step, Mapping)
        )

    @staticmethod
    def _view_entry_command(error_record: Mapping[str, Any]) -> str:
        """从错误上下文取得可插入蓝图的视图进入命令。"""
        explicit = str(error_record.get("view_entry_command") or "").strip()
        if explicit:
            return explicit
        required_view = str(error_record.get("required_view") or "").strip()
        if required_view.lower() == "system-view":
            return "system-view"
        if required_view.lower().startswith(("interface ", "ospf ", "bgp ")):
            return required_view
        return ""

    @staticmethod
    def _entry_expected_view(entry_command: str) -> str:
        """返回执行视图进入命令前必须处于的视图。"""
        return "user-view" if entry_command.lower() == "system-view" else "system-view"

    @staticmethod
    def _device_model(error_record: Mapping[str, Any]) -> str:
        """兼容分类结果附带的设备型号或完整设备信息。"""
        explicit = error_record.get("device_model")
        if explicit:
            return str(explicit)
        device_info = error_record.get("device_info")
        if isinstance(device_info, Mapping):
            return str(device_info.get("model") or "")
        return ""
