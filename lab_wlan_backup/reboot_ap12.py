# -*- coding: utf-8 -*-
"""AP1/AP2 stuck idle while AP3 came up: eNSP fit-APs only discovery once at boot.
Reboot AP1(2006) & AP2(2007) so they re-discover AC1 (now reachable) and register."""
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

def reboot_ap(name):
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
    s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8)
    s.settimeout(0.4)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass
    print(f"=== {name}: send reboot ===", flush=True)
    out = send_wait(s, 'reboot', 1.5)
    print(out[-200:], flush=True)
    # answer Y/N if present
    if 'Y/N' in out or '[Y/N]' in out:
        s.settimeout(10); s.send(b'y\r\n'); time.sleep(1.0)
    s.close()

for n in ['AP1', 'AP2']:
    reboot_ap(n)
    time.sleep(1)
print("\nAP1/AP2 reboot sent. Done.", flush=True)
