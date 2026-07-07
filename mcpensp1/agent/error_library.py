# -*- coding: utf-8 -*-
"""错误库 — 收录华为 CLI 常见错误，提供原因分析和自动恢复建议。

Recovery 优先查询 Error Library，不要让 AI 猜错误原因。
"""
from __future__ import annotations
import json
import os
import re
from typing import Dict, Any, Optional, List


class ErrorLibrary:
    """华为/H3C CLI 错误知识库。

    用法:
        lib = ErrorLibrary()
        result = lib.lookup("Error: The VLAN already exists")
        if result["auto_recoverable"]:
            print(result["fix"])
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
