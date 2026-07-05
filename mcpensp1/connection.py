# -*- coding: utf-8 -*-
"""Telnet connection to eNSP devices.

v2.1 — Prompt-driven reading with command classification and pagination.
"""
from __future__ import annotations
import re, socket, time, logging, threading

logger = logging.getLogger(__name__)


class TelnetConnection:
    """Telnet connection using raw socket (eNSP compatible, no IAC negotiation).

    Key improvements over v2:
    - Prompt regex detection (Huawei < > / [ ] / H3C / Cisco patterns)
    - Command classifier: display / diag / config / interactive
    - Auto pagination: sends space on `---- More ----`
    """

    # ── Prompt patterns for major vendors ──
    PROMPT_PATTERNS = [
        # Huawei: <SW1> or [SW1] or [SW1-GigabitEthernet0/0/1]
        re.compile(rb'<\S+>\s*$'),
        re.compile(rb'\[\S+\]\s*$'),
        re.compile(rb'\[\~?\S+[-\]].*\]\s*$'),
        # H3C: <SW1> or [SW1]
        re.compile(rb'<\S+>\s*$'),
        re.compile(rb'\[\S+\]\s*$'),
        # Cisco: SW1# or SW1(config)# or SW1(config-if)#
        re.compile(rb'\S+[>#]\s*$'),
        re.compile(rb'\S+\(config[^)]*\)[>#]\s*$'),
        # Generic fallback: any <> or [] ending line
        re.compile(rb'[<\[\]]\S+[>\]\)].*\s*$'),
    ]

    # ── Pagination marker ──
    MORE_PATTERN = re.compile(rb'---- More ----|-- More --|--more--')

    # ── Diagnostic command completion markers ──
    DIAG_DONE_PATTERN = re.compile(
        rb'---\s+.*\s+ping\s+statistics\s+---|'
        rb'\d+\s+packet[s]?\s+(transmitted|sent).*\d+\s+received|'
        rb'\d+%\s+packet\s+loss|'
        rb'traceroute\s+complete|'
        rb'Trace\s+complete'
    )

    # ── Interactive prompt markers ──
    YN_PATTERN = re.compile(rb'\[Y/?N\]|\(Y/?N\)')

    # ── Timeout per command type ──
    TIMEOUTS = {
        'display': 30,      # display current-configuration can be huge
        'diag': 10,         # ping / tracert
        'config': 5,        # system-view / interface / ospf etc.
        'interactive': 10,  # save / reboot / reset
        'default': 10,
    }

    # ── Per-type read chunk deadline extensions ──
    READ_EXTENSIONS = {
        'display': 0.5,
        'diag': 0.3,
        'config': 0.25,
        'interactive': 0.5,
        'default': 0.2,
    }

    # ── Max total bytes ──
    MAX_RECV = 4 * 1024 * 1024

    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self.sock = None
        self.lock = threading.Lock()

    # ════════════ helpers ════════════

    def _classify_cmd(self, cmd_lower: str) -> str:
        """Classify command type for timeout / read strategy."""
        if cmd_lower.startswith(('display', 'dir', 'show')):
            return 'display'
        if cmd_lower.startswith(('ping', 'tracert', 'traceroute')):
            return 'diag'
        if cmd_lower.startswith(('save', 'reboot', 'reset', 'erase',
                                  'format', 'delete')):
            return 'interactive'
        return 'config'

    def _has_prompt(self, data: bytes) -> bool:
        """Check whether any prompt pattern matches the last few lines."""
        lines = data.split(b'\r\n')
        if not lines:
            return False
        for line in reversed(lines[-4:]):
            stripped = line.strip()
            if not stripped:
                continue
            for pat in self.PROMPT_PATTERNS:
                if pat.search(stripped):
                    return True
        return False

    def _is_more(self, data: bytes) -> bool:
        """Check whether the output has a pagination marker."""
        return bool(self.MORE_PATTERN.search(data))

    def _is_diag_done(self, data: bytes) -> bool:
        """Check diagnostic completion marker."""
        return bool(self.DIAG_DONE_PATTERN.search(data))

    def _strip_escape(self, data: bytes) -> bytes:
        """Remove ANSI/VT escape codes from data."""
        return re.sub(rb'\x1b\[[0-9;]*[A-Za-z]', b'', data)

    def _flush(self) -> None:
        """Flush pending data from socket."""
        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(0.5)
        try:
            while True:
                d = self.sock.recv(65536)
                if not d:
                    break
        except (socket.timeout, OSError):
            pass
        self.sock.settimeout(old_timeout)

    # ════════════ connection lifecycle ════════════

    def connect(self) -> bool:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.host, self.port))
        time.sleep(0.5)
        self.sock.settimeout(0.5)
        try:
            while True:
                d = self.sock.recv(65536)
                if not d:
                    break
        except (socket.timeout, OSError):
            pass
        self.sock.settimeout(10)
        self.sock.send(b'\r\n')
        time.sleep(0.3)
        self._flush()
        return True

    def close(self) -> None:
        with self.lock:
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None

    # ════════════ prompt-driven send_cmd ════════════

    def send_cmd(self, cmd: str) -> str:
        """Send a command and read until a prompt is detected.

        Backward-compatible signature.  Internally uses prompt-driven
        reading with command-type-aware timeouts and auto-pagination.
        """
        with self.lock:
            if not self.sock:
                raise ConnectionError('Socket not connected')

            cmd_lower = cmd.strip().lower()
            cmd_type = self._classify_cmd(cmd_lower)
            deadline = self.TIMEOUTS[cmd_type]
            read_ext = self.READ_EXTENSIONS[cmd_type]
            global_deadline = time.time() + deadline

            # Flush pending
            self._flush()
            time.sleep(0.15)
            self._flush()

            # Send
            self.sock.send(f'{cmd}\r\n'.encode())
            time.sleep(0.3 if cmd_type == 'display' else 0.2)

            # ── Read loop ──
            chunks: list[bytes] = []
            total = 0
            next_deadline = global_deadline  # start with global cap
            pages_sent = 0
            diag_seen_done = False

            while time.time() < global_deadline:
                # Calculate read deadline for this chunk
                chunk_deadline = min(time.time() + read_ext, global_deadline)

                try:
                    self.sock.settimeout(read_ext)
                    data = self.sock.recv(65536)

                    if data:
                        chunks.append(data)
                        total += len(data)

                        # Cap
                        if total >= self.MAX_RECV:
                            break

                        # Recent tail for inspection
                        tail = b''.join(chunks[-6:])

                        # Pagination — send space
                        if self._is_more(tail) and pages_sent < 200:
                            self.sock.send(b' ')
                            time.sleep(0.1)
                            pages_sent += 1
                            continue

                        # Diagnostic done
                        if cmd_type == 'diag' and self._is_diag_done(tail):
                            diag_seen_done = True
                            # Short wait for trailing prompt
                            try:
                                self.sock.settimeout(0.3)
                                trailing = self.sock.recv(65536)
                                if trailing:
                                    chunks.append(trailing)
                                    total += len(trailing)
                            except (socket.timeout, OSError):
                                pass
                            break

                        # Prompt found — done
                        if self._has_prompt(b''.join(chunks[-8:])):
                            break

                        # Extend read deadline (still getting data)
                        chunk_deadline = time.time() + read_ext

                except socket.timeout:
                    # Short idle + prompt → done
                    if chunks and self._has_prompt(b''.join(chunks[-8:])):
                        break
                    if cmd_type == 'diag' and diag_seen_done:
                        break
                except OSError:
                    break

            # Reset timeout
            self.sock.settimeout(10)

            # Decode
            raw = b''.join(chunks)
            output = self._strip_escape(raw).decode('gbk', errors='ignore')

            # ── Auto-handle [Y/N] prompts ──
            auto_yn = 0
            while auto_yn < 3:
                tail = output[-200:] if len(output) > 200 else output
                if self.YN_PATTERN.search(tail.encode('gbk', errors='ignore')):
                    self.sock.send(b'y')
                    time.sleep(0.3)
                    self.sock.send(b'\r\n')
                    time.sleep(0.5)
                    yn_chunks = []
                    yn_deadline = time.time() + 5
                    while time.time() < yn_deadline:
                        try:
                            self.sock.settimeout(0.1)
                            c = self.sock.recv(65536)
                            if c:
                                yn_chunks.append(c)
                                if self._has_prompt(b''.join(yn_chunks)):
                                    break
                        except socket.timeout:
                            pass
                        except OSError:
                            break
                    self.sock.settimeout(10)
                    if yn_chunks:
                        yn_output = self._strip_escape(b''.join(yn_chunks)).decode(
                            'gbk', errors='ignore')
                        output += yn_output
                    auto_yn += 1
                else:
                    break

            return output

    # ════════════ firewall login (unchanged) ════════════

    def handle_firewall_login(self, username: str = 'admin',
                               password: str = 'Admin@1234') -> bool:
        """Handle USG6000V firewall login flow."""
        if not self.sock:
            return False
        try:
            initial = ''
            for _attempt in range(3):
                self.sock.send(b'\r\n')
                time.sleep(2)
                try:
                    self.sock.settimeout(3)
                    initial = self.sock.recv(65536).decode('gbk', errors='ignore')
                except Exception:
                    initial = ''
                self.sock.settimeout(10)
                if 'Username' in initial or 'Login' in initial:
                    break
            else:
                return False
            self.sock.send((username + '\r\n').encode())
            time.sleep(2)
            try:
                self.sock.settimeout(3)
                resp = self.sock.recv(65536).decode('gbk', errors='ignore')
            except Exception:
                resp = ''
            self.sock.settimeout(10)
            if 'Password' not in resp:
                return False
            self.sock.send((password + '\r\n').encode())
            time.sleep(3)
            try:
                self.sock.settimeout(3)
                resp = self.sock.recv(65536).decode('gbk', errors='ignore')
            except Exception:
                resp = ''
            self.sock.settimeout(10)
            if '[Y/N]' in resp or '(Y/N)' in resp:
                self.sock.send(b'y')
                time.sleep(0.5)
                self.sock.send(b'\r\n')
                time.sleep(3)
                try:
                    self.sock.settimeout(3)
                    resp = self.sock.recv(65536).decode('gbk', errors='ignore')
                except Exception:
                    resp = ''
                self.sock.settimeout(10)
                if 'old password' in resp.lower():
                    new_pw = password
                    self.sock.send((new_pw + '\r\n').encode())
                    time.sleep(2)
                    try:
                        self.sock.recv(65536)
                    except Exception:
                        pass
                    self.sock.send((new_pw + '\r\n').encode())
                    time.sleep(3)
                    try:
                        self.sock.recv(65536)
                    except Exception:
                        pass
                    self.sock.settimeout(10)
            time.sleep(1)
            self._flush()
            self.sock.send(b'\r\n')
            time.sleep(0.5)
            self._flush()
            return True
        except Exception as e:
            logger.debug('Firewall login failed: %s', e)
            return False

    # ════════════ prompt-based ping for heartbeat ════════════

    def probe_prompt(self, timeout: float = 3.0) -> bool:
        """Send a carriage return and check whether the device responds
        with a recognised prompt.  Fast, safe, no-command probe.

        Returns True if a prompt was detected within *timeout* seconds.
        """
        if not self.sock:
            return False
        try:
            with self.lock:
                self._flush()
                self.sock.send(b'\r\n')
                time.sleep(0.15)
                chunks: list[bytes] = []
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        self.sock.settimeout(0.3)
                        d = self.sock.recv(65536)
                        if d:
                            chunks.append(d)
                            if self._has_prompt(b''.join(chunks)):
                                self.sock.settimeout(10)
                                return True
                    except socket.timeout:
                        if chunks and self._has_prompt(b''.join(chunks)):
                            self.sock.settimeout(10)
                            return True
                    except OSError:
                        self.sock.settimeout(10)
                        return False
                self.sock.settimeout(10)
                return bool(chunks)
        except (ConnectionError, OSError):
            return False

    # ════════════ async bridge ════════════

    async def send_cmd_async(self, cmd: str) -> str:
        """异步接口——供 MCP Server 调用，不阻塞事件循环。"""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.send_cmd, cmd)


# lazy init for kb in app.py context
kb = None  # will be set by knowledge.py
