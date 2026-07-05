# -*- coding: utf-8 -*-
"""Command Executor - handles sending commands to eNSP devices.

Extracted from app.py. Provides send_command, batch_command, and related
command execution logic that was previously inline.
"""
from __future__ import annotations
import time
import logging
from typing import Any, Dict, List, Optional
from device_manager import dm

logger = logging.getLogger(__name__)

# ---- Blocked Commands ----

BLOCKED_COMMANDS = {
    'reboot', 'reset saved-configuration', 'erase startup-configuration',
    'format', 'delete', 'reset arp', 'reset bgp', 'reset ospf',
    'set authentication password', 'set user-password',
    'undo save', 'startup saved-configuration',
    'reset interface', 'reset statistics',
    'reset ip routing-table', 'reset mac-address',
    'clear configuration', 'reset arp all',
}

BLOCKED_PREFIXES = (
    'reboot', 'reset ', 'erase ', 'format ', 'delete ',
    'set authentication', 'set user-password',
    'undo save', 'startup saved-configuration',
    'clear ', 'initialize',
)

# ---- Command Catalog ----

COMMAND_CATALOG: Dict[str, Dict[str, Any]] = {}


def is_blocked_command(cmd_lower: str) -> bool:
    """Check if a command is in the blocked list."""
    if cmd_lower in BLOCKED_COMMANDS:
        return True
    for prefix in BLOCKED_PREFIXES:
        if cmd_lower.startswith(prefix):
            return True
    return False


class CommandExecutor:
    """Executes commands on eNSP devices via Telnet."""

    def __init__(self, knowledge_base=None):
        self.kb = knowledge_base
        self._undo_done: set = set()

    def send_command(self, path: str, command: str) -> dict:
        """Send a single command to a connected device."""
        conn = dm.get(path)
        if not conn:
            return {'success': False, 'error': 'Device not connected'}

        cmd_lower = command.strip().lower()
        if is_blocked_command(cmd_lower):
            return {'success': False, 'error': f'Blocked dangerous command: {cmd_lower}'}

        try:
            # Auto undo terminal monitor before first config command
            config_prefixes = ('system-view', 'interface ', 'vlan', 'ospf', 'vrrp', 'stp ',
                'dhcp', 'ip pool', 'ip route', 'firewall', 'capwap', 'wlan', 'sysname',
                'undo info', 'security-policy', 'aaa', 'manager-user', 'eth-trunk')

            if cmd_lower.startswith(config_prefixes) or cmd_lower in ('undo terminal monitor', 'undo t m'):
                _undo_key = f'_undo_tm_{path}'
                if _undo_key not in self._undo_done and cmd_lower not in ('undo terminal monitor', 'undo t m'):
                    try:
                        conn.send_cmd('undo terminal monitor')
                        self._undo_done.add(_undo_key)
                        time.sleep(0.1)
                    except Exception:
                        pass
                elif cmd_lower in ('undo terminal monitor', 'undo t m'):
                    self._undo_done.add(_undo_key)

            t0 = time.time()
            result = conn.send_cmd(command)
            elapsed = round(time.time() - t0, 3)

            _errs = ['Error:', 'Unrecognized command', 'Wrong parameter',
                     'Too many parameters', 'Ambiguous command', 'Incomplete command',
                     'Please renew the default configurations']
            cmd_success = bool(result and not any(kw in result for kw in _errs))

            if self.kb:
                dt = dm.get_type(path)
                self.kb.record_command(command, result, device_type=dt, device_path=path, success=cmd_success)

            return {'success': True, 'path': path, 'output': result,
                    'response_time': elapsed, 'cmd_success': cmd_success}

        except ConnectionError:
            dm.remove(path)
            dm.remove_name(path)
            return {'success': False, 'error': 'Connection lost, device disconnected'}
        except Exception as e:
            logger.error('Command failed for %s: %s', path, str(e)[:200])
            if self.kb:
                dt = dm.get_type(path)
                self.kb.record_command(command, 'Error', device_type=dt, device_path=path, success=False)
            return {'success': False, 'error': str(e)[:200]}

    def batch_command(self, path: str, commands: List[str],
                       wait: float = 0.1, auto_view: bool = True,
                       auto_undo_tm: bool = True) -> dict:
        """Send a batch of commands to a device."""
        conn = dm.get(path)
        if not conn:
            return {'success': False, 'error': 'Device not connected'}

        results = []
        cmd_count = 0
        success_count = 0

        for cmd in commands:
            cmd_lower = cmd.strip().lower()
            if is_blocked_command(cmd_lower):
                results.append({'command': cmd, 'success': False, 'output': 'Blocked'})
                continue

            cmd_count += 1
            try:
                t0 = time.time()
                output = conn.send_cmd(cmd)
                elapsed = round(time.time() - t0, 3)
                _errs = ['Error:', 'Unrecognized command', 'Wrong parameter']
                ok = bool(output and not any(kw in output for kw in _errs))
                if ok:
                    success_count += 1
                results.append({'command': cmd, 'success': ok, 'output': output, 'response_time': elapsed})
                time.sleep(wait)
            except ConnectionError:
                dm.remove(path)
                dm.remove_name(path)
                results.append({'command': cmd, 'success': False, 'output': 'Connection lost'})
                return {'success': False, 'error': 'Connection lost', 'results': results,
                        'total': cmd_count, 'success_count': success_count}
            except Exception as e:
                results.append({'command': cmd, 'success': False, 'output': str(e)[:200]})

        return {'success': True, 'path': path, 'results': results,
                'total': cmd_count, 'success_count': success_count}

    def send_command_to_group(self, paths: List[str], command: str) -> dict:
        """Send the same command to multiple devices."""
        results = []
        for path in paths:
            r = self.send_command(path, command)
            results.append({'path': path, **r})
        return {'success': True, 'results': results}


# Singleton
cmd_executor = CommandExecutor()
