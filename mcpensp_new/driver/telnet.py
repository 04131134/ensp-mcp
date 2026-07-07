# -*- coding: utf-8 -*-
"""Pure I/O Telnet driver for eNSP devices.

Design principles:
- Zero business logic — only bytes in, bytes out
- Per-device dedicated thread for async bridge (no shared ThreadPoolExecutor)
- Transport protocol for testability (MockTransport in tests)
- Prompt-driven reading with command-type-aware timeouts
- Auto-pagination (More → space), auto [Y/N] answer, auto flush
"""
from __future__ import annotations

import asyncio
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol


class Transport(Protocol):
    """Injectable socket transport for testability."""

    def connect(self, host: str, port: int) -> None: ...
    def send(self, data: bytes) -> None: ...
    def recv(self, bufsize: int) -> bytes: ...
    def close(self) -> None: ...
    def settimeout(self, timeout: float) -> None: ...
    def gettimeout(self) -> float | None: ...


class SocketTransport:
    """Production transport backed by a real TCP socket."""

    def __init__(self) -> None:
        self._sock: socket.socket | None = None

    def connect(self, host: str, port: int) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(10)
        self._sock.connect((host, port))

    def send(self, data: bytes) -> None:
        assert self._sock is not None
        self._sock.sendall(data)

    def recv(self, bufsize: int) -> bytes:
        assert self._sock is not None
        return self._sock.recv(bufsize)

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def settimeout(self, timeout: float) -> None:
        assert self._sock is not None
        self._sock.settimeout(timeout)

    def gettimeout(self) -> float | None:
        assert self._sock is not None
        return self._sock.gettimeout()


# ── Prompt regex patterns for major vendors ──

_PROMPT_PATTERNS = [
    re.compile(rb'<\S+>\s*$'),
    re.compile(rb'\[\S+\]\s*$'),
    re.compile(rb'\[\~?\S+[-\]].*\]\s*$'),
    re.compile(rb'\S+[>#]\s*$'),
    re.compile(rb'\S+\(config[^)]*\)[>#]\s*$'),
    re.compile(rb'[<\[\]]\S+[>\]\)].*\s*$'),
]

_MORE_PATTERN = re.compile(rb'---- More ----|-- More --|--more--')

_DIAG_DONE_PATTERN = re.compile(
    rb'---\s+.*\s+ping\s+statistics\s+---|'
    rb'\d+\s+packet[s]?\s+(transmitted|sent).*\d+\s+received|'
    rb'\d+%\s+packet\s+loss|'
    rb'traceroute\s+complete|'
    rb'Trace\s+complete'
)

_YN_PATTERN = re.compile(rb'\[Y/?N\]|\(Y/?N\)')

_TIMEOUTS = {'display': 30, 'diag': 10, 'config': 5, 'interactive': 10, 'default': 10}
_READ_EXTENSIONS = {'display': 0.5, 'diag': 0.3, 'config': 0.25, 'interactive': 0.5, 'default': 0.2}
_MAX_RECV = 4 * 1024 * 1024
_MAX_PAGES = 200
_MAX_YN = 3


@dataclass
class CommandResult:
    """Structured result of a single command execution."""
    output: str
    success: bool
    elapsed_ms: float
    errors: list[str] = field(default_factory=list)


class TelnetDriver:
    """Pure-I/O driver: send bytes, receive bytes, detect prompts.

    Each instance owns a dedicated single-worker thread pool for async bridging,
    ensuring heartbeat and commands on the *same* device are serialised without
    blocking any other device.
    """

    def __init__(self, host: str, port: int, transport: Transport | None = None) -> None:
        self.host = host
        self.port = port
        self._t = transport or SocketTransport()
        self._io_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f'telnet-{port}')

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _classify_cmd(cmd_lower: str) -> str:
        if cmd_lower.startswith(('display', 'dir', 'show')):
            return 'display'
        if cmd_lower.startswith(('ping', 'tracert', 'traceroute')):
            return 'diag'
        if cmd_lower.startswith(('save', 'reboot', 'reset', 'erase', 'format', 'delete')):
            return 'interactive'
        return 'config'

    @staticmethod
    def _has_prompt(data: bytes) -> bool:
        lines = data.split(b'\r\n')
        for line in reversed(lines[-4:]):
            stripped = line.strip()
            if not stripped:
                continue
            for pat in _PROMPT_PATTERNS:
                if pat.search(stripped):
                    return True
        return False

    @staticmethod
    def _is_more(data: bytes) -> bool:
        return bool(_MORE_PATTERN.search(data))

    @staticmethod
    def _is_diag_done(data: bytes) -> bool:
        return bool(_DIAG_DONE_PATTERN.search(data))

    @staticmethod
    def _strip_escape(data: bytes) -> bytes:
        return re.sub(rb'\x1b\[[0-9;]*[A-Za-z]', b'', data)

    def _flush(self) -> None:
        old = self._t.gettimeout()
        self._t.settimeout(0.3)
        try:
            while True:
                d = self._t.recv(65536)
                if not d:
                    break
        except (socket.timeout, OSError):
            pass
        self._t.settimeout(old or 10)

    # ── lifecycle ────────────────────────────────────────────

    def connect(self) -> None:
        self._t.connect(self.host, self.port)
        time.sleep(0.5)
        self._flush()
        self._t.send(b'\r\n')
        time.sleep(0.3)
        self._flush()
        self._t.settimeout(10)

    def close(self) -> None:
        with self._io_lock:
            self._t.close()
        self._executor.shutdown(wait=False)

    def handle_firewall_login(self, username: str = 'admin',
                               password: str = 'Admin@1234') -> bool:
        """Handle USG6000V firewall login flow."""
        for _attempt in range(3):
            self._t.send(b'\r\n')
            time.sleep(2)
            try:
                self._t.settimeout(3)
                initial = self._t.recv(65536).decode('gbk', errors='ignore')
            except Exception:
                initial = ''
            self._t.settimeout(10)
            if 'Username' in initial or 'Login' in initial:
                break
        else:
            return False

        self._t.send((username + '\r\n').encode())
        time.sleep(2)
        try:
            self._t.settimeout(3)
            resp = self._t.recv(65536).decode('gbk', errors='ignore')
        except Exception:
            resp = ''
        self._t.settimeout(10)
        if 'Password' not in resp:
            return False

        self._t.send((password + '\r\n').encode())
        time.sleep(3)
        try:
            self._t.settimeout(3)
            resp = self._t.recv(65536).decode('gbk', errors='ignore')
        except Exception:
            resp = ''
        self._t.settimeout(10)

        if '[Y/N]' in resp or '(Y/N)' in resp:
            self._t.send(b'y')
            time.sleep(0.5)
            self._t.send(b'\r\n')
            time.sleep(3)
            try:
                self._t.settimeout(3)
                resp = self._t.recv(65536).decode('gbk', errors='ignore')
            except Exception:
                resp = ''
            self._t.settimeout(10)
            if 'old password' in resp.lower():
                new_pw = password
                self._t.send((new_pw + '\r\n').encode())
                time.sleep(2)
                try:
                    self._t.recv(65536)
                except Exception:
                    pass
                self._t.send((new_pw + '\r\n').encode())
                time.sleep(3)
                try:
                    self._t.recv(65536)
                except Exception:
                    pass
                self._t.settimeout(10)

        time.sleep(1)
        self._flush()
        self._t.send(b'\r\n')
        time.sleep(0.5)
        self._flush()
        return True

    # ── command execution ────────────────────────────────────

    def execute(self, command: str) -> CommandResult:
        """Send a command and read until a prompt is detected.

        Thread-safe: serialises all I/O for this device via _io_lock.
        """
        with self._io_lock:
            cmd_lower = command.strip().lower()
            cmd_type = self._classify_cmd(cmd_lower)
            deadline = _TIMEOUTS[cmd_type]
            read_ext = _READ_EXTENSIONS[cmd_type]
            global_deadline = time.time() + deadline

            self._flush()
            time.sleep(0.15)
            self._flush()

            t0 = time.time()
            self._t.send(f'{command}\r\n'.encode())
            time.sleep(0.3 if cmd_type == 'display' else 0.2)

            chunks: list[bytes] = []
            total = 0
            pages_sent = 0
            diag_seen_done = False

            while time.time() < global_deadline:
                try:
                    self._t.settimeout(read_ext)
                    data = self._t.recv(65536)
                    if data:
                        chunks.append(data)
                        total += len(data)
                        if total >= _MAX_RECV:
                            break

                        tail = b''.join(chunks[-6:])

                        if self._is_more(tail) and pages_sent < _MAX_PAGES:
                            self._t.send(b' ')
                            time.sleep(0.1)
                            pages_sent += 1
                            continue

                        if cmd_type == 'diag' and self._is_diag_done(tail):
                            diag_seen_done = True
                            try:
                                self._t.settimeout(0.3)
                                trailing = self._t.recv(65536)
                                if trailing:
                                    chunks.append(trailing)
                                    total += len(trailing)
                            except (socket.timeout, OSError):
                                pass
                            break

                        if self._has_prompt(b''.join(chunks[-8:])):
                            break

                except socket.timeout:
                    if chunks and self._has_prompt(b''.join(chunks[-8:])):
                        break
                    if cmd_type == 'diag' and diag_seen_done:
                        break
                except OSError:
                    break

            self._t.settimeout(10)
            elapsed = (time.time() - t0) * 1000

            raw = b''.join(chunks)
            output = self._strip_escape(raw).decode('gbk', errors='ignore')

            # Auto-handle [Y/N]
            auto_yn = 0
            while auto_yn < _MAX_YN:
                tail_s = output[-200:] if len(output) > 200 else output
                if _YN_PATTERN.search(tail_s.encode('gbk', errors='ignore')):
                    self._t.send(b'y')
                    time.sleep(0.3)
                    self._t.send(b'\r\n')
                    time.sleep(0.5)
                    yn_chunks: list[bytes] = []
                    yn_deadline = time.time() + 5
                    while time.time() < yn_deadline:
                        try:
                            self._t.settimeout(0.1)
                            c = self._t.recv(65536)
                            if c:
                                yn_chunks.append(c)
                                if self._has_prompt(b''.join(yn_chunks)):
                                    break
                        except socket.timeout:
                            pass
                        except OSError:
                            break
                    self._t.settimeout(10)
                    if yn_chunks:
                        output += self._strip_escape(b''.join(yn_chunks)).decode(
                            'gbk', errors='ignore')
                    auto_yn += 1
                else:
                    break

            errors = _extract_errors(output, command)
            success = len(errors) == 0

            return CommandResult(output=output, success=success,
                                 elapsed_ms=round(elapsed, 1), errors=errors)

    # ── heartbeat probe ──────────────────────────────────────

    def is_alive(self, timeout: float = 3.0) -> bool:
        """Send \\r\\n and check for a prompt. Does NOT compete with execute() lock.

        Uses a separate short-lived socket probe to avoid blocking commands.
        """
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(timeout)
            probe.connect((self.host, self.port))
            time.sleep(0.3)
            probe.settimeout(0.3)
            try:
                while True:
                    d = probe.recv(65536)
                    if not d:
                        break
            except (socket.timeout, OSError):
                pass
            probe.settimeout(timeout)
            probe.send(b'\r\n')
            time.sleep(0.3)
            chunks: list[bytes] = []
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    probe.settimeout(0.3)
                    d = probe.recv(65536)
                    if d:
                        chunks.append(d)
                        if self._has_prompt(b''.join(chunks)):
                            return True
                except socket.timeout:
                    if chunks and self._has_prompt(b''.join(chunks)):
                        return True
                except OSError:
                    return False
            return bool(chunks)
        except (ConnectionError, OSError, socket.timeout):
            return False
        finally:
            try:
                probe.close()
            except Exception:
                pass

    # ── async bridge ─────────────────────────────────────────

    async def execute_async(self, command: str) -> CommandResult:
        """Async bridge using this device's dedicated single-worker executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self.execute, command)


# ── error extraction ────────────────────────────────────────────

_ERROR_MARKERS = [
    'Error:', 'Unrecognized command', 'Wrong parameter',
    'Too many parameters', 'Ambiguous command', 'Incomplete command',
    'Please renew the default configurations', 'Invalid',
    '% ',  # Cisco IOS error prefix
]


def _extract_errors(output: str, command: str) -> list[str]:
    """Extract error lines from command output."""
    errors: list[str] = []
    cmd_lower = command.strip().lower()
    # display commands are never "errors" even if output contains the word Error
    if cmd_lower.startswith(('display', 'dir', 'show')):
        return errors
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for marker in _ERROR_MARKERS:
            if marker in stripped:
                errors.append(stripped[:200])
                break
    return errors
