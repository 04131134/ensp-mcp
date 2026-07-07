# -*- coding: utf-8 -*-
"""CLI 状态机 — 维护当前设备 View 的视图栈。

支持：USER / SYSTEM / INTERFACE / VLAN / OSPF / AREA / ACL / AAA / BGP / RIP
操作：push / pop / return_to_user / current_view / view_stack

设计原则：
- 不依赖 Telnet 连接，纯状态管理
- 与现有 command_executor.py 完全解耦
- 作为 Agent 的内部状态追踪，不直接发送命令到设备
"""
from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any


class CLIView(Enum):
    """CLI 视图枚举。"""
    USER = "USER"
    SYSTEM = "SYSTEM"
    INTERFACE = "INTERFACE"
    VLAN = "VLAN"
    OSPF = "OSPF"
    AREA = "AREA"
    ACL = "ACL"
    AAA = "AAA"
    BGP = "BGP"
    RIP = "RIP"
    UNKNOWN = "UNKNOWN"


class ViewEntry:
    """视图栈条目 — 记录视图类型和上下文参数。"""

    def __init__(self, view: CLIView, params: Optional[Dict[str, Any]] = None):
        self.view = view
        self.params = params or {}

    def __repr__(self):
        return f"ViewEntry({self.view.value}, params={self.params})"


class CLIState:
    """CLI 视图栈状态机。

    用法：
        state = CLIState()
        state.push(CLIView.SYSTEM)          # 进入系统视图
        state.current_view()                # CLIView.SYSTEM
        state.pop()                         # 退出当前视图
        state.return_to_user()              # 一键回到用户视图
    """

    # 视图退出命令映射
    EXIT_COMMANDS: Dict[CLIView, str] = {
        CLIView.USER: None,
        CLIView.SYSTEM: "quit",
        CLIView.INTERFACE: "quit",
        CLIView.VLAN: "quit",
        CLIView.OSPF: "quit",
        CLIView.AREA: "quit",
        CLIView.ACL: "quit",
        CLIView.AAA: "quit",
        CLIView.BGP: "quit",
        CLIView.RIP: "quit",
        CLIView.UNKNOWN: None,
    }

    def __init__(self, device_name: str = ""):
        """初始化 CLI 状态机。

        参数:
            device_name: 设备名称（用于日志标识）
        """
        self._device_name = device_name
        self._stack: List[ViewEntry] = [ViewEntry(CLIView.USER)]
        self._unknown_prompt: Optional[str] = None

    # ── 视图操作 ──────────────────────────────────────────

    def push(self, view: CLIView, params: Optional[Dict[str, Any]] = None) -> None:
        """进入新视图，压栈。

        参数:
            view: 目标视图
            params: 视图参数（如接口名、VLAN ID 等）
        """
        self._stack.append(ViewEntry(view, params))

    def pop(self) -> CLIView:
        """退出当前视图，返回退出前的视图。

        返回:
            退出后的当前视图

        异常:
            ValueError: 已是最底层视图（USER），无法继续 pop
        """
        if len(self._stack) <= 1:
            raise ValueError("Cannot pop: already at USER view (bottom of stack)")
        self._stack.pop()
        return self.current_view()

    def return_to_user(self) -> CLIView:
        """一键回到用户视图。使用 return 命令跳过所有中间层。

        返回:
            CLIView.USER
        """
        self._stack = [ViewEntry(CLIView.USER)]
        return CLIView.USER

    def current_view(self) -> CLIView:
        """获取当前视图。"""
        return self._stack[-1].view

    def current_params(self) -> Dict[str, Any]:
        """获取当前视图的参数。"""
        return dict(self._stack[-1].params)

    def view_stack(self) -> List[ViewEntry]:
        """获取完整视图栈（深拷贝）。"""
        return [ViewEntry(e.view, dict(e.params)) for e in self._stack]

    def stack_depth(self) -> int:
        """当前视图栈深度。"""
        return len(self._stack)

    # ── 查询 ──────────────────────────────────────────────

    def is_at_user(self) -> bool:
        """是否在用户视图。"""
        return self._stack[-1].view == CLIView.USER

    def is_at_system(self) -> bool:
        """是否在系统视图。"""
        return self._stack[-1].view == CLIView.SYSTEM

    def get_exit_command(self) -> Optional[str]:
        """获取退出当前视图所需的命令。"""
        return self.EXIT_COMMANDS.get(self._stack[-1].view)

    def needs_to_enter(self, target: CLIView, target_params: Optional[Dict[str, Any]] = None) -> List[str]:
        """计算从当前视图到达目标视图需要的命令序列。

        参数:
            target: 目标视图
            target_params: 目标视图参数

        返回:
            命令序列（如 ["system-view", "interface GigabitEthernet0/0/1"]）
        """
        cmds: List[str] = []
        current = self._stack[-1].view

        if current == target:
            return cmds

        # 方案：先回到正确的父视图，再逐层进入
        # 简化处理：return 到 USER，再逐层进入
        if target == CLIView.USER:
            # 需要退出所有层
            for _ in range(self.stack_depth() - 1):
                cmd = self.get_exit_command()
                if cmd:
                    cmds.append(cmd)
            return cmds

        # 如果目标是 SYSTEM，从 USER 进入需要 system-view
        # 如果目标是更深层，先回到系统视图再进入
        transitions = [
            (CLIView.USER, CLIView.SYSTEM, "system-view"),
            (CLIView.SYSTEM, CLIView.INTERFACE, f"interface {target_params.get('ifname', '')}" if target_params else ""),
            (CLIView.SYSTEM, CLIView.VLAN, f"vlan {target_params.get('vlan_id', '')}" if target_params else ""),
            (CLIView.SYSTEM, CLIView.OSPF, f"ospf {target_params.get('proc_id', '')}" if target_params else ""),
            (CLIView.OSPF, CLIView.AREA, f"area {target_params.get('area_id', '')}" if target_params else ""),
            (CLIView.SYSTEM, CLIView.ACL, f"acl {target_params.get('acl_num', '')}" if target_params else ""),
            (CLIView.SYSTEM, CLIView.AAA, "aaa"),
            (CLIView.SYSTEM, CLIView.BGP, f"bgp {target_params.get('as_num', '')}" if target_params else ""),
            (CLIView.SYSTEM, CLIView.RIP, f"rip {target_params.get('proc_id', '')}" if target_params else ""),
        ]

        # 简单算法：找到从当前到目标的路径
        # 如果当前在某个子视图，先回到 SYSTEM
        if current not in (CLIView.USER, CLIView.SYSTEM):
            # 回到 SYSTEM
            for _ in range(self.stack_depth() - 2):
                cmds.append("quit")
            current = CLIView.SYSTEM

        # 从当前视图到目标
        if current == CLIView.USER and target != CLIView.USER:
            cmds.append("system-view")
            current = CLIView.SYSTEM

        if current == CLIView.SYSTEM and target == CLIView.SYSTEM:
            return cmds

        # 查找 transition
        for src, dst, cmd in transitions:
            if src == current and dst == target:
                if cmd:
                    cmds.append(cmd)
                return cmds

        return cmds

    def update_from_prompt(self, prompt: str) -> CLIView:
        """根据设备 prompt 同步更新内部状态（与 PromptParser 配合使用）。
        注意：这是一个轻量更新，仅用于 Agent 内部追踪，
        不影响实际设备状态。

        参数:
            prompt: 设备提示符，如 "<Huawei>" 或 "[Huawei-ospf-1]"

        返回:
            解析后的视图
        """
        from mcpensp1.agent.prompt_parser import PromptParser
        parser = PromptParser()
        parsed = parser.parse(prompt)
        self.sync_to_view(parsed["view"], parsed.get("params"))
        return self.current_view()

    def sync_to_view(self, view: CLIView, params: Optional[Dict[str, Any]] = None) -> None:
        """直接同步到指定视图（用于 PromptParser 解析后的状态同步）。

        参数:
            view: 目标视图
            params: 视图参数
        """
        if view == CLIView.USER:
            self._stack = [ViewEntry(CLIView.USER)]
            return

        if view == CLIView.SYSTEM:
            self._stack = [ViewEntry(CLIView.USER), ViewEntry(CLIView.SYSTEM)]
            return

        # 子视图：确保 SYSTEM 在栈中
        if len(self._stack) < 2:
            self._stack.append(ViewEntry(CLIView.SYSTEM))

        # 替换 SYSTEM 之上的所有层
        self._stack = self._stack[:2]
        self._stack.append(ViewEntry(view, params))

    def clone(self) -> CLIState:
        """深拷贝当前状态。"""
        new_state = CLIState(self._device_name)
        new_state._stack = [ViewEntry(e.view, dict(e.params)) for e in self._stack]
        return new_state

    def __repr__(self):
        views = " → ".join(e.view.value for e in self._stack)
        return f"CLIState({self._device_name}: {views})"
