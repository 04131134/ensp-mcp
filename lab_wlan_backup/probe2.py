# -*- coding: utf-8 -*-
"""Re-probe LSW1 and AC2 with screen-length 0 + longer waits."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def session(name, cmds, wait_each=5.0):
    port = PORTS[name]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect(('127.0.0.1', port))
    time.sleep(0.6)
    s.settimeout(0.5)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass
    s.settimeout(10)
    # disable paging
    s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8)
    s.settimeout(0.4)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass
    out = {}
    for c in cmds:
        s.settimeout(10)
        s.send((c + '\r\n').encode())
        buf = b''; end = time.time() + wait_each
        s.settimeout(0.4)
        try:
            while time.time() < end:
                d = s.recv(65536)
                if d: buf += d
        except socket.timeout:
            pass
        out[c] = buf.decode('gbk', errors='ignore')
    s.close()
    return out

print("===== LSW1 =====", flush=True)
for c, o in session('LSW1', ['display ip interface brief', 'display vlan', 'display interface brief']).items():
    print(f"--- {c} ---", flush=True); print(o[-1400:], flush=True)

print("\n===== AC2 =====", flush=True)
for c, o in session('AC2', ['display version', 'display ip interface brief', 'display ap all']).items():
    print(f"--- {c} ---", flush=True); print(o[-1400:], flush=True)
print("\n[DONE]", flush=True)
