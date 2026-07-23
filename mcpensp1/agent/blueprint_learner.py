# -*- coding: utf-8 -*-
"""从成功命令历史提炼可复用的网络配置蓝图。"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .knowledge_store import KnowledgeStore
from .types import KnowledgeRecord


class BlueprintLearner:
    """将一次成功的设备配置执行记录转化为可复用蓝图。"""

    _QUERY_COMMAND = re.compile(
        r"^\s*(?:display|show|ping|tracert|traceroute|dir)\b", re.IGNORECASE
    )
    _INTERFACE_NAME = re.compile(
        r"\b(?:gigabitethernet|xgigabitethernet|ethernet|ge|eth-trunk|vlanif)"
        r"\s*\d+(?:/\d+){0,3}\b",
        re.IGNORECASE,
    )
    _IP_ADDRESS = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    _VLAN_COMMAND = re.compile(r"\b(vlan(?:if)?)\s+(\d+)\b", re.IGNORECASE)
    _OSPF_PROCESS = re.compile(r"\bospf\s+(\d+)\b", re.IGNORECASE)
    _ROUTER_ID = re.compile(r"\brouter-id\s+((?:\d{1,3}\.){3}\d{1,3})\b", re.IGNORECASE)

    def __init__(self, knowledge_store: KnowledgeStore):
        """初始化蓝图学习器。

        参数:
            knowledge_store: 用于保存和更新蓝图的增长知识库。
        """
        self._knowledge_store = knowledge_store

    def learn_from_success(
        self,
        task_id: str,
        execution_log: List[Dict[str, str]],
        device_info: Dict[str, Any],
        topology_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """从一次成功执行中提炼并保存配置蓝图。

        当执行记录不包含配置命令时返回 ``None``，避免写入空模板。
        """
        configuration_log = self._purge_commands(execution_log)
        if not configuration_log:
            return None

        commands = [entry["command"] for entry in configuration_log]
        views = [entry.get("view", "") for entry in configuration_log]
        rebuilt_sequence = self._rebuild_view_sequence(commands, views)
        generalized_commands, parameter_sources = self._generalize(
            [step["command"] for step in rebuilt_sequence], topology_data
        )
        command_sequence = self._build_command_sequence(
            generalized_commands, rebuilt_sequence, parameter_sources
        )
        rollback_sequence = self._generate_rollback(generalized_commands)
        now = datetime.now(timezone.utc).isoformat()
        template = {
            "intent": self._infer_intent(task_id, generalized_commands),
            "device_requirements": self._device_requirements(device_info),
            "applicable_devices": self._applicable_devices(device_info),
            "preconditions": self._preconditions(generalized_commands),
            "command_sequence": command_sequence,
            "rollback_sequence": rollback_sequence,
            "verification_commands": self._verification_commands(generalized_commands),
            "parameter_sources": parameter_sources,
            "success_count": 1,
            "confidence": 0.5,
            "last_used": now,
        }
        template["blueprint_hash"] = self._blueprint_hash(command_sequence)
        return self._deduplicate(template)

    def _purge_commands(self, log: Sequence[Mapping[str, str]]) -> List[Dict[str, str]]:
        """移除查询和视图退出命令，保留带配置效果的原始记录。"""
        commands: List[Dict[str, str]] = []
        for entry in log:
            command = str(entry.get("command", "")).strip()
            if not command or self._QUERY_COMMAND.match(command):
                continue
            if command.lower() in {"quit", "return", "system-view"}:
                continue
            commands.append({
                "command": command,
                "output": str(entry.get("output", "")),
                "view": str(entry.get("view", "")),
            })
        return commands

    def _rebuild_view_sequence(
        self, commands: Sequence[str], views: Sequence[str]
    ) -> List[Dict[str, str]]:
        """依据执行视图补齐进入系统和接口等配置视图的命令。"""
        sequence: List[Dict[str, str]] = []
        current_view = "user-view"
        for command, view in zip(commands, views):
            expected_view = self._expected_view(view)
            entry_command = self._entry_command_for_view(view)

            if expected_view == "system-view" and current_view == "user-view":
                sequence.append({"command": "system-view", "expected_view": "user-view"})
                current_view = "system-view"
            elif expected_view == "system-view" and current_view not in {"system-view", "user-view"}:
                sequence.append({"command": "quit", "expected_view": current_view})
                current_view = "system-view"

            if (
                entry_command
                and current_view != expected_view
                and command.strip().lower() != entry_command.lower()
            ):
                if current_view != "system-view":
                    sequence.append({"command": "quit", "expected_view": current_view})
                    current_view = "system-view"
                sequence.append({"command": entry_command, "expected_view": "system-view"})
                current_view = expected_view

            sequence.append({"command": command, "expected_view": expected_view})
            current_view = self._view_after_command(command, expected_view)
        return sequence

    def _generalize(
        self, commands: Sequence[str], topology_data: Mapping[str, Any]
    ) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
        """参数化拓扑中的地址、接口和 VLAN，并保留参数来源。"""
        parameter_sources: Dict[str, Dict[str, str]] = {}
        interface_ips = list(self._find_interface_ips(topology_data))
        generalized: List[str] = []

        for command in commands:
            value = command
            value = self._replace_ospf_parameters(value, parameter_sources)
            for interface, ip_value, source in interface_ips:
                host_ip = ip_value.split("/", 1)[0]
                key = f"ip_interface_{interface}"
                placeholder = "{" + key + "}"
                if interface in value:
                    value = value.replace(interface, "{interface}")
                    parameter_sources.setdefault(
                        "interface", {"value": interface, "source": source}
                    )
                if host_ip in value:
                    value = value.replace(host_ip, placeholder)
                    parameter_sources[key] = {"value": ip_value, "source": source}

            value = self._replace_vlan(value, parameter_sources)
            value = self._replace_remaining_ip_addresses(value, parameter_sources)
            for interface in self._INTERFACE_NAME.findall(value):
                value = value.replace(interface, "{interface}")
                parameter_sources.setdefault(
                    "interface", {"value": interface, "source": "command"}
                )
            generalized.append(value)
        return generalized, parameter_sources

    def _generate_rollback(self, commands: Sequence[str]) -> List[str]:
        """按反向顺序为配置命令生成符合 VRP 习惯的回滚命令。"""
        rollback: List[str] = []
        for command in reversed(commands):
            normalized = command.strip()
            lower = normalized.lower()
            if not normalized or lower in {"system-view", "quit", "return"}:
                continue
            if lower.startswith("interface "):
                continue
            if lower.startswith("undo "):
                rollback.append(normalized[5:])
            elif lower.startswith("ip address "):
                rollback.append("undo ip address")
            elif lower.startswith("ospf "):
                process_id = normalized.split()[1] if len(normalized.split()) > 1 else ""
                rollback.append(f"undo ospf {process_id}".strip())
            else:
                rollback.append(f"undo {normalized}")
        return rollback

    def _deduplicate(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """按规范化命令序列合并相同蓝图，或创建新的模板记录。"""
        fingerprint = template["blueprint_hash"]
        for record in self._knowledge_store.search(category="template", limit=10000):
            if record.content.get("blueprint_hash") != fingerprint:
                continue
            record.success_count += 1
            record.usage_count += 1
            record.last_used = template["last_used"]
            record.content["success_count"] = record.success_count
            record.content["last_used"] = record.last_used
            record.content["applicable_devices"] = sorted(set(
                record.content.get("applicable_devices", [])
                + template.get("applicable_devices", [])
            ))
            self._knowledge_store.update(record)
            return record.content

        record = KnowledgeRecord(
            category="template",
            title=f"配置蓝图: {template['intent']}",
            content=template,
            device_type="huawei",
            tags=["blueprint", template["intent"]],
            confidence=template["confidence"],
            usage_count=1,
            success_count=1,
            source="learned",
            last_used=template["last_used"],
        )
        template["id"] = record.record_id
        self._knowledge_store.add(record)
        return template

    def _build_command_sequence(
        self,
        commands: Sequence[str],
        rebuilt_sequence: Sequence[Mapping[str, str]],
        parameter_sources: Mapping[str, Mapping[str, str]],
    ) -> List[Dict[str, Any]]:
        """将参数化命令和视图信息组装为蓝图步骤。"""
        result: List[Dict[str, Any]] = []
        for command, step in zip(commands, rebuilt_sequence):
            item: Dict[str, Any] = {
                "command": command,
                "expected_view": step["expected_view"],
            }
            parameters = {
                key: parameter_sources[key]["value"]
                for key in re.findall(r"\{([^{}]+)\}", command)
                if key in parameter_sources
            }
            if parameters:
                item["params"] = parameters
            result.append(item)
        return result

    @classmethod
    def _replace_ospf_parameters(
        cls, command: str, parameter_sources: Dict[str, Dict[str, str]]
    ) -> str:
        """提取 OSPF 进程号和路由器标识为可复用参数。"""
        def replace_process(match: re.Match[str]) -> str:
            parameter_sources.setdefault(
                "pid", {"value": match.group(1), "source": "command"}
            )
            return "ospf {pid}"

        def replace_router_id(match: re.Match[str]) -> str:
            parameter_sources.setdefault(
                "rid", {"value": match.group(1), "source": "command"}
            )
            return "router-id {rid}"

        command = cls._OSPF_PROCESS.sub(replace_process, command)
        return cls._ROUTER_ID.sub(replace_router_id, command)

    @classmethod
    def _replace_vlan(
        cls, command: str, parameter_sources: Dict[str, Dict[str, str]]
    ) -> str:
        """提取 VLAN 标识为可复用参数。"""
        def replace_vlan(match: re.Match[str]) -> str:
            parameter_sources.setdefault(
                "vlan_id", {"value": match.group(2), "source": "command"}
            )
            return f"{match.group(1)} {{vlan_id}}"

        return cls._VLAN_COMMAND.sub(replace_vlan, command)

    @classmethod
    def _replace_remaining_ip_addresses(
        cls, command: str, parameter_sources: Dict[str, Dict[str, str]]
    ) -> str:
        """参数化未由拓扑绑定的地址，同时保留 ip address 的掩码。"""
        address_command = re.match(
            r"^(\s*ip\s+address\s+)((?:\d{1,3}\.){3}\d{1,3})(.*)$",
            command,
            re.IGNORECASE,
        )
        if address_command:
            parameter_sources.setdefault(
                "ip_addr", {"value": "auto", "source": "command"}
            )
            return f"{address_command.group(1)}{{ip_addr}}{address_command.group(3)}"
        if re.match(r"^\s*ip\s+address\b", command, re.IGNORECASE):
            return command
        if cls._IP_ADDRESS.search(command):
            parameter_sources.setdefault(
                "ip_addr", {"value": "auto", "source": "command"}
            )
            return cls._IP_ADDRESS.sub("{ip_addr}", command)
        return command

    @classmethod
    def _expected_view(cls, view: str) -> str:
        """将设备原始提示符或视图名称归一为蓝图视图名称。"""
        normalized = view.strip().lower()
        if not normalized or "<" in normalized or "user" in normalized:
            return "user-view"
        if cls._INTERFACE_NAME.search(normalized):
            return "interface-view"
        if "ospf" in normalized:
            return "ospf-view"
        if "bgp" in normalized:
            return "bgp-view"
        return "system-view"

    @classmethod
    def _entry_command_for_view(cls, view: str) -> str:
        """从目标视图提取必要的进入命令。"""
        interface = cls._INTERFACE_NAME.search(view)
        if interface:
            return f"interface {interface.group(0)}"
        ospf = re.search(r"ospf[-\s]+(\d+)", view, re.IGNORECASE)
        if ospf:
            return f"ospf {ospf.group(1)}"
        bgp = re.search(r"bgp[-\s]+(\d+)", view, re.IGNORECASE)
        if bgp:
            return f"bgp {bgp.group(1)}"
        return ""

    @staticmethod
    def _view_after_command(command: str, current_view: str) -> str:
        """根据视图切换命令推断下一条命令所在视图。"""
        normalized = command.strip().lower()
        if normalized == "system-view":
            return "system-view"
        if normalized.startswith("interface "):
            return "interface-view"
        if normalized.startswith("ospf "):
            return "ospf-view"
        if normalized.startswith("bgp "):
            return "bgp-view"
        if normalized in {"quit", "return"}:
            return "system-view"
        return current_view

    @classmethod
    def _find_interface_ips(
        cls, topology_data: Mapping[str, Any]
    ) -> Iterable[Tuple[str, str, str]]:
        """递归提取拓扑中接口与地址的绑定关系。"""
        def walk(value: Any, path: str, implicit_interface: str = "") -> Iterable[Tuple[str, str, str]]:
            if not isinstance(value, Mapping):
                return
            interface = str(value.get("interface") or "")
            if not interface and cls._INTERFACE_NAME.fullmatch(implicit_interface):
                interface = implicit_interface
            ip_value = value.get("ip") or value.get("ip_address")
            if interface and isinstance(ip_value, str):
                yield interface, ip_value, path
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                next_interface = str(key) if cls._INTERFACE_NAME.fullmatch(str(key)) else interface
                if isinstance(child, Mapping):
                    yield from walk(child, child_path, next_interface)

        yield from walk(topology_data, "topology")

    @staticmethod
    def _blueprint_hash(command_sequence: Sequence[Mapping[str, Any]]) -> str:
        """计算只依赖规范化命令序列的稳定蓝图哈希。"""
        normalized = "\n".join(
            str(step["command"]).strip().lower() for step in command_sequence
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _infer_intent(task_id: str, commands: Sequence[str]) -> str:
        """由任务标识和命令关键词推断配置意图。"""
        context = f"{task_id} {' '.join(commands)}".lower()
        if "ospf" in context:
            return "configure_ospf_backbone"
        if "bgp" in context:
            return "configure_bgp"
        if "vlan" in context:
            return "configure_vlan"
        if "interface" in context or "ip address" in context:
            return "configure_interface"
        return "configure_network_feature"

    @staticmethod
    def _device_requirements(device_info: Mapping[str, Any]) -> List[str]:
        """生成蓝图可执行所需的设备角色和系统要求。"""
        role = str(device_info.get("role") or "network_device")
        return [role, "VRP8+"]

    @staticmethod
    def _applicable_devices(device_info: Mapping[str, Any]) -> List[str]:
        """生成当前成功样本覆盖的设备型号范围。"""
        model = str(device_info.get("model") or "")
        return [model] if model else []

    @staticmethod
    def _preconditions(commands: Sequence[str]) -> List[str]:
        """提取避免重复配置的前置条件。"""
        joined = "\n".join(commands).lower()
        if "ospf" in joined:
            return ["ospf process not configured"]
        if "bgp" in joined:
            return ["bgp process not configured"]
        if "vlan" in joined:
            return ["vlan not configured"]
        return []

    @staticmethod
    def _verification_commands(commands: Sequence[str]) -> List[str]:
        """根据配置协议生成建议的验证命令。"""
        joined = "\n".join(commands).lower()
        if "ospf" in joined:
            return ["display ospf brief"]
        if "bgp" in joined:
            return ["display bgp peer"]
        if "vlan" in joined:
            return ["display vlan"]
        return ["display ip interface brief"]
