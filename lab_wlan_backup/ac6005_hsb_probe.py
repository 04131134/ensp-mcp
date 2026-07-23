# -*- coding: utf-8 -*-
"""Probe AC6005 wlan-view to discover the REAL HSB/ac-protect syntax.
No auto-YES (avoid corruption). Use '?' help and exact-error capture."""
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

def cmd(s, c, w=6.0):
    s.settimeout(10); s.send((c + '\r\n').encode())
    buf = b''; end = time.time() + w; s.settimeout(0.5)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

def helpq(s, c, w=6.0):
    # send help query (no trailing CR) and read
    s.settimeout(10); s.send(c.encode())
    buf = b''; end = time.time() + w; s.settimeout(0.5)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
            if b'<AC1' in buf or b'<AC2' in buf:  # prompt returned
                break
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

s = connect('AC1')
print("== enter wlan ==", cmd(s, 'system-view', 2), flush=True)
print(cmd(s, 'wlan', 2), flush=True)

print("\n### exact: 'ac protect enable'", flush=True)
print(cmd(s, 'ac protect enable', 4.0)[-400:], flush=True)

print("\n### help: 'ac protect ?'", flush=True)
print(helpq(s, 'ac protect ?', 5.0)[-600:], flush=True)
print(cmd(s, '\r\n', 1.0), flush=True)  # clear

print("\n### help: 'ac ?'", flush=True)
print(helpq(s, 'ac ?', 5.0)[-600:], flush=True)
print(cmd(s, '\r\n', 1.0), flush=True)

print("\n### exact: 'display ac protect'", flush=True)
print(cmd(s, 'display ac protect', 4.0)[-400:], flush=True)

print("\n### help: 'display ?' filter protect/ac/hsb/backup", flush=True)
o = helpq(s, 'display ?', 6.0)
for line in o.splitlines():
    if any(k in line.lower() for k in ['protect','hsb','backup','ac ']):
        print("  >", line, flush=True)
s.close()
print("\n[DONE]", flush=True)
