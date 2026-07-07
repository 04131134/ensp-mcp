# -*- coding: utf-8 -*-
"""CLI 状态机单元测试 — 覆盖 CLIState / PromptParser / CommandValidator / CommandGenerator"""
from __future__ import annotations
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════
# CLIState 测试
# ═══════════════════════════════════════════════════════════

class TestCLIState:
    """测试 CLIState 视图栈管理。"""

    def test_initial_state_is_user(self):
        """初始状态应为 USER 视图。"""
        from mcpensp1.agent.cli_state import CLIState
        state = CLIState("SW1")
        assert state.current_view().value == "USER"
        assert state.stack_depth() == 1

    def test_push_system_view(self):
        """push SYSTEM 后应处于系统视图。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        state.push(CLIView.SYSTEM)
        assert state.current_view() == CLIView.SYSTEM
        assert state.stack_depth() == 2

    def test_push_interface_view(self):
        """push INTERFACE 后状态正确。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        state.push(CLIView.SYSTEM)
        state.push(CLIView.INTERFACE, {"ifname": "GigabitEthernet0/0/1"})
        assert state.current_view() == CLIView.INTERFACE
        assert state.current_params()["ifname"] == "GigabitEthernet0/0/1"
        assert state.stack_depth() == 3

    def test_pop_returns_to_previous(self):
        """pop 应返回到上一层视图。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        state.push(CLIView.SYSTEM)
        state.push(CLIView.INTERFACE)
        popped = state.pop()
        assert popped == CLIView.SYSTEM
        assert state.stack_depth() == 2

    def test_pop_from_user_raises(self):
        """从 USER pop 应抛出 ValueError。"""
        from mcpensp1.agent.cli_state import CLIState
        state = CLIState("SW1")
        with pytest.raises(ValueError, match="Cannot pop"):
            state.pop()

    def test_return_to_user_from_deep(self):
        """从多层视图 return 应回到 USER。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        state.push(CLIView.SYSTEM)
        state.push(CLIView.OSPF, {"proc_id": "1"})
        state.push(CLIView.AREA, {"area_id": "0"})
        assert state.stack_depth() == 4
        result = state.return_to_user()
        assert result.value == "USER"
        assert state.stack_depth() == 1

    def test_preserves_user_view_persists_below_system(self):
        """0层应当是 USER 视图。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        state.push(CLIView.SYSTEM)
        assert state.view_stack()[0].view == CLIView.USER

    def test_view_stack_returns_copy(self):
        """view_stack 返回深拷贝，修改不影响原始状态。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        stack = state.view_stack()
        stack.append(None)
        assert state.stack_depth() == 1

    def test_push_vlan_ospf_acl_aaa_bgp_rip(self):
        """依次推入多种视图类型。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        state.push(CLIView.SYSTEM)

        state.push(CLIView.VLAN, {"vlan_id": "10"})
        assert state.current_view() == CLIView.VLAN
        state.pop()

        state.push(CLIView.OSPF, {"proc_id": "1"})
        assert state.current_view() == CLIView.OSPF
        state.pop()

        state.push(CLIView.ACL, {"acl_num": "3000"})
        assert state.current_view() == CLIView.ACL
        state.pop()

        state.push(CLIView.AAA)
        assert state.current_view() == CLIView.AAA
        state.pop()

        state.push(CLIView.BGP, {"as_num": "65001"})
        assert state.current_view() == CLIView.BGP
        state.pop()

        state.push(CLIView.RIP, {"proc_id": "1"})
        assert state.current_view() == CLIView.RIP
        state.pop()

        assert state.current_view() == CLIView.SYSTEM

    def test_clone_is_independent(self):
        """clone 后两状态独立。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        a = CLIState("SW1")
        a.push(CLIView.SYSTEM)
        b = a.clone()
        b.push(CLIView.INTERFACE)
        assert a.current_view() == CLIView.SYSTEM
        assert b.current_view() == CLIView.INTERFACE

    def test_get_exit_command_for_user_returns_none(self):
        """用户视图无 exit 命令。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        assert state.get_exit_command() is None

    def test_get_exit_command_for_system_returns_quit(self):
        """系统视图 exit 命令为 quit。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        state.push(CLIView.SYSTEM)
        assert state.get_exit_command() == "quit"

    def test_sync_to_view_replaces_stack(self):
        """sync_to_view 直接替换视图栈。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        state.push(CLIView.SYSTEM)
        state.sync_to_view(CLIView.OSPF, {"proc_id": "1"})
        assert state.current_view() == CLIView.OSPF
        assert state.stack_depth() == 3  # USER → SYSTEM → OSPF

    def test_is_helpers(self):
        """is_at_user / is_at_system 辅助方法。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        state = CLIState("SW1")
        assert state.is_at_user() is True
        assert state.is_at_system() is False
        state.push(CLIView.SYSTEM)
        assert state.is_at_user() is False
        assert state.is_at_system() is True


# ═══════════════════════════════════════════════════════════
# PromptParser 测试
# ═══════════════════════════════════════════════════════════

class TestPromptParser:
    """测试 PromptParser 的 prompt 解析。"""

    @pytest.fixture
    def parser(self):
        from mcpensp1.agent.prompt_parser import PromptParser
        return PromptParser()

    def test_user_view_angle_bracket(self, parser):
        """<Huawei> 应解析为 USER。"""
        result = parser.parse("<Huawei>")
        assert result["view"].value == "USER"
        assert result["confidence"] == "high"

    def test_system_view_square_bracket(self, parser):
        """[Huawei] 应解析为 SYSTEM。"""
        result = parser.parse("[Huawei]")
        assert result["view"].value == "SYSTEM"

    def test_interface_view(self, parser):
        """[Huawei-GigabitEthernet0/0/1] 应解析为 INTERFACE。"""
        result = parser.parse("[Huawei-GigabitEthernet0/0/1]")
        assert result["view"].value == "INTERFACE"
        assert result["params"]["ifname"] == "GigabitEthernet0/0/1"

    def test_vlan_view(self, parser):
        """[Huawei-vlan10] 应解析为 VLAN。"""
        result = parser.parse("[Huawei-vlan10]")
        assert result["view"].value == "VLAN"
        assert result["params"]["vlan_id"] == "10"

    def test_ospf_view(self, parser):
        """[Huawei-ospf-1] 应解析为 OSPF。"""
        result = parser.parse("[Huawei-ospf-1]")
        assert result["view"].value == "OSPF"
        assert result["params"]["proc_id"] == "1"

    def test_area_view(self, parser):
        """[Huawei-ospf-1-area-0.0.0.0] 应解析为 AREA。"""
        result = parser.parse("[Huawei-ospf-1-area-0.0.0.0]")
        assert result["view"].value == "AREA"
        assert result["params"]["area_id"] == "0.0.0.0"

    def test_acl_view(self, parser):
        """[Huawei-acl-adv-3000] 应解析为 ACL。"""
        result = parser.parse("[Huawei-acl-adv-3000]")
        assert result["view"].value == "ACL"
        assert result["params"]["acl_num"] == "3000"

    def test_aaa_view(self, parser):
        """[Huawei-aaa] 应解析为 AAA。"""
        result = parser.parse("[Huawei-aaa]")
        assert result["view"].value == "AAA"

    def test_bgp_view(self, parser):
        """[Huawei-bgp] 应解析为 BGP。"""
        result = parser.parse("[Huawei-bgp]")
        assert result["view"].value == "BGP"

    def test_rip_view(self, parser):
        """[Huawei-rip-1] 应解析为 RIP。"""
        result = parser.parse("[Huawei-rip-1]")
        assert result["view"].value == "RIP"
        assert result["params"]["proc_id"] == "1"

    def test_unknown_prompt(self, parser):
        """无匹配模式应返回 UNKNOWN。"""
        result = parser.parse("random text")
        assert result["view"].value == "UNKNOWN"
        assert result["confidence"] == "low"

    def test_different_device_names(self, parser):
        """不同设备名但相同视图应正确解析。"""
        for dev in ["Huawei", "SW1", "LSW1", "R1", "AR1", "FW1", "AC1"]:
            result = parser.parse(f"<{dev}>")
            assert result["view"].value == "USER", f"Failed for {dev}"

            result = parser.parse(f"[{dev}]")
            assert result["view"].value == "SYSTEM", f"Failed for {dev}"

    def test_parse_quick_returns_enum(self, parser):
        """parse_quick 直接返回 CLIView 枚举。"""
        from mcpensp1.agent.cli_state import CLIView
        assert parser.parse_quick("<Huawei>") == CLIView.USER
        assert parser.parse_quick("[Huawei]") == CLIView.SYSTEM

    def test_is_valid_prompt(self, parser):
        """is_valid_prompt 正确区分合法/非法 prompt。"""
        assert parser.is_valid_prompt("<Huawei>") is True
        assert parser.is_valid_prompt("[SW1-ospf-1]") is True
        assert parser.is_valid_prompt("hello world") is False

    def test_detect_from_output(self, parser):
        """detect_from_output 从多行输出中提取 prompt。"""
        output = "display vlan\nVLAN ID: 10\n<Huawei>"
        prompt = parser.detect_from_output(output)
        assert prompt == "<Huawei>"


# ═══════════════════════════════════════════════════════════
# CommandValidator 测试
# ═══════════════════════════════════════════════════════════

class TestCommandValidator:
    """测试 CommandValidator 命令验证。"""

    @pytest.fixture
    def validator(self):
        from mcpensp1.agent.command_validator import CommandValidator
        return CommandValidator()

    @pytest.fixture
    def state(self):
        from mcpensp1.agent.cli_state import CLIState
        return CLIState("SW1")

    def test_allow_display_in_user_view(self, validator, state):
        """display 命令在 USER 视图应允许。"""
        result = validator.validate(state, "display version")
        assert result["allowed"] is True

    def test_allow_system_view_in_user(self, validator, state):
        """system-view 在 USER 视图应允许。"""
        result = validator.validate(state, "system-view")
        assert result["allowed"] is True

    def test_block_interface_in_user(self, validator, state):
        """interface 命令在 USER 视图应被阻止。"""
        result = validator.validate(state, "interface GigabitEthernet0/0/1")
        assert result["allowed"] is False
        assert "system-view" in result.get("suggestion", "")

    def test_allow_interface_in_system(self, validator, state):
        """interface 命令在 SYSTEM 视图应允许。"""
        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        result = validator.validate(state, "interface GigabitEthernet0/0/1")
        assert result["allowed"] is True

    def test_allow_ip_address_in_interface(self, validator, state):
        """ip address 在 INTERFACE 视图应允许。"""
        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        state.push(CLIView.INTERFACE)
        result = validator.validate(state, "ip address 10.0.0.1 255.255.255.0")
        assert result["allowed"] is True

    def test_block_vlan_in_user(self, validator, state):
        """vlan 命令在 USER 视图应被阻止。"""
        result = validator.validate(state, "vlan 10")
        assert result["allowed"] is False

    def test_allow_vlan_in_system(self, validator, state):
        """vlan 命令在 SYSTEM 视图应允许。"""
        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        result = validator.validate(state, "vlan 10")
        assert result["allowed"] is True

    def test_block_ip_route_in_interface(self, validator, state):
        """ip route 在 INTERFACE 视图应被阻止。"""
        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        state.push(CLIView.INTERFACE)
        result = validator.validate(state, "ip route-static 0.0.0.0 0.0.0.0 10.0.0.1")
        assert result["allowed"] is False

    def test_global_undo_allowed_everywhere(self, validator, state):
        """undo 命令在所有视图应允许。"""
        result = validator.validate(state, "undo info-center enable")
        assert result["allowed"] is True

        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        result = validator.validate(state, "undo stp")
        assert result["allowed"] is True

    def test_quit_not_allowed_at_user(self, validator, state):
        """quit 在 USER 视图不应被认为需要阻止（实际无影响）。"""
        result = validator.validate(state, "quit")
        # quit 在 USER 有特殊处理

    def test_return_allowed_everywhere(self, validator, state):
        """return 命令在所有视图应允许。"""
        result = validator.validate(state, "return")
        assert result["allowed"] is True

        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        state.push(CLIView.INTERFACE)
        result = validator.validate(state, "return")
        assert result["allowed"] is True

    def test_bgp_view_blocked_outside_system(self, validator, state):
        """bgp 命令在 USER 视图应被阻止。"""
        result = validator.validate(state, "bgp 65001")
        assert result["allowed"] is False

    def test_bgp_allowed_in_system(self, validator, state):
        """bgp 命令在 SYSTEM 视图应允许。"""
        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        result = validator.validate(state, "bgp 65001")
        assert result["allowed"] is True

    def test_ospf_router_id_in_ospf_view(self, validator, state):
        """router-id 在 OSPF 视图应允许。"""
        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        state.push(CLIView.OSPF)
        result = validator.validate(state, "router-id 1.1.1.1")
        assert result["allowed"] is True

    def test_acl_rule_in_acl_view(self, validator, state):
        """rule 在 ACL 视图应允许。"""
        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        state.push(CLIView.ACL)
        result = validator.validate(state, "rule 5 permit ip source 10.0.0.0 0.0.0.255")
        assert result["allowed"] is True

    def test_rip_network_in_rip_view(self, validator, state):
        """network 在 RIP 视图应允许。"""
        from mcpensp1.agent.cli_state import CLIView
        state.push(CLIView.SYSTEM)
        state.push(CLIView.RIP)
        result = validator.validate(state, "network 10.0.0.0")
        assert result["allowed"] is True

    def test_validate_batch_tracks_state(self, validator, state):
        """批量验证应正确追踪状态变化。"""
        from mcpensp1.agent.cli_state import CLIView
        commands = [
            "system-view",
            "interface GigabitEthernet0/0/1",
            "ip address 10.0.0.1 255.255.255.0",
            "quit",
            "vlan 10",
        ]
        results = validator.validate_batch(state, commands)
        assert results[0]["allowed"] is True  # system-view
        assert results[1]["allowed"] is True  # interface
        assert results[2]["allowed"] is True  # ip address
        assert results[3]["allowed"] is True  # quit
        assert results[4]["allowed"] is True  # vlan (现在在 SYSTEM)


# ═══════════════════════════════════════════════════════════
# CommandGenerator 测试
# ═══════════════════════════════════════════════════════════

class TestCommandGenerator:
    """测试 CommandGenerator 命令生成。"""

    @pytest.fixture
    def generator(self):
        from mcpensp1.agent.command_generator import CommandGenerator
        return CommandGenerator()

    @pytest.fixture
    def state(self):
        from mcpensp1.agent.cli_state import CLIState
        return CLIState("SW1")

    def test_display_action_from_user_no_nav(self, generator, state):
        """display Action 从 USER 视图：不需要导航命令。"""
        from mcpensp1.agent.command_generator import Action
        action = Action("display", params={"commands": ["display version"]})
        cmds = generator.generate(state, action, auto_return=False)
        assert "display version" in cmds
        assert "system-view" not in cmds

    def test_configure_interface_from_user(self, generator, state):
        """配置接口从 USER：应生成 system-view + interface + quit。"""
        from mcpensp1.agent.command_generator import Action
        action = Action("configure_interface", params={
            "ifname": "GigabitEthernet0/0/1",
            "ip_address": "10.0.0.1",
            "netmask": "255.255.255.0",
        })
        cmds = generator.generate(state, action)
        assert "system-view" in cmds
        assert "interface GigabitEthernet0/0/1" in cmds
        assert "ip address 10.0.0.1 255.255.255.0" in cmds
        # 应包含返回命令
        assert any(c in cmds for c in ["quit", "return"])

    def test_configure_interface_already_in_system(self, generator, state):
        """配置接口从 SYSTEM：不需要 system-view。"""
        from mcpensp1.agent.cli_state import CLIView
        from mcpensp1.agent.command_generator import Action
        state.push(CLIView.SYSTEM)
        action = Action("configure_interface", params={
            "ifname": "GigabitEthernet0/0/1",
        })
        cmds = generator.generate(state, action, auto_return=False)
        assert "system-view" not in cmds
        assert "interface GigabitEthernet0/0/1" in cmds

    def test_configure_vlan_from_user(self, generator, state):
        """配置 VLAN 从 USER。"""
        from mcpensp1.agent.command_generator import Action
        action = Action("configure_vlan", params={
            "vlan_id": "10",
            "description": "Management VLAN"
        })
        cmds = generator.generate(state, action)
        assert "system-view" in cmds
        assert "vlan 10" in cmds
        assert "description Management VLAN" in cmds

    def test_configure_ospf_from_user(self, generator, state):
        """配置 OSPF 从 USER。"""
        from mcpensp1.agent.command_generator import Action
        action = Action("configure_ospf", params={
            "proc_id": "1",
            "router_id": "1.1.1.1",
        })
        cmds = generator.generate(state, action)
        assert "system-view" in cmds
        assert "ospf 1" in cmds
        assert "router-id 1.1.1.1" in cmds

    def test_configure_acl_from_user(self, generator, state):
        """配置 ACL 从 USER。"""
        from mcpensp1.agent.command_generator import Action
        action = Action("configure_acl", params={
            "acl_num": "3000",
            "rules": ["rule 5 permit ip source 10.0.0.0 0.0.0.255 destination any"],
        })
        cmds = generator.generate(state, action)
        assert "system-view" in cmds
        assert "acl 3000" in cmds
        assert "rule 5 permit ip source 10.0.0.0 0.0.0.255 destination any" in cmds

    def test_configure_bgp_from_user(self, generator, state):
        """配置 BGP 从 USER。"""
        from mcpensp1.agent.command_generator import Action
        action = Action("configure_bgp", params={
            "as_num": "65001",
        })
        cmds = generator.generate(state, action)
        assert "system-view" in cmds
        assert "bgp 65001" in cmds

    def test_no_auto_return_during_intermediate_actions(self, generator, state):
        """中间 Action 的 auto_return=False 不应生成返回命令。"""
        from mcpensp1.agent.command_generator import Action
        action = Action("configure_interface", params={
            "ifname": "GigabitEthernet0/0/1",
        })
        cmds = generator.generate(state, action, auto_return=False)
        assert "system-view" in cmds
        assert "interface GigabitEthernet0/0/1" in cmds
        # auto_return=False 时不应包含 quit
        assert "quit" not in cmds

    def test_generate_batch_multiple_actions(self, generator, state):
        """批量 Action 应连续生成正确命令。"""
        from mcpensp1.agent.command_generator import Action
        actions = [
            Action("configure_vlan", params={"vlan_id": "10"}),
            Action("configure_interface", params={
                "ifname": "GigabitEthernet0/0/1",
                "ip_address": "10.0.0.1",
                "netmask": "255.255.255.0",
            }),
        ]
        cmds = generator.generate_batch(state, actions)
        assert "system-view" in cmds
        assert "vlan 10" in cmds
        assert "interface GigabitEthernet0/0/1" in cmds
        assert "ip address 10.0.0.1 255.255.255.0" in cmds


# ═══════════════════════════════════════════════════════════
# 集成测试：Prompt 驱动状态同步
# ═══════════════════════════════════════════════════════════

class TestPromptStateIntegration:
    """测试 PromptParser + CLIState 集成。"""

    def test_parse_then_sync_state(self):
        """Prompt 解析后同步 CLIState。"""
        from mcpensp1.agent.prompt_parser import PromptParser
        from mcpensp1.agent.cli_state import CLIState, CLIView

        parser = PromptParser()
        state = CLIState("SW1")

        # 模拟设备返回 SYSTEM prompt
        result = parser.parse("[SW1]")
        state.sync_to_view(result["view"], result.get("params"))
        assert state.current_view() == CLIView.SYSTEM

        # 模拟进入 INTERFACE
        result = parser.parse("[SW1-GigabitEthernet0/0/1]")
        state.sync_to_view(result["view"], result.get("params"))
        assert state.current_view() == CLIView.INTERFACE

    def test_update_from_prompt(self):
        """update_from_prompt 直接从 prompt 更新状态。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView

        state = CLIState("SW1")
        state.update_from_prompt("[SW1-ospf-1]")
        assert state.current_view() == CLIView.OSPF
        assert state.current_params()["proc_id"] == "1"


# ═══════════════════════════════════════════════════════════
# 兼容性测试：新模块不影响现有功能
# ═══════════════════════════════════════════════════════════

class TestCompatibility:
    """确保新模块可独立导入且不影响现有代码。"""

    def test_all_new_modules_importable(self):
        """所有新模块应可独立导入。"""
        from mcpensp1.agent.cli_state import CLIState, CLIView
        from mcpensp1.agent.prompt_parser import PromptParser
        from mcpensp1.agent.command_validator import CommandValidator
        from mcpensp1.agent.command_generator import CommandGenerator, Action
        assert True

    def test_existing_imports_still_work(self):
        """现有模块导入不应受影响。"""
        from mcpensp1.command_executor import CommandExecutor, is_blocked_command
        from mcpensp1.device_manager import DeviceManager
        from mcpensp1.knowledge import KnowledgeBase
        from mcpensp1.agent.planner import DAGPlanner
        from mcpensp1.agent.runtime import AgentRuntime
        from mcpensp1.agent.verifier import SemanticVerifier
        assert True

    def test_view_rules_json_is_valid(self):
        """view_rules.json 应为合法 JSON。"""
        import json
        path = os.path.join(
            os.path.dirname(__file__), "..", "mcpensp1", "kb", "cli", "view_rules.json"
        )
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "views" in data
        assert "view_transitions" in data
        assert len(data["views"]) >= 10
