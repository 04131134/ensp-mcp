# -*- coding: utf-8 -*-
"""能力管理器 — 执行前检查设备型号、支持协议、支持命令、支持特性。

Planner 必须先查询 Capability，禁止生成设备不支持的配置。
"""
from __future__ import annotations
from typing import Dict, Any, Optional, List, Set


# 设备型号能力矩阵
_MODEL_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "S5700": {
        "type": "switch",
        "layer": "L3",
        "protocols": ["vlan", "stp", "rstp", "mstp", "ospf", "rip", "bgp", "dhcp",
                      "dhcp-snooping", "acl", "lacp", "lldp", "igmp", "static-route",
                      "vrrp", "port-security", "snmp"],
        "max_vlans": 4094,
        "supports_stack": True,
        "ports": {"GigabitEthernet": [24, 28, 48, 52], "XGigabitEthernet": [0, 4]},
    },
    "S3700": {
        "type": "switch",
        "layer": "L2+",
        "protocols": ["vlan", "stp", "rstp", "static-route", "dhcp-snooping",
                      "acl", "lacp", "lldp", "port-security"],
        "max_vlans": 4094,
        "supports_stack": True,
        "ports": {"GigabitEthernet": [24, 28, 48], "Ethernet": [0, 24]},
    },
    "AR2220": {
        "type": "router",
        "layer": "L3",
        "protocols": ["ospf", "rip", "bgp", "static-route", "dhcp", "dhcp-server",
                      "acl", "nat", "vrrp", "gre", "ipsec", "snmp", "mpls"],
        "max_vlans": 4094,
        "supports_stack": False,
        "ports": {"GigabitEthernet": [3, 8], "Serial": [0, 4]},
    },
    "USG6000V": {
        "type": "firewall",
        "layer": "L3",
        "protocols": ["ospf", "rip", "bgp", "static-route", "acl", "nat",
                      "vrrp", "ipsec", "gre", "security-policy", "zone"],
        "max_vlans": 256,
        "supports_stack": False,
        "ports": {"GigabitEthernet": [4, 8]},
    },
    "AC6605": {
        "type": "ac",
        "layer": "L3",
        "protocols": ["wlan", "capwap", "vlan", "dhcp", "static-route",
                      "acl", "radius", "portal"],
        "max_vlans": 4094,
        "supports_stack": False,
        "max_aps": 256,
        "ports": {"GigabitEthernet": [2, 4]},
    },
    "AP4050DN": {
        "type": "ap",
        "layer": "L2",
        "protocols": ["wlan", "capwap"],
        "max_vlans": 1,
        "supports_stack": False,
        "ports": {"GigabitEthernet": [1, 2]},
    },
}

# 设备型号名称映射
_MODEL_ALIASES: Dict[str, str] = {
    "s5700": "S5700", "s3700": "S3700", "ar2220": "AR2220",
    "usg6000v": "USG6000V", "ac6605": "AC6605", "ap4050dn": "AP4050DN",
    "switch": "S5700", "router": "AR2220",
    "firewall": "USG6000V", "fw": "USG6000V",
    "ac": "AC6605", "ap": "AP4050DN",
}

# 协议到所需视图的映射
_PROTOCOL_REQUIRED_VIEW: Dict[str, str] = {
    "vlan": "SYSTEM",
    "interface": "SYSTEM",
    "ospf": "OSPF",
    "bgp": "BGP",
    "rip": "RIP",
    "acl": "ACL",
    "aaa": "AAA",
    "dhcp": "SYSTEM",
    "static-route": "SYSTEM",
    "stp": "SYSTEM",
    "rstp": "SYSTEM",
    "mstp": "SYSTEM",
    "vrrp": "SYSTEM",
    "lacp": "INTERFACE",
    "wlan": "SYSTEM",
    "capwap": "SYSTEM",
    "security-policy": "SYSTEM",
    "zone": "SYSTEM",
    "nat": "SYSTEM",
    "ipsec": "SYSTEM",
    "gre": "SYSTEM",
    "port-security": "INTERFACE",
}


class CapabilityManager:
    """设备能力管理器 — Planner 必须查询后才能生成配置。

    用法:
        cm = CapabilityManager()
        result = cm.check("S5700", "ospf")
        if not result["supported"]:
            print(result["reason"])
    """

    def __init__(self):
        """初始化能力管理器。"""
        self._capabilities = dict(_MODEL_CAPABILITIES)

    def get_model_capabilities(self, model: str) -> Optional[Dict[str, Any]]:
        """获取设备型号的完整能力信息。

        参数:
            model: 设备型号（如 "S5700"、"AR2220"）

        返回:
            设备能力字典，或 None
        """
        # 标准化型号名
        normalized = self._normalize_model(model)
        return self._capabilities.get(normalized)

    def check_protocol(self, model: str, protocol: str) -> Dict[str, Any]:
        """检查设备是否支持某协议。

        参数:
            model: 设备型号
            protocol: 协议名称（如 "ospf"、"vlan"、"bgp"）

        返回:
            {
                "supported": bool,
                "model": 标准化后的型号,
                "protocol": 协议,
                "required_view": 协议所需的视图（如果支持）,
                "reason": 不支持的原因（如果不支持）
            }
        """
        caps = self.get_model_capabilities(model)
        normalized = self._normalize_model(model)

        if caps is None:
            return {
                "supported": False,
                "model": normalized,
                "protocol": protocol,
                "required_view": None,
                "reason": f"未知设备型号: {model}",
            }

        supported_protocols = set(p.lower() for p in caps.get("protocols", []))
        if protocol.lower() in supported_protocols:
            return {
                "supported": True,
                "model": normalized,
                "protocol": protocol,
                "required_view": _PROTOCOL_REQUIRED_VIEW.get(protocol.lower(), "SYSTEM"),
                "reason": None,
            }

        return {
            "supported": False,
            "model": normalized,
            "protocol": protocol,
            "required_view": None,
            "reason": f"设备 {normalized} 不支持协议 {protocol}。支持的协议: {caps.get('protocols', [])}",
        }

    def check_commands(self, model: str, commands: List[str]) -> Dict[str, Any]:
        """批量检查命令列表是否被设备支持。

        参数:
            model: 设备型号
            commands: 命令列表

        返回:
            {
                "all_supported": bool,
                "supported": [...],
                "blocked": [...],
                "warnings": [...]
            }
        """
        result: Dict[str, Any] = {
            "all_supported": True,
            "supported": [],
            "blocked": [],
            "warnings": [],
        }

        caps = self.get_model_capabilities(model)
        if caps is None:
            result["all_supported"] = False
            result["blocked"] = commands
            result["warnings"].append(f"未知设备型号: {model}")
            return result

        from mcpensp1.command_executor import is_blocked_command
        for cmd in commands:
            cmd_lower = cmd.strip().lower()
            if is_blocked_command(cmd_lower):
                result["blocked"].append({"command": cmd, "reason": "危险命令被拦截"})
                result["all_supported"] = False
            else:
                result["supported"].append(cmd)

        return result

    def get_supported_protocols(self, model: str) -> List[str]:
        """获取设备支持的所有协议列表。"""
        caps = self.get_model_capabilities(model)
        if caps is None:
            return []
        return list(caps.get("protocols", []))

    def get_device_type(self, model: str) -> str:
        """获取设备类型。"""
        caps = self.get_model_capabilities(model)
        return caps["type"] if caps else "unknown"

    def suggest_model_for_protocol(self, protocol: str) -> List[str]:
        """推荐支持指定协议的设备型号列表。"""
        results = []
        for model, caps in self._capabilities.items():
            supported = [p.lower() for p in caps.get("protocols", [])]
            if protocol.lower() in supported:
                results.append(model)
        return results

    def _normalize_model(self, model: str) -> str:
        """标准化设备型号名。"""
        return _MODEL_ALIASES.get(model.lower(), model.upper())

    def reload_capabilities(self, capabilities: Optional[Dict[str, Any]] = None):
        """热加载能力数据（用于运行时更新）。"""
        if capabilities:
            self._capabilities = capabilities
        else:
            self._capabilities = dict(_MODEL_CAPABILITIES)
