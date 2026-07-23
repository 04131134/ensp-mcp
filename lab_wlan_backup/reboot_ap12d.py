# -*- coding: utf-8 -*-
"""Robust AP console reboot (no screen-length; matches the flow that captured the
prompt). Poll-read up to 10s; when 'Continue' appears, send YES. Wait+verify."""
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

def connect_dev(name):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10); s.connect(('127.0.0.1', PORTS[name]))
    time.sleep(0.6); drain(s)
    return s

def reboot_console(name):
    s = connect_dev(name)
    s.settimeout(10); s.send(b'reboot\r\n')
    buf = b''
    sent = False
    for _ in range(12):  # up to ~12s
        try:
            s.settimeout(0.8)
            d = s.recv(65536)
            if d: buf += d
        except socket.timeout:
            pass
        txt = buf.decode('gbk', errors='ignore')
        if 'Continue' in txt and not sent:
            s.settimeout(10); s.send(b'YES\r\n')
            sent = True
            print(f"[{name}] Continue seen -> YES sent", flush=True)
            time.sleep(1.5); drain(s)
            break
    if not sent:
        print(f"[{name}] WARNING: Continue never seen; retrying reboot once", flush=True)
        s.settimeout(10); s.send(b'reboot\r\n'); time.sleep(2.0)
        s.settimeout(10); s.send(b'YES\r\n'); time.sleep(2.0); drain(s)
    s.close()

for n in ['AP1', 'AP2']:
    reboot_console(n); time.sleep(1)

print("Waiting 90s for AP1/AP2 reboot + re-register to AC1 ...", flush=True)
time.sleep(90)

s = connect_dev('AC1')
for label, cmd, w in [
    ('display ap all', 'display ap all', 4.0),
    ('display radio all', 'display radio all', 4.0),
    ('display vap all', 'display vap all', 4.0),
]:
    s.settimeout(10); s.send((cmd + '\r\n').encode())
    buf = b''; end = time.time() + w
    s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    print(f"\n===== {label} =====", flush=True)
    print(buf.decode('gbk', errors='ignore')[-1700:], flush=True)
s.close()
print("\n[DONE]", flush=True)
