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
    """实验反思引擎

    v3.1 增强（第二阶段 Step9）:
    - set_error_library(): 注入 ErrorLibrary 后，对失败节点关联错误原因做因果分析
    - 输出结构化因果（cause/fix/confidence）而非纯字符串拼接
    - 开关 causal_reflection，未注入 error_library 时回退原有行为
    """

    def __init__(self):
        self._error_library = None
        self.causal_reflection: bool = True

    def set_error_library(self, lib) -> None:
        """注入 ErrorLibrary 实例，启用失败节点因果分析。传 None 关闭。"""
        self._error_library = lib

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

        # 2.5 因果分析：关联 error_library 解释失败节点原因（Step9）
        causes = self._analyze_failure_causes(result)
        for cause in causes:
            reflection.what_went_wrong.append(cause['summary'])
            if cause.get('fix'):
                reflection.optimization_suggestions.append(cause['fix'])

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

    def _analyze_failure_causes(self, result: ExperimentResult) -> List[Dict[str, Any]]:
        """对失败节点关联 error_library 进行因果分析（Step9）。

        遍历 plan 中 status=failed 的节点，提取 error 文本查 error_library，
        命中则返回结构化因果 {node_id, summary, fix, confidence}。
        开关 causal_reflection=False / error_library 未注入 / 查询异常 → 返回空列表。
        """
        causes: List[Dict[str, Any]] = []
        if not self.causal_reflection or not self._error_library:
            return causes
        if not result.plan:
            return causes
        for node in result.plan.nodes.values():
            if node.status != 'failed' or not node.result:
                continue
            # 从 node.result 提取错误文本
            if isinstance(node.result, dict):
                error_text = str(node.result.get('error', '') or node.result.get('commands', ''))
            else:
                error_text = str(node.result)
            if not error_text or error_text == '[]':
                continue
            try:
                lookup = self._error_library.lookup(error_text)
                if lookup.get('found'):
                    cause = lookup.get('cause', '未知原因')
                    fix = lookup.get('fix')
                    confidence = lookup.get('confidence', 0.5)
                    summary = f"节点 {node.label} 失败原因: {cause}"
                    causes.append({
                        'node_id': node.node_id,
                        'summary': summary,
                        'fix': f"修复建议({node.node_id}): {fix}" if fix else None,
                        'confidence': confidence,
                    })
                    logger.info(
                        '[Reflection] 因果分析: 节点 %s → %s (confidence=%.2f)',
                        node.node_id, cause, confidence,
                    )
            except Exception as e:
                logger.warning('[Reflection] error_library 查询异常 (%s): %s', node.node_id, e)
        return causes
