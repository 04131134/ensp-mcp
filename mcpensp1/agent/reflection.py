# -*- coding: utf-8 -*-
"""
实验反思引擎

功能：
- 实验结束后自动总结
- 分析成功/失败原因
- 提取可复用经验
- 推荐最佳实践
- 生成知识更新建议
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from .types import (
    ExecutionPlan, ExperimentResult, PlanNode, ReflectionEntry,
    VerificationResult,
)

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """实验反思引擎"""

    def reflect(self, result: ExperimentResult) -> ReflectionEntry:
        """对实验结果进行反思"""
        reflection = ReflectionEntry(
            experiment_id=result.experiment_id,
        )

        # 1. 总结成功和失败
        if result.plan:
            for node in result.plan.nodes.values():
                if node.status == 'success':
                    reflection.what_went_well.append(
                        f"成功: {node.label} ({node.node_id})"
                    )
                    # 推荐成功的命令
                    reflection.recommended_commands.extend(node.commands)
                elif node.status == 'failed':
                    reflection.what_went_wrong.append(
                        f"失败: {node.label} ({node.node_id}), 重试 {node.retry_count} 次"
                    )

        # 2. 从验证结果中学习
        for vr in result.verification_results:
            if vr.passed:
                reflection.what_went_well.append(f"验证通过: {vr.check_name} - {vr.detail}")
            else:
                reflection.what_went_wrong.append(f"验证失败: {vr.check_name} - {vr.detail}")
                if vr.suggestions:
                    reflection.optimization_suggestions.extend(vr.suggestions)

        # 3. 提取经验教训
        reflection.lessons_learned = self._extract_lessons(result)

        # 4. 生成知识更新建议
        reflection.knowledge_updates = self._suggest_knowledge_updates(result)

        # 5. 生成摘要
        reflection.summary = self._generate_summary(result, reflection)

        logger.info('[Reflection] 实验 %s 反思完成: %d 条经验, %d 条建议',
                     result.experiment_id,
                     len(reflection.lessons_learned),
                     len(reflection.optimization_suggestions))
        return reflection

    def _extract_lessons(self, result: ExperimentResult) -> List[str]:
        """提取经验教训"""
        lessons = []

        # 成功模式
        if result.success:
            if result.plan:
                success_nodes = [n for n in result.plan.nodes.values() if n.status == 'success']
                config_order = [n.label for n in success_nodes if n.node_type.value == 'config']
                if config_order:
                    lessons.append(f"成功的配置顺序: {' → '.join(config_order)}")

        # 失败模式
        if result.plan:
            failed_nodes = [n for n in result.plan.nodes.values() if n.status == 'failed']
            for node in failed_nodes:
                if node.result and 'error' in str(node.result):
                    lessons.append(f"命令失败经验: {node.label} - 检查依赖和视图")

        # 重试经验
        total_retries = sum(
            n.retry_count for n in result.plan.nodes.values()
        ) if result.plan else 0
        if total_retries > 0:
            lessons.append(f"本次实验共重试 {total_retries} 次，注意检查前置条件")

        # 验证经验
        for vr in result.verification_results:
            if not vr.passed and vr.suggestions:
                lessons.append(f"验证 {vr.check_name} 失败时: {vr.suggestions[0]}")

        return lessons

    def _suggest_knowledge_updates(self, result: ExperimentResult) -> List[Dict[str, Any]]:
        """建议知识库更新"""
        updates = []

        if result.plan:
            # 成功配置序列
            success_cmds = []
            for node in result.plan.nodes.values():
                if node.status == 'success' and node.commands:
                    success_cmds.extend(node.commands)
            if success_cmds:
                updates.append({
                    'category': 'command',
                    'content': f"验证有效的命令序列: {'; '.join(success_cmds[:5])}",
                    'tags': ['verified', 'auto-extracted'],
                    'importance': 0.8,
                })

            # 配置顺序
            config_nodes = [
                n for n in result.plan.nodes.values()
                if n.status == 'success' and n.node_type.value == 'config'
            ]
            if len(config_nodes) > 1:
                updates.append({
                    'category': 'config_order',
                    'content': f"推荐配置顺序: {' → '.join(n.label for n in config_nodes)}",
                    'tags': ['config-order', 'auto-extracted'],
                    'importance': 0.7,
                })

            # 失败案例
            for node in result.plan.nodes.values():
                if node.status == 'failed' and node.result:
                    updates.append({
                        'category': 'error',
                        'content': f"失败案例: {node.label} - {str(node.result)[:200]}",
                        'tags': ['failure', 'auto-extracted'],
                        'importance': 0.6,
                    })

        return updates

    def _generate_summary(self, result: ExperimentResult, reflection: ReflectionEntry) -> str:
        """生成反思摘要"""
        parts = []
        status = "成功 ✅" if result.success else "失败 ❌"
        parts.append(f"实验 {status}")

        if result.plan:
            total = len(result.plan.nodes)
            success = sum(1 for n in result.plan.nodes.values() if n.status == 'success')
            parts.append(f"执行 {success}/{total} 步成功")

        if result.total_commands > 0:
            parts.append(f"共 {result.total_commands} 条命令, {result.successful_commands} 条成功")

        if result.repair_attempts > 0:
            parts.append(f"修复 {result.repair_attempts} 轮")

        if reflection.lessons_learned:
            parts.append(f"总结 {len(reflection.lessons_learned)} 条经验")

        return ', '.join(parts)
