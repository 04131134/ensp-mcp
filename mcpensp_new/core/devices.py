# -*- coding: utf-8 -*-
"""Device Manager — single source of truth for device state.

Each device has:
- A TelnetDriver (the I/O channel)
- A cached name (from display current-configuration | include sysname)
- A cached type (huawei/h3c/cisco/juniper/unknown)
- Topology name mapping (port → name, from user-uploaded topology)

Built-in heartbeat: background task that probes every connected device.
"""
from __future__ import annotations

import asyncio
import logging
import re
import socket
import threading
from typing import Callable

from driver.telnet import TelnetDriver

logger = logging.getLogger(__name__)


class DeviceManager:
    """Thread-safe device lifecycle manager."""

    def __init__(self) -> None:
        self._drivers: dict[str, TelnetDriver] = {}
        self._names: dict[str, str] = {}
        self._types: dict[str, str] = {}
        self._topo_names: dict[int, str] = {}
        self._lock = threading.RLock()
        self._heartbeat_interval = 30
        self._max_reconnect = 3
        self._reconnect_counts: dict[str, int] = {}
        self._on_status_change: Callable[[str, bool, str], None] | None = None

    # ── connection CRUD ──────────────────────────────────────

    def connect(self, port: int) -> str:
        """Connect to device at port. Returns its path '127.0.0.1:{port}'."""
        path = f'127.0.0.1:{port}'
        with self._lock:
            existing = self._drivers.get(path)
            if existing is not None:
                try:
                    existing.is_alive(timeout=1.0)
                    return path
                except Exception:
                    existing.close()
                    del self._drivers[path]

        import time
        driver = TelnetDriver('127.0.0.1', port)
        driver.connect()

        try:
            driver.handle_firewall_login()
        except Exception:
            pass

        try:
            driver.execute('undo terminal monitor')
            time.sleep(0.1)
        except Exception:
            pass

        name = self._detect_device_name(driver)
        dtype = self._detect_device_type(name)

        with self._lock:
            self._drivers[path] = driver
            self._names[path] = name
            self._types[path] = dtype
            self._reconnect_counts.pop(path, None)

        return path

    def disconnect(self, path: str) -> None:
        with self._lock:
            driver = self._drivers.pop(path, None)
            if driver:
                driver.close()
            self._names.pop(path, None)
            self._types.pop(path, None)
            self._reconnect_counts.pop(path, None)

    def get_driver(self, path: str) -> TelnetDriver | None:
        with self._lock:
            return self._drivers.get(path)

    def has(self, path: str) -> bool:
        with self._lock:
            return path in self._drivers

    def list_all(self) -> list[dict]:
        with self._lock:
            result = []
            for path in self._drivers:
                port = int(path.split(':')[1])
                topo_name = self._topo_names.get(port)
                result.append({
                    'path': path,
                    'port': port,
                    'name': topo_name or self._names.get(path, path),
                    'device_type': self._types.get(path, 'unknown'),
                })
            return result

    # ── metadata ─────────────────────────────────────────────

    def get_name(self, path: str) -> str:
        with self._lock:
            return self._names.get(path, path)

    def get_type(self, path: str) -> str:
        with self._lock:
            return self._types.get(path, 'unknown')

    def rename(self, path: str, name: str) -> None:
        with self._lock:
            self._names[path] = name

    # ── topology names ───────────────────────────────────────

    def get_topo_name(self, port: int) -> str | None:
        return self._topo_names.get(port)

    def set_topo_name(self, port: int, name: str) -> None:
        self._topo_names[port] = name

    def get_topo_names(self) -> dict[int, str]:
        return dict(self._topo_names)

    # ── scanning ─────────────────────────────────────────────

    def scan_ports(self, start: int = 2000, end: int = 2050) -> list[int]:
        """Return list of open TCP ports in range."""
        found: list[int] = []
        for port in range(start, end + 1):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    found.append(port)
                s.close()
            except Exception:
                pass
        return found

    def scan_devices(self, start: int = 2000, end: int = 2050) -> list[dict]:
        """Scan ports and annotate with cached metadata."""
        ports = self.scan_ports(start, end)
        result = []
        for port in ports:
            path = f'127.0.0.1:{port}'
            topo_name = self._topo_names.get(port)
            result.append({
                'port': port,
                'path': path,
                'name': topo_name or self._names.get(path, path),
                'device_type': self._types.get(path, 'unknown'),
            })
        return result

    # ── heartbeat (built-in) ─────────────────────────────────

    def on_status_change(self, callback: Callable[[str, bool, str], None]) -> None:
        """Register callback(path, alive:bool, message:str) for status changes."""
        self._on_status_change = callback

    async def start_heartbeat(self, interval: int = 30,
                               max_reconnect: int = 3) -> None:
        """Background heartbeat loop. Use asyncio.create_task() to run."""
        self._heartbeat_interval = interval
        self._max_reconnect = max_reconnect

        while True:
            await asyncio.sleep(self._heartbeat_interval)
            try:
                paths = list(self._drivers.keys())
                for path in paths:
                    alive = await self._check_device(path)
                    name = self._names.get(path, path)
                    if not alive:
                        with self._lock:
                            count = self._reconnect_counts.get(path, 0) + 1
                            self._reconnect_counts[path] = count
                        if count <= self._max_reconnect:
                            self._try_reconnect(path)
                        elif self._on_status_change:
                            self._on_status_change(path, False,
                                                    f'{name} 已断开')
                    else:
                        self._reconnect_counts.pop(path, None)
            except Exception:
                logger.exception('Heartbeat cycle failed')

    async def _check_device(self, path: str) -> bool:
        """Probe a device. Runs in executor to avoid blocking event loop."""
        driver = self._drivers.get(path)
        if driver is None:
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, driver.is_alive, 3.0)

    def _try_reconnect(self, path: str) -> None:
        """Attempt to reconnect a failed device."""
        with self._lock:
            driver = self._drivers.get(path)
            if driver is None:
                return
            port = driver.port
        try:
            new_driver = TelnetDriver('127.0.0.1', port)
            new_driver.connect()
            with self._lock:
                old = self._drivers.get(path)
                if old:
                    try:
                        old.close()
                    except Exception:
                        pass
                self._drivers[path] = new_driver
            name = self._names.get(path, path)
            if self._on_status_change:
                self._on_status_change(path, True, f'{name} 已恢复')
        except Exception as e:
            logger.debug('Reconnect failed for %s: %s', path, e)

    # ── detection helpers ────────────────────────────────────

    @staticmethod
    def _detect_device_name(driver: TelnetDriver) -> str:
        try:
            raw = driver.execute('display version').output
            if not raw:
                return ''
            lower = raw.lower()
            if 'huawei' in lower or 'h3c' in lower:
                nr = driver.execute(
                    'display current-configuration | include sysname').output
                if nr and 'Unrecognized' not in nr and 'Error' not in nr:
                    m = re.search(r'^sysname\s+(\S+)', nr,
                                  re.IGNORECASE | re.MULTILINE)
                    if m:
                        return m.group(1)
            return ''
        except Exception:
            return ''

    @staticmethod
    def _detect_device_type(name: str) -> str:
        upper = name.upper()
        if 'LSW' in upper or 'SW' in upper:
            return 'switch'
        if 'AR' in upper:
            return 'router'
        if 'AC' in upper:
            return 'ac'
        if 'AP' in upper:
            return 'ap'
        if 'FW' in upper or 'USG' in upper:
            return 'firewall'
        if 'PC' in upper:
            return 'pc'
        return 'unknown'
