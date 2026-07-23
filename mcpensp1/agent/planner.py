# -*- coding: utf-8 -*-
"""
DAG Execution Planner with CLI Command Templates - FIXED

Key fix: Nodes now carry actual Huawei CLI commands, not just labels.
"""
from __future__ import annotations
import re
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple
from .types import (
    ExecutionPlan, PlanNode, NodeType, RecoveryStrategy,
    TaskGoal, KnowledgeRecord,
)

logger = logging.getLogger(__name__)


# ==================== PROTOCOL DEPENDENCIES ====================

PROTOCOL_DEPENDENCIES = {
    'vlan': {'prerequisites': [], 'creates': ['vlan_id'], 'description': 'VLAN Creation'},
    'interface': {'prerequisites': ['vlan'], 'creates': ['interface_ip'], 'description': 'Interface IP Config'},
    'vlanif': {'prerequisites': ['vlan'], 'creates': ['vlanif_ip'], 'description': 'VLANIF Interface Config'},
    'trunk': {'prerequisites': ['vlan'], 'creates': ['trunk_link'], 'description': 'Trunk Port Config'},
    'access': {'prerequisites': ['vlan'], 'creates': ['access_link'], 'description': 'Access Port Config'},
    'dhcp': {'prerequisites': ['vlanif'], 'creates': ['dhcp_pool'], 'description': 'DHCP Pool Config'},
    'ospf': {'prerequisites': ['interface', 'vlanif'], 'creates': ['ospf_process'], 'description': 'OSPF Routing'},
    'bgp': {'prerequisites': ['interface'], 'creates': ['bgp_process'], 'description': 'BGP Routing'},
    'vrrp': {'prerequisites': ['vlanif'], 'creates': ['vrrp_group'], 'description': 'VRRP Redundancy'},
    'mstp': {'prerequisites': ['vlan'], 'creates': ['mstp_region'], 'description': 'MSTP Spanning Tree'},
    'acl': {'prerequisites': [], 'creates': ['acl_rule'], 'description': 'ACL Rules'},
    'nat': {'prerequisites': ['interface'], 'creates': ['nat_rule'], 'description': 'NAT Translation'},
    'ipsec': {'prerequisites': ['interface'], 'creates': ['ipsec_sa'], 'description': 'IPSec VPN'},
    'static_route': {'prerequisites': ['interface'], 'creates': ['static_route'], 'description': 'Static Routing'},
    'rip': {'prerequisites': ['interface'], 'creates': ['rip_process'], 'description': 'RIP Routing'},
}


# ==================== CLI COMMAND TEMPLATES (CRITICAL FIX) ====================
# Each protocol maps to Huawei VRP CLI commands with {variable} placeholders.
# Variables are resolved at runtime from goal.variables or defaults.

COMMAND_TEMPLATES: Dict[str, Dict[str, Any]] = {
    'vlan': {
        'commands': ['vlan {vlan_id}', 'quit'],
        'default_vars': {'vlan_id': '10'},
    },
    'access': {
        'commands': ['interface {port}', 'port link-type access', 'port default vlan {vlan_id}', 'quit'],
        'default_vars': {'port': 'GE0/0/1', 'vlan_id': '10'},
    },
    'trunk': {
        'commands': ['interface {port}', 'port link-type trunk', 'port trunk allow-pass vlan {vlan_list}', 'quit'],
        'default_vars': {'port': 'GE0/0/24', 'vlan_list': 'all'},
    },
    'vlanif': {
        'commands': ['interface Vlanif {vlan_id}', 'ip address {ip} {mask}', 'quit'],
        'default_vars': {'vlan_id': '10', 'ip': '192.168.10.1', 'mask': '255.255.255.0'},
    },
    'interface': {
        'commands': ['interface {port}', 'ip address {ip} {mask}', 'quit'],
        'default_vars': {'port': 'GE0/0/1', 'ip': '10.0.0.1', 'mask': '255.255.255.0'},
    },
    'dhcp': {
        'commands': [
            'ip pool {pool_name}', 'network {network} mask {mask}',
            'gateway-list {gateway}', 'quit',
        ],
        'default_vars': {'pool_name': 'pool10', 'network': '192.168.10.0', 'mask': '255.255.255.0', 'gateway': '192.168.10.1'},
    },
    'ospf': {
        'commands': ['ospf {process_id} router-id {router_id}', 'area {area_id}', 'network {network} {wildcard}', 'quit', 'quit'],
        'default_vars': {'process_id': '1', 'router_id': '1.1.1.1', 'area_id': '0', 'network': '192.168.10.0', 'wildcard': '0.0.0.255'},
    },
    'bgp': {
        'commands': ['bgp {local_as}', 'peer {peer_ip} as-number {peer_as}', 'quit'],
        'default_vars': {'local_as': '65001', 'peer_ip': '10.0.0.2', 'peer_as': '65002'},
    },
    'vrrp': {
        'commands': ['interface Vlanif {vlan_id}', 'vrrp vrid {vrid} virtual-ip {virtual_ip}', 'vrrp vrid {vrid} priority {priority}', 'quit'],
        'default_vars': {'vlan_id': '10', 'vrid': '1', 'virtual_ip': '192.168.10.254', 'priority': '120'},
    },
    'mstp': {
        'commands': ['stp region-configuration', 'region-name {region_name}', 'revision-level {revision}', 'instance {instance} vlan {vlan_list}', 'active region-configuration', 'quit'],
        'default_vars': {'region_name': 'mstp-region', 'revision': '1', 'instance': '1', 'vlan_list': '10'},
    },
    'acl': {
        'commands': ['acl number {acl_id}', 'rule {rule_id} permit source {source} {wildcard}', 'quit'],
        'default_vars': {'acl_id': '3001', 'rule_id': '5', 'source': '192.168.10.0', 'wildcard': '0.0.0.255'},
    },
    'nat': {
        'commands': ['interface {port}', 'nat outbound {acl_id}', 'quit'],
        'default_vars': {'port': 'GE0/0/0', 'acl_id': '3001'},
    },
    'ipsec': {
        'commands': [
            'ike proposal {ike_proposal}', 'quit',
            'ike peer {ike_peer}', 'pre-shared-key cipher {psk}', 'remote-address {remote_ip}', 'quit',
            'ipsec proposal {ipsec_proposal}', 'quit',
            'ipsec policy {policy_name} {seq} isakmp', 'security acl {acl_id}', 'ike-peer {ike_peer}', 'quit',
        ],
        'default_vars': {'ike_proposal': '1', 'ike_peer': 'peer1', 'psk': 'Admin@123', 'remote_ip': '10.0.0.2', 'ipsec_proposal': 'prop1', 'policy_name': 'map1', 'seq': '1', 'acl_id': '3001'},
    },
    'static_route': {
        'commands': ['ip route-static {dest} {mask} {next_hop}'],
        'default_vars': {'dest': '192.168.20.0', 'mask': '255.255.255.0', 'next_hop': '10.0.0.2'},
    },
    'rip': {
        'commands': ['rip {process_id}', 'network {network}', 'version 2', 'quit'],
        'default_vars': {'process_id': '1', 'network': '192.168.10.0'},
    },
    'connectivity': {
        'commands': ['ping {target_ip}'],
        'default_vars': {'target_ip': '192.168.20.1'},
    },
}


# ==================== VERIFY COMMANDS ====================

VERIFY_COMMANDS = {
    'vlan': ['display vlan'],
    'interface': ['display ip interface brief'],
    'vlanif': ['display ip interface brief'],
    'trunk': ['display port vlan'],
    'access': ['display port vlan'],
    'dhcp': ['display ip pool'],
    'ospf': ['display ospf peer brief'],
    'bgp': ['display bgp peer'],
    'vrrp': ['display vrrp brief'],
    'mstp': ['display stp brief'],
    'acl': ['display acl all'],
    'nat': ['display nat session'],
    'ipsec': ['display ipsec sa'],
    'static_route': ['display ip routing-table'],
    'rip': ['display rip'],
    'connectivity': ['ping {target_ip}'],
}


def _resolve_commands(template_key: str, variables: Optional[Dict[str, str]] = None) -> List[str]:
    """Resolve CLI commands from template, filling in variables."""
    tmpl = COMMAND_TEMPLATES.get(template_key)
    if not tmpl:
        return []
    merged_vars = dict(tmpl.get('default_vars', {}))
    if variables:
        merged_vars.update(variables)
    commands = []
    for cmd in tmpl['commands']:
        try:
            commands.append(cmd.format(**merged_vars))
        except KeyError:
            commands.append(cmd)
    return commands


def _resolve_verify_commands(protocol: str, variables: Optional[Dict[str, str]] = None) -> List[str]:
    """Resolve verification commands for a protocol."""
    cmds = VERIFY_COMMANDS.get(protocol, ['display current-configuration'])
    if not variables:
        return cmds
    resolved = []
    for cmd in cmds:
        try:
            resolved.append(cmd.format(**variables))
        except KeyError:
            resolved.append(cmd)
    return resolved


class DAGPlanner:
    """DAG Execution Planner - now generates actual CLI commands.

    v3.1 增强（第二阶段，经验/能力驱动）:
    - set_knowledge_store(): 注入知识库后，plan_from_goal 优先用成功经验覆盖模板命令
    - set_capability_manager(): 注入能力管理器后，校验设备是否支持目标协议
    - 两项均通过开关控制，默认开启但依赖注入；未注入时回退原有模板行为（向后兼容）
    """

    def __init__(self):
        self._templates: Dict[str, Dict[str, Any]] = self._load_default_templates()
        # 第二阶段：经验/能力驱动（可选注入，None 时回退模板行为）
        self._knowledge_store = None
        self._capability_manager = None
        self.use_experience: bool = True    # 开关：经验覆盖命令
        self.check_capability: bool = True  # 开关：能力校验
        # 批次1：结构化命令库（可选注入）
        self._knowledge_base = None
        self.use_structured_kb: bool = True  # 开关：结构化命令增强
        self._experience_applied_nodes: set = set()  # 追踪被经验覆盖的节点（不重复覆盖）

    def set_knowledge_store(self, store) -> None:
        """注入 KnowledgeStore 实例，启用经验驱动命令生成。

        注入后 plan_from_goal 会检索 success_case，命中则用经验命令覆盖模板命令。
        传 None 关闭经验覆盖（回退纯模板行为）。
        """
        self._knowledge_store = store

    def set_capability_manager(self, cm) -> None:
        """注入 CapabilityManager 实例，启用设备能力校验。

        注入后 plan_from_goal 会校验目标协议是否被设备支持，不支持仅 log warning（不阻塞）。
        传 None 关闭能力校验。
        """
        self._capability_manager = cm

    def set_knowledge_base(self, kb) -> None:
        """注入 KnowledgeBase 实例，启用结构化命令增强（批次1）。

        plan_from_goal 会调用 suggest_commands 查询设备型号对应的配置命令，
        增强未被经验覆盖的 ConfigNode。传 None 关闭结构化命令增强。
        """
        self._knowledge_base = kb

    def _load_default_templates(self) -> Dict[str, Dict[str, Any]]:
        return {
            'campus': {
                'name': 'Campus Network',
                'description': 'Three-layer campus network',
                'phases': [
                    {'id': 'vlan', 'name': 'Create VLANs', 'protocol': 'vlan', 'type': 'config'},
                    {'id': 'access', 'name': 'Access Ports', 'protocol': 'access', 'type': 'config', 'depends': ['vlan']},
                    {'id': 'trunk', 'name': 'Trunk Ports', 'protocol': 'trunk', 'type': 'config', 'depends': ['vlan']},
                    {'id': 'vlanif', 'name': 'VLANIF Interfaces', 'protocol': 'vlanif', 'type': 'config', 'depends': ['vlan']},
                    {'id': 'dhcp', 'name': 'DHCP Pool', 'protocol': 'dhcp', 'type': 'config', 'depends': ['vlanif']},
                    {'id': 'ospf', 'name': 'OSPF Routing', 'protocol': 'ospf', 'type': 'config', 'depends': ['vlanif']},
                    {'id': 'vrrp', 'name': 'VRRP', 'protocol': 'vrrp', 'type': 'config', 'depends': ['vlanif']},
                    {'id': 'mstp', 'name': 'MSTP', 'protocol': 'mstp', 'type': 'config', 'depends': ['vlan']},
                    {'id': 'verify', 'name': 'Verification', 'protocol': 'connectivity', 'type': 'verify', 'depends': ['ospf', 'dhcp']},
                ],
            },
            'ospf_area': {
                'name': 'OSPF Multi-Area',
                'phases': [
                    {'id': 'interface', 'name': 'Interface IP', 'protocol': 'interface', 'type': 'config'},
                    {'id': 'ospf', 'name': 'OSPF Config', 'protocol': 'ospf', 'type': 'config', 'depends': ['interface']},
                    {'id': 'verify', 'name': 'Verify OSPF', 'protocol': 'ospf', 'type': 'verify', 'depends': ['ospf']},
                ],
            },
            'bgp': {
                'name': 'BGP Peering',
                'phases': [
                    {'id': 'interface', 'name': 'Interface IP', 'protocol': 'interface', 'type': 'config'},
                    {'id': 'ospf_underlay', 'name': 'OSPF Underlay', 'protocol': 'ospf', 'type': 'config', 'depends': ['interface']},
                    {'id': 'bgp', 'name': 'BGP Config', 'protocol': 'bgp', 'type': 'config', 'depends': ['ospf_underlay']},
                    {'id': 'verify', 'name': 'Verify BGP', 'protocol': 'bgp', 'type': 'verify', 'depends': ['bgp']},
                ],
            },
            'vpn': {
                'name': 'IPSec VPN',
                'phases': [
                    {'id': 'interface', 'name': 'Interface IP', 'protocol': 'interface', 'type': 'config'},
                    {'id': 'static_route', 'name': 'Static Route', 'protocol': 'static_route', 'type': 'config', 'depends': ['interface']},
                    {'id': 'acl', 'name': 'ACL', 'protocol': 'acl', 'type': 'config'},
                    {'id': 'ipsec', 'name': 'IPSec', 'protocol': 'ipsec', 'type': 'config', 'depends': ['acl', 'static_route']},
                    {'id': 'verify', 'name': 'Verify VPN', 'protocol': 'ipsec', 'type': 'verify', 'depends': ['ipsec']},
                ],
            },
            'basic_routing': {
                'name': 'Basic Routing',
                'phases': [
                    {'id': 'interface', 'name': 'Interface IP', 'protocol': 'interface', 'type': 'config'},
                    {'id': 'static_route', 'name': 'Static Route', 'protocol': 'static_route', 'type': 'config', 'depends': ['interface']},
                    {'id': 'verify', 'name': 'Verify Routing', 'protocol': 'static_route', 'type': 'verify', 'depends': ['static_route']},
                ],
            },
        }

    def plan_from_goal(
        self,
        goal: TaskGoal,
        knowledge_context: Optional[Dict[str, Any]] = None,
        devices: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        plan = ExecutionPlan(experiment_id=goal.description[:20], goal=goal)
        # Extract variables: explicit constraints take priority, then auto-extract from text
        variables = self._extract_variables(goal.description, knowledge_context)
        if goal.constraints and isinstance(goal.constraints[0], dict):
            variables.update(goal.constraints[0])  # explicit constraints override auto-extracted

        template = self._match_template(goal)
        if template:
            logger.info('[Planner] Matched template: %s', template['name'])
            plan = self._plan_from_template(template, goal, devices, variables)
        else:
            plan = self._plan_from_analysis(goal, knowledge_context, devices, variables)

        # 第二阶段：经验驱动 — 用知识库成功经验覆盖模板命令（开关 use_experience）
        self._experience_applied_nodes.clear()
        self._apply_experience(plan, goal)

        # 批次1：结构化命令增强 — 用 structured_commands_kb 增强未被经验覆盖的节点（开关 use_structured_kb）
        self._enrich_with_structured_kb(plan, devices)

        self._add_verification_nodes(plan, variables)
        self._set_recovery_strategies(plan)

        # 第二阶段：能力驱动 — 校验设备是否支持目标协议（开关 check_capability，不阻塞）
        self._check_capabilities(self._extract_protocols(goal.description), devices)

        plan.status = 'ready'
        logger.info('[Planner] Plan: %d nodes, order: %s', len(plan.nodes), plan.execution_order)
        return plan

    def _match_template(self, goal: TaskGoal) -> Optional[Dict[str, Any]]:
        desc_lower = goal.description.lower()
        keyword_map = {
            'campus': ['campus', 'teaching', 'admin', 'access layer', 'aggregation', 'core layer',
                       '\u6821\u56ed', '\u6559\u5b66\u697c', '\u884c\u653f\u697c', '\u63a5\u5165\u5c42', '\u6c47\u805a\u5c42', '\u6838\u5fc3\u5c42'],
            'ospf_area': ['ospf', 'multi-area', 'area', 'route summarization',
                          '\u591a\u533a\u57df', '\u8def\u7531\u6c47\u603b'],
            'bgp': ['bgp', 'as', 'autonomous', '\u81ea\u6cbb\u7cfb\u7edf'],
            'vpn': ['vpn', 'ipsec', 'tunnel', '\u96a7\u9053', '\u7ad9\u70b9\u5230\u7ad9\u70b9'],
            'basic_routing': ['static route', 'routing', 'route',
                              '\u9759\u6001\u8def\u7531', '\u8def\u7531\u4e92\u901a', '\u57fa\u7840\u8def\u7531'],
        }
        best_match, best_score = None, 0
        for tmpl_id, keywords in keyword_map.items():
            score = sum(1 for kw in keywords if kw in desc_lower)
            if score > best_score:
                best_score = score
                best_match = tmpl_id
        if best_match and best_score >= 1:
            return self._templates.get(best_match)
        return None

    def _plan_from_template(
        self, template: Dict[str, Any], goal: TaskGoal,
        devices: Optional[Dict[str, Any]], variables: Dict[str, str],
    ) -> ExecutionPlan:
        plan = ExecutionPlan(goal=goal)
        for phase in template['phases']:
            proto = phase.get('protocol', phase['id'])
            is_verify = phase.get('type') == 'verify'
            if is_verify:
                cmds = _resolve_verify_commands(proto, variables)
            else:
                cmds = _resolve_commands(proto, variables)
            node = PlanNode(
                node_id=phase['id'],
                label=phase['name'],
                node_type=NodeType.VERIFY if is_verify else NodeType.CONFIG,
                commands=cmds,
                dependencies=phase.get('depends', []),
                verify_commands=_resolve_verify_commands(proto, variables) if not is_verify else [],
            )
            plan.add_node(node)
        return plan

    def _plan_from_analysis(
        self, goal: TaskGoal, knowledge_context: Optional[Dict[str, Any]],
        devices: Optional[Dict[str, Any]], variables: Dict[str, str],
    ) -> ExecutionPlan:
        plan = ExecutionPlan(goal=goal)
        protocols = self._extract_protocols(goal.description)
        logger.info('[Planner] Protocols: %s', protocols)

        created_nodes = set()
        for proto in protocols:
            deps = PROTOCOL_DEPENDENCIES.get(proto, {})
            for prereq in deps.get('prerequisites', []):
                if prereq not in created_nodes and prereq in PROTOCOL_DEPENDENCIES:
                    cmds = _resolve_commands(prereq, variables)
                    plan.add_node(PlanNode(
                        node_id=prereq,
                        label=PROTOCOL_DEPENDENCIES[prereq]['description'],
                        node_type=NodeType.CONFIG,
                        commands=cmds,
                        verify_commands=_resolve_verify_commands(prereq, variables),
                    ))
                    created_nodes.add(prereq)
            if proto not in created_nodes:
                prereq_ids = [p for p in deps.get('prerequisites', []) if p in created_nodes]
                cmds = _resolve_commands(proto, variables)
                plan.add_node(PlanNode(
                    node_id=proto,
                    label=deps.get('description', f'{proto} Config'),
                    node_type=NodeType.CONFIG,
                    commands=cmds,
                    dependencies=prereq_ids,
                    verify_commands=_resolve_verify_commands(proto, variables),
                ))
                created_nodes.add(proto)

        return plan

    def _extract_protocols(self, description: str) -> List[str]:
        desc_lower = description.lower()
        protocols = []
        keyword_to_protocol = {
            'vlan': 'vlan', 'trunk': 'trunk', 'access': 'access',
            'dhcp': 'dhcp', 'ospf': 'ospf', 'bgp': 'bgp',
            'vrrp': 'vrrp', 'mstp': 'mstp', 'stp': 'mstp',
            'acl': 'acl', 'nat': 'nat', 'ipsec': 'ipsec', 'vpn': 'ipsec',
            'rip': 'rip', 'vlanif': 'vlanif', 'svi': 'vlanif',
        }
        # Static route detection (longer match first)
        if 'static' in desc_lower and 'route' in desc_lower:
            protocols.append('static_route')
        for keyword, proto in keyword_to_protocol.items():
            if keyword in desc_lower and proto not in protocols:
                protocols.append(proto)
        if not protocols:
            protocols = ['vlan', 'interface']
        return protocols

    def _extract_variables(self, description: str, knowledge_context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Extract real configuration variables from user request text.
        
        Parses IPs, VLAN IDs, port names, masks, areas, etc. from natural language
        so the planner generates actual commands instead of generic placeholders.
        """
        variables = {}

        # Extract IPv4 addresses
        ips = re.findall(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', description)
        if ips:
            variables['all_ips'] = ips
            # First IP is often the gateway or router-id
            if len(ips) >= 1:
                variables['ip'] = ips[0]
            if len(ips) >= 2:
                variables['gateway'] = ips[0]
                variables['target_ip'] = ips[-1]

        # Extract subnet masks (dotted or CIDR)
        masks = re.findall(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', description)
        cidr = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/(\d{1,2})\b', description)
        if cidr:
            variables['cidr'] = cidr[0]
            # Convert first CIDR to wildcard mask
            prefix = int(cidr[0])
            host_bits = 32 - prefix
            wildcard_int = (1 << host_bits) - 1
            variables['wildcard'] = f'{(wildcard_int >> 24) & 0xFF}.{(wildcard_int >> 16) & 0xFF}.{(wildcard_int >> 8) & 0xFF}.{wildcard_int & 0xFF}'

        # Extract VLAN IDs
        vlan_matches = re.findall(r'[Vv][Ll][Aa][Nn]\s*(\d+)', description)
        if vlan_matches:
            variables['vlan_id'] = vlan_matches[0]
            if len(vlan_matches) > 1:
                variables['vlan_list'] = ','.join(vlan_matches)

        # Extract port names (GE0/0/X, Eth0/0/X, etc.)
        ports = re.findall(r'\b(GE\d+/\d+/\d+|Eth\d+/\d+/\d+|XGE\d+/\d+/\d+)\b', description, re.IGNORECASE)
        if ports:
            variables['port'] = ports[0]
            if len(ports) > 1:
                variables['ports'] = ports

        # Extract OSPF area
        area_match = re.search(r'[Aa]rea\s*(\d+)', description)
        if area_match:
            variables['area_id'] = area_match.group(1)

        # Extract router-id
        rid_match = re.search(r'[Rr]outer[- ]?[Ii][Dd]\s+(\S+)', description)
        if rid_match:
            variables['router_id'] = rid_match.group(1)

        # Extract AS numbers
        as_match = re.search(r'[Aa][Ss]\s*(\d+)', description)
        if as_match:
            variables['local_as'] = as_match.group(1)

        # Extract pool names
        pool_match = re.search(r'[Pp]ool\s+(\S+)', description)
        if pool_match:
            variables['pool_name'] = pool_match.group(1)

        # Merge with knowledge context if available
        if knowledge_context:
            for key, val in knowledge_context.items():
                if key not in variables and isinstance(val, str):
                    variables[key] = val

        return variables

    def _add_verification_nodes(self, plan: ExecutionPlan, variables: Dict[str, str] = None):
        config_nodes = [n for n in plan.nodes.values() if n.node_type == NodeType.CONFIG]
        has_verify = any(n.node_type == NodeType.VERIFY for n in plan.nodes.values())
        if has_verify or not config_nodes:
            return
        verify_cmds = ['display ip interface brief', 'display ip routing-table']
        if variables:
            try:
                verify_cmds.append(f'ping {variables.get("target_ip", "192.168.20.1")}')
            except Exception:
                verify_cmds.append('ping 192.168.20.1')
        plan.add_node(PlanNode(
            node_id='final_verify',
            label='Comprehensive Verification',
            node_type=NodeType.VERIFY,
            dependencies=[n.node_id for n in config_nodes],
            commands=verify_cmds,
        ))

    def _set_recovery_strategies(self, plan: ExecutionPlan):
        for node in plan.nodes.values():
            if node.node_type == NodeType.VERIFY:
                continue
            node.recovery_strategy = RecoveryStrategy.RETRY

    def _apply_experience(self, plan: ExecutionPlan, goal: TaskGoal) -> None:
        """用知识库成功经验覆盖模板命令（经验驱动）。

        检索 knowledge_store 的 success_case，若某 experiment_type 有高置信度经验，
        则用经验命令覆盖对应 ConfigNode 的 commands。
        开关 use_experience=False / store 未注入 / 检索异常 → 静默回退模板行为。
        """
        if not self.use_experience or not self._knowledge_store:
            return
        try:
            results = self._knowledge_store.query_for_task(goal.description)
        except Exception as e:
            logger.warning('[Planner] 经验检索失败，回退模板: %s', e)
            return
        success_cases = results.get('success_cases', []) if isinstance(results, dict) else []
        if not success_cases:
            return
        # 建立 experiment_type / protocol -> 经验命令 映射
        exp_cmds_by_key: Dict[str, List[str]] = {}
        for rec in success_cases:
            content = rec.content if isinstance(rec.content, dict) else {}
            cmds = content.get('commands')
            exp_type = content.get('experiment_type', '') or getattr(rec, 'protocol', '')
            if cmds and exp_type:
                exp_cmds_by_key[exp_type] = list(cmds)
        if not exp_cmds_by_key:
            return
        # 覆盖 config 节点命令（节点 id 通常对应 protocol 或 experiment_type）
        applied = 0
        for node in plan.nodes.values():
            if node.node_type != NodeType.CONFIG:
                continue
            exp_cmds = exp_cmds_by_key.get(node.node_id)
            if exp_cmds:
                node.commands = list(exp_cmds)
                applied += 1
                self._experience_applied_nodes.add(node.node_id)
                logger.info('[Planner] 节点 %s 用经验命令覆盖 (%d 条)', node.node_id, len(node.commands))
        if applied:
            logger.info('[Planner] 经验驱动: 覆盖 %d 个节点的命令', applied)

    def _enrich_with_structured_kb(
        self, plan: ExecutionPlan, devices: Optional[Dict[str, Any]],
    ) -> None:
        """用 structured_commands_kb 增强命令候选（批次1，优先级 P1）。

        调用 suggest_commands(device_model, 'system_view') 获取设备型号对应的配置命令，
        按 function 名称模糊匹配 plan 的 ConfigNode，为未被经验覆盖的节点提供命令。

        只增强，不覆盖：
        - 已被 _apply_experience 覆盖的节点 → 跳过（保留经验+上下文）
        - VerifyNode / 已有丰富 verify_commands 的节点 → 跳过
        - 结构化 KB 未命中 → 跳过后续 COMMAND_TEMPLATES 兜底

        开关 use_structured_kb=False / kb 未注入 / devices 无型号 → 静默跳过。
        """
        if not self.use_structured_kb or not self._knowledge_base:
            return
        if not devices:
            return
        device_model = devices.get('model') if isinstance(devices, dict) else None
        if not device_model:
            return

        try:
            result = self._knowledge_base.suggest_commands(device_model, 'system_view')
        except Exception as e:
            logger.warning('[Planner] structured_kb 查询失败，降级模板: %s', e)
            return

        sv_cmds = result.get('system_view', [])
        if not sv_cmds:
            return

        # 按 function 分组: {function_name: [cmd_text, ...]}
        func_cmds: Dict[str, List[str]] = {}
        for c in sv_cmds:
            fn = c.get('group', '')
            cmd_text = c.get('cmd', '')
            if fn and cmd_text:
                func_cmds.setdefault(fn, []).append(cmd_text)

        if not func_cmds:
            return

        # 模糊匹配 plan 的 ConfigNode
        applied = 0
        for node in plan.nodes.values():
            if node.node_type != NodeType.CONFIG:
                continue
            # 跳过已被经验覆盖的节点（保留经验命令+上下文）
            if node.node_id in self._experience_applied_nodes:
                continue

            # 匹配: node_id 或 label 与 function 名模糊匹配
            matched_cmds = self._match_structured_commands(node.node_id, node.label, func_cmds)
            if matched_cmds:
                # 保留原有 verify_commands（结构化 KB 不覆盖验证命令）
                node.commands = list(matched_cmds)
                applied += 1
                logger.info(
                    '[Planner] structured_kb 增强节点 %s (%d 条命令)',
                    node.node_id, len(node.commands),
                )

        if applied:
            logger.info('[Planner] structured_kb 增强 %d 个节点', applied)

    @staticmethod
    def _match_structured_commands(
        node_id: str, label: str, func_cmds: Dict[str, List[str]],
    ) -> Optional[List[str]]:
        """模糊匹配 plan 节点 ID/标签到 structured_kb 的 function 名。

        匹配规则（子串双向匹配，不区分大小写）:
            node_id='vlan', func_name='VLAN'       → True
            node_id='ospf', func_name='OSPF路由'   → True
            node_id='interface', func_name='接口配置' → True
            node_id='bgp', func_name='BGP路由'     → True
            label='VLAN Config', func_name='VLAN'  → True
        """
        nk = node_id.lower()
        nl = label.lower()
        for fn_name, cmds in func_cmds.items():
            fl = fn_name.lower()
            # 双向子串匹配
            if nk in fl or fl in nk or nl in fl or fl in nl:
                return cmds
        return None

    def _check_capabilities(
        self, protocols: List[str], devices: Optional[Dict[str, Any]],
    ) -> None:
        """校验设备是否支持目标协议（能力驱动，不阻塞）。

        需 devices 含设备型号信息（dict 形如 {'model': 'S5700'} 或 {'models': [...]}）。
        当前 runtime 未传 devices，故默认跳过；未来 runtime 传入型号后自动生效。
        开关 check_capability=False / cm 未注入 / devices 缺型号 → 跳过。
        不支持的协议仅 log warning，不抛异常（避免破坏现有流程）。
        """
        if not self.check_capability or not self._capability_manager:
            return
        if not devices or not protocols:
            return
        # 从 devices 提取型号（兼容多种结构）
        models: List[str] = []
        if isinstance(devices, dict):
            models = devices.get('models') or ([devices.get('model')] if devices.get('model') else [])
        models = [m for m in models if m]
        if not models:
            return
        for model in models:
            for proto in protocols:
                try:
                    result = self._capability_manager.check_protocol(model, proto)
                    if not result.get('supported'):
                        logger.warning(
                            '[Planner] 能力校验: 设备 %s 不支持协议 %s — %s',
                            model, proto, result.get('reason'),
                        )
                except Exception as e:
                    logger.warning('[Planner] 能力校验异常 %s/%s: %s', model, proto, e)

    def update_plan_after_failure(
        self, plan: ExecutionPlan, failed_node_id: str, error_info: Dict[str, Any],
    ) -> ExecutionPlan:
        failed_node = plan.nodes.get(failed_node_id)
        if not failed_node:
            return plan
        failed_node.retry_count += 1
        if failed_node.retry_count >= failed_node.max_retries:
            failed_node.status = 'failed'
            for node in plan.nodes.values():
                if failed_node_id in node.dependencies:
                    node.status = 'skipped'
        else:
            failed_node.status = 'pending'
        return plan

    def get_plan_summary(self, plan: ExecutionPlan) -> str:
        lines = [f'## Execution Plan ({len(plan.nodes)} steps)\n']
        for i, nid in enumerate(plan.execution_order, 1):
            node = plan.nodes[nid]
            icon = "V" if node.node_type == NodeType.VERIFY else "C"
            lines.append(f'{i}. [{icon}] {node.label} ({len(node.commands)} cmds)')
        return '\n'.join(lines)
