# -*- coding: utf-8 -*-
"""Command Pipeline — extensible middleware chain for command execution.

Each middleware can:
- Intercept and block a command (return result immediately)
- Modify the execution context (e.g. auto-switch view)
- Inject pre-commands (e.g. undo terminal monitor)
- Execute the command and record side-effects

Pipeline is constructed from configurable middlewares at startup.
"""
from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import yaml

from core.devices import DeviceManager
from core.diagnostics import diagnose
from core.knowledge import KnowledgeService
from driver.telnet import CommandResult

logger = logging.getLogger(__name__)

# ── Blocked commands (loaded from config/security.yaml with fallback) ──

_DEFAULT_BLOCKED_EXACT = {
    'reboot', 'reset saved-configuration', 'erase startup-configuration',
    'format', 'delete', 'reset arp', 'reset bgp', 'reset ospf',
    'set authentication password', 'set user-password',
    'undo save', 'startup saved-configuration',
    'reset interface', 'reset statistics',
    'reset ip routing-table', 'reset mac-address',
    'clear configuration', 'reset arp all',
}

_DEFAULT_BLOCKED_PREFIXES = (
    'reboot', 'reset ', 'erase ', 'format ', 'delete ',
    'set authentication', 'set user-password',
    'undo save', 'startup saved-configuration',
    'clear ', 'initialize',
)


def _load_security_config() -> tuple[set[str], tuple[str, ...]]:
    """Load blocked commands from config/security.yaml.

    Falls back to hardcoded defaults if the file is missing or unreadable.
    """
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'security.yaml',
    )
    try:
        with open(config_path, encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError('Invalid security.yaml format')
        blocked_exact = set(data.get('blocked_exact', []))
        blocked_prefixes = tuple(data.get('blocked_prefixes', []))
        if not blocked_exact and not blocked_prefixes:
            raise ValueError('security.yaml is empty')
        logger.info('Loaded %d blocked exact + %d blocked prefixes from security.yaml',
                    len(blocked_exact), len(blocked_prefixes))
        return blocked_exact, blocked_prefixes
    except Exception as e:
        logger.warning('Failed to load security.yaml: %s. Using hardcoded defaults.', e)
        return _DEFAULT_BLOCKED_EXACT, _DEFAULT_BLOCKED_PREFIXES


_BLOCKED_EXACT, _BLOCKED_PREFIXES = _load_security_config()

_CONFIG_PREFIXES = (
    'system-view', 'interface ', 'vlan', 'ospf', 'vrrp', 'stp ',
    'dhcp', 'ip pool', 'ip route', 'firewall', 'capwap', 'wlan',
    'sysname', 'undo info', 'security-policy', 'aaa', 'manager-user',
    'eth-trunk',
)


@dataclass
class CommandContext:
    """Context object passed through the pipeline."""
    path: str
    command: str
    device_name: str = ''
    device_type: str = ''
    pre_commands: list[str] = field(default_factory=list)


class Middleware(ABC):
    """Abstract middleware in the command execution pipeline."""

    @abstractmethod
    async def handle(self, ctx: CommandContext,
                     next_handler: Callable[..., Awaitable[dict]]) -> dict:
        """Process or intercept a command.

        Args:
            ctx: Command execution context.
            next_handler: Callable that invokes the next middleware in chain.
                Accepts optional CommandContext to pass modified context downstream.

        Returns:
            dict: {'success': bool, 'output': str, ...}
        """
        ...


class BlockDangerousCommands(Middleware):
    """Reject dangerous commands before they reach the device."""

    async def handle(self, ctx: CommandContext, next_handler) -> dict:
        cmd_lower = ctx.command.strip().lower()
        if cmd_lower in _BLOCKED_EXACT:
            return {
                'success': False,
                'cmd_success': False,
                'output': '',
                'error': f'危险命令已被拦截: {cmd_lower}',
                'path': ctx.path,
                'elapsed_ms': 0,
            }
        for prefix in _BLOCKED_PREFIXES:
            if cmd_lower.startswith(prefix):
                return {
                    'success': False,
                    'cmd_success': False,
                    'output': '',
                    'error': f'危险命令已被拦截: {cmd_lower}',
                    'path': ctx.path,
                    'elapsed_ms': 0,
                }
        return await next_handler(ctx)


class AutoUndoTerminalMonitor(Middleware):
    """Auto-inject 'undo terminal monitor' before first config command."""

    def __init__(self) -> None:
        self._done: set[str] = set()

    async def handle(self, ctx: CommandContext, next_handler) -> dict:
        cmd_lower = ctx.command.strip().lower()
        if cmd_lower.startswith(_CONFIG_PREFIXES):
            key = f'undo_tm_{ctx.path}'
            if key not in self._done and cmd_lower not in (
                    'undo terminal monitor', 'undo t m'):
                ctx.pre_commands.append('undo terminal monitor')
                self._done.add(key)
            elif cmd_lower in ('undo terminal monitor', 'undo t m'):
                self._done.add(key)
        return await next_handler(ctx)


class ExecuteCommand(Middleware):
    """Actually execute the command via TelnetDriver."""

    def __init__(self, devices: DeviceManager) -> None:
        self._devices = devices

    async def handle(self, ctx: CommandContext, next_handler) -> dict:
        driver = self._devices.get_driver(ctx.path)
        if not driver:
            return {
                'success': False,
                'cmd_success': False,
                'output': '',
                'error': f'设备未连接: {ctx.path}',
                'path': ctx.path,
                'elapsed_ms': 0,
            }

        for pre_cmd in ctx.pre_commands:
            try:
                await driver.execute_async(pre_cmd)
            except Exception:
                pass

        try:
            result: CommandResult = await driver.execute_async(ctx.command)
        except ConnectionError:
            self._devices.disconnect(ctx.path)
            return {
                'success': False,
                'cmd_success': False,
                'output': '',
                'error': '连接断开',
                'path': ctx.path,
                'elapsed_ms': 0,
            }
        except Exception as e:
            return {
                'success': False,
                'cmd_success': False,
                'output': str(e)[:500],
                'error': str(e)[:200],
                'path': ctx.path,
                'elapsed_ms': 0,
            }

        return {
            'success': True,
            'cmd_success': result.success,
            'output': result.output,
            'errors': result.errors,
            'path': ctx.path,
            'elapsed_ms': result.elapsed_ms,
        }


class RecordToKnowledge(Middleware):
    """Fire-and-forget knowledge base recording."""

    def __init__(self, knowledge: KnowledgeService) -> None:
        self._kb = knowledge

    async def handle(self, ctx: CommandContext, next_handler) -> dict:
        result = await next_handler(ctx)
        try:
            self._kb.record_command(
                command=ctx.command,
                result=CommandResult(
                    output=result.get('output', ''),
                    success=result.get('cmd_success', False),
                    elapsed_ms=result.get('elapsed_ms', 0),
                    errors=result.get('errors', []),
                ),
                device_path=ctx.path,
                device_type=ctx.device_type,
            )
        except Exception:
            pass
        return result


# ── Pipeline ──────────────────────────────────────────────────

class CommandPipeline:
    """Orchestrates middleware chain for command execution."""

    def __init__(self, middlewares: list[Middleware]) -> None:
        self._middlewares = middlewares

    async def execute(self, ctx: CommandContext) -> dict:
        """Execute a command through the pipeline."""

        async def _run(index: int) -> dict:
            if index >= len(self._middlewares):
                return {
                    'success': False,
                    'cmd_success': False,
                    'output': '',
                    'error': 'Pipeline exhausted without result',
                    'path': ctx.path,
                    'elapsed_ms': 0,
                }

            async def _next(next_ctx: CommandContext | None = None) -> dict:
                if next_ctx is not None:
                    return await self._middlewares[index].handle(
                        next_ctx, lambda c=next_ctx: _run(index + 1))
                return await _run(index + 1)

            return await self._middlewares[index].handle(ctx, _next)

        return await _run(0)


def create_default_pipeline(
    devices: DeviceManager,
    knowledge: KnowledgeService,
) -> CommandPipeline:
    """Create the default middleware pipeline."""
    return CommandPipeline([
        BlockDangerousCommands(),
        AutoUndoTerminalMonitor(),
        ExecuteCommand(devices),
        RecordToKnowledge(knowledge),
    ])
