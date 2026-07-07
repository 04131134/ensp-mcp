# -*- coding: utf-8 -*-
"""Action 驱动的 Runtime 执行引擎。

新流程：
    Receive Task → Capability Check → Planner → Action Plan
    → Dependency Graph → Command Generator → CLI Validator
    → Executor → Prompt Parser → CLI State Update
    → Semantic Verify → Repair → Knowledge Update

渐进式迁移：不修改原有 runtime.py，新旧 Runtime 共存。
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
import logging

from .action_types import ActionType, ActionNode, ActionPlan, ConfigObject
from .dependency_graph import DependencyGraph
from .cli_state import CLIState, CLIView
from .command_validator import CommandValidator
from .command_generator import CommandGenerator, Action
from .prompt_parser import PromptParser

logger = logging.getLogger(__name__)


class ActionDrivenRuntime:
    """Action 驱动的执行引擎 — 完整的 14 步闭环执行流程。

    用法:
        runtime = ActionDrivenRuntime(command_executor=None)
        result = runtime.execute(
            task="配置 VLAN 10 和 VLAN 20，并配置 OSPF",
            device_paths=["127.0.0.1:2001"],
            device_model="S5700",
        )
    """

    def __init__(self, command_executor: Optional[Any] = None,
                 verifier: Optional[Any] = None,
                 knowledge_store: Optional[Any] = None,
                 memory_store: Optional[Any] = None):
        """初始化。

        参数:
            command_executor: CommandExecutor 实例
            verifier: SemanticVerifier 实例
            knowledge_store: KnowledgeStore 实例
            memory_store: MemoryStore 实例
        """
        self._executor = command_executor
        self._verifier = verifier
        self._knowledge_store = knowledge_store
        self._memory_store = memory_store
        self._validator = CommandValidator()
        self._generator = CommandGenerator()
        self._prompt_parser = PromptParser()

    def execute(self, task: str, device_paths: List[str],
                device_model: str = "S5700",
                experiment_type: str = "general") -> Dict[str, Any]:
        """执行任务的完整流程。

        参数:
            task: 自然语言任务描述
            device_paths: 目标设备路径列表
            device_model: 设备型号
            experiment_type: 实验类型

        返回:
            {
                "success": bool,
                "plan_id": str,
                "nodes_completed": int,
                "nodes_failed": int,
                "retried": int,
                "state_updates": [...],
                "reflection": {...},
                "knowledge_updates": [...],
                "duration_ms": float,
            }
        """
        t0 = datetime.now(timezone.utc)
        state_updates: List[Dict[str, Any]] = []
        nodes_completed = 0
        nodes_failed = 0
        retried = 0

        try:
            # ══ Step 1-2: Capability Check ══════════════
            from .capability_manager import CapabilityManager
            cm = CapabilityManager()
            caps = cm.get_model_capabilities(device_model)
            if caps is None:
                return {"success": False, "error": f"Unknown device model: {device_model}"}

            # ══ Step 3-4: Planner → Action Plan ═══════════
            plan = self._plan_task(task, device_paths, experiment_type, device_model)

            # ══ Step 5: Dependency Graph ═══════════════
            dg = DependencyGraph.from_plan(plan)

            if dg.has_cycle():
                cycle = dg.find_cycle()
                return {
                    "success": False,
                    "error": f"Circular dependency detected: {cycle}",
                    "plan_id": plan.plan_id,
                }

            # ══ Step 6-7: Generate CLI + Validate ════════
            cli_state = CLIState(device_paths[0] if device_paths else "")
            all_valid = True

            for action in plan.actions:
                cli_commands = self._generate_cli(action, cli_state)
                for cmd in cli_commands:
                    result = self._validator.validate(cli_state, cmd)
                    if not result["allowed"]:
                        logger.warning("CLI validation failed: %s - %s", cmd, result.get("suggestion"))
                        all_valid = False
                    # Update simulated CLI state
                    self._update_cli_state(cli_state, cmd)

            if not all_valid:
                logger.warning("Some CLI commands failed validation; attempting execution anyway")

            # ══ Step 8-9: Execute + Update State ════════
            exec_order = dg.topological_sort()

            for aid in exec_order:
                action = plan.get_action(aid)
                if action is None:
                    continue

                dg.monitor_action(aid, "running")

                # Execute
                exec_result = self._execute_action(action, device_paths[0] if device_paths else "")
                if exec_result.get("success"):
                    nodes_completed += 1
                    dg.monitor_action(aid, "success")
                else:
                    nodes_failed += 1
                    dg.monitor_action(aid, "failed")

                    # ══ Step 10-11: Repair (local recovery) ══
                    repair = self._attempt_repair(action, exec_result)
                    if repair.get("retry"):
                        retried += 1
                        dg.retry_action(aid)
                        retry_result = self._execute_action(action, device_paths[0] if device_paths else "")
                        if retry_result.get("success"):
                            dg.monitor_action(aid, "success")
                            nodes_completed += 1
                            nodes_failed -= 1

                # Record state update
                state_updates.append({
                    "action_id": aid,
                    "action_type": action.action_type.value,
                    "device": device_paths[0] if device_paths else "",
                    "status": dg._status.get(aid),
                    "result": exec_result,
                })

            # ══ Step 12-13: Verify + Reflect ════════════
            reflection = self._reflect(plan, nodes_completed, nodes_failed, retried)

            # ══ Step 14: Knowledge Update ════════════
            knowledge_updates = self._update_knowledge(plan, state_updates, reflection)

            duration_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000

            return {
                "success": nodes_failed == 0,
                "plan_id": plan.plan_id,
                "nodes_completed": nodes_completed,
                "nodes_failed": nodes_failed,
                "retried": retried,
                "state_updates": state_updates,
                "reflection": reflection,
                "knowledge_updates": knowledge_updates,
                "duration_ms": round(duration_ms, 2),
            }

        except Exception as e:
            logger.error("Action-driven execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "plan_id": "",
                "nodes_completed": nodes_completed,
                "nodes_failed": nodes_failed,
                "retried": retried,
            }

    # ── Internal: Planning ─────────────────────────────────

    def _plan_task(self, task: str, device_paths: List[str],
                   experiment_type: str, device_model: str) -> ActionPlan:
        """将自然语言任务转换为 ActionPlan。"""
        import uuid
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        plan = ActionPlan(
            plan_id=plan_id,
            experiment_type=experiment_type,
            description=task,
            metadata={"device_model": device_model, "device_paths": device_paths},
        )

        # 基于关键词的协议检测
        task_lower = task.lower()
        protocols_detected = []
        if "vlan" in task_lower:
            protocols_detected.append("vlan")
        if "ospf" in task_lower:
            protocols_detected.append("ospf")
        if "acl" in task_lower:
            protocols_detected.append("acl")
        if "bgp" in task_lower:
            protocols_detected.append("bgp")
        if "rip" in task_lower:
            protocols_detected.append("rip")

        device = device_paths[0] if device_paths else "unknown"
        action_index = 0

        for proto in protocols_detected:
            plugin = self._load_plugin(proto)
            if plugin is None:
                continue

            # Generate ConfigObjects
            try:
                params, prev_ids = self._extract_params(task, proto, device, action_index)
                action_index = prev_ids

                configs = plugin.generate_config_objects(params, device, start_id=action_index + 1)
                action_index += len(configs) + 1

                for cfg in configs:
                    action_node = ActionNode(
                        id=cfg.id,
                        action_type=self._map_action_type(cfg.action),
                        config_object=cfg,
                        depends_on=cfg.preconditions,
                    )
                    plan.add_action(action_node)
            except Exception as e:
                logger.warning("Failed to generate configs for %s: %s", proto, e)

        return plan

    def _extract_params(self, task: str, proto: str, device: str,
                        start_index: int) -> tuple:
        """从任务描述中提取协议参数。"""
        import re
        params: Dict[str, Any] = {}
        if proto == "vlan":
            vlan_ids = re.findall(r"[Vv][Ll][Aa][Nn]\s*(\d+)", task)
            ports = re.findall(r"([Gg]igabit[Ee]thernet\d+/\d+/\d+)", task)
            params["vlan_id"] = vlan_ids[0] if vlan_ids else "10"
            params["ports"] = ports
            params["mode"] = "access"
        elif proto == "ospf":
            params["proc_id"] = "1"
            params["router_id"] = "1.1.1.1"
            params["areas"] = [{"area_id": "0", "networks": ["10.0.0.0 0.0.0.255"]}]
        elif proto == "acl":
            params["acl_num"] = "3000"
            params["type"] = "advanced"
            params["rules"] = ["rule 5 permit ip source any destination any"]
        elif proto == "bgp":
            params["as_num"] = "65001"
            params["router_id"] = "1.1.1.1"

        return params, start_index

    def _load_plugin(self, proto: str) -> Optional[Any]:
        """加载协议插件。"""
        try:
            if proto == "vlan":
                from mcpensp1.protocols import VLANPlugin
                return VLANPlugin
            elif proto == "ospf":
                from mcpensp1.protocols import OSPFPlugin
                return OSPFPlugin
            elif proto == "acl":
                from mcpensp1.protocols import ACLPlugin
                return ACLPlugin
            elif proto == "bgp":
                from mcpensp1.protocols import BGPPlugin
                return BGPPlugin
        except ImportError:
            pass
        return None

    def _map_action_type(self, action: str) -> ActionType:
        """映射 action 字符串到 ActionType。"""
        mapping = {
            "create_vlan": ActionType.CONFIGURE_VLAN,
            "assign_port_vlan": ActionType.CONFIGURE_VLAN,
            "create_ospf_process": ActionType.CONFIGURE_OSPF,
            "configure_ospf_area": ActionType.CONFIGURE_OSPF_AREA,
            "create_acl": ActionType.CONFIGURE_ACL,
            "add_acl_rule": ActionType.CONFIGURE_ACL,
            "create_bgp_process": ActionType.CONFIGURE_BGP,
            "configure_bgp_peer": ActionType.CONFIGURE_BGP,
            "advertise_bgp_network": ActionType.CONFIGURE_BGP,
        }
        return mapping.get(action, ActionType.CONFIGURE_GLOBAL)

    # ── Internal: Generate CLI ────────────────────────────

    def _generate_cli(self, action: ActionNode, cli_state: CLIState) -> List[str]:
        """从 ActionNode 生成 CLI 命令。"""
        action_type = action.action_type
        params = action.config_object.target

        act = Action(action_type.value, params=params)
        return self._generator.generate(cli_state, act)

    def _update_cli_state(self, cli_state: CLIState, cmd: str) -> None:
        """模拟 CLI 状态更新。"""
        cmd_lower = cmd.strip().lower()
        if cmd_lower == "system-view":
            cli_state.push(CLIView.SYSTEM)
        elif cmd_lower == "return":
            cli_state.return_to_user()
        elif cmd_lower == "quit":
            try:
                cli_state.pop()
            except ValueError:
                pass
        elif cmd_lower.startswith("interface ") and "loopback" not in cmd_lower:
            cli_state.push(CLIView.INTERFACE)

    # ── Internal: Execute ─────────────────────────────────

    def _execute_action(self, action: ActionNode,
                        device_path: str) -> Dict[str, Any]:
        """执行单个 Action。"""
        if self._executor is None:
            return {"success": True, "note": "no executor (dry run)"}

        try:
            cli_state = CLIState(device_path)
            commands = self._generate_cli(action, cli_state)

            result = self._executor.batch_command(device_path, commands)
            return result if isinstance(result, dict) else {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Internal: Repair ───────────────────────────────────

    def _attempt_repair(self, action: ActionNode,
                        exec_result: Dict[str, Any]) -> Dict[str, Any]:
        """尝试修复失败的 Action。"""
        error_text = exec_result.get("error", "")
        if not error_text:
            return {"retry": False}

        from .error_library import ErrorLibrary
        lib = ErrorLibrary()
        lookup = lib.lookup(error_text)

        if lookup.get("auto_recoverable"):
            return {"retry": True, "fix": lookup.get("fix", "")}

        return {"retry": False}

    # ── Internal: Reflect ──────────────────────────────────

    def _reflect(self, plan: ActionPlan, completed: int, failed: int,
                 retried: int) -> Dict[str, Any]:
        """反思执行结果。"""
        return {
            "plan_id": plan.plan_id,
            "description": plan.description,
            "total_actions": len(plan.actions),
            "completed": completed,
            "failed": failed,
            "retried": retried,
            "success_rate": round(completed / max(1, len(plan.actions)), 2),
            "lessons": self._extract_lessons(completed, failed, retried),
        }

    def _extract_lessons(self, completed: int, failed: int,
                         retried: int) -> List[str]:
        """提取经验教训。"""
        lessons = []
        if failed > 0 and retried == 0:
            lessons.append("Some actions failed without recovery; review error patterns")
        if retried > 0 and failed == 0:
            lessons.append(f"All {retried} failed actions recovered successfully")
        if completed > 0:
            lessons.append(f"Successfully completed {completed} actions")
        return lessons

    # ── Internal: Knowledge Update ─────────────────────────

    def _update_knowledge(self, plan: ActionPlan,
                          state_updates: List[Dict[str, Any]],
                          reflection: Dict[str, Any]) -> List[str]:
        """更新知识库。"""
        updates = []
        for update in state_updates:
            if update.get("status") == "success":
                updates.append(f"Knowledge: {update['action_id']} succeeded")
        return updates
