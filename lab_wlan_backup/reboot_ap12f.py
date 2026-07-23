# -*- coding: utf-8 -*-
"""FINAL AP1/AP2 reboot attempt: clear any pending [Y/N], re-sync prompt, then
send reboot (+retry) and answer YES on Continue. If APs come up, great; else
we proceed with AP3 only."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def drain(s, t=1.0):
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
    return s

def reboot_console(name):
    s = connect_dev(name)
    # clear any pending prompt
    s.settimeout(10); s.send(b'NO\r\n'); time.sleep(0.8); drain(s, 0.8)
    s.settimeout(10); s.send(b'\r\n'); time.sleep(1.0); drain(s, 1.0)
    # send reboot (twice in case first missed)
    s.settimeout(10); s.send(b'reboot\r\n'); time.sleep(1.0)
    s.settimeout(10); s.send(b'reboot\r\n'); time.sleep(1.0)
    buf = b''; sent = False
    for _ in range(12):
        try:
            s.settimeout(0.8); d = s.recv(65536)
        except socket.timeout:
            d = b''
        if d: buf += d
        if 'Continue' in buf.decode('gbk', errors='ignore') and not sent:
            s.settimeout(10); s.send(b'YES\r\n'); sent = True
            time.sleep(2.0); drain(s, 2.0)
            print(f"[{name}] YES sent", flush=True)
            break
    if not sent:
        print(f"[{name}] Still no Continue prompt", flush=True)
    s.close()

for n in ['AP1', 'AP2']:
    reboot_console(n); time.sleep(1)

print("Waiting 90s for re-register ...", flush=True)
time.sleep(90)

s = connect_dev('AC1')
for label, cmd, w in [
    ('display ap all', 'display ap all', 4.0),
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
    print(buf.decode('gbk', errors='ignore')[-1200:], flush=True)
s.close()
print("\n[DONE]", flush=True)
