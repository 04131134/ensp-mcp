# -*- coding: utf-8 -*-
"""Prompt 解析器 — 根据设备 Prompt 判断真实 View。

不相信 AI 的猜测，从设备实际返回的提示符中解析当前视图。

支持的 Prompt 模式：
    <Huawei>           → USER
    [Huawei]           → SYSTEM
    [Huawei-GigabitEthernet0/0/1] → INTERFACE
    [Huawei-vlan10]    → VLAN
    [Huawei-ospf-1]    → OSPF
    [Huawei-ospf-1-area-0.0.0.0] → AREA
    [Huawei-acl-adv-3000] → ACL
    [Huawei-aaa]       → AAA
    [Huawei-bgp]       → BGP
    [Huawei-rip-1]     → RIP
"""
from __future__ import annotations
import re
import json
import os
from typing import Dict, Any, Optional, Tuple
from .cli_state import CLIView


class PromptParser:
    """根据设备 prompt 字符串判断当前 CLI 视图。

    规则来源：kb/cli/view_rules.json（可扩展，无需修改代码）
    """

    def __init__(self, rules_path: Optional[str] = None):
        """初始化解析器。

        参数:
            rules_path: view_rules.json 路径，默认自动查找
        """
        self._rules = self._load_rules(rules_path)
        self._compile_patterns()

    def _load_rules(self, rules_path: Optional[str] = None) -> dict:
        """加载视图规则文件。"""
        if rules_path is None:
            rules_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "kb", "cli", "view_rules.json"
            )
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # 回退到内置默认规则
            return self._default_rules()

    def _default_rules(self) -> dict:
        """内置回退规则（view_rules.json 不可用时）。"""
        return {
            "views": {
                "USER": {"prompt_pattern": r"^<[A-Za-z0-9_-]+>$"},
                "SYSTEM": {"prompt_pattern": r"^\[[A-Za-z0-9_-]+\]$"},
                "INTERFACE": {"prompt_pattern": r"^\[[A-Za-z0-9_-]+-(GigabitEthernet|Ethernet|Vlanif|LoopBack|Null|Eth-Trunk)[0-9/]+\]$"},
                "VLAN": {"prompt_pattern": r"^\[[A-Za-z0-9_-]+-vlan[0-9]+\]$"},
                "OSPF": {"prompt_pattern": r"^\[[A-Za-z0-9_-]+-ospf-[0-9]+\]$"},
                "AREA": {"prompt_pattern": r"^\[[A-Za-z0-9_-]+-ospf-[0-9]+-area-[0-9.]+\]$"},
                "ACL": {"prompt_pattern": r"^\[[A-Za-z0-9_-]+-acl(-adv|-basic)?-[0-9]+\]$"},
                "AAA": {"prompt_pattern": r"^\[[A-Za-z0-9_-]+-aaa\]$"},
                "BGP": {"prompt_pattern": r"^\[[A-Za-z0-9_-]+-bgp(-[a-zA-Z0-9]+)?\]$"},
                "RIP": {"prompt_pattern": r"^\[[A-Za-z0-9_-]+-rip(-[0-9]+)?\]$"},
            }
        }

    def _compile_patterns(self):
        """预编译所有视图的正则模式。"""
        self._compiled: Dict[str, re.Pattern] = {}
        views = self._rules.get("views", {})
        for view_name, view_def in views.items():
            pattern_str = view_def.get("prompt_pattern", "")
            if pattern_str:
                try:
                    self._compiled[view_name] = re.compile(pattern_str)
                except re.error:
                    pass

    def parse(self, prompt: str) -> Dict[str, Any]:
        """解析 prompt 字符串，返回视图信息。

        参数:
            prompt: 设备提示符，如 "<Huawei>" 或 "[Huawei-ospf-1]"

        返回:
            {
                "view": CLIView 枚举值,
                "view_name": 视图名称字符串,
                "params": {"ifname": ..., "vlan_id": ...} 等,
                "confidence": "high" | "medium" | "low",
                "raw": 原始 prompt
            }
        """
        prompt = prompt.strip().replace("\r\n", "").replace("\n", "")

        # 去除可能的 ANSI 转义序列
        ansi_escape = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
        prompt = ansi_escape.sub("", prompt)

        result: Dict[str, Any] = {
            "view": CLIView.UNKNOWN,
            "view_name": "UNKNOWN",
            "params": {},
            "confidence": "low",
            "raw": prompt,
        }

        for view_name, pattern in self._compiled.items():
            m = pattern.search(prompt)
            if m:
                result["view"] = CLIView[view_name]
                result["view_name"] = view_name
                result["confidence"] = "high"
                result["params"] = self._extract_params(view_name, prompt, m)
                break

        return result

    def _extract_params(self, view_name: str, prompt: str, match: re.Match) -> Dict[str, Any]:
        """从匹配结果中提取视图参数。"""
        params: Dict[str, Any] = {}
        try:
            if view_name == "INTERFACE":
                # 提取接口名
                iface_match = re.search(r"(GigabitEthernet|Ethernet|Vlanif|LoopBack|Null|Eth-Trunk)([0-9/]+)", prompt)
                if iface_match:
                    params["ifname"] = iface_match.group(0)
            elif view_name == "VLAN":
                vlan_match = re.search(r"vlan(\d+)", prompt, re.IGNORECASE)
                if vlan_match:
                    params["vlan_id"] = vlan_match.group(1)
            elif view_name in ("OSPF", "RIP"):
                proc_match = re.search(r"-(ospf|rip)-(\d+)", prompt, re.IGNORECASE)
                if proc_match:
                    params["proc_id"] = proc_match.group(2)
            elif view_name == "AREA":
                area_match = re.search(r"area-([0-9.]+)", prompt, re.IGNORECASE)
                if area_match:
                    params["area_id"] = area_match.group(1)
            elif view_name == "ACL":
                acl_match = re.search(r"acl(-adv|-basic)?-(\d+)", prompt, re.IGNORECASE)
                if acl_match:
                    params["acl_num"] = acl_match.group(2)
            elif view_name == "BGP":
                as_match = re.search(r"bgp-(\d+)", prompt, re.IGNORECASE)
                if as_match:
                    params["as_num"] = as_match.group(1)
        except Exception:
            pass
        return params

    def parse_quick(self, prompt: str) -> CLIView:
        """快速解析，只返回 CLIView 枚举。"""
        result = self.parse(prompt)
        return result["view"]

    def detect_from_output(self, output: str) -> Optional[str]:
        """从命令输出中检测提示符行。

        参数:
            output: Telnet 命令输出

        返回:
            检测到的提示符字符串，或 None
        """
        lines = output.strip().split("\n")
        # 从后往前找提示符
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            # 尝试匹配所有已知的 prompt 模式
            for pattern in self._compiled.values():
                if pattern.search(line):
                    return line
        return None

    def is_valid_prompt(self, prompt: str) -> bool:
        """验证字符串是否为合法的设备提示符。"""
        result = self.parse(prompt)
        return result["view"] != CLIView.UNKNOWN

    def reload_rules(self, rules_path: Optional[str] = None):
        """重新加载规则文件（知识库更新后调用）。"""
        self._rules = self._load_rules(rules_path)
        self._compile_patterns()
