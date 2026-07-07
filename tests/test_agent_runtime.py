# -*- coding: utf-8 -*-
"""Agent Runtime Module Tests"""
import os
import sys
import json
import tempfile
import pytest

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcpensp1'))


# ==================== Planner Tests ====================

class TestPlanner:
    """Test DAG Planner generates real commands and valid DAG."""

    def test_generates_commands(self):
        """Planner must produce non-empty command lists for config nodes."""
        from agent.planner import DAGPlanner
        from agent.types import TaskGoal
        planner = DAGPlanner()
        goal = TaskGoal(description='Configure campus network with VLAN and OSPF', raw_request='campus network')
        plan = planner.plan_from_goal(goal)
        config_nodes = [n for n in plan.nodes.values() if n.node_type.value == 'config']
        assert len(config_nodes) > 0, 'No config nodes generated'
        for node in config_nodes:
            assert len(node.commands) > 0, f'Node {node.node_id} has empty commands'

    def test_dag_no_cycles(self):
        """DAG must have no circular dependencies."""
        from agent.planner import DAGPlanner
        from agent.types import TaskGoal
        planner = DAGPlanner()
        goal = TaskGoal(description='OSPF multi-area routing', raw_request='ospf')
        plan = planner.plan_from_goal(goal)
        # Topological sort should succeed
        assert len(plan.execution_order) == len(plan.nodes), 'Execution order mismatch'

    def test_template_matching(self):
        """Planner should match campus template."""
        from agent.planner import DAGPlanner
        from agent.types import TaskGoal
        planner = DAGPlanner()
        goal = TaskGoal(description='Campus network with access layer and core layer', raw_request='')
        plan = planner.plan_from_goal(goal)
        node_ids = list(plan.nodes.keys())
        assert 'vlan' in node_ids, 'VLAN node missing from campus plan'

    def test_verify_node_has_commands(self):
        """Verify nodes must also carry commands."""
        from agent.planner import DAGPlanner
        from agent.types import TaskGoal, NodeType
        planner = DAGPlanner()
        goal = TaskGoal(description='Basic routing with static route', raw_request='')
        plan = planner.plan_from_goal(goal)
        verify_nodes = [n for n in plan.nodes.values() if n.node_type == NodeType.VERIFY]
        for node in verify_nodes:
            assert len(node.commands) > 0, f'Verify node {node.node_id} has no commands'


# ==================== Verifier Tests ====================

class TestVerifier:
    """Test Semantic Verifier output parsers."""

    def test_parse_ip_brief(self):
        from agent.verifier import SemanticVerifier
        sample = """Interface                 IP Address/Mask      Physical   Protocol
GE0/0/0                 10.0.0.1/24            up         up
GE0/0/1                 192.168.10.1/24        up         up
NULL0                   unassigned             up         up(s)"""
        result = SemanticVerifier._parse_ip_brief(sample)
        assert len(result) >= 2
        assert '10.0.0.1' in result[0].get('ip', '')

    def test_parse_ospf_peer(self):
        from agent.verifier import SemanticVerifier
        sample = """ OSPF Process 1 with Router ID 1.1.1.1
                  Peer Statistic Information
-----------------------------------------------------------------------------
 Area Id     Interface          Neighbor id      State
 0.0.0.0     GE0/0/0            2.2.2.2          Full
 0.0.0.0     GE0/0/1            3.3.3.3          Full
-----------------------------------------------------------------------------"""
        result = SemanticVerifier._parse_ospf_peer(sample)
        full_peers = [p for p in result if p.get('state') == 'Full']
        assert len(full_peers) == 2

    def test_parse_vlan(self):
        from agent.verifier import SemanticVerifier
        sample = """10   GE0/0/1 GE0/0/2
20   GE0/0/3"""
        result = SemanticVerifier._parse_vlan(sample)
        assert len(result) >= 1
        assert result[0]['vlan_id'] == 10


# ==================== Memory Tests ====================

class TestMemory:
    """Test Memory persistence and dedup."""

    def test_dedup(self):
        from agent.memory import MemoryStore
        from agent.types import MemoryEntry
        with tempfile.TemporaryDirectory() as td:
            store = MemoryStore(os.path.join(td, 'mem.json'))
            store.add(MemoryEntry(category='lesson', content='VLAN must be created first', tags=['vlan']))
            store.add(MemoryEntry(category='lesson', content='VLAN must be created first', tags=['ospf']))
            entries = store.recall(limit=10)
            assert len(entries) == 1, f'Expected 1 deduped entry, got {len(entries)}'
            assert 'ospf' in entries[0].tags, 'Tags should be merged'

    def test_persistence(self):
        from agent.memory import MemoryStore
        from agent.types import MemoryEntry
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'mem.json')
            store = MemoryStore(path)
            store.add(MemoryEntry(category='command', content='display vlan', importance=0.9))
            # Reload
            store2 = MemoryStore(path)
            entries = store2.recall(limit=10)
            assert len(entries) == 1
            assert entries[0].content == 'display vlan'


# ==================== KnowledgeStore Tests ====================

class TestKnowledgeStore:
    """Test KnowledgeStore add/search."""

    def test_add_and_search(self):
        from agent.knowledge_store import KnowledgeStore
        from agent.types import KnowledgeRecord
        with tempfile.TemporaryDirectory() as td:
            store = KnowledgeStore(os.path.join(td, 'kb.json'))
            store.add(KnowledgeRecord(
                category='success_case',
                title='OSPF area 0 success',
                content={'commands': ['ospf 1', 'area 0']},
                tags=['ospf'],
            ))
            results = store.search(query='OSPF')
            assert len(results) >= 1
            assert results[0].title == 'OSPF area 0 success'


# ==================== Recovery Tests ====================

class TestRecovery:
    """Test Recovery engine round limits."""

    def test_max_rounds(self):
        from agent.recovery import RecoveryEngine
        from agent.types import PlanNode, NodeType
        engine = RecoveryEngine(command_executor=lambda p, c: {'success': False, 'output': 'Error'})
        node = PlanNode(node_id='test', label='Test', commands=['vlan 10'])
        # Simulate 3 failures
        for _ in range(3):
            node.retry_count += 1
        assert node.retry_count >= engine.MAX_REPAIR_ROUNDS


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
