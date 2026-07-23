# -*- coding: utf-8 -*-
"""Get exact 'ac-list' syntax; check AP3 reachability; re-check AP state after wait."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def drain(s, t=0.5):
    s.settimeout(t)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass

def connect(name):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10); s.connect(('127.0.0.1', PORTS[name]))
    time.sleep(0.6); drain(s, 0.6)
    s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.6); drain(s, 0.6)
    return s

def cmd(s, c, w=5.0):
    s.settimeout(10); s.send((c + '\r\n').encode())
    buf = b''; end = time.time() + w; s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

def helpq(s, c, w=5.0):
    s.settimeout(10); s.send(c.encode())
    buf = b''; end = time.time() + w; s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
            if b'wlan-ap' in buf or b'wlan-view' in buf or b'<AC' in buf: break
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

s = connect('AC1')
print(cmd(s, 'system-view', 2), flush=True)
print(cmd(s, 'wlan', 2), flush=True)
print(cmd(s, 'ap-id 3', 2), flush=True)
print("\n### 'ac-list ?' syntax:", flush=True)
print(helpq(s, 'ac-list ?', 5.0)[-500:], flush=True)
print(cmd(s, '\r\n', 1.0), flush=True)
print(cmd(s, 'quit', 1.0), flush=True)
print(cmd(s, 'quit', 1.0), flush=True)  # to user view
s.close()

print("\n### Is AP3 reachable? ping 10.1.1.251 from AR1", flush=True)
s = connect('AR1')
o = cmd(s, 'ping -c 3 10.1.1.251', 12.0)
line=[l for l in o.splitlines() if 'packet' in l]
print(line[-1] if line else o[-120:], flush=True)
s.close()

print("\n### AP state re-check after 20s", flush=True); time.sleep(20)
for ac in ['AC1','AC2']:
    s = connect(ac)
    print("[%s] %s" % (ac, cmd(s, 'display ap all', 5.0)[-300:]), flush=True)
    s.close()
print("\n[DONE]", flush=True)
