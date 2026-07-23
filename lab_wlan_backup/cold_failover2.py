# -*- coding: utf-8 -*-
"""COLD failover (robust): auto-answer [Y/N] with YES. Add ap-id 1/2/3 to AC2
after AC1 Vlanif10 is down, verify AP3 migrates to AC2. Also confirm AC1
Vlanif10 really went down."""
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

def cmd(s, c, wait=1.3):
    """Send a command; if a [Y/N] prompt appears, answer YES and continue."""
    s.settimeout(10); s.send((c + '\r\n').encode())
    buf = b''; end = time.time() + wait
    s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    txt = buf.decode('gbk', errors='ignore')
    if 'Y/N' in txt or 'Continue' in txt:
        s.settimeout(10); s.send(b'YES\r\n'); time.sleep(1.2); drain(s, 1.2)
    return txt

# ---- ensure AC1 Vlanif10 down ----
print(">>> confirm AC1 Vlanif10 shutdown", flush=True)
s = connect_dev('AC1')
for c in ['system-view', 'interface Vlanif10', 'shutdown', 'return']:
    cmd(s, c, 1.0)
s.close()
time.sleep(3)
s = connect_dev('AC1')
print("AC1 Vlanif10:", cmd(s, 'display ip interface brief', 3.0)[-400:], flush=True)
s.close()

# ---- add ap-id 1/2/3 to AC2 (auto-YES on any prompt) ----
print(">>> add ap-id 1/2/3 to AC2", flush=True)
s = connect_dev('AC2')
for c in [
    'system-view', 'wlan',
    'ap-id 1 type-id 45 ap-mac 00e0-fc1b-3720', 'ap-name AP1', 'ap-group default', 'quit',
    'ap-id 2 type-id 45 ap-mac 00e0-fcdb-0400', 'ap-name AP2', 'ap-group default', 'quit',
    'ap-id 3 type-id 45 ap-mac 00e0-fcf8-32e0', 'ap-name AP3', 'ap-group default', 'quit',
    'return',
]:
    print(f"   {c}", flush=True)
    o = cmd(s, c, 1.3)
    if 'Y/N' in o: print("     (answered YES)", flush=True)
    time.sleep(0.3)
s.close()

print("    waiting 60s for AP3 to re-register to AC2 ...", flush=True)
time.sleep(60)

s = connect_dev('AC2')
print("\n===== AC2 display ap all =====", flush=True)
print(cmd(s, 'display ap all', 4.0)[-1400:], flush=True)
s.close()
s = connect_dev('AC1')
print("\n===== AC1 display ap all =====", flush=True)
print(cmd(s, 'display ap all', 4.0)[-1400:], flush=True)
s.close()
print("\n[DONE]", flush=True)
