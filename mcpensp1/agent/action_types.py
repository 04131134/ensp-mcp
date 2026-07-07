# -*- coding: utf-8 -*-
"""内部统一 AST — Action / ConfigObject / ProtocolObject。

不要在内部分保存 CLI 字符串，CLI 仅由 CommandGenerator 生成。
"""
from __future__ import annotations
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════

class ActionType(Enum):
    """Action 类型枚举。"""
    # 配置类
    CONFIGURE_INTERFACE = "configure_interface"
    CONFIGURE_VLAN = "configure_vlan"
    CONFIGURE_OSPF = "configure_ospf"
    CONFIGURE_OSPF_AREA = "configure_ospf_area"
    CONFIGURE_ACL = "configure_acl"
    CONFIGURE_AAA = "configure_aaa"
    CONFIGURE_BGP = "configure_bgp"
    CONFIGURE_RIP = "configure_rip"
    CONFIGURE_DHCP = "configure_dhcp"
    CONFIGURE_STATIC_ROUTE = "configure_static_route"
    CONFIGURE_GLOBAL = "configure_global"
    # 验证类
    VERIFY_INTERFACE = "verify_interface"
    VERIFY_VLAN = "verify_vlan"
    VERIFY_OSPF = "verify_ospf"
    VERIFY_OSPF_NEIGHBOR = "verify_ospf_neighbor"
    VERIFY_CONNECTIVITY = "verify_connectivity"
    VERIFY_STP = "verify_stp"
    VERIFY_ACL = "verify_acl"
    VERIFY_BGP = "verify_bgp"
    # 查询类
    DISPLAY = "display"
    PING = "ping"
    TRACERT = "tracert"


class ProtocolCategory(Enum):
    """协议分类。"""
    L2_SWITCHING = "l2_switching"   # VLAN / STP / RSTP / MSTP
    L3_ROUTING = "l3_routing"       # OSPF / BGP / RIP / 静态路由
    SECURITY = "security"            # ACL / 防火墙 / 安全策略
    ACCESS = "access"                # AAA / 802.1X / Portal
    WIRELESS = "wireless"            # WLAN / CAPWAP
    SERVICES = "services"            # DHCP / NAT / VRRP


# ═══════════════════════════════════════════════════════════
# 核心 AST 数据结构
# ═══════════════════════════════════════════════════════════

@dataclass
class ProtocolObject:
    """协议对象 — 表示一个协议的完整配置。

    示例:
        ProtocolObject(
            protocol="ospf",
            proc_id=1,
            router_id="1.1.1.1",
            areas=[{"area_id": "0", "networks": ["10.0.0.0 0.0.0.255"]}],
        )
    """
    protocol: str                                # 协议名: ospf / vlan / acl / bgp
    category: Optional[ProtocolCategory] = None  # 协议分类
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol": self.protocol,
            "category": self.category.value if self.category else None,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ProtocolObject:
        return cls(
            protocol=d["protocol"],
            category=ProtocolCategory(d["category"]) if d.get("category") else None,
            params=d.get("params", {}),
        )


@dataclass
class ConfigObject:
    """配置对象 — 表示一次配置操作的完整语义。

    示例:
        ConfigObject(
            action="create_vlan",
            target={"vlan_id": "10", "description": "Management"},
            device="LSW1",
            verify={"type": "vlan_exists", "vlan_id": "10"},
        )
    """
    id: str = ""                                   # 唯一 ID
    action: str = ""                               # 操作: create_vlan / configure_interface / ...
    target: Dict[str, Any] = field(default_factory=dict)  # 目标参数
    device: str = ""                               # 目标设备
    verify: Dict[str, Any] = field(default_factory=dict)  # 验证规则
    preconditions: List[str] = field(default_factory=list)  # 前置条件 ID 列表
    protocol_objects: List[ProtocolObject] = field(default_factory=list)  # 关联协议对象
    tags: List[str] = field(default_factory=list)  # 标签

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "target": dict(self.target),
            "device": self.device,
            "verify": dict(self.verify),
            "preconditions": list(self.preconditions),
            "protocol_objects": [p.to_dict() for p in self.protocol_objects],
            "tags": list(self.tags),
        }


@dataclass
class ActionNode:
    """Action 执行节点 — Dependency Graph 中的一个节点。

    包含：
    - 配置对象
    - 执行状态
    - 依赖关系
    - 超时/重试设置
    """
    id: str                                   # 唯一标识
    action_type: ActionType                   # Action 类型
    config_object: ConfigObject               # 配置对象
    depends_on: List[str] = field(default_factory=list)  # 依赖的 Action ID
    retry_count: int = 0                      # 当前重试次数
    max_retries: int = 3                      # 最大重试次数
    timeout: float = 60.0                     # 超时（秒）
    status: str = "pending"                   # pending / running / success / failed / skipped

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action_type": self.action_type.value,
            "config_object": self.config_object.to_dict(),
            "depends_on": list(self.depends_on),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
            "status": self.status,
        }


@dataclass
class ActionPlan:
    """Action Plan — Planner 的输出。

    包含 Action 节点列表、依赖图、元信息。
    不包含任何 CLI 字符串。
    """
    plan_id: str = ""                          # 计划 ID
    experiment_type: str = ""                  # 实验类型
    description: str = ""                      # 实验描述
    actions: List[ActionNode] = field(default_factory=list)  # Action 节点列表
    protocol_objects: List[ProtocolObject] = field(default_factory=list)  # 协议对象列表
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元信息

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "experiment_type": self.experiment_type,
            "description": self.description,
            "actions": [a.to_dict() for a in self.actions],
            "protocol_objects": [p.to_dict() for p in self.protocol_objects],
            "metadata": dict(self.metadata),
        }

    def get_action(self, action_id: str) -> Optional[ActionNode]:
        """按 ID 获取 Action。"""
        for a in self.actions:
            if a.id == action_id:
                return a
        return None

    def add_action(self, action: ActionNode) -> None:
        """添加 Action 到计划中。"""
        self.actions.append(action)

    def get_root_actions(self) -> List[ActionNode]:
        """获取根 Action（无依赖）。"""
        return [a for a in self.actions if not a.depends_on]
