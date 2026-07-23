# -*- coding: utf-8 -*-
"""以原子文件写入方式持久化运行时学习到的设备约束。"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping


class ConstraintStore:
    """持久化错误分类产生的命令和设备能力约束。"""

    def __init__(self, persist_path: str):
        """初始化约束存储。

        参数:
            persist_path: JSON 约束文件的存储路径。
        """
        self._path = persist_path
        self._lock = threading.Lock()

    def add(
        self,
        constraint: Mapping[str, Any],
        task_id: str = "",
        device_model: str = "",
    ) -> Dict[str, Any]:
        """写入约束，并记录触发任务、设备型号和时间戳。"""
        with self._lock:
            data = self._read()
            record = {
                "id": uuid.uuid4().hex,
                "command_pattern": str(constraint.get("command_pattern", "")),
                "alternative": str(constraint.get("alternative", "")),
                "task_id": task_id,
                "device_model": device_model,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            data["constraints"].append(record)
            self._atomic_write(data)
            return record

    def list(self) -> List[Dict[str, Any]]:
        """读取当前全部约束记录。"""
        with self._lock:
            return list(self._read()["constraints"])

    def _read(self) -> Dict[str, List[Dict[str, Any]]]:
        """读取约束文件；不存在或损坏时返回空集合。"""
        if not os.path.exists(self._path):
            return {"constraints": []}
        try:
            with open(self._path, "r", encoding="utf-8") as file:
                data = json.load(file)
            constraints = data.get("constraints", [])
            return {"constraints": constraints if isinstance(constraints, list) else []}
        except (OSError, json.JSONDecodeError):
            return {"constraints": []}

    def _atomic_write(self, data: Mapping[str, Any]) -> None:
        """先写入同目录临时文件，再原子替换正式约束文件。"""
        directory = os.path.dirname(self._path) or "."
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self._path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise
