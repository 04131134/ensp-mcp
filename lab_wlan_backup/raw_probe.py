# -*- coding: utf-8 -*-
"""Raw short-timeout probe: connect, send \\r\\n, dump bytes for 3s.
Tells us which device consoles are alive and what prompt they show."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def probe(name, cmd='\r\n', wait=3.0):
    port = PORTS[name]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    try:
        s.connect(('127.0.0.1', port))
    except OSError as e:
        print(f"[{name}] CONNECT FAIL: {e}", flush=True)
        return
    time.sleep(0.5)
    s.settimeout(0.5)
    # drain banner
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass
    s.settimeout(10)
    s.send((cmd + '\r\n').encode())
    # read with short deadline
    buf = b''
    end = time.time() + wait
    s.settimeout(0.3)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    s.close()
    text = buf.decode('gbk', errors='ignore')
    # show last 400 chars
    print(f"===== {name} (cmd={cmd!r}) =====", flush=True)
    print(text[-500:], flush=True)

for n in ['AC1','AC2','LSW1','AR1','AR3','AP1']:
    probe(n, 'display version', 3.0)
    time.sleep(0.3)
print("\n[ALL DONE]", flush=True)
