# -*- coding: utf-8 -*-
"""FIX: AC1 uplink GE0/0/1 is in VLAN 1, so Vlanif10 is down -> CAPWAP dead ->
3 APs idle. Put GE0/0/1 in trunk allowing VLAN 10 (and 40 for service traffic)
so Vlanif10 comes up and APs can register."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

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

cmds = [
    'system-view',
    'interface GigabitEthernet0/0/1',
    'port link-type trunk',
    'port trunk pvid vlan 10',
    'port trunk allow-pass vlan 10 40',
    'quit', 'quit',
]
for c in cmds:
    print(f"> {c}", flush=True)
    print(send_wait(s, c, 1.2)[-160:], flush=True)
    time.sleep(0.3)

print("\n--- display vlan (expect GE0/0/1 in VLAN 10) ---", flush=True)
print(send_wait(s, 'display vlan', 3.0)[-900:], flush=True)
print("\n--- display ip interface brief (expect Vlanif10 up) ---", flush=True)
print(send_wait(s, 'display ip interface brief', 3.0)[-700:], flush=True)
s.close()
print("\n[DONE]", flush=True)
