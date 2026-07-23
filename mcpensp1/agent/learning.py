# -*- coding: utf-8 -*-
"""
自主学习引擎

功能：
- 从成功实验中抽取经验
- 从失败实验中生成排障案例
- 自动更新知识库和记忆
- 识别可模板化的实验模式
- 学习命令成功率和设备能力
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from .types import (
    ExperimentResult, ReflectionEntry, MemoryEntry, KnowledgeRecord,
)

logger = logging.getLogger(__name__)

# eNSP 平台默认设备类型（eNSP 仅模拟华为设备）。
# 提取为常量消除魔法字符串散落，_infer_device_type 预留多厂商扩展口。
DEFAULT_DEVICE_TYPE = 'huawei'


class LearningEngine:
    """自主学习引擎"""

    def __init__(self, memory_store, knowledge_store):
        """
        Args:
            memory_store: MemoryStore 实例
            knowledge_store: KnowledgeStore 实例
        """
        self._memory = memory_store
        self._knowledge = knowledge_store

    def _infer_device_type(self, result: ExperimentResult) -> str:
        """从实验结果推断设备类型。

        当前 ExperimentResult 未携带设备型号字段，eNSP 平台默认 huawei。
        未来 runtime 填充 result.device_models 后，此处可优先取实际型号。
        """
        # TODO(第二阶段后续): 当 ExperimentResult 增加 device_models 字段后，
        #   优先 return result.device_models[0] if result.device_models else DEFAULT_DEVICE_TYPE
        return DEFAULT_DEVICE_TYPE

    def _extract_verify_commands(self, vr) -> List[str]:
        """从验证结果提取实际使用的命令，兜底用检查名。

        VerificationResult 不直接存命令，但 verifier 可能把命令放进 evidence。
        若 evidence 无命令，用 check_name 作为标识（避免 record_verify_method 传空 commands）。
        """
        if vr.evidence:
            cmd = vr.evidence.get('command') or vr.evidence.get('commands')
            if isinstance(cmd, list) and cmd:
                return [str(c) for c in cmd]
            if isinstance(cmd, str) and cmd:
                return [cmd]
        return [vr.check_name]

    def learn_from_experiment(self, result: ExperimentResult, reflection: ReflectionEntry) -> Dict[str, int]:
        """从实验结果中学习"""
        stats = {'memory_created': 0, 'knowledge_created': 0}

        # 1. 学习经验教训 → 记忆
        for lesson in reflection.lessons_learned:
            self._memory.add(MemoryEntry(
                category='lesson',
                content=lesson,
                tags=['auto-learned', result.experiment_id],
                importance=0.7,
                experiment_id=result.experiment_id,
            ))
            stats['memory_created'] += 1

        # 2. 学习推荐命令 → 记忆
        for cmd in reflection.recommended_commands:
            self._memory.add(MemoryEntry(
                category='command',
                content=f"验证有效: {cmd}",
                tags=['verified', 'auto-learned'],
                importance=0.8,
                experiment_id=result.experiment_id,
            ))
            stats['memory_created'] += 1

        # 3. 记录成功案例 → 知识库
        if result.success and result.plan:
            success_cmds = []
            for node in result.plan.nodes.values():
                if node.status == 'success' and node.commands:
                    success_cmds.extend(node.commands)
            if success_cmds:
                self._knowledge.record_success(
                    commands=success_cmds,
                    device_type=self._infer_device_type(result),
                    experiment_type=result.experiment_id,
                    context={'plan_id': result.plan.plan_id},
                )
                stats['knowledge_created'] += 1

        # 4. 记录失败案例 → 知识库
        if result.plan:
            for node in result.plan.nodes.values():
                if node.status == 'failed' and node.commands:
                    self._knowledge.record_failure(
                        failed_command=node.commands[0] if node.commands else '',
                        error_message=str(node.result)[:200] if node.result else '未知错误',
                        device_type=self._infer_device_type(result),
                        experiment_type=result.experiment_id,
                    )
                    stats['knowledge_created'] += 1

        # 5. 记录配置顺序 → 知识库
        if result.success and result.plan:
            config_nodes = [
                n for n in result.plan.nodes.values()
                if n.status == 'success' and n.node_type.value == 'config'
            ]
            if len(config_nodes) > 1:
                steps = [{'name': n.label, 'node_id': n.node_id} for n in config_nodes]
                self._knowledge.record_config_order(
                    experiment_type=result.experiment_id,
                    steps=steps,
                )
                stats['knowledge_created'] += 1

        # 6. 记录验证方法 → 知识库
        for vr in result.verification_results:
            if vr.passed:
                self._knowledge.record_verify_method(
                    protocol=vr.check_name,
                    commands=self._extract_verify_commands(vr),
                    expected=vr.detail,
                )
                stats['knowledge_created'] += 1

        # 7. 学习失败模式 → 记忆
        for vr in result.verification_results:
            if not vr.passed:
                self._memory.add(MemoryEntry(
                    category='error',
                    content=f"验证失败: {vr.check_name} - {vr.detail}",
                    tags=['verification-failure', 'auto-learned'],
                    importance=0.6,
                    experiment_id=result.experiment_id,
                ))
                if vr.suggestions:
                    self._memory.add(MemoryEntry(
                        category='troubleshoot',
                        content=f"排障建议 ({vr.check_name}): {'; '.join(vr.suggestions[:3])}",
                        tags=['troubleshoot', 'auto-learned'],
                        importance=0.7,
                        experiment_id=result.experiment_id,
                    ))
                stats['memory_created'] += 1

        # 8. 识别可模板化的实验
        if result.success and result.plan and len(result.plan.nodes) >= 3:
            self._suggest_template(result)
            stats['knowledge_created'] += 1

        logger.info('[Learning] 学习完成: 记忆+%d, 知识+%d',
                     stats['memory_created'], stats['knowledge_created'])
        return stats

    def _suggest_template(self, result: ExperimentResult):
        """从成功实验中提取模板"""
        if not result.plan:
            return
        config_nodes = [
            n for n in result.plan.nodes.values()
            if n.status == 'success' and n.node_type.value == 'config'
        ]
        if len(config_nodes) < 2:
            return

        phases = []
        for node in config_nodes:
            phases.append({
                'id': node.node_id,
                'name': node.label,
                'commands': node.commands,
                'dependencies': node.dependencies,
            })

        self._knowledge.record_experiment_template(
            name=f"实验模板: {result.experiment_id}",
            description=f"从成功实验 {result.experiment_id} 自动提取",
            phases=phases,
        )

    def daily_review(self) -> Dict[str, Any]:
        """每日回顾（可定期调用）"""
        # 清理过时记忆
        cleaned = self._memory.cleanup_stale(max_age_days=90, min_importance=0.2)

        # 统计
        memory_stats = self._memory.get_stats()
        knowledge_stats = self._knowledge.get_stats()

        return {
            'memory_cleaned': cleaned,
            'memory_stats': memory_stats,
            'knowledge_stats': knowledge_stats,
        }
