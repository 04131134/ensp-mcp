# -*- coding: utf-8 -*-
"""View-aware command routing for Huawei VRP devices.

Key features:
- Maps every command to its required view (user/system)
- Detects current view from prompt
- Auto-switches view when needed
- VRP cool-down protection: after 3+ consecutive quit/return, wait 3s
"""
from __future__ import annotations
import time, logging, re

logger = logging.getLogger(__name__)


# Commands that MUST run in system view
SYSTEM_VIEW_PREFIXES = (
    'interface ', 'vlan', 'ospf', 'bgp', 'vrrp', 'stp ',
    'dhcp', 'ip pool', 'ip route', 'firewall', 'capwap', 'wlan',
    'sysname', 'undo info', 'security-policy', 'aaa',
    'manager-user', 'eth-trunk', 'ip address', 'port ',
    'traffic-filter', 'rule ', 'description ', 'network ',
    'area ', 'router-id', 'silent-interface', 'import-route',
    'default-route', 'revision-level', 'region-name',
    'instance ', 'active region', 'gateway-list', 'dns-list',
    'dhcp select', 'service-vlan', 'set priority', 'add interface',
    'undo shutdown', 'shutdown', 'service-manage',
    'security-profile', 'ssid-profile', 'vap-profile',
    'ap-id', 'ap-mac', 'ap-name', 'ap-group', 'radio ',
    'undo ', 'authentication-profile', 'mac-authen', 'dot1x',
    'ntp-service', 'snmp-agent', 'user-interface',
    'authentication-mode', 'idle-timeout', 'nat ',
    'ipsec', 'pki', 'license', 'undo', 'snmp',
    'mode lacp', 'mode manual', 'load-balance',
    'max active-linknumber',
)

# Commands that MUST run in user view
USER_VIEW_PREFIXES = (
    'display ', 'show ', 'dir ',
    'ping', 'tracert', 'traceroute', 'telnet',
    'save',
    'system-view',
    'startup saved-configuration',
)

NAVIGATION_COMMANDS = {'system-view', 'quit', 'return', 'exit'}
VRP_COOLDOWN_AFTER = 3
VRP_COOLDOWN_SECONDS = 3.0


class ViewRouter:
    """Routes commands to the correct VRP view."""

    def __init__(self):
        self._consecutive_quits = {}
        self._current_view = {}

    def classify(self, cmd: str) -> str:
        cmd_lower = cmd.strip().lower()
        if cmd_lower in NAVIGATION_COMMANDS:
            return 'navigation'
        if cmd_lower.startswith(SYSTEM_VIEW_PREFIXES):
            return 'system'
        if cmd_lower.startswith(USER_VIEW_PREFIXES):
            return 'user'
        return 'system'

    def detect_view(self, conn) -> str:
        if hasattr(conn, 'current_view'):
            return conn.current_view
        return 'unknown'

    def update_view(self, path: str, view: str) -> None:
        self._current_view[path] = view

    def _handle_cooldown(self, path: str, cmd_lower: str) -> None:
        if cmd_lower in ('quit', 'return'):
            self._consecutive_quits[path] = self._consecutive_quits.get(path, 0) + 1
            if self._consecutive_quits[path] >= VRP_COOLDOWN_AFTER:
                logger.info('VRP cool-down on %s (%d quits), waiting %.1fs',
                           path, self._consecutive_quits[path], VRP_COOLDOWN_SECONDS)
                time.sleep(VRP_COOLDOWN_SECONDS)
                self._consecutive_quits[path] = 0
        else:
            self._consecutive_quits[path] = 0

    def ensure_view(self, conn, path: str, required_view: str) -> bool:
        if required_view == 'navigation':
            return True
        current = self.detect_view(conn)
        if current == required_view:
            return True
        if required_view == 'system' and current != 'system':
            try:
                conn.send_cmd('system-view')
                time.sleep(0.2)
                self.update_view(path, 'system')
                return True
            except Exception as e:
                logger.warning('ViewRouter: %s system-view switch failed: %s', path, e)
                return False
        if required_view == 'user' and current != 'user':
            try:
                conn.send_cmd('return')
                time.sleep(0.3)
                self.update_view(path, 'user')
                return True
            except Exception as e:
                logger.warning('ViewRouter: %s return switch failed: %s', path, e)
                return False
        return False

    def before_command(self, conn, path: str, cmd: str) -> bool:
        cmd_lower = cmd.strip().lower()
        required = self.classify(cmd)
        self._handle_cooldown(path, cmd_lower)
        if cmd_lower == 'system-view':
            self.update_view(path, 'system')
            return True
        if cmd_lower in ('quit', 'return'):
            return True
        return self.ensure_view(conn, path, required)


view_router = ViewRouter()


ERROR_PATTERNS = [
    'Error:', 'Unrecognized command', 'Wrong parameter',
    'Too many parameters', 'Ambiguous command', 'Incomplete command',
    'Please renew the default configurations',
]

def check_command_error(output: str) -> dict:
    errors = [p for p in ERROR_PATTERNS if p in output]
    return {'success': len(errors) == 0, 'errors': errors}
