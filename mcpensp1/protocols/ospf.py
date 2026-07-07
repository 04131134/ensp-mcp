# -*- coding: utf-8 -*-
"""OSPF 协议插件 — Capability / Generator / Verifier / Recovery"""
from __future__ import annotations
from typing import List, Dict, Any
from ..agent.action_types import ConfigObject, ProtocolCategory


class OSPFPlugin:
    """OSPF 协议插件。"""
    PROTOCOL = "ospf"
    CATEGORY = ProtocolCategory.L3_ROUTING

    @classmethod
    def capability(cls) -> Dict[str, Any]:
        return {
            "protocol": "ospf",
            "supported_devices": ["S5700", "AR2220", "USG6000V"],
            "commands": ["ospf", "area", "network", "router-id", "silent-interface"],
        }

    @classmethod
    def generate_config_objects(cls, params: Dict[str, Any], device: str,
                                start_id: int = 1) -> List[ConfigObject]:
        configs = []
        proc_id = str(params.get("proc_id", 1))
        router_id = params.get("router_id", "")
        areas = params.get("areas", [])

        configs.append(ConfigObject(
            id=f"ospf_{start_id}", action="create_ospf_process",
            target={"proc_id": proc_id, "router_id": router_id},
            device=device, verify={"type": "ospf_process", "proc_id": proc_id},
        ))
        for i, area in enumerate(areas):
            configs.append(ConfigObject(
                id=f"ospf_area_{start_id + i + 1}", action="configure_ospf_area",
                target={"proc_id": proc_id, "area_id": area.get("area_id", "0"),
                        "networks": area.get("networks", [])},
                device=device, preconditions=[f"ospf_{start_id}"],
                verify={"type": "ospf_peer"},
            ))
        return configs

    @classmethod
    def verify_commands(cls, proc_id: str = "1") -> List[str]:
        return ["display ospf peer", "display ip routing-table protocol ospf"]

    @classmethod
    def recovery(cls, error_message: str) -> Dict[str, Any]:
        if "router ID" in error_message.lower() or "router-id" in error_message.lower():
            return {"action": "configure_router_id", "reason": "Need router-id"}
        if "process does not exist" in error_message.lower():
            return {"action": "create_first", "reason": "Need to create OSPF process first"}
        return {"action": "abort", "reason": "Unknown error"}
