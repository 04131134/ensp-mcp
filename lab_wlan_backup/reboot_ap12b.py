# -*- coding: utf-8 -*-
"""Reboot AP1/AP2 properly (AP console wants YES/NO), then wait and verify all 3 APs normal."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def drain(s, t=0.5):
    s.settimeout(0.5)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass

def send_wait(s, cmd, wait=1.2):
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

def reboot_ap(name):
    port = PORTS[name]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect(('127.0.0.1', port))
    time.sleep(0.6)
    drain(s)
    s.settimeout(10)
    s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8); drain(s)
    out = send_wait(s, 'reboot', 1.5)
    print(f"[{name}] reboot prompt seen: {'YES' in out or 'reboot' in out}", flush=True)
    # AP console asks 'System will reboot! Continue ? [y/n]:' -> needs YES/NO
    s.settimeout(10); s.send(b'YES\r\n'); time.sleep(1.5); drain(s)
    s.close()
    print(f"[{name}] reboot issued", flush=True)

for n in ['AP1', 'AP2']:
    reboot_ap(n); time.sleep(1)

print("Waiting 70s for AP1/AP2 to reboot + re-register ...", flush=True)
time.sleep(70)

# verify on AC1
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10); s.connect(('127.0.0.1', PORTS['AC1']))
time.sleep(0.6); drain(s)
s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8); drain(s)
for label, cmd, w in [
    ('display ap all', 'display ap all', 4.0),
    ('display radio all', 'display radio all', 4.0),
    ('display vap all', 'display vap all', 4.0),
]:
    print(f"\n===== {label} =====", flush=True)
    print(send_wait(s, cmd, w)[-1600:], flush=True)
s.close()
print("\n[DONE]", flush=True)
