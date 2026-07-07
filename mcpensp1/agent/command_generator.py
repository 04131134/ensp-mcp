# -*- coding: utf-8 -*-
"""命令生成器 — 根据目标视图和 Action 自动生成完整 CLI 命令序列。

Planner 不再直接拼接 CLI，而是输出 Action（高层意图）。
Generator 根据当前 View 自动生成所需的 system-view / quit / return 命令，
保证命令始终运行在正确 View。
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
from .cli_state import CLIState, CLIView


class Action:
    """Planner 输出的高层操作意图。

    示例:
        Action("enter_interface", params={"ifname": "GigabitEthernet0/0/1"})
        Action("config", params={"commands": ["ip address 10.0.0.1 24"]})
        Action("verify", params={"commands": ["display ip interface brief"]})
    """

    def __init__(self, action_type: str, params: Optional[Dict[str, Any]] = None):
        self.action_type = action_type
        self.params = params or {}

    def __repr__(self):
        return f"Action({self.action_type}, params={self.params})"


class CommandGenerator:
    """根据当前 CLI 状态和 Action 生成完整的 CLI 命令序列。

    职责：
    1. 自动计算视图切换命令（system-view / quit / return）
    2. 在正确视图包装配置命令
    3. 配置完成后自动回到用户视图

    用法:
        generator = CommandGenerator()
        state = CLIState("SW1")
        action = Action("configure_interface", params={
            "ifname": "GigabitEthernet0/0/1",
            "ip_address": "10.0.0.1",
            "netmask": "255.255.255.0"
        })
        cmds = generator.generate(state, action)
        # → ["system-view", "interface GigabitEthernet0/0/1",
        #    "ip address 10.0.0.1 255.255.255.0", "quit", "quit"]
    """

    # Action 类型到目标视图的映射
    ACTION_VIEW_MAP: Dict[str, CLIView] = {
        "display": CLIView.USER,
        "show": CLIView.USER,
        "ping": CLIView.USER,
        "tracert": CLIView.USER,
        "system_view": CLIView.SYSTEM,
        "configure_global": CLIView.SYSTEM,
        "configure_interface": CLIView.INTERFACE,
        "configure_vlan": CLIView.VLAN,
        "configure_ospf": CLIView.OSPF,
        "configure_area": CLIView.AREA,
        "configure_acl": CLIView.ACL,
        "configure_aaa": CLIView.AAA,
        "configure_bgp": CLIView.BGP,
        "configure_rip": CLIView.RIP,
        "verify": CLIView.USER,
        "verify_interface": CLIView.USER,
        "verify_ospf": CLIView.USER,
        "verify_vlan": CLIView.USER,
        "verify_stp": CLIView.USER,
    }

    # 标准 Action 处理函数
    ACTION_HANDLERS: Dict[str, str] = {
        "configure_interface": "interface {ifname}",
        "configure_vlan": "vlan {vlan_id}",
        "configure_ospf": "ospf {proc_id}",
        "configure_area": "area {area_id}",
        "configure_acl": "acl {acl_num}",
        "configure_aaa": "aaa",
        "configure_bgp": "bgp {as_num}",
        "configure_rip": "rip {proc_id}",
    }

    def generate(self, state: CLIState, action: Action,
                 auto_return: bool = True) -> List[str]:
        """根据 Action 生成完整的 CLI 命令序列。

        参数:
            state: 当前 CLI 状态（会克隆，不影响原状态）
            action: Planner 输出的 Action
            auto_return: 完成后是否自动返回到用户视图（默认 True）

        返回:
            完整的 CLI 命令序列
        """
        sim = state.clone()
        cmds: List[str] = []

        target_view = self._get_target_view(action)

        # 步骤 1：视图导航
        nav_cmds = self._navigate(sim, target_view, action.params)
        cmds.extend(nav_cmds)

        # 步骤 2：执行核心命令
        core_cmds = self._get_core_commands(action)
        cmds.extend(core_cmds)

        # 步骤 3：自动返回用户视图（可选）
        if auto_return and target_view != CLIView.USER:
            return_cmds = self._navigate_to_view(sim, target_view, CLIView.USER)
            cmds.extend(return_cmds)

        return cmds

    def _get_target_view(self, action: Action) -> CLIView:
        """确定 Action 的目标视图。"""
        return self.ACTION_VIEW_MAP.get(action.action_type, CLIView.SYSTEM)

    def _navigate(self, sim: CLIState, target: CLIView,
                  params: Dict[str, Any]) -> List[str]:
        """生成从当前视图到目标视图的导航命令。"""
        cmds: List[str] = []
        current = sim.current_view()

        if current == target:
            return cmds

        if target == CLIView.USER:
            # 退出所有层
            for _ in range(sim.stack_depth() - 1):
                cmds.append("quit")
            sim.return_to_user()
            return cmds

        # 如果当前不在 USER 且目标是 SYSTEM
        if target == CLIView.SYSTEM:
            if current != CLIView.USER:
                cmds.append("return")
                sim.return_to_user()
            cmds.append("system-view")
            sim.push(CLIView.SYSTEM)
            return cmds

        # 目标是子视图：先确保在 SYSTEM
        if current == CLIView.USER:
            cmds.append("system-view")
            sim.push(CLIView.SYSTEM)
            current = CLIView.SYSTEM

        if current not in (CLIView.SYSTEM, target):
            # 在错误的子视图，先退出到 SYSTEM
            while sim.current_view() not in (CLIView.USER, CLIView.SYSTEM):
                cmds.append("quit")
                try:
                    sim.pop()
                except ValueError:
                    break
            if sim.current_view() == CLIView.USER:
                cmds.append("system-view")
                sim.push(CLIView.SYSTEM)

        # 进入目标视图
        enter_cmd = self._get_enter_command(target, params)
        if enter_cmd:
            cmds.append(enter_cmd)
            sim.push(target, params)

        return cmds

    def _navigate_to_view(self, sim: CLIState, from_view: CLIView,
                          to_view: CLIView) -> List[str]:
        """简化：从给定视图回到目标视图。"""
        cmds: List[str] = []
        if to_view == CLIView.USER:
            while sim.current_view() != CLIView.USER:
                cmds.append("quit")
                try:
                    sim.pop()
                except ValueError:
                    break
        return cmds

    def _get_core_commands(self, action: Action) -> List[str]:
        """提取 Action 的核心配置命令。"""
        params = action.params
        cmds: List[str] = []

        if action.action_type in self.ACTION_HANDLERS:
            # 标准 Action：生成进入命令 + 配置命令
            # 进入命令已由 _navigate 处理，这里只做配置命令
            pass

        if "commands" in params:
            cmds.extend(params["commands"])

        # 特定 Action 的处理
        if action.action_type == "configure_interface":
            if "ip_address" in params and "netmask" in params:
                cmds.append(f"ip address {params['ip_address']} {params['netmask']}")
            if params.get("description"):
                cmds.append(f"description {params['description']}")
            if params.get("shutdown"):
                cmds.append("shutdown")
            elif "shutdown" in params:
                cmds.append("undo shutdown")

        elif action.action_type == "configure_vlan":
            if params.get("description"):
                cmds.append(f"description {params['description']}")

        elif action.action_type == "configure_ospf":
            if "router_id" in params:
                cmds.append(f"router-id {params['router_id']}")
            if "silent_interfaces" in params:
                for iface in params["silent_interfaces"]:
                    cmds.append(f"silent-interface {iface}")

        elif action.action_type == "configure_area":
            if "networks" in params:
                for net in params["networks"]:
                    cmds.append(f"network {net}")

        elif action.action_type == "configure_acl":
            if "rules" in params:
                for rule in params["rules"]:
                    cmds.append(rule)

        elif action.action_type in ("display", "show", "ping", "tracert", "verify",
                                     "verify_interface", "verify_ospf", "verify_vlan",
                                     "verify_stp"):
            # 验证命令直接返回
            pass

        return cmds

    def _get_enter_command(self, view: CLIView,
                           params: Dict[str, Any]) -> Optional[str]:
        """获取进入指定视图的命令。"""
        handlers: Dict[CLIView, str] = {
            CLIView.INTERFACE: "interface {ifname}",
            CLIView.VLAN: "vlan {vlan_id}",
            CLIView.OSPF: "ospf {proc_id}",
            CLIView.AREA: "area {area_id}",
            CLIView.ACL: "acl {acl_num}",
            CLIView.AAA: "aaa",
            CLIView.BGP: "bgp {as_num}",
            CLIView.RIP: "rip {proc_id}",
        }

        template = handlers.get(view)
        if template:
            try:
                return template.format(**params)
            except KeyError:
                return template
        return None

    def generate_batch(self, state: CLIState, actions: List[Action],
                       auto_return: bool = True) -> List[str]:
        """批量生成多个 Action 的命令序列。

        参数:
            state: 初始状态
            actions: Action 列表
            auto_return: 最后一个 Action 完成后是否回到用户视图

        返回:
            完整的命令序列
        """
        cmds: List[str] = []
        sim = state.clone()

        for i, action in enumerate(actions):
            is_last = (i == len(actions) - 1)
            use_return = auto_return and is_last
            batch_cmds = self.generate(sim, action, auto_return=use_return)
            cmds.extend(batch_cmds)

        return cmds
