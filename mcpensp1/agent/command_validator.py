# -*- coding: utf-8 -*-
"""命令验证器 — 执行前验证当前 View 是否允许执行目标命令。

核心原则：不得在不正确的视图中发送命令，返回修正建议。
"""
from __future__ import annotations
import json
import os
from typing import Dict, Any, Optional, List, Tuple
from .cli_state import CLIState, CLIView


class CommandValidator:
    """验证命令是否可在当前 CLI 视图中执行。

    用法：
        validator = CommandValidator()
        result = validator.validate(state, "interface GigabitEthernet0/0/1")
        if not result["allowed"]:
            print(result["suggestion"])  # → "需要先执行: system-view"
    """

    def __init__(self, rules_path: Optional[str] = None):
        """初始化验证器。

        参数:
            rules_path: view_rules.json 路径，默认自动查找
        """
        self._rules = self._load_rules(rules_path)
        self._build_command_map()

    def _load_rules(self, rules_path: Optional[str] = None) -> dict:
        if rules_path is None:
            rules_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "kb", "cli", "view_rules.json"
            )
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return self._default_rules()

    def _default_rules(self) -> dict:
        return {
            "views": {
                "USER": {"allowed_commands": ["display", "dir", "ping", "tracert", "telnet", "system-view", "save", "reset", "terminal"]},
                "SYSTEM": {"allowed_commands": ["display", "interface", "vlan", "ospf", "bgp", "rip", "acl", "aaa",
                    "dhcp", "ip pool", "ip route", "stp", "vrrp", "sysname", "undo", "wlan", "capwap",
                    "firewall", "security-policy", "eth-trunk", "user-interface", "info-center", "return"]},
                "INTERFACE": {"allowed_commands": ["display", "ip address", "ip binding", "port link-type", "port default",
                    "port trunk", "undo", "shutdown", "description", "stp", "lacp", "dhcp", "arp", "igmp", "lldp", "port-security"]},
                "VLAN": {"allowed_commands": ["display", "description", "undo"]},
                "OSPF": {"allowed_commands": ["display", "area", "undo", "description", "router-id", "silent-interface", "preference"]},
                "AREA": {"allowed_commands": ["display", "network", "undo", "authentication-mode"]},
                "ACL": {"allowed_commands": ["display", "rule", "undo", "description"]},
                "AAA": {"allowed_commands": ["display", "undo", "authentication-scheme", "authorization-scheme", "accounting-scheme", "domain", "local-user"]},
                "BGP": {"allowed_commands": ["display", "undo", "router-id", "peer", "network", "import-route", "preference"]},
                "RIP": {"allowed_commands": ["display", "undo", "version", "network", "summary"]},
            },
            "global_commands": {
                "display": {"allowed_in": "*"},
                "undo": {"allowed_in": "*"},
                "quit": {"allowed_in": "*"},
            }
        }

    def _build_command_map(self):
        """构建命令前缀到允许视图的映射。"""
        self._cmd_map: Dict[str, List[str]] = {}

        # 全局命令（所有视图通用）
        global_cmds = self._rules.get("global_commands", {})
        for cmd_prefix in global_cmds:
            self._cmd_map[cmd_prefix] = ["*"]

        # 视图特定命令
        views = self._rules.get("views", {})
        for view_name, view_def in views.items():
            allowed = view_def.get("allowed_commands", [])
            for cmd_prefix in allowed:
                if cmd_prefix not in self._cmd_map:
                    self._cmd_map[cmd_prefix] = []
                if view_name not in self._cmd_map[cmd_prefix]:
                    self._cmd_map[cmd_prefix].append(view_name)

    def validate(self, state: CLIState, command: str) -> Dict[str, Any]:
        """验证命令是否可在当前视图执行。

        参数:
            state: 当前 CLI 状态
            command: 待验证的命令字符串

        返回:
            {
                "allowed": bool,
                "command": 原始命令,
                "current_view": 当前视图,
                "required_view": 需要的视图（如果不允许）,
                "suggestion": 修正建议（中文）,
                "correction_cmds": 修正命令序列,
                "reason": 原因说明
            }
        """
        current_view = state.current_view()
        cmd_lower = command.strip().lower()

        result: Dict[str, Any] = {
            "allowed": True,
            "command": command,
            "current_view": current_view.value,
            "required_view": None,
            "suggestion": None,
            "correction_cmds": [],
            "reason": "",
        }

        # 特殊命令处理
        # return 命令：任何视图都可以执行
        if cmd_lower == "return":
            return result

        # quit 命令：除 USER 外都可以
        if cmd_lower == "quit":
            if current_view == CLIView.USER:
                result["allowed"] = False
                result["reason"] = "已在用户视图，无法继续 quit"
                result["suggestion"] = "当前已是最外层视图，无需退出"
            return result

        # system-view：只能在 USER 执行
        if cmd_lower == "system-view":
            if current_view == CLIView.USER:
                return result
            if current_view == CLIView.SYSTEM:
                result["allowed"] = False
                result["reason"] = "已在系统视图"
                result["suggestion"] = "当前已在系统视图，无需再次执行 system-view"
                return result
            result["allowed"] = False
            result["suggestion"] = "需要先执行: return（回到用户视图）"
            result["correction_cmds"] = ["return"]
            result["reason"] = "system-view 只能在用户视图执行"
            return result

        # 查找命令的命令前缀
        matched_prefix, matched_prefix_len = self._find_command_match(cmd_lower)

        if matched_prefix is None:
            result["allowed"] = False
            result["reason"] = f"未知命令前缀: {cmd_lower}"
            result["suggestion"] = "命令不在已知命令列表中，请确认命令正确性"
            return result

        # 获取允许的视图
        allowed_views = self._cmd_map.get(matched_prefix, [])

        # "*" 表示全局允许
        if "*" in allowed_views:
            return result

        # 检查当前视图是否在允许列表中
        if current_view.value in allowed_views:
            return result

        # 不允许：确定需要的视图
        result["allowed"] = False
        result["required_view"] = allowed_views[0] if allowed_views else "SYSTEM"
        result["reason"] = f"命令 '{matched_prefix}' 不允许在 {current_view.value} 视图执行"

        # 生成修正建议
        correction, suggestion = self._suggest_correction(state, command, allowed_views)
        result["correction_cmds"] = correction
        result["suggestion"] = suggestion

        return result

    def _find_command_match(self, cmd_lower: str) -> Tuple[Optional[str], int]:
        """查找命令匹配的命令前缀。

        返回:
            (匹配的前缀, 前缀长度)
        """
        # 尝试完整匹配
        for prefix in sorted(self._cmd_map.keys(), key=len, reverse=True):
            if cmd_lower == prefix:
                return prefix, len(prefix)

        # 尝试前缀匹配（空格分隔的第一个词）
        first_word = cmd_lower.split()[0] if " " in cmd_lower else cmd_lower
        if first_word in self._cmd_map:
            return first_word, len(first_word)

        # 精确前缀匹配
        for prefix in sorted(self._cmd_map.keys(), key=len, reverse=True):
            if cmd_lower.startswith(prefix):
                return prefix, len(prefix)

        return None, 0

    def _suggest_correction(self, state: CLIState, command: str,
                            allowed_views: List[str]) -> Tuple[List[str], str]:
        """生成修正命令序列和建议文本。"""
        current_view = state.current_view().value
        correction: List[str] = []

        if allowed_views:
            target = allowed_views[0]

            if target == "USER":
                # 需要回到 USER
                if current_view != "USER":
                    correction.append("return")
                    suggestion = "需要先执行: return（回到用户视图）"
                else:
                    suggestion = "当前已在用户视图"
            elif target == "SYSTEM":
                if current_view == "USER":
                    correction.append("system-view")
                    suggestion = "需要先执行: system-view（进入系统视图）"
                elif current_view != "SYSTEM":
                    correction.append("return")
                    suggestion = "需要先执行: return → system-view"
                else:
                    suggestion = "当前已在系统视图"
            else:
                # 需要进入特定子视图
                if current_view == "USER":
                    correction.append("system-view")
                    suggestion = f"需要先执行: system-view（进入系统视图），然后进入 {target} 视图"
                elif current_view == "SYSTEM":
                    suggestion = f"需要在 {target} 视图中执行，请先进入对应视图"
                else:
                    correction.append("quit")
                    suggestion = f"需要先执行: quit（退出当前视图），再进入 {target} 视图"
        else:
            suggestion = "建议回到系统视图: return → system-view"

        return correction, suggestion

    def validate_batch(self, state: CLIState, commands: List[str]) -> List[Dict[str, Any]]:
        """批量验证命令列表。

        参数:
            state: 初始 CLI 状态
            commands: 命令列表

        返回:
            验证结果列表，每个元素包含 allowed/command/suggestion 等
        """
        results = []
        sim_state = state.clone()

        for cmd in commands:
            result = self.validate(sim_state, cmd)
            results.append(result)
            # 模拟执行：允许的命令更新模拟状态
            if result["allowed"]:
                self._simulate_execution(sim_state, cmd)

        return results

    def _simulate_execution(self, state: CLIState, command: str) -> None:
        """模拟命令执行对状态的影响（仅用于批量验证）。"""
        cmd_lower = command.strip().lower()

        if cmd_lower.startswith("interface ") and "loopback" not in cmd_lower:
            state.push(CLIView.INTERFACE)
        elif cmd_lower == "system-view":
            state.push(CLIView.SYSTEM)
        elif cmd_lower == "return":
            state.return_to_user()
        elif cmd_lower == "quit":
            try:
                state.pop()
            except ValueError:
                pass

    def reload_rules(self, rules_path: Optional[str] = None):
        """重新加载规则文件。"""
        self._rules = self._load_rules(rules_path)
        self._build_command_map()
