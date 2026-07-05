# -*- coding: utf-8 -*-
"""Heartbeat monitor for eNSP device connections."""
from __future__ import annotations
from typing import Any
import time, threading, logging
from datetime import datetime, timezone

from connection import TelnetConnection
from device_manager import dm

logger = logging.getLogger(__name__)

class HeartbeatMonitor:
    def __init__(self, kb_ref):
        self.kb = kb_ref
        self.status = {}
        self.lock = threading.Lock()
        self.running = False
        self.reconnect_counts = {}
        self.reconnect_lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.running: return
            self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            try: self._check_all()
            except Exception as e: logger.warning('[Heartbeat] %s', e)
            time.sleep(HEARTBEAT_INTERVAL)

    def _check_all(self):
        current_devices = list(dm.list_all().keys())
        for path in current_devices:
            alive = self._ping(path)
            with self.lock:
                old = self.status.get(path, {}).get('alive')
                self.status[path] = {'alive': alive, 'last_check': self._now(), 'last_alive': self._now() if alive else self.status.get(path, {}).get('last_alive'), 'response_time': self.status.get(path, {}).get('response_time', 0)}
            if old is True and alive is False:
                with self.reconnect_lock:
                    self.reconnect_counts[path] = self.reconnect_counts.get(path, 0) + 1
                    count = self.reconnect_counts[path]
                if count <= HEARTBEAT_RECONNECT_ATTEMPTS:
                    self._try_reconnect(path)
                else:
                    nm = dm.get_name(path, path)
                    socketio.emit('heartbeat_status', {'path': path, 'alive': False, 'status': 'disconnected', 'message': f'{nm} 已断开'})
            elif old is False and alive is True:
                with self.reconnect_lock:
                    self.reconnect_counts[path] = 0
                nm = dm.get_name(path, path)
                socketio.emit('heartbeat_status', {'path': path, 'alive': True, 'status': 'reconnected', 'message': f'{nm} 已恢复'})
            else:
                socketio.emit('heartbeat_status', {'path': path, 'alive': alive, 'status': 'alive' if alive else 'unresponsive', 'response_time': self.status.get(path, {}).get('response_time', 0)})
        with self.lock:
            current_paths = set(dm.list_all().keys())
            stale = [p for p in self.status if p not in current_paths]
            for p in stale: self.status.pop(p, None)
        with self.reconnect_lock:
            stale_rc = [p for p in self.reconnect_counts if p not in current_paths]
            for p in stale_rc: self.reconnect_counts.pop(p, None)

    def _ping(self, path):
        """Check device liveness by probing with real prompt detection."""
        conn = dm.get(path)
        if not conn or not conn.sock:
            return False
        try:
            t0 = time.time()
            if hasattr(conn, 'probe_prompt'):
                alive = conn.probe_prompt(timeout=3.0)
            else:
                import select
                _, writable, errored = select.select([], [conn.sock], [conn.sock], 0.5)
                if errored:
                    raise ConnectionError('Socket error')
                if not writable:
                    raise ConnectionError('Socket not writable')
                alive = True
            with self.lock:
                self.status.setdefault(path, {})['response_time'] = round(time.time() - t0, 3)
            return alive
        except Exception:
            try:
                port = int(path.split(':')[1])
                nc = TelnetConnection('127.0.0.1', port)
                nc.connect()
                dm.set(path, nc)
                return True
            except Exception as e:
                logger.debug('Ping reconnect failed for %s: %s', path, e)
                return False
    def _try_reconnect(self, path):
        if not dm.has(path):
            return
        nc = None
        try:
            port = int(path.split(':')[1])
            nc = TelnetConnection('127.0.0.1', port)
            nc.connect()
            dm.set(path, nc)
            nm = dm.get_name(path, path)
            socketio.emit('heartbeat_status', {'path': path, 'alive': True, 'status': 'reconnected', 'message': f'{nm} 已恢复成功'})
        except Exception as e:
            logger.error('Reconnect failed for %s: %s', path, e)
            if nc:
                try: nc.close()
                except OSError: pass

    def get_status(self, path: str | None = None) -> dict[str, Any]:
        with self.lock: return self.status.get(path, {'alive': False}) if path else dict(self.status)

    def _now(self): return datetime.now(timezone.utc).isoformat()


