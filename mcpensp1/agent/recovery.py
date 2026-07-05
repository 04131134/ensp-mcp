# -*- coding: utf-8 -*-
"""
自动恢复引擎

功能：
- 验证失败时自动分析原因
- 基于知识库查找修复方案
- 重新规划并执行
- 最多 3 轮修复尝试
- 仍失败时生成完整诊断报告
"""
from __future__ import annotations
import logging
from typing import Any, Callable, Dict, List, Optional
from .types import ExecutionPlan, PlanNode, VerificationResult, RecoveryStrategy

logger = logging.getLogger(__name__)


class RecoveryEngine:
    """自动恢复引擎"""

    MAX_REPAIR_ROUNDS = 3

    # 常见错误模式和修复策略
    ERROR_PATTERNS = {
        'unrecognized command': {
            'cause': '命令不在当前视图',
            'fix': '检查并切换到正确视图',
            'strategy': RecoveryStrategy.RETRY,
            'suggested_commands': ['system-view'],
        },
        'the vlan does not exist': {
            'cause': 'VLAN 未创建',
            'fix': '先创建 VLAN',
            'strategy': RecoveryStrategy.RETRY,
            'suggested_commands': ['vlan {vlan_id}'],
        },
        'the interface does not exist': {
            'cause': '接口不存在或名称错误',
            'fix': '检查接口名称拼写',
            'strategy': RecoveryStrategy.RETRY,
        },
        'error: invalid': {
            'cause': '参数无效',
            'fix': '检查命令参数',
            'strategy': RecoveryStrategy.RETRY,
        },
        'neighbor state not full': {
            'cause': 'OSPF 邻居未建立',
            'fix': '检查 Area ID、网络类型、Hello Timer',
            'strategy': RecoveryStrategy.RETRY,
        },
        'timeout': {
            'cause': '操作超时',
            'fix': '等待后重试',
            'strategy': RecoveryStrategy.RETRY,
        },
        'insufficient resources': {
            'cause': '资源不足',
            'fix': '清理不需要的配置后重试',
            'strategy': RecoveryStrategy.ALTERNATIVE,
        },
    }

    def __init__(
        self,
        command_executor: Callable[[str, str], Dict[str, Any]],
        knowledge_search: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
    ):
        self._exec_cmd = command_executor
        self._search_kb = knowledge_search

    def analyze_failure(
        self,
        node: PlanNode,
        error_output: str,
        verification_results: Optional[List[VerificationResult]] = None,
    ) -> Dict[str, Any]:
        """分析失败原因"""
        error_lower = error_output.lower().strip()
        analysis = {
            'node_id': node.node_id,
            'original_commands': node.commands,
            'error_output': error_output[:500],
            'matched_patterns': [],
            'suggested_fixes': [],
            'kb_references': [],
            'confidence': 0.0,
        }

        # 1. 模式匹配
        for pattern, info in self.ERROR_PATTERNS.items():
            if pattern in error_lower:
                analysis['matched_patterns'].append({
                    'pattern': pattern,
                    'cause': info['cause'],
                    'fix': info['fix'],
                })
                if 'suggested_commands' in info:
                    analysis['suggested_fixes'].extend(info['suggested_commands'])
                analysis['confidence'] = max(analysis['confidence'], 0.8)

        # 2. 搜索知识库
        if self._search_kb:
            try:
                kb_results = self._search_kb(error_output[:100])
                for rec in kb_results[:3]:
                    if rec.get('category') == 'troubleshoot':
                        solution = rec.get('content', {}).get('solution', [])
                        if solution:
                            analysis['suggested_fixes'].extend(solution)
                            analysis['confidence'] = max(analysis['confidence'], 0.7)
                    analysis['kb_references'].append(rec.get('title', ''))
            except Exception:
                pass

        # 3. 基于验证结果分析
        if verification_results:
            for vr in verification_results:
                if not vr.passed and vr.suggestions:
                    analysis['suggested_fixes'].extend(vr.suggestions)

        # 去重
        analysis['suggested_fixes'] = list(dict.fromkeys(analysis['suggested_fixes']))

        if not analysis['matched_patterns'] and not analysis['suggested_fixes']:
            analysis['confidence'] = 0.3
            analysis['suggested_fixes'] = ['检查设备当前配置', '确认命令语法正确']

        return analysis

    def attempt_recovery(
        self,
        plan: ExecutionPlan,
        failed_node_id: str,
        device_path: str,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """尝试恢复"""
        node = plan.nodes.get(failed_node_id)
        if not node:
            return {'success': False, 'error': '节点不存在'}

        node.retry_count += 1
        if node.retry_count > self.MAX_REPAIR_ROUNDS:
            return {
                'success': False,
                'error': f'已达到最大修复轮次 ({self.MAX_REPAIR_ROUNDS})',
                'analysis': analysis,
                'diagnostic_report': self._generate_diagnostic_report(node, analysis),
            }

        # 尝试修复命令
        fix_commands = self._generate_fix_commands(node, analysis)
        if not fix_commands:
            return {'success': False, 'error': '无法生成修复命令', 'analysis': analysis}

        logger.info('[Recovery] 第 %d 轮修复: %s', node.retry_count, fix_commands)

        # 执行修复命令
        results = []
        for cmd in fix_commands:
            resp = self._exec_cmd(device_path, cmd)
            results.append({'command': cmd, 'success': resp.get('success', False), 'output': resp.get('output', '')})

        # 重新执行原始命令
        original_results = []
        for cmd in node.commands:
            resp = self._exec_cmd(device_path, cmd)
            original_results.append({'command': cmd, 'success': resp.get('success', False), 'output': resp.get('output', '')})

        all_success = all(r['success'] for r in original_results)
        return {
            'success': all_success,
            'round': node.retry_count,
            'fix_results': results,
            'retry_results': original_results,
            'analysis': analysis,
        }

    def _generate_fix_commands(self, node: PlanNode, analysis: Dict[str, Any]) -> List[str]:
        """生成修复命令"""
        commands = []
        # 1. 使用分析中建议的修复命令
        for fix_cmd in analysis.get('suggested_fixes', []):
            if fix_cmd.startswith(('undo', 'display', 'system-view', 'vlan', 'interface')):
                commands.append(fix_cmd)

        # 2. 使用节点自带的恢复命令
        if node.recovery_commands:
            commands.extend(node.recovery_commands)

        # 3. 默认恢复：先退回用户视图再重试
        if not commands:
            commands = ['return', 'system-view']

        return commands[:5]  # 最多 5 条修复命令

    def _generate_diagnostic_report(self, node: PlanNode, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成完整诊断报告"""
        return {
            'title': f'诊断报告: {node.label}',
            'node_id': node.node_id,
            'attempted_commands': node.commands,
            'retry_count': node.retry_count,
            'error_analysis': analysis,
            'conclusion': f'经过 {node.retry_count} 轮修复尝试，节点 "{node.label}" 仍未能成功执行。',
            'recommendations': [
                '检查 eNSP 设备是否正常运行',
                '检查设备型号是否支持相关命令',
                '检查当前视图是否正确',
                '手动执行命令确认具体错误',
                '参考知识库中的排障案例',
            ],
        }

    def generate_full_diagnostic(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """生成整个实验的完整诊断报告"""
        failed_nodes = [n for n in plan.nodes.values() if n.status == 'failed']
        return {
            'experiment_id': plan.experiment_id,
            'plan_status': plan.status,
            'total_nodes': len(plan.nodes),
            'failed_nodes': len(failed_nodes),
            'failed_details': [
                {
                    'node_id': n.node_id,
                    'label': n.label,
                    'commands': n.commands,
                    'retry_count': n.retry_count,
                    'result': n.result,
                }
                for n in failed_nodes
            ],
            'conclusion': f'实验 {plan.experiment_id} 共 {len(plan.nodes)} 步，{len(failed_nodes)} 步失败。',
            'next_steps': [
                '查看每个失败节点的详细错误信息',
                '检查设备连接状态',
                '确认实验拓扑和 IP 规划',
                '参考知识库中的相关实验模板',
            ],
        }
