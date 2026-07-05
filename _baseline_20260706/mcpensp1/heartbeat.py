# -*- coding: utf-8 -*-
"""Heartbeat monitor for eNSP device connections."""
from __future__ import annotations
from typing import Any
import time, threading, logging
from datetime import datetime, timezone

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
        with devices_lock:
            current_devices = list(devices.keys())
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
                    with name_lock:
                        nm = device_names.get(path, path)
                    socketio.emit('heartbeat_status', {'path': path, 'alive': False, 'status': 'disconnected', 'message': f'{nm} 宸叉柇寮€'})
            elif old is False and alive is True:
                with self.reconnect_lock:
                    self.reconnect_counts[path] = 0
                with name_lock:
                    nm = device_names.get(path, path)
                socketio.emit('heartbeat_status', {'path': path, 'alive': True, 'status': 'reconnected', 'message': f'{nm} 已恢复'})
            else:
                socketio.emit('heartbeat_status', {'path': path, 'alive': alive, 'status': 'alive' if alive else 'unresponsive', 'response_time': self.status.get(path, {}).get('response_time', 0)})
        with self.lock:
            stale = [p for p in self.status if p not in devices]
            for p in stale: self.status.pop(p, None)
        with self.reconnect_lock:
            stale_rc = [p for p in self.reconnect_counts if p not in devices]
            for p in stale_rc: self.reconnect_counts.pop(p, None)

    def _ping(self, path):
        """Check device liveness by probing socket, without sending commands."""
        with devices_lock:
            conn = devices.get(path)
        if not conn or not conn.sock:
            return False
        try:
            t0 = time.time()
            import select  # already imported at top
            # Use select to check if socket is still alive (very fast)
            _, writable, errored = select.select([], [conn.sock], [conn.sock], 0.5)
            if errored:
                raise ConnectionError('Socket error')
            if not writable:
                raise ConnectionError('Socket not writable')
            with self.lock:
                self.status.setdefault(path, {})['response_time'] = round(time.time() - t0, 3)
            return True
        except Exception:
            try:
                port = int(path.split(':')[1])
                nc = TelnetConnection('127.0.0.1', port)
                nc.connect()
                with devices_lock:
                    old = devices.get(path)
                    if old:
                        try: old.close()
                        except OSError: pass
                    devices[path] = nc
                return True
            except Exception as e:
                logger.debug('Ping reconnect failed for %s: %s', path, e)
                return False
    def _try_reconnect(self, path):
        with devices_lock:
            if path not in devices: return
        nc = None
        try:
            port = int(path.split(':')[1])
            nc = TelnetConnection('127.0.0.1', port)
            nc.connect()
            with devices_lock:
                if path not in devices:
                    try: nc.close()
                    except OSError: pass
                    return
                old = devices.get(path)
                if old:
                    try: old.close()
                    except OSError: pass
                devices[path] = nc
            with name_lock:
                nm = device_names.get(path, path)
            socketio.emit('heartbeat_status', {'path': path, 'alive': True, 'status': 'reconnected', 'message': f'{nm} 已恢复愬姛'})
        except Exception as e:
            logger.error('Reconnect failed for %s: %s', path, e)
            if nc:
                try: nc.close()
                except OSError: pass

    def get_status(self, path: str | None = None) -> dict[str, Any]:
        with self.lock: return self.status.get(path, {'alive': False}) if path else dict(self.status)

    def _now(self): return datetime.now(timezone.utc).isoformat()


