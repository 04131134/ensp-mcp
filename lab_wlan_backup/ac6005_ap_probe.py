# -*- coding: utf-8 -*-
"""Careful probe: find correct 'ac-list' cmd under ap-id; check AC2 ac-protect;
check AP3 current state. No auto-YES."""
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
    buf = b''; end = time.time() + w; s.settimeout(0.5)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

def helpq(s, c, w=5.0):
    s.settimeout(10); s.send(c.encode())
    buf = b''; end = time.time() + w; s.settimeout(0.5)
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
print("\n### ap-id 3 view, then '?' for ac-list/protect commands", flush=True)
print(cmd(s, 'ap-id 3', 2), flush=True)
o = helpq(s, '?', 5.0)
for line in o.splitlines():
    if any(k in line.lower() for k in ['ac','protect','list','dual','home']):
        print("  >", line.strip(), flush=True)
print(cmd(s, '\r\n', 1.0), flush=True)  # back to ap view
print(cmd(s, 'quit', 1.0), flush=True)  # back to wlan view

print("\n### AC1 display ac protect", flush=True)
print(cmd(s, 'display ac protect', 4.0)[-500:], flush=True)
print(cmd(s, 'quit', 1.0), flush=True)
print(cmd(s, 'display ap all', 5.0)[-600:], flush=True)
s.close()

print("\n### AC2 display ac protect + ap all", flush=True)
s = connect('AC2')
print(cmd(s, 'system-view', 2), flush=True)
print(cmd(s, 'wlan', 2), flush=True)
print(cmd(s, 'display ac protect', 4.0)[-500:], flush=True)
print(cmd(s, 'quit', 1.0), flush=True)
print(cmd(s, 'display ap all', 5.0)[-600:], flush=True)
s.close()
print("\n[DONE]", flush=True)
