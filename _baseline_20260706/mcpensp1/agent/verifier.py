# -*- coding: utf-8 -*-
"""
语义化验证引擎

功能：
- 自动执行 display/show 命令获取设备状态
- 语义化解析输出（非简单字符串匹配）
- 自动判断配置是否成功
- 返回结构化验证结果
- 支持多协议联合验证
"""
from __future__ import annotations
import re
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from .types import VerificationResult

logger = logging.getLogger(__name__)


class SemanticVerifier:
    """语义化验证引擎"""

    def __init__(self, command_executor: Callable[[str, str], Dict[str, Any]]):
        """
        Args:
            command_executor: 命令执行函数 (device_path, command) -> {'success': bool, 'output': str}
        """
        self._exec_cmd = command_executor

    def verify_all(self, device_path: str, target_ip: Optional[str] = None) -> List[VerificationResult]:
        """执行全面验证"""
        results = []
        results.extend(self.verify_interfaces(device_path))
        results.extend(self.verify_vlans(device_path))
        results.extend(self.verify_routing(device_path))
        results.extend(self.verify_ospf(device_path))
        results.extend(self.verify_stp(device_path))
        results.extend(self.verify_acl(device_path))
        if target_ip:
            results.extend(self.verify_connectivity(device_path, target_ip))
        return results

    def verify_interfaces(self, device_path: str) -> VerificationResult:
        """验证接口状态"""
        resp = self._exec_cmd(device_path, 'display ip interface brief')
        if not resp.get('success'):
            return VerificationResult(
                check_name='interface_status',
                passed=False,
                detail='无法获取接口信息',
                actual=resp.get('output', ''),
            )
        output = resp.get('output', '')
        interfaces = self._parse_ip_brief(output)
        up_count = sum(1 for iface in interfaces if iface.get('status', '').lower() == 'up')
        total = len(interfaces)
        passed = up_count > 0
        return VerificationResult(
            check_name='interface_status',
            passed=passed,
            detail=f'{up_count}/{total} 接口 UP',
            evidence={'interfaces': interfaces, 'up_count': up_count, 'total': total},
            expected='至少一个接口 UP',
            actual=f'{up_count} 个接口 UP',
        )

    def verify_vlans(self, device_path: str) -> VerificationResult:
        """验证 VLAN 配置"""
        resp = self._exec_cmd(device_path, 'display vlan')
        if not resp.get('success'):
            return VerificationResult(
                check_name='vlan_config',
                passed=False,
                detail='无法获取 VLAN 信息',
                actual=resp.get('output', ''),
            )
        output = resp.get('output', '')
        vlans = self._parse_vlan(output)
        passed = len(vlans) > 0
        return VerificationResult(
            check_name='vlan_config',
            passed=passed,
            detail=f'已配置 {len(vlans)} 个 VLAN',
            evidence={'vlans': vlans, 'count': len(vlans)},
            expected='VLAN 已创建',
            actual=f'{len(vlans)} 个 VLAN',
        )

    def verify_routing(self, device_path: str) -> VerificationResult:
        """验证路由表"""
        resp = self._exec_cmd(device_path, 'display ip routing-table')
        if not resp.get('success'):
            return VerificationResult(
                check_name='routing_table',
                passed=False,
                detail='无法获取路由表',
                actual=resp.get('output', ''),
            )
        output = resp.get('output', '')
        routes = self._parse_routing_table(output)
        # 分类路由
        by_proto: Dict[str, int] = {}
        for r in routes:
            proto = r.get('protocol', 'Unknown')
            by_proto[proto] = by_proto.get(proto, 0) + 1
        passed = len(routes) > 0
        return VerificationResult(
            check_name='routing_table',
            passed=passed,
            detail=f'路由表有 {len(routes)} 条路由',
            evidence={'routes_count': len(routes), 'by_protocol': by_proto},
            expected='有路由条目',
            actual=f'{len(routes)} 条路由',
        )

    def verify_ospf(self, device_path: str) -> VerificationResult:
        """验证 OSPF 邻居"""
        resp = self._exec_cmd(device_path, 'display ospf peer brief')
        if not resp.get('success'):
            return VerificationResult(
                check_name='ospf_neighbor',
                passed=False,
                detail='无法获取 OSPF 邻居信息（可能未配置 OSPF）',
                actual=resp.get('output', ''),
                confidence=0.5,
            )
        output = resp.get('output', '')
        peers = self._parse_ospf_peer(output)
        full_peers = [p for p in peers if 'full' in p.get('state', '').lower()]
        passed = len(full_peers) > 0
        return VerificationResult(
            check_name='ospf_neighbor',
            passed=passed,
            detail=f'OSPF 邻居: {len(full_peers)}/{len(peers)} Full',
            evidence={'peers': peers, 'full_count': len(full_peers), 'total_count': len(peers)},
            expected='OSPF 邻居状态 Full',
            actual=f'{len(full_peers)} 个 Full 邻居',
            suggestions=[] if passed else [
                '检查两端 Area ID 是否一致',
                '检查 Hello/Dead Timer 是否匹配',
                '检查网络类型是否一致',
                '检查接口 IP 是否在同一网段',
            ] if peers else ['未发现 OSPF 邻居，检查 OSPF 是否已配置'],
        )

    def verify_stp(self, device_path: str) -> VerificationResult:
        """验证 STP/MSTP"""
        resp = self._exec_cmd(device_path, 'display stp brief')
        if not resp.get('success'):
            return VerificationResult(
                check_name='stp_status',
                passed=False,
                detail='无法获取 STP 信息',
                actual=resp.get('output', ''),
                confidence=0.5,
            )
        output = resp.get('output', '')
        stp_info = self._parse_stp_brief(output)
        passed = bool(stp_info)
        return VerificationResult(
            check_name='stp_status',
            passed=passed,
            detail='STP 已激活',
            evidence={'stp_info': stp_info},
            expected='STP 运行正常',
            actual='STP 已激活' if passed else 'STP 未激活',
        )

    def verify_acl(self, device_path: str) -> VerificationResult:
        """验证 ACL"""
        resp = self._exec_cmd(device_path, 'display acl all')
        if not resp.get('success'):
            return VerificationResult(
                check_name='acl_config',
                passed=False,
                detail='无法获取 ACL 信息',
                actual=resp.get('output', ''),
                confidence=0.5,
            )
        output = resp.get('output', '')
        has_acl = 'rule' in output.lower() or 'acl' in output.lower()
        return VerificationResult(
            check_name='acl_config',
            passed=has_acl,
            detail='ACL 已配置' if has_acl else '未发现 ACL 规则',
            evidence={'has_rules': has_acl},
        )

    def verify_connectivity(self, device_path: str, target_ip: str) -> VerificationResult:
        """验证连通性"""
        resp = self._exec_cmd(device_path, f'ping {target_ip}')
        if not resp.get('success'):
            return VerificationResult(
                check_name='connectivity',
                passed=False,
                detail=f'Ping {target_ip} 命令执行失败',
                actual=resp.get('output', ''),
            )
        output = resp.get('output', '')
        # 解析 ping 结果
        loss_match = re.search(r'(\d+)%\s*(?:packet\s*)?loss', output)
        loss_rate = int(loss_match.group(1)) if loss_match else 100
        rtt_match = re.search(r'(?:avg|average)\s*=?\s*(\d+)', output)
        avg_rtt = int(rtt_match.group(1)) if rtt_match else None
        passed = loss_rate < 100
        return VerificationResult(
            check_name='connectivity',
            passed=passed,
            detail=f'Ping {target_ip}: 丢包率 {loss_rate}%' + (f', 平均 RTT {avg_rtt}ms' if avg_rtt else ''),
            evidence={'target': target_ip, 'loss_rate': loss_rate, 'avg_rtt': avg_rtt},
            expected='Ping 成功（丢包率 0%）',
            actual=f'丢包率 {loss_rate}%',
            suggestions=[] if passed else [
                '检查路由表是否有到目标的路由',
                '检查 ACL 是否阻止了 ICMP',
                '检查中间设备配置',
                '逐跳 ping 定位断点',
            ],
        )

    def verify_custom(self, device_path: str, check_name: str, verify_commands: List[str], expected_pattern: str = "") -> VerificationResult:
        """自定义验证"""
        all_outputs = []
        for cmd in verify_commands:
            resp = self._exec_cmd(device_path, cmd)
            all_outputs.append({'command': cmd, 'success': resp.get('success', False), 'output': resp.get('output', '')})

        if expected_pattern:
            pattern = re.compile(expected_pattern, re.IGNORECASE)
            for out in all_outputs:
                if pattern.search(out.get('output', '')):
                    return VerificationResult(
                        check_name=check_name,
                        passed=True,
                        detail=f'匹配预期模式: {expected_pattern}',
                        evidence={'outputs': all_outputs},
                    )
            return VerificationResult(
                check_name=check_name,
                passed=False,
                detail=f'未匹配预期模式: {expected_pattern}',
                evidence={'outputs': all_outputs},
            )

        # 无预期模式时，检查命令是否成功执行
        all_ok = all(out.get('success') for out in all_outputs)
        return VerificationResult(
            check_name=check_name,
            passed=all_ok,
            detail='所有验证命令执行成功' if all_ok else '部分验证命令执行失败',
            evidence={'outputs': all_outputs},
        )

    def quick_verify(self, device_path: str, check_type: str, **kwargs) -> VerificationResult:
        """快速验证（兼容旧接口）"""
        dispatch = {
            'interface': lambda: self.verify_interfaces(device_path),
            'vlan': lambda: self.verify_vlans(device_path),
            'route': lambda: self.verify_routing(device_path),
            'routing': lambda: self.verify_routing(device_path),
            'ospf': lambda: self.verify_ospf(device_path),
            'stp': lambda: self.verify_stp(device_path),
            'acl': lambda: self.verify_acl(device_path),
            'ping': lambda: self.verify_connectivity(device_path, kwargs.get('target_ip', '127.0.0.1')),
        }
        handler = dispatch.get(check_type)
        if handler:
            return handler()
        return VerificationResult(
            check_name=check_type,
            passed=False,
            detail=f'未知验证类型: {check_type}',
        )

    # ==================== 输出解析器 ====================

    @staticmethod
    def _parse_ip_brief(output: str) -> List[Dict[str, str]]:
        """解析 display ip interface brief 输出"""
        interfaces = []
        for line in output.splitlines():
            line = line.strip()
            if not line or 'Interface' in line or '---' in line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                iface = {'name': parts[0]}
                # 查找 IP 地址
                for part in parts[1:]:
                    if re.match(r'\d+\.\d+\.\d+\.\d+', part):
                        iface['ip'] = part
                    elif part.lower() in ('up', 'down', '*down'):
                        iface['status'] = part
                    elif part.lower() in ('up',):
                        iface['protocol'] = part
                if 'ip' not in iface:
                    iface['ip'] = '*'
                if 'status' not in iface:
                    iface['status'] = parts[-1] if parts[-1].lower() in ('up', 'down', '*down') else 'unknown'
                interfaces.append(iface)
        return interfaces

    @staticmethod
    def _parse_vlan(output: str) -> List[Dict[str, Any]]:
        """解析 display vlan 输出"""
        vlans = []
        current_vlan = None
        for line in output.splitlines():
            s = line.strip()
            m = re.match(r'^(\d+)\s', s)
            if m:
                if current_vlan:
                    vlans.append(current_vlan)
                current_vlan = {'vlan_id': int(m.group(1)), 'ports': []}
                # 提取端口
                ports_str = s[m.end():].strip()
                if ports_str:
                    current_vlan['ports'] = [p.strip() for p in ports_str.split() if p.strip()]
            elif current_vlan and s and not s.startswith('---'):
                # 续行的端口
                current_vlan['ports'].extend([p.strip() for p in s.split() if p.strip()])
        if current_vlan:
            vlans.append(current_vlan)
        return vlans

    @staticmethod
    def _parse_routing_table(output: str) -> List[Dict[str, str]]:
        """解析 display ip routing-table 输出"""
        routes = []
        for line in output.splitlines():
            s = line.strip()
            if not s or s.startswith('---') or 'Destination' in s or 'Routing Table' in s:
                continue
            # 匹配路由条目
            m = re.match(r'^(\S+)\s+(\S+)\s+(\S+)', s)
            if m:
                routes.append({
                    'destination': m.group(1),
                    'protocol': m.group(2),
                    'nexthop': m.group(3),
                })
        return routes

    @staticmethod
    def _parse_ospf_peer(output: str) -> List[Dict[str, str]]:
        """解析 display ospf peer brief 输出"""
        peers = []
        for line in output.splitlines():
            s = line.strip()
            if not s or 'Peer' in s or '---' in s or 'OSPF' in s:
                continue
            parts = s.split()
            if len(parts) >= 4:
                peers.append({
                    'area': parts[0],
                    'interface': parts[1],
                    'neighbor_id': parts[2],
                    'state': parts[3],
                })
        return peers

    @staticmethod
    def _parse_stp_brief(output: str) -> Dict[str, Any]:
        """解析 display stp brief 输出"""
        info: Dict[str, Any] = {'ports': []}
        for line in output.splitlines():
            s = line.strip()
            if 'CIST Root' in s or 'Root Bridge' in s:
                info['root_bridge'] = s
            elif 'MSTI' in s:
                info['msti'] = s
            elif s and not s.startswith('---') and 'Interface' not in s:
                parts = s.split()
                if len(parts) >= 3:
                    info['ports'].append({
                        'name': parts[0],
                        'role': parts[1] if len(parts) > 1 else '',
                        'state': parts[2] if len(parts) > 2 else '',
                    })
        return info
