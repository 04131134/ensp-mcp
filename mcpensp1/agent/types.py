# -*- coding: utf-8 -*-
"""Agent Runtime 共享数据类型定义"""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskPhase(str, Enum):
    """任务生命周期阶段"""
    RECEIVED = "received"           # 已接收
    UNDERSTANDING = "understanding" # 理解需求
    MEMORY_LOAD = "memory_load"     # 加载记忆
    KNOWLEDGE_SEARCH = "knowledge_search"  # 搜索知识
    PLANNING = "planning"           # 生成计划
    DEPENDENCY_CHECK = "dependency_check"  # 检查依赖
    DEVICE_SCAN = "device_scan"     # 扫描设备
    EXECUTING = "executing"         # 执行中
    VERIFYING = "verifying"         # 验证中
    REPAIRING = "repairing"         # 修复中
    REFLECTING = "reflecting"       # 反思中
    LEARNING = "learning"           # 学习中
    COMPLETED = "completed"         # 完成
    FAILED = "failed"               # 失败


class NodeType(str, Enum):
    """DAG 节点类型"""
    CONFIG = "config"           # 配置命令
    VERIFY = "verify"           # 验证步骤
    WAIT = "wait"               # 等待收敛
    DECISION = "decision"       # 条件判断
    RECOVERY = "recovery"       # 恢复操作


class RecoveryStrategy(str, Enum):
    """恢复策略类型"""
    ROLLBACK = "rollback"               # 回滚配置
    RETRY = "retry"                     # 重试命令
    ALTERNATIVE = "alternative"         # 替代方案
    MANUAL = "manual"                   # 需要人工干预


@dataclass
class TaskGoal:
    """实验任务目标"""
    description: str
    raw_request: str
    experiment_type: str = "general"  # campus/vpn/ospf/bgp/general
    constraints: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    priority: int = 1


@dataclass
class MemoryEntry:
    """记忆条目"""
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    category: str = "general"  # lesson/command/pattern/error/success/template
    content: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5  # 0.0-1.0
    access_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed: str = ""
    experiment_id: str = ""

    def touch(self):
        self.access_count += 1
        self.last_accessed = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeRecord:
    """知识记录"""
    record_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    category: str = "command"  # command/experience/template/troubleshoot/best_practice/config_order/device_capability
    title: str = ""
    content: Dict[str, Any] = field(default_factory=dict)
    device_type: str = "huawei"
    protocol: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.8  # 置信度 0.0-1.0
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    source: str = "observed"  # observed/learned/manual/template
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used: str = ""

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    def record_usage(self, success: bool):
        self.usage_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.last_used = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['success_rate'] = self.success_rate
        return d


@dataclass
class PlanNode:
    """DAG 计划节点"""
    node_id: str
    label: str
    node_type: NodeType = NodeType.CONFIG
    commands: List[str] = field(default_factory=list)
    device_path: str = ""
    dependencies: List[str] = field(default_factory=list)  # 依赖的 node_id 列表
    verify_commands: List[str] = field(default_factory=list)
    recovery_strategy: Optional[RecoveryStrategy] = None
    recovery_commands: List[str] = field(default_factory=list)
    status: str = "pending"  # pending/running/success/failed/skipped
    result: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: int = 30

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionPlan:
    """执行计划（DAG）"""
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    experiment_id: str = ""
    goal: Optional[TaskGoal] = None
    nodes: Dict[str, PlanNode] = field(default_factory=dict)
    execution_order: List[str] = field(default_factory=list)  # 拓扑排序后的执行顺序
    status: str = "draft"  # draft/ready/executing/completed/failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: PlanNode):
        self.nodes[node.node_id] = node
        self._recompute_order()

    def _recompute_order(self):
        """拓扑排序计算执行顺序"""
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        for nid, node in self.nodes.items():
            for dep in node.dependencies:
                if dep in in_degree:
                    in_degree[nid] += 1
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        order = []
        while queue:
            queue.sort()  # 稳定排序
            current = queue.pop(0)
            order.append(current)
            for nid, node in self.nodes.items():
                if current in node.dependencies:
                    in_degree[nid] -= 1
                    if in_degree[nid] == 0:
                        queue.append(nid)
        self.execution_order = order

    def get_ready_nodes(self) -> List[PlanNode]:
        """获取当前可执行的节点（所有依赖已完成）"""
        ready = []
        for nid in self.execution_order:
            node = self.nodes[nid]
            if node.status != "pending":
                continue
            deps_ok = all(
                self.nodes[dep].status == "success"
                for dep in node.dependencies
                if dep in self.nodes
            )
            if deps_ok:
                ready.append(node)
        return ready

    def is_complete(self) -> bool:
        return all(n.status in ("success", "skipped") for n in self.nodes.values())

    def has_failures(self) -> bool:
        return any(n.status == "failed" for n in self.nodes.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'plan_id': self.plan_id,
            'experiment_id': self.experiment_id,
            'goal': asdict(self.goal) if self.goal else None,
            'nodes': {nid: n.to_dict() for nid, n in self.nodes.items()},
            'execution_order': self.execution_order,
            'status': self.status,
            'created_at': self.created_at,
            'metadata': self.metadata,
        }


@dataclass
class VerificationResult:
    """验证结果"""
    check_name: str
    passed: bool
    detail: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    expected: str = ""
    actual: str = ""
    confidence: float = 1.0
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReflectionEntry:
    """反思记录"""
    reflection_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    experiment_id: str = ""
    summary: str = ""
    what_went_well: List[str] = field(default_factory=list)
    what_went_wrong: List[str] = field(default_factory=list)
    lessons_learned: List[str] = field(default_factory=list)
    recommended_commands: List[str] = field(default_factory=list)
    optimization_suggestions: List[str] = field(default_factory=list)
    knowledge_updates: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentResult:
    """实验结果"""
    experiment_id: str
    success: bool
    goal: Optional[TaskGoal] = None
    plan: Optional[ExecutionPlan] = None
    verification_results: List[VerificationResult] = field(default_factory=list)
    reflection: Optional[ReflectionEntry] = None
    duration_seconds: float = 0
    total_commands: int = 0
    successful_commands: int = 0
    failed_commands: int = 0
    repair_attempts: int = 0
    knowledge_entries_created: int = 0
    memory_entries_created: int = 0
    execution_log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            'experiment_id': self.experiment_id,
            'success': self.success,
            'duration_seconds': self.duration_seconds,
            'total_commands': self.total_commands,
            'successful_commands': self.successful_commands,
            'failed_commands': self.failed_commands,
            'repair_attempts': self.repair_attempts,
            'knowledge_entries_created': self.knowledge_entries_created,
            'memory_entries_created': self.memory_entries_created,
            'execution_log': self.execution_log,
        }
        if self.goal:
            d['goal'] = asdict(self.goal)
        if self.plan:
            d['plan_summary'] = {
                'total_nodes': len(self.plan.nodes),
                'completed': sum(1 for n in self.plan.nodes.values() if n.status == 'success'),
                'failed': sum(1 for n in self.plan.nodes.values() if n.status == 'failed'),
            }
        if self.verification_results:
            d['verification'] = [v.to_dict() for v in self.verification_results]
        if self.reflection:
            d['reflection'] = self.reflection.to_dict()
        return d
