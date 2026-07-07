# -*- coding: utf-8 -*-
"""ACL 协议插件 — Capability / Generator / Verifier / Recovery"""
from __future__ import annotations
from typing import List, Dict, Any
from ..agent.action_types import ConfigObject, ProtocolCategory


class ACLPlugin:
    """ACL 协议插件。"""
    PROTOCOL = "acl"
    CATEGORY = ProtocolCategory.SECURITY

    @classmethod
    def capability(cls) -> Dict[str, Any]:
        return {
            "protocol": "acl",
            "supported_devices": ["S5700", "S3700", "AR2220", "USG6000V", "AC6605"],
            "commands": ["acl", "rule", "traffic-filter", "packet-filter"],
        }

    @classmethod
    def generate_config_objects(cls, params: Dict[str, Any], device: str,
                                start_id: int = 1) -> List[ConfigObject]:
        acl_num = str(params.get("acl_num", 3000))
        rules = params.get("rules", [])

        configs = [ConfigObject(
            id=f"acl_{start_id}", action="create_acl",
            target={"acl_num": acl_num, "type": params.get("type", "advanced")},
            device=device, verify={"type": "acl_exists", "acl_num": acl_num},
        )]
        for i, rule in enumerate(rules):
            configs.append(ConfigObject(
                id=f"acl_rule_{start_id + i + 1}", action="add_acl_rule",
                target={"acl_num": acl_num, "rule": rule},
                device=device, preconditions=[f"acl_{start_id}"],
            ))
        return configs

    @classmethod
    def verify_commands(cls, acl_num: str = "3000") -> List[str]:
        return [f"display acl {acl_num}"]

    @classmethod
    def recovery(cls, error_message: str) -> Dict[str, Any]:
        if "already exists" in error_message.lower():
            return {"action": "skip", "reason": "ACL already exists"}
        return {"action": "abort", "reason": "Unknown error"}
