# -*- coding: utf-8 -*-
"""BGP 协议插件 — Capability / Generator / Verifier / Recovery"""
from __future__ import annotations
from typing import List, Dict, Any
from ..agent.action_types import ConfigObject, ProtocolCategory


class BGPPlugin:
    """BGP 协议插件。"""
    PROTOCOL = "bgp"
    CATEGORY = ProtocolCategory.L3_ROUTING

    @classmethod
    def capability(cls) -> Dict[str, Any]:
        return {
            "protocol": "bgp",
            "supported_devices": ["S5700", "AR2220", "USG6000V"],
            "commands": ["bgp", "peer", "network", "import-route", "router-id"],
        }

    @classmethod
    def generate_config_objects(cls, params: Dict[str, Any], device: str,
                                start_id: int = 1) -> List[ConfigObject]:
        as_num = str(params.get("as_num", 65001))
        router_id = params.get("router_id", "")
        peers = params.get("peers", [])
        networks = params.get("networks", [])

        configs = [ConfigObject(
            id=f"bgp_{start_id}", action="create_bgp_process",
            target={"as_num": as_num, "router_id": router_id},
            device=device, verify={"type": "bgp_process", "as_num": as_num},
        )]
        for i, peer in enumerate(peers):
            configs.append(ConfigObject(
                id=f"bgp_peer_{start_id + i + 1}", action="configure_bgp_peer",
                target={"as_num": as_num, "peer": peer},
                device=device, preconditions=[f"bgp_{start_id}"],
            ))
        for i, net in enumerate(networks):
            configs.append(ConfigObject(
                id=f"bgp_net_{start_id + len(peers) + i + 1}", action="advertise_bgp_network",
                target={"as_num": as_num, "network": net},
                device=device, preconditions=[f"bgp_{start_id}"],
            ))
        return configs

    @classmethod
    def verify_commands(cls) -> List[str]:
        return ["display bgp peer", "display bgp routing-table"]

    @classmethod
    def recovery(cls, error_message: str) -> Dict[str, Any]:
        if "peer does not exist" in error_message.lower():
            return {"action": "configure_peer", "reason": "Need to configure peer first"}
        return {"action": "abort", "reason": "Unknown error"}
