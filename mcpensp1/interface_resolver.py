# -*- coding: utf-8 -*-
"""接口映射自动推理（第三阶段 Step7）

多源推理链：
1. 设备型号规则（盒式 0/0/(N+1) vs 子卡 0/0/N）— .topo 解析时主逻辑
2. display interface brief 校验（可选，需设备连接）— 运行时增强
3. 回退 Index{index} — 兜底

工作记忆铁律：永远不信任 .topo 的 srcIndex，下接口命令前必跑 display interface brief

设备型号规则（来自实战经验）：
- 盒式设备（S5700/S3700/AC6605）：端口从 1 起始 → srcIndex=N → G0/0/(N+1)
- 子卡设备（AR3260/USG6000V）：端口从 0 起始 → srcIndex=N → G0/0/N

向后兼容：model 为 None 时默认盒式（与旧 _build_interface_map 行为一致）
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# 盒式设备（端口 1 起始）：华为 S 系列交换机、AC 无线控制器
_BOX_MODEL_KEYWORDS = (
    'S5700', 'S3700', 'S2700', 'S5300', 'S3300', 'AC6605', 'AC6005', 'ACU2',
)

# 子卡设备（端口 0 起始）：华为 AR 系列路由器、USG 防火墙
_MODULE_MODEL_KEYWORDS = (
    'AR3260', 'AR2220', 'AR1200', 'AR169', 'AR2200', 'AR200',
    'USG6000', 'USG5500', 'USG6500',
)


def _is_module_model(model: Optional[str]) -> bool:
    """判断是否为子卡设备（端口 0 起始）。

    AR 系列、USG 系列、含 Router/FW 关键词的视为子卡。
    model 为 None/空时返回 False（默认盒式，向后兼容）。
    """
    if not model:
        return False
    model_upper = model.upper()
    for kw in _MODULE_MODEL_KEYWORDS:
        if kw.upper() in model_upper:
            return True
    # 通用判断：AR 开头的路由器、USG 防火墙
    if model_upper.startswith('AR') or 'USG' in model_upper:
        return True
    if 'ROUTER' in model_upper or 'FW' in model_upper:
        return True
    return False


def _is_box_model(model: Optional[str]) -> bool:
    """判断是否为盒式设备（端口 1 起始）。

    S 系列交换机、AC 无线控制器。model 为 None/空时返回 True（默认盒式）。
    """
    if not model:
        return True
    model_upper = model.upper()
    for kw in _BOX_MODEL_KEYWORDS:
        if kw.upper() in model_upper:
            return True
    # S 开头的交换机（排除 STA 无线终端）
    if model_upper.startswith('S') and 'STA' not in model_upper:
        return True
    if 'SWITCH' in model_upper:
        return True
    return False


def build_interface_map(dev_element, model: Optional[str] = None) -> Dict[int, str]:
    """根据设备型号构建 srcIndex → 接口名映射（型号感知）。

    盒式设备（S5700/S3700/AC6605）：端口 1 起始 → G0/0/1, G0/0/2, ...
    子卡设备（AR3260/USG6000V）：端口 0 起始 → G0/0/0, G0/0/1, ...

    Args:
        dev_element: .topo XML 的 <dev> 元素，含 <slot><interface interfacename="GE" count="24"/>
        model: 设备型号（如 "S5700"、"AR3260"）。None 时默认盒式（向后兼容旧行为）

    Returns:
        {srcIndex: interface_name} 映射，srcIndex 从 0 起（与旧 _build_interface_map 一致）
    """
    ifaces = []
    type_counter = {}
    is_module = _is_module_model(model)
    # 盒式端口 1 起始，子卡端口 0 起始
    start_idx = 0 if is_module else 1
    for slot in dev_element.iter('slot'):
        for iface in slot.iter('interface'):
            name = iface.get('interfacename', '')
            try:
                count = int(iface.get('count', 0))
            except (ValueError, TypeError):
                count = 0
            for _ in range(count):
                idx = type_counter.get(name, start_idx - 1) + 1
                ifaces.append(f'{name}0/0/{idx}')
                type_counter[name] = idx
    if is_module:
        logger.debug('[InterfaceResolver] %s 子卡设备，端口 0 起始', model)
    return {idx: name for idx, name in enumerate(ifaces)}


def resolve_interface(iface_map: Dict[int, str], index) -> str:
    """解析接口索引为接口名，查不到回退 Index{index}。

    与旧 app._resolve_interface 签名一致，向后兼容。
    """
    try:
        return iface_map.get(int(index), f'Index{index}')
    except (ValueError, TypeError):
        return f'Index{index}'


class InterfaceResolver:
    """多源接口推理器（型号规则 + 可选 display 校验 + 回退）。

    工作记忆铁律：永远不信任 .topo 的 srcIndex，下接口命令前必跑 display interface brief。
    本类提供 display 校验能力，但 .topo 解析时设备可能未连接，display 校验为可选运行时增强。
    """

    def __init__(self, command_executor: Optional[Callable[[str, str], Dict[str, Any]]] = None):
        """
        Args:
            command_executor: 可选，命令执行函数 (device_path, command) -> result。
                              注入后可用 verify_by_display 进行运行时校验。
        """
        self._executor = command_executor

    def build_map(self, dev_element, model: Optional[str] = None) -> Dict[int, str]:
        """构建接口映射（委托给模块级 build_interface_map）。"""
        return build_interface_map(dev_element, model)

    def resolve(self, iface_map: Dict[int, str], index) -> str:
        """解析接口名（委托给模块级 resolve_interface）。"""
        return resolve_interface(iface_map, index)

    def verify_by_display(self, device_path: str, interface_name: str) -> Optional[bool]:
        """用 display interface brief 校验接口是否真实存在（需设备连接）。

        工作记忆铁律：下接口命令前必跑 display interface brief。

        Returns:
            True: 接口存在
            False: 接口不存在
            None: 未注入 executor / 设备未连接 / 执行异常 / 无法判断
        """
        if not self._executor or not device_path:
            return None
        try:
            resp = self._executor(device_path, 'display interface brief')
            output = resp.get('output', '') if isinstance(resp, dict) else str(resp)
            return interface_name in output
        except Exception as e:
            logger.warning('[InterfaceResolver] display 校验异常 %s: %s', interface_name, e)
            return None

    def resolve_with_verification(
        self,
        dev_element,
        model: Optional[str],
        index,
        device_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """多源推理主入口：型号规则映射 + 可选 display 校验。

        Args:
            dev_element: .topo XML 的 <dev> 元素
            model: 设备型号
            index: srcIndex
            device_path: 设备路径（如 '127.0.0.1:2000'），传入则尝试 display 校验

        Returns:
            {
                'interface': 推理出的接口名,
                'model': 设备型号,
                'is_module': 是否子卡设备,
                'verified': display 校验结果 (True/False/None),
                'source': 推理来源 ('rule'/'fallback')
            }
        """
        is_module = _is_module_model(model)
        iface_map = self.build_map(dev_element, model)
        resolved = self.resolve(iface_map, index)
        source = 'rule' if not resolved.startswith('Index') else 'fallback'

        verified = None
        if device_path and self._executor and source == 'rule':
            verified = self.verify_by_display(device_path, resolved)
            # display 校验失败时仍返回推理结果，但标记 verified=False，由调用方决策

        return {
            'interface': resolved,
            'model': model or 'unknown',
            'is_module': is_module,
            'verified': verified,
            'source': source,
        }
