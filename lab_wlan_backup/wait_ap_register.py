# -*- coding: utf-8 -*-
"""Wait for APs to register to AC1 after uplink fix, then verify ap/radio/vap."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def send_wait(s, cmd, wait=2.0):
    s.settimeout(10)
    s.send((cmd + '\r\n').encode())
    buf = b''; end = time.time() + wait
    s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(('127.0.0.1', PORTS['AC1']))
time.sleep(0.6)
s.settimeout(0.5)
try:
    while True:
        d = s.recv(65536)
        if not d: break
except socket.timeout:
    pass
s.settimeout(10)
s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8)
s.settimeout(0.4)
try:
    while True:
        d = s.recv(65536)
        if not d: break
except socket.timeout:
    pass

print("Waiting 60s for CAPWAP registration ...", flush=True)
time.sleep(60)

for label, cmd, w in [
    ('display ap all', 'display ap all', 4.0),
    ('display radio all', 'display radio all', 4.0),
    ('display vap all', 'display vap all', 4.0),
    ('display station all', 'display station all', 4.0),
]:
    print(f"\n===== {label} =====", flush=True)
    print(send_wait(s, cmd, w)[-1600:], flush=True)

s.close()
print("\n[DONE]", flush=True)
