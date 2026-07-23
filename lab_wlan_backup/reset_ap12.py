# -*- coding: utf-8 -*-
"""AP1/AP2 consoles won't take reboot over telnet. Reset them from AC1 via ap-reset
(ap-id 1 and 2), then wait and verify all 3 APs normal with radios up."""
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

def send_wait(s, cmd, wait=1.5):
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
s.settimeout(10); s.connect(('127.0.0.1', PORTS['AC1']))
time.sleep(0.6); drain(s)
s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8); drain(s)

for cmd in ['system-view', 'wlan', 'ap-reset ap-id 1', 'ap-reset ap-id 2', 'quit', 'quit']:
    print(f"> {cmd}", flush=True)
    print(send_wait(s, cmd, 2.0)[-200:], flush=True)
    time.sleep(0.4)
s.close()

print("Waiting 75s for AP1/AP2 reset + re-register ...", flush=True)
time.sleep(75)

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
    print(send_wait(s, cmd, w)[-1700:], flush=True)
s.close()
print("\n[DONE]", flush=True)
