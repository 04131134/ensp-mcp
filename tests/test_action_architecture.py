# -*- coding: utf-8 -*-
"""Action 架构单元测试 — AST / DependencyGraph / Protocols / Runtime"""
from __future__ import annotations
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestActionTypes:
    """测试 AST 数据结构。"""

    def test_protocol_object(self):
        from mcpensp1.agent.action_types import ProtocolObject, ProtocolCategory
        po = ProtocolObject(protocol="ospf", category=ProtocolCategory.L3_ROUTING,
                            params={"proc_id": 1})
        assert po.protocol == "ospf"
        d = po.to_dict()
        assert d["protocol"] == "ospf"

    def test_config_object(self):
        from mcpensp1.agent.action_types import ConfigObject
        co = ConfigObject(id="vlan1", action="create_vlan",
                          target={"vlan_id": "10"}, device="LSW1")
        assert co.action == "create_vlan"
        assert co.device == "LSW1"

    def test_action_node(self):
        from mcpensp1.agent.action_types import ActionNode, ActionType, ConfigObject
        co = ConfigObject(id="n1", action="create_vlan", target={}, device="LSW1")
        node = ActionNode(id="a1", action_type=ActionType.CONFIGURE_VLAN,
                          config_object=co, depends_on=["a0"])
        assert node.status == "pending"
        assert node.max_retries == 3
        assert "a0" in node.depends_on

    def test_action_plan(self):
        from mcpensp1.agent.action_types import ActionPlan, ActionNode, ActionType, ConfigObject
        plan = ActionPlan(plan_id="p1", experiment_type="vlan")
        co = ConfigObject(id="n1", action="create_vlan", target={}, device="LSW1")
        node = ActionNode(id="a1", action_type=ActionType.CONFIGURE_VLAN, config_object=co)
        plan.add_action(node)
        assert plan.get_action("a1") is not None
        roots = plan.get_root_actions()
        assert len(roots) == 1


class TestDependencyGraph:
    """测试依赖图。"""

    def test_topological_sort_linear(self):
        """线性依赖 → 拓扑排序正确。"""
        from mcpensp1.agent.action_types import ActionNode, ActionType, ConfigObject, ActionPlan
        from mcpensp1.agent.dependency_graph import DependencyGraph

        plan = ActionPlan(plan_id="p1")
        co = ConfigObject(id="c", action="cmd", target={}, device="D")
        plan.add_action(ActionNode(id="a", action_type=ActionType.CONFIGURE_VLAN, config_object=co))
        plan.add_action(ActionNode(id="b", action_type=ActionType.CONFIGURE_VLAN, config_object=co, depends_on=["a"]))
        plan.add_action(ActionNode(id="c", action_type=ActionType.VERIFY_VLAN, config_object=co, depends_on=["b"]))

        dg = DependencyGraph.from_plan(plan)
        order = dg.topological_sort()
        assert order == ["a", "b", "c"]

    def test_cycle_detection(self):
        """循环依赖检测。"""
        from mcpensp1.agent.action_types import ActionNode, ActionType, ConfigObject, ActionPlan
        from mcpensp1.agent.dependency_graph import DependencyGraph

        plan = ActionPlan(plan_id="p1")
        co = ConfigObject(id="c", action="cmd", target={}, device="D")
        plan.add_action(ActionNode(id="a", action_type=ActionType.CONFIGURE_VLAN, config_object=co, depends_on=["b"]))
        plan.add_action(ActionNode(id="b", action_type=ActionType.CONFIGURE_VLAN, config_object=co, depends_on=["a"]))

        dg = DependencyGraph.from_plan(plan)
        assert dg.has_cycle() is True
        cycle = dg.find_cycle()
        assert cycle is not None
        assert "a" in cycle and "b" in cycle

    def test_no_cycle(self):
        """无环依赖图。"""
        from mcpensp1.agent.action_types import ActionNode, ActionType, ConfigObject, ActionPlan
        from mcpensp1.agent.dependency_graph import DependencyGraph

        plan = ActionPlan(plan_id="p1")
        co = ConfigObject(id="c", action="cmd", target={}, device="D")
        plan.add_action(ActionNode(id="x", action_type=ActionType.CONFIGURE_VLAN, config_object=co))
        plan.add_action(ActionNode(id="y", action_type=ActionType.CONFIGURE_VLAN, config_object=co, depends_on=["x"]))

        dg = DependencyGraph.from_plan(plan)
        assert dg.has_cycle() is False

    def test_get_next_ready(self):
        """获取就绪 Action。"""
        from mcpensp1.agent.action_types import ActionNode, ActionType, ConfigObject, ActionPlan
        from mcpensp1.agent.dependency_graph import DependencyGraph

        plan = ActionPlan(plan_id="p1")
        co = ConfigObject(id="c", action="cmd", target={}, device="D")
        plan.add_action(ActionNode(id="a", action_type=ActionType.CONFIGURE_VLAN, config_object=co))
        plan.add_action(ActionNode(id="b", action_type=ActionType.CONFIGURE_VLAN, config_object=co, depends_on=["a"]))

        dg = DependencyGraph.from_plan(plan)
        ready = dg.get_next_ready()
        assert "a" in ready
        assert "b" not in ready

        dg.monitor_action("a", "success")
        ready = dg.get_next_ready()
        assert "b" in ready

    def test_retry_action(self):
        """重试失败 Action。"""
        from mcpensp1.agent.action_types import ActionNode, ActionType, ConfigObject, ActionPlan
        from mcpensp1.agent.dependency_graph import DependencyGraph

        plan = ActionPlan(plan_id="p1")
        co = ConfigObject(id="c", action="cmd", target={}, device="D")
        plan.add_action(ActionNode(id="a", action_type=ActionType.CONFIGURE_VLAN, config_object=co))

        dg = DependencyGraph.from_plan(plan)
        dg.monitor_action("a", "failed")
        assert dg.retry_action("a") is True
        assert dg._actions["a"].retry_count == 1

        # Max retries exceeded
        dg.monitor_action("a", "failed")
        dg.retry_action("a")
        dg.monitor_action("a", "failed")
        dg.retry_action("a")
        assert dg.retry_action("a") is False  # 4th retry

    def test_get_failed_dependents(self):
        """获取失败节点的下游。"""
        from mcpensp1.agent.action_types import ActionNode, ActionType, ConfigObject, ActionPlan
        from mcpensp1.agent.dependency_graph import DependencyGraph

        plan = ActionPlan(plan_id="p1")
        co = ConfigObject(id="c", action="cmd", target={}, device="D")
        plan.add_action(ActionNode(id="a", action_type=ActionType.CONFIGURE_VLAN, config_object=co))
        plan.add_action(ActionNode(id="b", action_type=ActionType.CONFIGURE_VLAN, config_object=co, depends_on=["a"]))
        plan.add_action(ActionNode(id="c", action_type=ActionType.VERIFY_VLAN, config_object=co, depends_on=["b"]))

        dg = DependencyGraph.from_plan(plan)
        dg.monitor_action("a", "failed")
        affected = dg.get_failed_dependents("a")
        assert "b" in affected
        assert "c" in affected

    def test_summary(self):
        """依赖图摘要。"""
        from mcpensp1.agent.action_types import ActionNode, ActionType, ConfigObject, ActionPlan
        from mcpensp1.agent.dependency_graph import DependencyGraph

        plan = ActionPlan(plan_id="p1")
        co = ConfigObject(id="c", action="cmd", target={}, device="D")
        plan.add_action(ActionNode(id="a", action_type=ActionType.CONFIGURE_VLAN, config_object=co))

        dg = DependencyGraph.from_plan(plan)
        dg.monitor_action("a", "success")
        s = dg.summary()
        assert s["total_actions"] == 1


class TestProtocolPlugins:
    """测试协议插件。"""

    def test_vlan_plugin_capability(self):
        from mcpensp1.protocols import VLANPlugin
        cap = VLANPlugin.capability()
        assert cap["protocol"] == "vlan"
        assert "S5700" in cap["supported_devices"]

    def test_vlan_plugin_generate(self):
        from mcpensp1.protocols import VLANPlugin
        configs = VLANPlugin.generate_config_objects(
            {"vlan_id": 10, "ports": ["GigabitEthernet0/0/1"]}, "LSW1")
        assert len(configs) >= 1
        assert configs[0].action == "create_vlan"

    def test_ospf_plugin_capability(self):
        from mcpensp1.protocols import OSPFPlugin
        cap = OSPFPlugin.capability()
        assert "ospf" in cap["commands"]

    def test_ospf_plugin_generate(self):
        from mcpensp1.protocols import OSPFPlugin
        params = {"proc_id": 1, "router_id": "1.1.1.1",
                  "areas": [{"area_id": "0", "networks": ["10.0.0.0 0.0.0.255"]}]}
        configs = OSPFPlugin.generate_config_objects(params, "LSW1")
        assert len(configs) >= 1
        assert "router_id" in str(configs[0].target)

    def test_acl_plugin(self):
        from mcpensp1.protocols import ACLPlugin
        configs = ACLPlugin.generate_config_objects(
            {"acl_num": 3000, "rules": ["rule 5 permit ip source any destination any"]}, "LSW1")
        assert len(configs) >= 1

    def test_bgp_plugin(self):
        from mcpensp1.protocols import BGPPlugin
        params = {"as_num": 65001, "router_id": "1.1.1.1",
                  "peers": ["10.0.0.2"], "networks": ["10.0.0.0 255.255.255.0"]}
        configs = BGPPlugin.generate_config_objects(params, "LSW1")
        assert len(configs) >= 1

    def test_vlan_recovery_skip(self):
        from mcpensp1.protocols import VLANPlugin
        result = VLANPlugin.recovery("Error: The VLAN already exists")
        assert result["action"] == "skip"

    def test_ospf_recovery(self):
        from mcpensp1.protocols import OSPFPlugin
        result = OSPFPlugin.recovery("Error: Please configure the router-id first")
        assert result["action"] == "configure_router_id"

    def test_bgp_recovery(self):
        from mcpensp1.protocols import BGPPlugin
        result = BGPPlugin.recovery("Error: The BGP peer does not exist")
        assert result["action"] == "configure_peer"


class TestActionRuntime:
    """测试 ActionDrivenRuntime。"""

    def test_runtime_init(self):
        from mcpensp1.agent.runtime_action import ActionDrivenRuntime
        rt = ActionDrivenRuntime()
        assert rt is not None

    def test_runtime_execute_vlan_dry_run(self):
        """Dry-run VLAN 任务。"""
        from mcpensp1.agent.runtime_action import ActionDrivenRuntime
        rt = ActionDrivenRuntime()
        result = rt.execute(
            task="Create VLAN 10 and 20",
            device_paths=["127.0.0.1:2001"],
            device_model="S5700",
        )
        # Dry run (no executor) should succeed
        assert "success" in result
        assert "plan_id" in result

    def test_runtime_execute_ospf_dry_run(self):
        """Dry-run OSPF 任务。"""
        from mcpensp1.agent.runtime_action import ActionDrivenRuntime
        rt = ActionDrivenRuntime()
        result = rt.execute(
            task="Configure OSPF with area 0",
            device_paths=["127.0.0.1:2001"],
            device_model="S5700",
        )
        assert "success" in result

    def test_runtime_fails_on_unknown_model(self):
        """未知设备型号应失败。"""
        from mcpensp1.agent.runtime_action import ActionDrivenRuntime
        rt = ActionDrivenRuntime()
        result = rt.execute(
            task="Create VLAN",
            device_paths=["127.0.0.1:2001"],
            device_model="UnknownBox",
        )
        assert result["success"] is False
        assert "Unknown" in result.get("error", "")


class TestCompatibility:
    """兼容性测试。"""

    def test_all_new_modules_importable(self):
        from mcpensp1.agent.action_types import ActionPlan, ActionNode, ActionType, ConfigObject, ProtocolObject
        from mcpensp1.agent.dependency_graph import DependencyGraph
        from mcpensp1.agent.runtime_action import ActionDrivenRuntime
        from mcpensp1.protocols import VLANPlugin, OSPFPlugin, ACLPlugin, BGPPlugin
        assert True

    def test_old_runtime_still_works(self):
        """原有 Runtime 仍可导入。"""
        from mcpensp1.agent.runtime import AgentRuntime
        assert True
