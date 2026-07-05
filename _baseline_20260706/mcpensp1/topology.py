# -*- coding: utf-8 -*-
"""Topology graph engine for eNSP network topology."""
from __future__ import annotations
from typing import Any
import threading

class TopologyEngine:
    def __init__(self):
        self.graph, self.nodes, self.links = {}, [], []
        self.lock = threading.Lock()

    def load(self, data: dict[str, Any]) -> None:
        with self.lock:
            self.nodes = data.get('nodes', [])
            self.links = data.get('links', [])
            self.graph = {n.get('id', ''): {'info': n, 'neighbors': []} for n in self.nodes}
            for l in self.links:
                s, t = l.get('source', ''), l.get('target', '')
                if s in self.graph and t in self.graph:
                    self.graph[s]['neighbors'].append({'target': t, 'link': l})
                    self.graph[t]['neighbors'].append({'target': s, 'link': l})

    def get_neighbors(self, nid: str) -> list[dict[str, Any]]:
        with self.lock: return self.graph.get(nid, {}).get('neighbors', []) if nid in self.graph else []

    def find_path(self, start: str, end: str) -> list[str] | None:
        with self.lock:
            if start not in self.graph or end not in self.graph: return None
            if start == end: return [start]
            visited = {start}
            queue = deque([[start]])
            while queue:
                path = queue.popleft()
                for nb in self.graph.get(path[-1], {}).get('neighbors', []):
                    n = nb['target']
                    if n == end: return path + [n]
                    if n not in visited:
                        visited.add(n)
                        queue.append(path + [n])
            return None

    def get_device_connections(self, nid: str) -> list[dict[str, Any]]:
        with self.lock:
            if nid not in self.graph: return []
            return [{'target': nb['target'], 'target_name': self.graph.get(nb['target'], {}).get('info', {}).get('name', nb['target']), 'link': nb['link']} for nb in self.graph[nid]['neighbors']]

    def get_summary(self) -> dict[str, Any]:
        with self.lock:
            return {'node_count': len(self.nodes), 'link_count': len(self.links),
                    'nodes': [{'id': n.get('id'), 'name': n.get('name', n.get('id')), 'type': n.get('type', 'unknown')} for n in self.nodes],
                    'links': [{'source': l.get('source'), 'target': l.get('target'), 'source_interface': l.get('source_interface', ''), 'target_interface': l.get('target_interface', ''), 'line_type': l.get('line_type', 'Copper')} for l in self.links]}


