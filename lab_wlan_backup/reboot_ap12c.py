# -*- coding: utf-8 -*-
"""Properly reboot AP1/AP2 from AC1 (answer YES to confirm), then wait+verify.
First ensure we are back at AC1 user view to avoid nested prompts."""
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

# --- AC1: ensure at user view, then ap-reset ap-id 1 & 2 with YES ---
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10); s.connect(('127.0.0.1', PORTS['AC1']))
time.sleep(0.6); drain(s)
s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8); drain(s)

# get to user view fresh
for _ in range(3):
    s.settimeout(10); s.send(b'quit\r\n'); time.sleep(0.5); drain(s)
s.settimeout(10); s.send(b'\r\n'); time.sleep(0.5); drain(s)

for apid in [1, 2]:
    print(f">> ap-reset ap-id {apid}", flush=True)
    s.settimeout(10); s.send(f'ap-reset ap-id {apid}\r\n'.encode()); time.sleep(1.2)
    o = send_wait(s, '', 1.0)
    print(o[-200:], flush=True)
    if 'Y/N' in o:
        s.settimeout(10); s.send(b'YES\r\n'); time.sleep(1.5); drain(s)
        print(f"   answered YES for ap-id {apid}", flush=True)
s.close()

print("Waiting 80s for AP1/AP2 to reboot + re-register ...", flush=True)
time.sleep(80)

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
