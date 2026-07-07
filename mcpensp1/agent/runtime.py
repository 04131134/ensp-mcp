# -*- coding: utf-8 -*-
"""
Agent Runtime 运行时编排器

核心工作流：
  Receive Task → Understand Goal → Load Memory → Search Knowledge →
  Planning → Execute → Observe → Verify → Repair → Reflect → Update Memory → Finish

每个阶段独立运行，失败时自动进入恢复流程。
"""
from __future__ import annotations
import os
import time
import uuid
import logging
import threading
from typing import Any, Callable, Dict, List, Optional
from .types import (
    TaskPhase, TaskGoal, ExecutionPlan, PlanNode, NodeType,
    ExperimentResult, VerificationResult, ReflectionEntry, MemoryEntry,
)
from .memory import MemoryStore
from .knowledge_store import KnowledgeStore
from .planner import DAGPlanner
from .verifier import SemanticVerifier
from .recovery import RecoveryEngine
from .reflection import ReflectionEngine
from .learning import LearningEngine

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Agent 运行时编排器 - 闭环实验执行"""

    def __init__(
        self,
        data_dir: str,
        command_executor: Callable[[str, str], Dict[str, Any]],
        device_scanner: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        """
        Args:
            data_dir: 数据持久化目录
            command_executor: 命令执行函数 (device_path, command) -> result
            device_scanner: 设备扫描函数 -> {devices: [...]}
        """
        self._data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # 初始化各子系统
        self.memory = MemoryStore(os.path.join(data_dir, 'memory.json'))
        self.knowledge = KnowledgeStore(os.path.join(data_dir, 'knowledge_store.json'))
        self.planner = DAGPlanner()
        
        # 初始化配置方法库（优先级最高）
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from config_method_store import ConfigMethodStore
        self.config_methods = ConfigMethodStore(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'kb'))
        self.verifier = SemanticVerifier(command_executor)
        self.recovery = RecoveryEngine(command_executor)
        self.reflection = ReflectionEngine()
        self.learning = LearningEngine(self.memory, self.knowledge)

        self._exec_cmd = command_executor
        self._scan_devices = device_scanner

        # 活跃实验跟踪
        self._active_experiments: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

        logger.info('[Runtime] Agent Runtime v3.0 初始化完成')

    def execute_task(
        self,
        request: str,
        device_paths: Optional[List[str]] = None,
        experiment_type: str = "general",
        constraints: Optional[List[str]] = None,
    ) -> ExperimentResult:
        """
        执行完整实验任务（闭环）

        工作流：
        1. 理解需求
        2. 加载记忆
        3. 搜索知识
        4. 生成计划
        5. 检查依赖
        6. 执行配置
        7. 观察结果
        8. 验证配置
        9. 修复问题（最多3轮）
        10. 反思总结
        11. 更新记忆
        """
        experiment_id = f"exp_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        logger.info('=== 实验 %s 开始: %s ===', experiment_id, request[:80])

        # 初始化实验结果
        result = ExperimentResult(
            experiment_id=experiment_id,
            success=False,
        )

        try:
            # ========== 阶段 1: 理解需求 ==========
            self._update_phase(experiment_id, TaskPhase.UNDERSTANDING)
            goal = TaskGoal(
                description=request,
                raw_request=request,
                experiment_type=experiment_type,
                constraints=constraints or [],
            )
            result.goal = goal
            logger.info('[阶段1] 理解需求: %s', goal.description[:80])

            # ========== 阶段 2: 加载记忆 ==========
            self._update_phase(experiment_id, TaskPhase.MEMORY_LOAD)
            relevant_memories = self.memory.recall(query=request, limit=10)
            memory_context = self.memory.summarize_for_prompt(query=request)
            logger.info('[阶段2] 加载 %d 条相关记忆', len(relevant_memories))

            # ========== 阶段 2.5: 查询配置方法库（最高优先级） ==========
            self._update_phase(experiment_id, TaskPhase.KNOWLEDGE_SEARCH)
            
            # 提取关键词进行配置方法库查询
            config_method_results = []
            keywords = request.lower().split()
            
            # 搜索配置方法库
            for keyword in keywords:
                if len(keyword) > 1:  # 忽略单字符
                    results = self.config_methods.search_methods(keyword)
                    config_method_results.extend(results)
            
            # 去重
            seen_ids = set()
            unique_methods = []
            for m in config_method_results:
                mid = m.get('id')
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    unique_methods.append(m)
            config_method_results = unique_methods
            
            if config_method_results:
                logger.info('[阶段2.5] 配置方法库命中: %d 个方法', len(config_method_results))
                # 使用最佳匹配的配置方法
                best_method = config_method_results[0]
                logger.info('[阶段2.5] 使用配置方法: %s', best_method.get('name'))
                # 获取标准命令序列
                standard_commands = self.config_methods.get_method_commands(best_method.get('id'))
                logger.info('[阶段2.5] 标准命令序列: %s', standard_commands[:5] if standard_commands else [])
            else:
                logger.info('[阶段2.5] 配置方法库无命中，将查询知识库')
            
            # ========== 阶段 3: 搜索知识库 ==========
            knowledge_context = self.knowledge.query_for_task(request)
            knowledge_summary = self.knowledge.summarize_for_prompt(request)
            logger.info('[阶段3] 知识库检索: %d 个类别命中', len(knowledge_context))

            # ========== 阶段 4: 生成执行计划 ==========
            self._update_phase(experiment_id, TaskPhase.PLANNING)
            plan = self.planner.plan_from_goal(
                goal=goal,
                knowledge_context=knowledge_context,
            )
            result.plan = plan
            plan.experiment_id = experiment_id
            logger.info('[阶段4] 生成计划: %d 步', len(plan.nodes))

            # ========== 阶段 5: 检查依赖 ==========
            self._update_phase(experiment_id, TaskPhase.DEPENDENCY_CHECK)
            # 检查循环依赖
            if self._has_circular_dependency(plan):
                raise RuntimeError('计划存在循环依赖')
            logger.info('[阶段5] 依赖检查通过')

            # ========== 阶段 6-9: 执行 → 验证 → 修复 循环 ==========
            result = self._execute_plan_loop(
                plan=plan,
                device_paths=device_paths or [],
                result=result,
            )

            # ========== 阶段 10: 反思 ==========
            self._update_phase(experiment_id, TaskPhase.REFLECTING)
            reflection = self.reflection.reflect(result)
            result.reflection = reflection
            logger.info('[阶段10] 反思完成: %d 条经验', len(reflection.lessons_learned))

            # ========== 阶段 11: 学习 ==========
            self._update_phase(experiment_id, TaskPhase.LEARNING)
            learning_stats = self.learning.learn_from_experiment(result, reflection)
            result.knowledge_entries_created = learning_stats['knowledge_created']
            result.memory_entries_created = learning_stats['memory_created']
            logger.info('[阶段11] 学习完成: 知识+%d, 记忆+%d',
                        learning_stats['knowledge_created'],
                        learning_stats['memory_created'])

        except Exception as e:
            logger.error('实验 %s 异常: %s', experiment_id, e, exc_info=True)
            result.success = False
            if result.reflection is None:
                result.reflection = ReflectionEntry(
                    experiment_id=experiment_id,
                    summary=f'实验异常终止: {str(e)}',
                    what_went_wrong=[str(e)],
                )

        finally:
            result.duration_seconds = time.time() - start_time
            self._update_phase(experiment_id, TaskPhase.COMPLETED if result.success else TaskPhase.FAILED)
            # 清理活跃实验
            with self._lock:
                self._active_experiments.pop(experiment_id, None)

        logger.info('=== 实验 %s 结束: %s (耗时 %.1f 秒) ===',
                     experiment_id,
                     '成功' if result.success else '失败',
                     result.duration_seconds)
        return result

    def _execute_plan_loop(
        self,
        plan: ExecutionPlan,
        device_paths: List[str],
        result: ExperimentResult,
    ) -> ExperimentResult:
        """执行计划的主循环：执行 → 验证 → 修复"""
        plan.status = 'executing'
        repair_round = 0

        while repair_round <= self.recovery.MAX_REPAIR_ROUNDS:
            # 按拓扑顺序执行
            for node_id in plan.execution_order:
                node = plan.nodes[node_id]
                if node.status in ('success', 'skipped'):
                    continue

                self._update_phase(result.experiment_id, TaskPhase.EXECUTING)

                # 选择设备路径
                device_path = self._select_device(node, device_paths)

                if node.node_type == NodeType.VERIFY:
                    # 验证节点
                    self._execute_verify_node(node, device_path, result)
                else:
                    # 配置节点
                    self._execute_config_node(node, device_path, result)

            # 检查是否全部成功
            if plan.is_complete():
                plan.status = 'completed'
                result.success = True
                break

            # 有失败节点，进入修复流程
            failed_nodes = [n for n in plan.nodes.values() if n.status == 'failed']
            if not failed_nodes:
                break

            repair_round += 1
            result.repair_attempts = repair_round
            self._update_phase(result.experiment_id, TaskPhase.REPAIRING)
            logger.info('[修复] 第 %d 轮, %d 个失败节点', repair_round, len(failed_nodes))

            # 尝试修复
            for node in failed_nodes:
                analysis = self.recovery.analyze_failure(node, str(node.result or ''))
                recovery_result = self.recovery.attempt_recovery(
                    plan=plan,
                    failed_node_id=node.node_id,
                    device_path=self._select_device(node, device_paths),
                    analysis=analysis,
                )
                if recovery_result.get('success'):
                    node.status = 'success'
                    node.result = recovery_result
                    logger.info('[修复] 节点 %s 修复成功', node.node_id)
                else:
                    logger.warning('[修复] 节点 %s 修复失败', node.node_id)

        if not result.success:
            plan.status = 'failed'

        return result

    def _execute_config_node(self, node: PlanNode, device_path: str, result: ExperimentResult):
        """执行配置节点"""
        node.status = 'running'
        logger.info('[执行] %s -> %s', node.label, device_path)

        cmd_results = []
        all_success = True
        for cmd in node.commands:
            resp = self._exec_cmd(device_path, cmd)
            # Fix H4: check cmd_success (actual command result) not just transport success
            output_text = resp.get('output', '')
            cmd_ok = resp.get('cmd_success', resp.get('success', False))
            # Also detect CLI errors in output
            if cmd_ok and ('Error' in output_text[:200] or 'Unrecognized command' in output_text[:200]):
                cmd_ok = False
            cmd_results.append({
                'command': cmd,
                'success': cmd_ok,
                'output': output_text[:200],
            })
            result.total_commands += 1
            if cmd_ok:
                result.successful_commands += 1
            else:
                result.failed_commands += 1
                all_success = False

        if all_success:
            node.status = 'success'
            node.result = {'commands': cmd_results}
        else:
            node.status = 'failed'
            node.result = {'commands': cmd_results, 'error': '部分命令执行失败'}

    def _execute_verify_node(self, node: PlanNode, device_path: str, result: ExperimentResult):
        """执行验证节点"""
        node.status = 'running'
        logger.info('[验证] %s -> %s', node.label, device_path)

        verification_results = []

        if node.verify_commands:
            for cmd in node.verify_commands:
                vr = self.verifier.verify_custom(device_path, node.node_id, [cmd])
                verification_results.append(vr)
        else:
            # 根据节点类型自动选择验证命令
            proto = node.node_id
            vr = self.verifier.quick_verify(device_path, proto)
            verification_results.append(vr)

        result.verification_results.extend(verification_results)
        all_passed = all(vr.passed for vr in verification_results)

        if all_passed:
            node.status = 'success'
            node.result = {'verifications': [vr.to_dict() for vr in verification_results]}
        else:
            node.status = 'failed'
            node.result = {
                'verifications': [vr.to_dict() for vr in verification_results],
                'failed_checks': [vr.check_name for vr in verification_results if not vr.passed],
            }

    def _select_device(self, node: PlanNode, device_paths: List[str]) -> str:
        """选择执行设备"""
        if node.device_path:
            return node.device_path
        if device_paths:
            return device_paths[0]
        return ''


    def _auto_detect_devices(self) -> List[str]:
        """Auto-detect connected device paths by probing the executor."""
        # Try common eNSP port range
        detected = []
        for port in range(2000, 2020):
            path = f'127.0.0.1:{port}'
            try:
                resp = self._exec_cmd(path, 'display version')
                if resp.get('success') and resp.get('output'):
                    detected.append(path)
            except Exception:
                pass
        return detected

    def _has_circular_dependency(self, plan: ExecutionPlan) -> bool:
        """检查循环依赖"""
        visited = set()
        path = set()

        def dfs(nid: str) -> bool:
            if nid in path:
                return True
            if nid in visited:
                return False
            visited.add(nid)
            path.add(nid)
            node = plan.nodes.get(nid)
            if node:
                for dep in node.dependencies:
                    if dfs(dep):
                        return True
            path.discard(nid)
            return False

        return any(dfs(nid) for nid in plan.nodes)

    def _update_phase(self, experiment_id: str, phase: TaskPhase):
        """更新实验阶段"""
        with self._lock:
            if experiment_id not in self._active_experiments:
                self._active_experiments[experiment_id] = {}
            self._active_experiments[experiment_id]['phase'] = phase.value
            self._active_experiments[experiment_id]['updated_at'] = time.time()

    def get_status(self, experiment_id: Optional[str] = None) -> Dict[str, Any]:
        """获取运行状态"""
        with self._lock:
            if experiment_id:
                return self._active_experiments.get(experiment_id, {'phase': 'unknown'})
            return {
                'active_experiments': len(self._active_experiments),
                'experiments': dict(self._active_experiments),
                'memory_stats': self.memory.get_stats(),
                'knowledge_stats': self.knowledge.get_stats(),
            }

    # ==================== 便捷 API ====================

    def get_memory_summary(self, query: str = "") -> str:
        """获取记忆摘要"""
        return self.memory.summarize_for_prompt(query)

    def get_knowledge_summary(self, query: str, device_type: str = "") -> str:
        """获取知识摘要"""
        return self.knowledge.summarize_for_prompt(query, device_type)

    def get_plan(self, goal: str, experiment_type: str = "general") -> Dict[str, Any]:
        """获取执行计划（不执行）"""
        task_goal = TaskGoal(description=goal, raw_request=goal, experiment_type=experiment_type)
        plan = self.planner.plan_from_goal(task_goal)
        return plan.to_dict()
