# -*- coding: utf-8 -*-
"""COLD backup failover test (angle 3):
1) shutdown AC1 Vlanif10 -> CAPWAP source lost, AP3 drops tunnel to AC1.
2) add ap-id 1/2/3 (type 45) to AC2 -> AP re-discovers and registers to AC2.
3) verify AP state on both ACs.
AP1/AP2 are idle (eNSP AP console can't be rebooted here) so only AP3 is expected
to migrate; we record that honestly."""
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

def send_wait(s, cmd, wait=1.3):
    s.settimeout(10); s.send((cmd + '\r\n').encode())
    buf = b''; end = time.time() + wait
    s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

def read_cmd(s, cmd, w=4.0):
    return send_wait(s, cmd, w)

# ---- 1) shutdown AC1 Vlanif10 ----
print(">>> [COLD] shutdown AC1 Vlanif10 (kill CAPWAP source)", flush=True)
s = connect_dev('AC1')
for c in ['system-view', 'interface Vlanif10', 'shutdown', 'return']:
    s.settimeout(10); s.send((c + '\r\n').encode()); time.sleep(0.5); drain(s, 0.5)
s.close()
print("    AC1 Vlanif10 shut down", flush=True)
time.sleep(5)

# ---- 2) add ap-id 1/2/3 to AC2 (cold take-over) ----
print(">>> [COLD] add ap-id 1/2/3 to AC2 (take-over)", flush=True)
s = connect_dev('AC2')
for c in [
    'system-view', 'wlan',
    'ap-id 1 type-id 45 ap-mac 00e0-fc1b-3720', 'ap-name AP1', 'ap-group default', 'quit',
    'ap-id 2 type-id 45 ap-mac 00e0-fcdb-0400', 'ap-name AP2', 'ap-group default', 'quit',
    'ap-id 3 type-id 45 ap-mac 00e0-fcf8-32e0', 'ap-name AP3', 'ap-group default', 'quit',
    'return',
]:
    print(f"   {c}", flush=True)
    o = send_wait(s, c, 1.3)
    print(o[-120:], flush=True)
    time.sleep(0.3)
s.close()

print("    waiting 60s for AP re-registration to AC2 ...", flush=True)
time.sleep(60)

# ---- 3) verify ----
s = connect_dev('AC2')
print("\n===== AC2 display ap all (after failover) =====", flush=True)
print(read_cmd(s, 'display ap all', 4.0)[-1400:], flush=True)
s.close()

s = connect_dev('AC1')
print("\n===== AC1 display ap all (after failover) =====", flush=True)
print(read_cmd(s, 'display ap all', 4.0)[-1400:], flush=True)
s.close()
print("\n[DONE]", flush=True)
