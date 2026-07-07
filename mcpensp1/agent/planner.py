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
    """DAG Execution Planner - now generates actual CLI commands."""

    def __init__(self):
        self._templates: Dict[str, Dict[str, Any]] = self._load_default_templates()

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

        self._add_verification_nodes(plan, variables)
        self._set_recovery_strategies(plan)
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
