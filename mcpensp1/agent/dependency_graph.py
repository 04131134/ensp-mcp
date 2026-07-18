# -*- coding: utf-8 -*-
"""Dependency Graph — Action 依赖关系管理。

支持：
- 拓扑排序
- 循环检测
- 失败节点重试（局部恢复）
- 局部重跑（不因一个节点失败而重跑整个实验）
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, Set, Tuple, Callable
from collections import deque
from .action_types import ActionNode, ActionPlan


class DependencyGraph:
    """Action 执行依赖图。

    用法:
        dg = DependencyGraph.from_plan(plan)
        order = dg.topological_sort()  # → ["a1", "a2", "a3"]
        dg.monitor_action(action_id, status="success")
        if dg.has_cycle():
            logging.getLogger(__name__).debug("检测到循环依赖!")
    """

    def __init__(self):
        self._actions: Dict[str, ActionNode] = {}
        self._adj: Dict[str, List[str]] = {}       # 邻接表（正向边）
        self._reverse_adj: Dict[str, List[str]] = {}  # 反向边
        self._status: Dict[str, str] = {}            # action_id → status

    @classmethod
    def from_plan(cls, plan: ActionPlan) -> DependencyGraph:
        """从 ActionPlan 构建依赖图。"""
        dg = cls()
        for action in plan.actions:
            dg.add_action(action)
        return dg

    def add_action(self, action: ActionNode) -> None:
        """添加 Action 到图中。"""
        aid = action.id
        self._actions[aid] = action
        if aid not in self._adj:
            self._adj[aid] = []
        if aid not in self._reverse_adj:
            self._reverse_adj[aid] = []
        self._status[aid] = action.status

        # 建立依赖边
        for dep in action.depends_on:
            if dep not in self._adj:
                self._adj[dep] = []
            self._adj[dep].append(aid)
            self._reverse_adj[aid].append(dep)

    def topological_sort(self) -> List[str]:
        """拓扑排序 — 返回可执行顺序。

        返回:
            Action ID 列表（按拓扑序排列）

        异常:
            ValueError: 存在循环依赖
        """
        in_degree: Dict[str, int] = {}
        for aid in self._adj:
            in_degree[aid] = 0
        for u in self._adj:
            for v in self._adj[u]:
                in_degree[v] = in_degree.get(v, 0) + 1

        queue = deque([aid for aid, deg in in_degree.items() if deg == 0])
        result: List[str] = []

        while queue:
            u = queue.popleft()
            result.append(u)
            for v in self._adj.get(u, []):
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(result) != len(self._adj):
            raise ValueError("检测到循环依赖，拓扑排序失败")

        return result

    def has_cycle(self) -> bool:
        """检测是否存在循环依赖。"""
        try:
            self.topological_sort()
            return False
        except ValueError:
            return True

    def find_cycle(self) -> Optional[List[str]]:
        """找到循环依赖路径（如果存在）。"""
        visited: Dict[str, int] = {}
        for aid in self._adj:
            visited[aid] = 0

        path: List[str] = []

        def dfs(u: str) -> Optional[List[str]]:
            visited[u] = 1
            path.append(u)
            for v in self._adj.get(u, []):
                if visited.get(v, 0) == 1:
                    cycle_start = path.index(v)
                    return path[cycle_start:] + [v]
                if visited.get(v, 0) == 0:
                    result = dfs(v)
                    if result:
                        return result
            visited[u] = 2
            path.pop()
            return None

        for aid in self._adj:
            if visited.get(aid, 0) == 0:
                result = dfs(aid)
                if result:
                    return result
        return None

    def get_next_ready(self) -> List[str]:
        """获取所有就绪的 Action（所有依赖已完成且自身未执行）。

        返回:
            就绪的 Action ID 列表
        """
        ready = []
        for aid in self._adj:
            if self._status.get(aid) != "pending":
                continue
            deps_satisfied = all(
                self._status.get(dep) == "success"
                for dep in self._reverse_adj.get(aid, [])
            )
            if deps_satisfied:
                ready.append(aid)
        return ready

    def monitor_action(self, action_id: str, status: str) -> None:
        """更新 Action 执行状态。"""
        if action_id in self._status:
            self._status[action_id] = status
            if action_id in self._actions:
                self._actions[action_id].status = status

    def get_failed_dependents(self, action_id: str) -> List[str]:
        """获取因某 Action 失败而受影响的后续 Action。

        参数:
            action_id: 失败的 Action ID

        返回:
            受影响（需要跳过）的 Action ID 列表
        """
        if self._status.get(action_id) != "failed":
            return []

        affected = []
        queue = deque([action_id])
        visited: Set[str] = set()

        while queue:
            u = queue.popleft()
            if u in visited:
                continue
            visited.add(u)
            for v in self._adj.get(u, []):
                affected.append(v)
                queue.append(v)

        return affected

    def get_retry_candidates(self) -> List[str]:
        """获取可重试的失败 Action。

        返回:
            状态为 failed 且未超过 max_retries 的 Action ID
        """
        candidates = []
        for aid, action in self._actions.items():
            if self._status.get(aid) == "failed":
                if action.retry_count < action.max_retries:
                    candidates.append(aid)
        return candidates

    def retry_action(self, action_id: str) -> bool:
        """准备重试 Action。

        参数:
            action_id: 要重试的 Action ID

        返回:
            是否成功准备重试
        """
        if action_id not in self._actions:
            return False
        action = self._actions[action_id]
        if action.retry_count >= action.max_retries:
            return False
        action.retry_count += 1
        self._status[action_id] = "pending"
        return True

    def get_subgraph_for_recovery(self, failed_id: str) -> List[str]:
        """获取局部恢复所需的 Action 子集。

        只重跑失败节点及其直接依赖，不重跑整个实验。

        参数:
            failed_id: 失败的 Action ID

        返回:
            需要重新执行的 Action ID 列表（含失败节点本身）
        """
        recover_set = [failed_id]

        # BFS 向下：获取所有下游节点
        queue = deque([failed_id])
        visited: Set[str] = {failed_id}
        while queue:
            u = queue.popleft()
            for v in self._adj.get(u, []):
                if v not in visited:
                    visited.add(v)
                    recover_set.append(v)
                    queue.append(v)

        return recover_set

    def summary(self) -> Dict[str, Any]:
        """依赖图摘要。"""
        statuses = {}
        for k, v in self._status.items():
            statuses[v] = statuses.get(v, 0) + 1

        return {
            "total_actions": len(self._actions),
            "statuses": statuses,
            "has_cycle": self.has_cycle(),
            "ready_count": len(self.get_next_ready()),
            "failed_count": statuses.get("failed", 0),
            "cycle_path": self.find_cycle(),
        }
