# -*- coding: utf-8 -*-
"""错误库 — 收录华为 CLI 常见错误，提供原因分析和自动恢复建议。

Recovery 优先查询 Error Library，不要让 AI 猜错误原因。
"""
from __future__ import annotations
import json
import logging
import os
import re
from typing import Dict, Any, Optional, List


class ErrorClassifier:
    """根据设备命令输出生成结构化错误记录。

    分类器不依赖静态错误库，适用于知识库成长时记录一次命令执行失败。
    """

    _ENVIRONMENT_MARKERS = (
        "---- more ----",
        "connection timed out",
        "press any key",
        "error: timeout",
    )
    _DEVICE_NOT_SUPPORTED_MARKERS = (
        "is not supported",
        "feature not available",
    )
    _CONFIG_CONFLICT_MARKERS = (
        "already exists",
        "conflict",
    )
    _SYNTAX_MARKERS = (
        "unrecognized command",
        "error: wrong parameter",
    )
    _CONFIGURATION_COMMAND = re.compile(
        r"^(?:undo\s+)?(?:interface|vlan|ospf|bgp|isis|rip|acl|aaa|wlan|"
        r"ip\s+pool|dhcp|traffic\s+classifier|port|shutdown|description|ip\s+address)\b"
    )

    def classify(
        self,
        device_info: Dict[str, Any],
        failed_command: str,
        output: str,
        current_view: str,
    ) -> Dict[str, Any]:
        """分类命令执行失败，并返回可存入知识库的错误记录。

        参数:
            device_info: 设备型号、角色和软件版本等信息。
            failed_command: 执行失败的原始命令。
            output: 设备返回的原始输出。
            current_view: 执行命令时所在的设备视图。
        """
        normalized_output = output.lower()
        summary = output[:200]

        if self._contains_any(normalized_output, self._ENVIRONMENT_MARKERS):
            return self._record(
                "environment_issue", 0.95,
                "关闭分页或检查 eNSP 连接状态后重试该命令。", summary,
            )

        if self._contains_any(normalized_output, self._DEVICE_NOT_SUPPORTED_MARKERS):
            device_name = self._device_name(device_info)
            return self._record(
                "device_not_supported", 0.95,
                "确认设备能力，并改用等价命令或支持该特性的设备。", summary,
                constraint={
                    "command_pattern": failed_command.strip(),
                    "alternative": f"查询 {device_name} 支持的等价命令或改用支持该特性的设备。",
                },
            )

        if self._contains_any(normalized_output, self._CONFIG_CONFLICT_MARKERS):
            return self._record(
                "config_conflict", 0.90,
                "检查现有配置；复用、修改或先删除冲突对象后重试。", summary,
            )

        if "incomplete command" in normalized_output and self._view_is_incorrect(
            failed_command, current_view
        ):
            return self._record(
                "context_error", 0.85,
                "先切换到该配置命令要求的视图，再补全并执行命令。", summary,
            )

        if self._contains_any(normalized_output, self._SYNTAX_MARKERS):
            return self._record(
                "syntax_error", 0.90,
                "核对命令拼写、关键字和参数格式后重试。", summary,
            )

        return self._record(
            "planning_error", 0.40,
            "检查前置配置、命令顺序和业务逻辑后重新规划。", summary,
        )

    @staticmethod
    def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
        """判断输出是否包含任一错误标识。"""
        return any(marker in text for marker in markers)

    @classmethod
    def _view_is_incorrect(cls, failed_command: str, current_view: str) -> bool:
        """判断配置类命令是否在非配置视图中执行。"""
        if not cls._CONFIGURATION_COMMAND.match(failed_command.strip().lower()):
            return False

        view = current_view.strip().lower()
        return not ("[" in view or "system" in view or "config" in view)

    @staticmethod
    def _device_name(device_info: Dict[str, Any]) -> str:
        """生成用于修复建议的设备标识。"""
        model = str(device_info.get("model") or "当前设备")
        role = str(device_info.get("role") or "")
        return f"{model}（{role}）" if role else model

    @staticmethod
    def _record(
        error_type: str,
        confidence: float,
        suggestion: str,
        raw_output_summary: str,
        constraint: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """构造统一的错误记录结构。"""
        record: Dict[str, Any] = {
            "error_type": error_type,
            "confidence": confidence,
            "suggestion": suggestion,
            "raw_output_summary": raw_output_summary,
        }
        if constraint is not None:
            record["constraint"] = constraint
        return record


class ErrorLibrary:
    """华为/H3C CLI 错误知识库。

    用法:
        lib = ErrorLibrary()
        result = lib.lookup("Error: The VLAN already exists")
        if result["auto_recoverable"]:
            logging.getLogger(__name__).debug("%s", result["fix"])
    """

    def __init__(self, errors_path: Optional[str] = None):
        """初始化错误库。

        参数:
            errors_path: huawei_errors.json 路径，默认自动查找
        """
        self._errors = self._load(errors_path)

    def _load(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """加载错误数据。"""
        if path is None:
            path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "kb", "errors", "huawei_errors.json"
            )
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("errors", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def lookup(self, error_text: str) -> Dict[str, Any]:
        """查询错误信息。

        参数:
            error_text: 设备返回的错误消息（支持模糊匹配）

        返回:
            {
                "found": bool,
                "matched_id": str 或 None,
                "cause": str,
                "fix": str,
                "auto_recoverable": bool,
                "category": str,
                "confidence": "exact" | "partial" | "none"
            }
        """
        error_text_lower = error_text.lower().strip()
        best_match = None
        best_confidence = "none"

        for entry in self._errors:
            pattern = entry.get("pattern", "")
            pattern_lower = pattern.lower()

            # 精确匹配
            if pattern_lower in error_text_lower:
                return {
                    "found": True,
                    "matched_id": entry["id"],
                    "cause": entry.get("cause", ""),
                    "fix": entry.get("fix", ""),
                    "auto_recoverable": entry.get("auto_recoverable", False),
                    "category": entry.get("category", ""),
                    "confidence": "exact",
                }
            # 关键词匹配
            key_words = pattern_lower.replace("error:", "").replace("error", "").strip()
            if key_words and key_words[:15] in error_text_lower:
                best_match = entry
                best_confidence = "partial"

        if best_match:
            return {
                "found": True,
                "matched_id": best_match["id"],
                "cause": best_match.get("cause", ""),
                "fix": best_match.get("fix", ""),
                "auto_recoverable": best_match.get("auto_recoverable", False),
                "category": best_match.get("category", ""),
                "confidence": "partial",
            }

        return {
            "found": False,
            "matched_id": None,
            "cause": "",
            "fix": "",
            "auto_recoverable": False,
            "category": "unknown",
            "confidence": "none",
        }

    def lookup_by_id(self, error_id: str) -> Optional[Dict[str, Any]]:
        """按错误 ID 查询。"""
        for entry in self._errors:
            if entry["id"] == error_id:
                return dict(entry)
        return None

    def is_recoverable(self, error_text: str) -> bool:
        """快速判断错误是否可自动恢复。"""
        result = self.lookup(error_text)
        return result["auto_recoverable"]

    def get_fix(self, error_text: str) -> str:
        """获取修复建议。"""
        result = self.lookup(error_text)
        return result["fix"] if result["found"] else ""

    def search_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按类别搜索错误。"""
        return [e for e in self._errors if e.get("category") == category]

    def list_categories(self) -> List[str]:
        """列出所有错误类别。"""
        return sorted(set(e.get("category", "") for e in self._errors))

    def reload(self, path: Optional[str] = None):
        """重新加载错误库。"""
        self._errors = self._load(path)
