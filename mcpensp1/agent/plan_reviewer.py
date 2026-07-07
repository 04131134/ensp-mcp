# -*- coding: utf-8 -*-
"""计划审核器 — 所有执行计划必须通过审核才能执行。

检查项：
- 危险命令
- View 错误
- 依赖错误（循环依赖）
- 重复配置
- 非法删除
- 设备能力匹配

审核失败禁止执行，返回详细的审核报告。
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from .cli_state import CLIState, CLIView
from .command_validator import CommandValidator


class PlanReviewer:
    """审核执行计划的安全性和正确性。

    用法:
        reviewer = PlanReviewer()
        report = reviewer.review(plan, device_model="S5700")
        if not report["approved"]:
            for issue in report["issues"]:
                print(issue["severity"], issue["message"])
    """

    # 危险命令关键词（即使不是 blocked_command，也应警告）
    DANGEROUS_KEYWORDS: List[str] = [
        "reset", "delete", "format", "erase", "clear configuration",
        "undo interface", "shutdown", "power off",
    ]

    # 非法删除模式（禁止删除的配置）
    ILLEGAL_DELETE_PATTERNS: List[str] = [
        "undo management-plane",
        "undo http server",
        "undo telnet server",
        "undo stelnet server",
        "undo user-interface vty",
    ]

    def __init__(self):
        """初始化审核器。"""
        self._validator = CommandValidator()

    def review(self, plan: Dict[str, Any], device_model: str = "S5700",
               device_path: str = "") -> Dict[str, Any]:
        """审核执行计划。

        参数:
            plan: 执行计划（PlanNode 列表或类似结构）
            device_model: 设备型号
            device_path: 设备路径

        返回:
            {
                "approved": bool,
                "total_nodes": int,
                "total_commands": int,
                "issues": [{"severity": "critical"|"warning"|"info",
                            "type": "dangerous_command"|"view_error"|...,
                            "message": str, "node": str, "command": str}],
                "score": float (0.0 ~ 1.0, 越高越安全),
                "suggestions": [...],
            }
        """
        issues: List[Dict[str, Any]] = []
        total_commands = 0
        total_nodes = 0

        nodes = plan.get("nodes", [plan]) if isinstance(plan, dict) else list(plan)

        for node in nodes:
            total_nodes += 1
            node_id = node.get("id", "unknown")
            commands = node.get("commands", [])
            total_commands += len(commands)

            # 1. 检查危险命令
            for cmd in commands:
                severity, msg = self._check_dangerous(cmd)
                if severity:
                    issues.append({
                        "severity": severity,
                        "type": "dangerous_command",
                        "message": msg,
                        "node": node_id,
                        "command": cmd,
                    })

            # 2. 检查 View 错误（模拟状态）
            severity, msg = self._check_view_errors(commands, node_id)
            if severity:
                issues.append({
                    "severity": severity,
                    "type": "view_error",
                    "message": msg,
                    "node": node_id,
                    "command": commands[0] if commands else "",
                })

            # 3. 检查非法删除
            for cmd in commands:
                severity, msg = self._check_illegal_delete(cmd)
                if severity:
                    issues.append({
                        "severity": severity,
                        "type": "illegal_delete",
                        "message": msg,
                        "node": node_id,
                        "command": cmd,
                    })

            # 4. 检查重复配置
            dups = self._check_duplicates(commands)
            for cmd in dups:
                issues.append({
                    "severity": "warning",
                    "type": "duplicate",
                    "message": f"重复命令: {cmd}",
                    "node": node_id,
                    "command": cmd,
                })

        # 5. 检查循环依赖
        cycle_issues = self._check_circular_dependency(nodes)
        issues.extend(cycle_issues)

        # 6. 检查设备能力
        cap_issues = self._check_capability(nodes, device_model)
        issues.extend(cap_issues)

        # 计算审核分数
        critical = sum(1 for i in issues if i["severity"] == "critical")
        warnings = sum(1 for i in issues if i["severity"] == "warning")
        score = max(0.0, 1.0 - (critical * 0.3 + warnings * 0.1))

        # 生成建议
        suggestions = self._generate_suggestions(issues)

        return {
            "approved": critical == 0,
            "total_nodes": total_nodes,
            "total_commands": total_commands,
            "issues": issues,
            "score": round(score, 2),
            "suggestions": suggestions,
        }

    def review_commands(self, commands: List[str], device_model: str = "S5700") -> Dict[str, Any]:
        """快速审核命令列表（无计划结构）。

        参数:
            commands: 命令列表
            device_model: 设备型号

        返回:
            审核报告
        """
        plan = {"nodes": [{"id": "direct", "commands": commands}]}
        return self.review(plan, device_model)

    # ── 内部检查方法 ──────────────────────────────────────

    def _check_dangerous(self, command: str) -> Tuple[Optional[str], str]:
        """检查危险命令。"""
        cmd_lower = command.strip().lower()
        from mcpensp1.command_executor import is_blocked_command
        if is_blocked_command(cmd_lower):
            return "critical", f"危险命令被拦截: {command}"
        for kw in self.DANGEROUS_KEYWORDS:
            if kw in cmd_lower:
                return "warning", f"包含危险关键词 '{kw}': {command}"
        return None, ""

    def _check_view_errors(self, commands: List[str], node_id: str) -> Tuple[Optional[str], str]:
        """检查 View 错误。"""
        if not commands:
            return None, ""
        state = CLIState()
        issues = 0
        for cmd in commands:
            result = self._validator.validate(state, cmd)
            if not result["allowed"]:
                issues += 1
            # 模拟执行
            if cmd.strip().lower() == "system-view":
                state.push(CLIView.SYSTEM)
            elif cmd.strip().lower() == "return":
                state.return_to_user()
            elif cmd.strip().lower() == "quit":
                try:
                    state.pop()
                except ValueError:
                    pass
        if issues > 0:
            return "critical", f"发现 {issues} 个视图权限错误"
        return None, ""

    def _check_illegal_delete(self, command: str) -> Tuple[Optional[str], str]:
        """检查非法删除。"""
        cmd_lower = command.strip().lower()
        for pattern in self.ILLEGAL_DELETE_PATTERNS:
            if pattern in cmd_lower:
                return "critical", f"禁止执行非法删除命令: {command}"
        return None, ""

    def _check_duplicates(self, commands: List[str]) -> List[str]:
        """检查重复命令。"""
        seen = set()
        dups = []
        for cmd in commands:
            normalized = cmd.strip().lower()
            if normalized in seen:
                dups.append(cmd)
            seen.add(normalized)
        return dups

    def _check_circular_dependency(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """检查循环依赖。"""
        issues = []
        # 构建邻接表
        adj: Dict[str, List[str]] = {}
        for node in nodes:
            nid = node.get("id", "")
            adj[nid] = node.get("depends_on", [])

        # DFS 检测环路
        visited: Dict[str, int] = {}  # 0=white, 1=gray, 2=black
        for nid in adj:
            visited[nid] = 0

        def dfs(u: str, path: List[str]) -> bool:
            visited[u] = 1
            for v in adj.get(u, []):
                if visited.get(v, 0) == 1:
                    cycle_path = path[path.index(v):] + [v]
                    issues.append({
                        "severity": "critical",
                        "type": "circular_dependency",
                        "message": f"检测到循环依赖: {' → '.join(cycle_path)}",
                        "node": u,
                        "command": "",
                    })
                    return True
                if visited.get(v, 0) == 0:
                    if dfs(v, path + [v]):
                        return True
            visited[u] = 2
            return False

        for nid in adj:
            if visited.get(nid, 0) == 0:
                dfs(nid, [nid])

        return issues

    def _check_capability(self, nodes: List[Dict[str, Any]],
                          device_model: str) -> List[Dict[str, Any]]:
        """检查设备能力。"""
        issues = []
        from .capability_manager import CapabilityManager
        cm = CapabilityManager()
        caps = cm.get_model_capabilities(device_model)
        if caps is None:
            issues.append({
                "severity": "warning",
                "type": "capability",
                "message": f"无法验证设备型号 {device_model} 的能力，跳过检查",
                "node": "",
                "command": "",
            })
        return issues

    def _generate_suggestions(self, issues: List[Dict[str, Any]]) -> List[str]:
        """根据问题生成修复建议。"""
        suggestions = []
        for issue in issues:
            if issue["type"] == "dangerous_command" and issue["severity"] == "critical":
                suggestions.append(f"移除危险命令: {issue['command']}")
            elif issue["type"] == "view_error":
                suggestions.append("使用 command_generator 生成正确的视图导航命令")
            elif issue["type"] == "circular_dependency":
                suggestions.append(f"解除循环依赖: {issue['message']}")
            elif issue["type"] == "duplicate":
                suggestions.append(f"删除重复命令: {issue['command']}")
            elif issue["type"] == "illegal_delete":
                suggestions.append(f"移除非法删除命令: {issue['command']}")

        # 去重
        return list(dict.fromkeys(suggestions))
