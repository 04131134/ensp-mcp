# -*- coding: utf-8 -*-
"""Device Manager - centralized device state management for eNSP-MCP.

Extracted from app.py to provide a single point of truth for device connections,
names, types, and topology names.
"""
from __future__ import annotations
import os
import socket
import threading
from typing import Optional, Dict, List

from connection import TelnetConnection

logger = __import__('logging').getLogger(__name__)


class DeviceManager:
    """Thread-safe manager for eNSP device connections and metadata."""

    def __init__(self):
        self._devices: Dict[str, TelnetConnection] = {}
        self._names: Dict[str, str] = {}
        self._types: Dict[str, str] = {}
        self._topo_names: Dict[int, str] = {}
        self._role_counters: Dict[str, int] = {}
        self._state_lock = threading.Lock()
        self._name_lock = threading.Lock()
        self._role_lock = threading.Lock()

    # ---- Device CRUD ----

    def list_all(self) -> Dict[str, TelnetConnection]:
        """Return a snapshot of all connected devices (thread-safe)."""
        with self._state_lock:
            return dict(self._devices)

    def get(self, path: str) -> Optional[TelnetConnection]:
        """Get a device connection by path."""
        with self._state_lock:
            return self._devices.get(path)

    def set(self, path: str, conn: TelnetConnection) -> None:
        """Set (replace) a device connection. Closes old connection if exists."""
        with self._state_lock:
            old = self._devices.get(path)
            if old:
                try:
                    old.close()
                except OSError:
                    pass
            self._devices[path] = conn

    def remove(self, path: str) -> Optional[TelnetConnection]:
        """Remove and return a device connection."""
        with self._state_lock:
            return self._devices.pop(path, None)

    def has(self, path: str) -> bool:
        """Check if a device is connected."""
        with self._state_lock:
            return path in self._devices

    # ---- Name management ----

    def get_name(self, path: str, default: str = '') -> str:
        """Get device display name."""
        with self._name_lock:
            return self._names.get(path, default or path)

    def set_name(self, path: str, name: str) -> None:
        """Set device display name."""
        with self._name_lock:
            self._names[path] = name

    def remove_name(self, path: str) -> Optional[str]:
        """Remove and return device name."""
        with self._name_lock:
            return self._names.pop(path, None)

    def get_type(self, path: str) -> str:
        """Get device type."""
        with self._name_lock:
            return self._types.get(path, 'unknown')

    def set_type(self, path: str, dtype: str) -> None:
        """Set device type."""
        with self._name_lock:
            self._types[path] = dtype

    # ---- Topology name management ----

    def get_topo_name(self, port: int) -> Optional[str]:
        """Get topology name for a port."""
        return self._topo_names.get(port)

    def set_topo_name(self, port: int, name: str) -> None:
        """Set topology name for a port."""
        self._topo_names[port] = name

    def get_topo_names(self) -> Dict[int, str]:
        """Get all topology name mappings."""
        return dict(self._topo_names)

    def next_role_name(self, role: str) -> str:
        """Get next auto-incremented name for a device role."""
        with self._role_lock:
            cnt = self._role_counters.get(role, 0) + 1
            self._role_counters[role] = cnt
        return f'{role}{cnt}'

    # ---- Scanning ----

    def scan_ports(self, start: int = 2000, end: int = 2050) -> List[dict]:
        """Scan for open TCP ports (eNSP devices)."""
        found = []
        for port in range(start, end + 1):
            s = None
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    found.append({'port': port, 'path': f'127.0.0.1:{port}'})
            except Exception:
                pass
            finally:
                if s:
                    try:
                        s.close()
                    except OSError:
                        pass
        return found

    def scan_devices(self, start: int = 2000, end: int = 2050) -> List[dict]:
        """Scan and annotate devices with names and types."""
        r = self.scan_ports(start, end)
        for d in r:
            port = d['port']
            topo_name = self._topo_names.get(port)
            d['name'] = topo_name or self._names.get(d['path'], d['path'])
            d['device_type'] = self._types.get(d['path'], 'unknown')
        return r

    def get_connected_summary(self) -> List[dict]:
        """Get a list of all connected devices with metadata."""
        result = []
        for path in list(self._devices.keys()):
            conn = self._devices.get(path)
            if not conn:
                continue
            port = int(path.split(':')[1])
            topo_name = self._topo_names.get(port)
            name = topo_name or self._names.get(path, path)
            result.append({
                'path': path, 'port': port,
                'name': name,
                'device_type': self._types.get(path, 'unknown'),
            })
        return result


# Singleton instance
dm = DeviceManager()
