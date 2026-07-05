# -*- coding: utf-8 -*-
"""Telnet connection to eNSP devices."""
from __future__ import annotations
import re, socket, time, logging, threading

logger = logging.getLogger(__name__)

class TelnetConnection:
    """Telnet connection using raw socket (eNSP compatible, no IAC negotiation)."""
    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self.sock = None
        self.lock = threading.Lock()

    def connect(self) -> bool:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.host, self.port))
        time.sleep(0.5)
        # Flush initial data
        self.sock.settimeout(0.5)
        try:
            while True:
                d = self.sock.recv(65536)
                if not d: break
        except (socket.timeout, OSError):
            pass
        self.sock.settimeout(10)
        # Send enter and flush prompt
        self.sock.send(b'\r\n')
        time.sleep(0.3)
        self._flush()
        return True

    def _flush(self) -> None:
        """Flush pending data from socket."""
        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(0.5)
        try:
            while True:
                d = self.sock.recv(65536)
                if not d: break
        except (socket.timeout, OSError):
            pass
        self.sock.settimeout(old_timeout)

    def _strip_escape(self, data: bytes) -> bytes:
        """Remove ANSI/VT escape codes from data."""
        return re.sub(rb'\x1b\[[0-9;]*[A-Za-z]', b'', data)

    def send_cmd(self, cmd: str) -> str:
        MAX_RECV = 4 * 1024 * 1024
        GLOBAL_TIMEOUT = 30  # Fix H5: hard 30s ceiling to prevent hangs
        with self.lock:
            if not self.sock:
                raise ConnectionError('Socket not connected')
            cmd_lower = cmd.strip().lower()
            is_display = cmd_lower.startswith('display') or cmd_lower.startswith('dir')
            is_diag = cmd_lower.startswith(('ping', 'tracert'))
            recv_timeout = 3 if is_display else (4 if is_diag else 1.5)
            global_deadline = time.time() + GLOBAL_TIMEOUT
            # Flush pending data thoroughly
            self._flush()
            time.sleep(0.15)
            self._flush()
            # Send command
            self.sock.send(f'{cmd}\r\n'.encode())
            time.sleep(0.3 if is_display else 0.2)
            # Read response
            chunks = []
            total = 0
            deadline = min(time.time() + recv_timeout, global_deadline)
            while time.time() < deadline and time.time() < global_deadline:
                try:
                    self.sock.settimeout(0.1)
                    data = self.sock.recv(65536)
                    if data:
                        chunks.append(data)
                        total += len(data)
                        if total >= MAX_RECV:
                            break
                        deadline = time.time() + 0.5  # extend if still getting data
                except socket.timeout:
                    pass
                except OSError:
                    break
            self.sock.settimeout(10)
            output = b''.join(chunks)
            output = self._strip_escape(output).decode('gbk', errors='ignore')
            # Auto-handle [Y/N] prompts
            auto_yn = 0
            while auto_yn < 3:
                tail = output[-200:] if len(output) > 200 else output
                if re.search(r'\[Y/?N\]|\(Y/?N\)', tail):
                    self.sock.send(b'y')
                    time.sleep(0.3)
                    self.sock.send(b'\r\n')
                    time.sleep(0.5)
                    follow_deadline = time.time() + recv_timeout
                    while time.time() < follow_deadline:
                        try:
                            self.sock.settimeout(0.1)
                            c = self.sock.recv(65536)
                            if c:
                                chunks.append(c)
                                total += len(c)
                                if total >= MAX_RECV:
                                    break
                        except socket.timeout:
                            pass
                        except OSError:
                            break
                    self.sock.settimeout(10)
                    output = self._strip_escape(b''.join(chunks)).decode('gbk', errors='ignore')
                    auto_yn += 1
                else:
                    break
            return output

    def handle_firewall_login(self, username: str = 'admin', password: str = 'Admin@1234') -> bool:
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
            # Send username
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
            # Send password
            self.sock.send((password + '\r\n').encode())
            time.sleep(3)
            try:
                self.sock.settimeout(3)
                resp = self.sock.recv(65536).decode('gbk', errors='ignore')
            except Exception:
                resp = ''
            self.sock.settimeout(10)
            # Handle password change
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
                    # Send the OLD password (same as login password)
                    # New password (change to same for simplicity, or use a new one)
                    new_pw = password
                    self.sock.send((new_pw + '\r\n').encode())
                    time.sleep(2)
                    try: self.sock.recv(65536)
                    except Exception: pass
                    # Confirm new password
                    self.sock.send((new_pw + '\r\n').encode())
                    time.sleep(3)
                    try: self.sock.recv(65536)
                    except Exception: pass
                    self.sock.settimeout(10)
            # Flush
            time.sleep(1)
            self._flush()
            self.sock.send(b'\r\n')
            time.sleep(0.5)
            self._flush()
            return True
        except Exception as e:
            logger.debug('Firewall login failed: %s', e)
            return False

    def close(self) -> None:
        with self.lock:
            if self.sock:
                try: self.sock.close()
                except OSError: pass
                self.sock = None

    # lazy init for kb in app.py context
kb = None  # will be set by knowledge.py
