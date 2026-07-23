# -*- coding: utf-8 -*-
"""Re-probe AC2 and LSW1 with screen-length 0 + longer reads to get their real state."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def drain(s, t=0.6):
    s.settimeout(t)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass

def connect_dev(name):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10); s.connect(('127.0.0.1', PORTS[name]))
    time.sleep(0.6); drain(s, 0.6)
    s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8); drain(s, 0.8)
    return s

def read_cmd(s, cmd, w=5.0):
    s.settimeout(10); s.send((cmd + '\r\n').encode())
    buf = b''; end = time.time() + w
    s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

print("===== AC2 =====", flush=True)
s = connect_dev('AC2')
for c in ['display version', 'display ip interface brief', 'display ap all', 'display vlan']:
    print(f"--- {c} ---", flush=True)
    print(read_cmd(s, c, 5.0)[-1000:], flush=True)
    time.sleep(0.3)
s.close()

print("\n===== LSW1 =====", flush=True)
s = connect_dev('LSW1')
for c in ['display ip interface brief', 'display vlan', 'display ospf peer brief']:
    print(f"--- {c} ---", flush=True)
    print(read_cmd(s, c, 5.0)[-1200:], flush=True)
    time.sleep(0.3)
s.close()
print("\n[DONE]", flush=True)
