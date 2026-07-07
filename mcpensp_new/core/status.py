# -*- coding: utf-8 -*-
"""Device Status Monitor — lightweight health check for connected devices.

Provides:
- Per-device connectivity probe (TCP-level)
- Prompt detection (session-level)
- Aggregate status summary for all connected devices

Design: pure detection, no auto-repair. AI decides what to do with the results.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from core.devices import DeviceManager

logger = logging.getLogger(__name__)


@dataclass
class DeviceStatus:
    path: str
    name: str
    device_type: str
    tcp_alive: bool
    session_alive: bool
    checked_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StatusMonitor:
    """Checks device health at the TCP and application-session level."""

    def __init__(self, devices: DeviceManager) -> None:
        self._devices = devices

    def check_one(self, path: str) -> DeviceStatus | None:
        """Probe a single device. Returns None if device is not registered."""
        driver = self._devices.get_driver(path)
        if driver is None:
            return None

        tcp_alive = False
        session_alive = False

        try:
            tcp_alive = driver.is_alive(timeout=2.0)
        except Exception:
            pass

        if tcp_alive:
            try:
                session_alive = driver.is_alive(timeout=2.0)
            except Exception:
                pass

        return DeviceStatus(
            path=path,
            name=self._devices.get_name(path),
            device_type=self._devices.get_type(path),
            tcp_alive=tcp_alive,
            session_alive=session_alive,
            checked_at=_now(),
        )

    def check_all(self) -> list[dict]:
        """Probe every connected device and return status list."""
        results: list[dict] = []
        for path in list(self._devices._drivers.keys()):
            status = self.check_one(path)
            if status is None:
                results.append({
                    'path': path,
                    'name': self._devices.get_name(path),
                    'device_type': self._devices.get_type(path),
                    'error': 'device not registered',
                })
            else:
                results.append({
                    'path': status.path,
                    'name': status.name,
                    'device_type': status.device_type,
                    'tcp_alive': status.tcp_alive,
                    'session_alive': status.session_alive,
                    'checked_at': status.checked_at,
                })
        return results

    def summary(self) -> dict:
        """Return aggregate status summary for all connected devices."""
        all_status = self.check_all()
        total = len(all_status)
        tcp_ok = sum(1 for s in all_status if s.get('tcp_alive', False))
        session_ok = sum(1 for s in all_status if s.get('session_alive', False))

        return {
            'total': total,
            'tcp_alive': tcp_ok,
            'session_alive': session_ok,
            'has_dead_devices': tcp_ok < total,
            'checked_at': _now(),
            'devices': all_status,
        }
