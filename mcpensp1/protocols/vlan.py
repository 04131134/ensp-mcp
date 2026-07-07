# -*- coding: utf-8 -*-
"""VLAN 协议插件 — Capability / Generator / Verifier / Recovery"""
from __future__ import annotations
from typing import List, Dict, Any
from ..agent.action_types import ActionType, ConfigObject, ProtocolObject, ProtocolCategory


class VLANPlugin:
    """VLAN 协议插件。"""
    PROTOCOL = "vlan"
    CATEGORY = ProtocolCategory.L2_SWITCHING

    @classmethod
    def capability(cls) -> Dict[str, Any]:
        return {
            "protocol": "vlan",
            "supported_devices": ["S5700", "S3700", "AC6605", "AR2220"],
            "max_vlans": 4094,
            "commands": ["vlan", "port link-type", "port default vlan", "port trunk allow-pass vlan"],
        }

    @classmethod
    def generate_config_objects(cls, params: Dict[str, Any], device: str,
                                start_id: int = 1) -> List[ConfigObject]:
        configs = []
        vid = str(params.get("vlan_id", 10))
        desc = params.get("description", "")
        ports = params.get("ports", [])

        configs.append(ConfigObject(
            id=f"vlan_{start_id}", action="create_vlan",
            target={"vlan_id": vid, "description": desc},
            device=device, verify={"type": "vlan_exists", "vlan_id": vid},
        ))
        for i, port in enumerate(ports):
            configs.append(ConfigObject(
                id=f"vlan_port_{start_id + i + 1}", action="assign_port_vlan",
                target={"port": port, "vlan_id": vid, "mode": params.get("mode", "access")},
                device=device, preconditions=[f"vlan_{start_id}"],
                verify={"type": "port_vlan", "port": port, "vlan_id": vid},
            ))
        return configs

    @classmethod
    def verify_commands(cls, vlan_id: str = "") -> List[str]:
        cmds = ["display vlan"]
        if vlan_id:
            cmds.append(f"display vlan {vlan_id}")
        return cmds

    @classmethod
    def recovery(cls, error_message: str) -> Dict[str, Any]:
        if "already exists" in error_message.lower():
            return {"action": "skip", "reason": "VLAN already exists"}
        if "does not exist" in error_message.lower():
            return {"action": "create_first", "reason": "Need to create VLAN first"}
        return {"action": "abort", "reason": "Unknown error"}
