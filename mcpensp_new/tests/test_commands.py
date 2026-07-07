# -*- coding: utf-8 -*-
"""Tests for CommandPipeline — middleware chain, blocked commands."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.commands import (
    AutoUndoTerminalMonitor,
    BlockDangerousCommands,
    CommandContext,
    CommandPipeline,
    ExecuteCommand,
    RecordToKnowledge,
    create_default_pipeline,
)
from core.devices import DeviceManager
from core.knowledge import KnowledgeService
from driver.telnet import CommandResult, TelnetDriver


@pytest.fixture
def knowledge():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        yield KnowledgeService(d)


@pytest.fixture
def devices():
    return DeviceManager()


@pytest.fixture
def pipeline(devices, knowledge):
    return create_default_pipeline(devices, knowledge)


@pytest.mark.asyncio
async def test_block_dangerous_command(pipeline):
    ctx = CommandContext(path='127.0.0.1:2000', command='reboot')
    result = await pipeline.execute(ctx)
    assert result['success'] is False
    assert '已被拦截' in result.get('error', '')


@pytest.mark.asyncio
async def test_block_reset_command(pipeline):
    ctx = CommandContext(path='127.0.0.1:2000', command='reset saved-configuration')
    result = await pipeline.execute(ctx)
    assert result['success'] is False


@pytest.mark.asyncio
async def test_device_not_connected(pipeline):
    ctx = CommandContext(path='127.0.0.1:9999', command='display version')
    result = await pipeline.execute(ctx)
    assert result['success'] is False
    assert '未连接' in result.get('error', '')


@pytest.mark.asyncio
async def test_execute_success(knowledge):
    dm = DeviceManager()
    driver = TelnetDriver('127.0.0.1', 2000)

    mock_result = CommandResult(output='Huawei...', success=True, elapsed_ms=50)
    driver.execute = MagicMock(return_value=mock_result)
    driver.execute_async = MagicMock()
    async def fake_async(cmd):
        return mock_result
    driver.execute_async = fake_async

    dm._drivers['127.0.0.1:2000'] = driver

    pipeline = create_default_pipeline(dm, knowledge)
    ctx = CommandContext(path='127.0.0.1:2000', command='display version')
    result = await pipeline.execute(ctx)

    assert result['success'] is True
    assert result['cmd_success'] is True


@pytest.mark.asyncio
async def test_auto_undo_tm(knowledge):
    """Ensure undo terminal monitor is auto-injected before first config command."""
    dm = DeviceManager()
    driver = TelnetDriver('127.0.0.1', 2000)
    mock_result = CommandResult(output='ok', success=True, elapsed_ms=10)
    driver.execute = MagicMock(return_value=mock_result)

    received = []

    async def fake_async(cmd):
        received.append(cmd)
        return mock_result

    driver.execute_async = fake_async
    dm._drivers['127.0.0.1:2000'] = driver

    pipeline = create_default_pipeline(dm, knowledge)

    # First config command should trigger undo t m injection
    ctx1 = CommandContext(path='127.0.0.1:2000', command='system-view')
    await pipeline.execute(ctx1)

    # Check that undo terminal monitor was sent
    undo_tm_sent = any('undo terminal monitor' in c for c in received)
    assert undo_tm_sent, f'Expected undo terminal monitor, got: {received}'


def test_create_default_pipeline(devices, knowledge):
    p = create_default_pipeline(devices, knowledge)
    assert len(p._middlewares) == 4
    assert isinstance(p._middlewares[0], BlockDangerousCommands)
    assert isinstance(p._middlewares[1], AutoUndoTerminalMonitor)
    assert isinstance(p._middlewares[2], ExecuteCommand)
    assert isinstance(p._middlewares[3], RecordToKnowledge)
