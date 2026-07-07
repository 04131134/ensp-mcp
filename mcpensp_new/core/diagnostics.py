# -*- coding: utf-8 -*-
"""Error Diagnostics — tells AI *why* a command failed, without auto-fixing.

This is the "analytics" half of the old RecoveryEngine. It does NOT attempt
to execute fix commands — AI decides what to do with the diagnosis.

Pattern-matched error → cause → suggested next action.
"""
from __future__ import annotations

ERROR_PATTERNS: dict[str, dict] = {
    'unrecognized command': {
        'cause': '命令不在当前视图或拼写错误',
        'suggestion': '检查是否在正确视图（system-view / interface view），或检查命令拼写',
        'common_fix': '先执行 system-view 进入系统视图',
    },
    'the vlan does not exist': {
        'cause': 'VLAN 未创建',
        'suggestion': '先使用 vlan batch {id} 创建 VLAN，再配置端口',
    },
    'the interface does not exist': {
        'cause': '接口名称错误或接口不存在',
        'suggestion': '使用 display interface brief 确认接口名称',
    },
    'wrong parameter': {
        'cause': '命令参数格式不正确',
        'suggestion': '检查 ip address 格式（如 192.168.1.1 255.255.255.0）',
    },
    'too many parameters': {
        'cause': '命令包含多余参数',
        'suggestion': '移除多余参数后重试',
    },
    'ambiguous command': {
        'cause': '命令缩写不明确，匹配到多个命令',
        'suggestion': '使用完整命令名而非缩写',
    },
    'incomplete command': {
        'cause': '命令不完整，缺少必要参数',
        'suggestion': '补全缺失的参数后重试',
    },
    'please renew the default configurations': {
        'cause': '设备配置异常，需要恢复默认配置后再操作',
        'suggestion': '执行 reset saved-configuration 后重启设备',
    },
    '% incomplete': {
        'cause': '命令不完整（Cisco IOS）',
        'suggestion': '补全命令参数',
    },
    '% invalid': {
        'cause': '命令在当前模式下无效（Cisco IOS）',
        'suggestion': '检查是否在正确的配置模式下',
    },
    '% ambiguous': {
        'cause': '命令缩写不明确（Cisco IOS）',
        'suggestion': '使用完整命令名',
    },
    'error:': {
        'cause': '命令执行出错',
        'suggestion': '检查命令格式、视图和前置条件',
    },
    'neighbor state not full': {
        'cause': 'OSPF 邻居未建立或状态异常',
        'suggestion': '检查 OSPF area ID、网络类型、Hello/Dead 间隔是否匹配',
    },
    'timeout': {
        'cause': '操作超时',
        'suggestion': '等待设备稳定后重试，或使用 display 类命令先确认状态',
    },
    'connection lost': {
        'cause': '设备连接断开',
        'suggestion': '使用 connect_device 重新连接设备',
    },
}


def diagnose(error_output: str) -> dict:
    """Analyse command error output and return structured diagnosis.

    Returns:
        {
            'matched_patterns': [{'pattern': str, 'cause': str, 'suggestion': str}],
            'confidence': float,  # 0.0-1.0
            'summary': str,       # Human-readable summary for AI
        }
    """
    error_lower = error_output.lower().strip()
    if not error_lower:
        return {
            'matched_patterns': [],
            'confidence': 0.0,
            'summary': 'No error output to analyze.',
        }

    matched = []
    for pattern, info in ERROR_PATTERNS.items():
        if pattern in error_lower:
            matched.append({
                'pattern': pattern,
                'cause': info['cause'],
                'suggestion': info['suggestion'],
            })
            if 'common_fix' in info:
                matched[-1]['common_fix'] = info['common_fix']

    if not matched:
        return {
            'matched_patterns': [],
            'confidence': 0.2,
            'summary': (
                '未能匹配到已知错误模式。建议：\n'
                '1. 使用 display current-configuration 检查当前配置\n'
                '2. 使用 display interface brief 确认接口状态\n'
                '3. 确认命令在正确的视图下执行'
            ),
        }

    confidence = min(0.9, 0.4 + len(matched) * 0.2)
    lines = ['## 错误诊断']
    for m in matched:
        lines.append(f'- **{m["pattern"]}**: {m["cause"]}')
        lines.append(f'  建议: {m["suggestion"]}')
        if 'common_fix' in m:
            lines.append(f'  常见修复: {m["common_fix"]}')

    return {
        'matched_patterns': matched,
        'confidence': confidence,
        'summary': '\n'.join(lines),
    }


def diagnose_result(results: list[dict]) -> dict:
    """Diagnose a batch of command results.

    Args:
        results: [{'command': str, 'output': str, 'success': bool}, ...]
    """
    failed = [r for r in results if not r.get('success', True)]
    if not failed:
        return {
            'has_errors': False,
            'confidence': 1.0,
            'summary': '所有命令执行成功。',
        }

    diagnoses = []
    for r in failed:
        d = diagnose(r.get('output', ''))
        d['command'] = r.get('command', '')
        diagnoses.append(d)

    lines = [f'## {len(failed)} 条命令执行失败\n']
    for d in diagnoses:
        lines.append(f'### {d.get("command", "unknown")}')
        lines.append(d['summary'])
        lines.append('')

    return {
        'has_errors': True,
        'failed_count': len(failed),
        'diagnoses': diagnoses,
        'confidence': max(d['confidence'] for d in diagnoses) if diagnoses else 0.0,
        'summary': '\n'.join(lines),
    }
