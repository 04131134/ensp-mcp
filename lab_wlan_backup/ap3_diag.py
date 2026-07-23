# -*- coding: utf-8 -*-
"""Diagnose AP3: ping its last IP, check ap verbose, capwap link, and LSW1 MAC table reachability."""
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
    buf = b''; end = time.time() + w; s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

print("### ping AP3 last IP 10.1.1.251 from AR1", flush=True)
s = connect('AR1')
o = cmd(s, 'ping -c 3 10.1.1.251', 12.0)
print([l for l in o.splitlines() if 'packet' in l][-1:] or o[-120:], flush=True)
s.close()

print("\n### AC1 display ap id 3 verbose", flush=True)
s = connect('AC1')
print(cmd(s, 'display ap id 3 verbose', 6.0)[-900:], flush=True)
s.close()

print("\n### AC2 display ap id 3 verbose", flush=True)
s = connect('AC2')
print(cmd(s, 'display ap id 3 verbose', 6.0)[-900:], flush=True)
s.close()

print("\n### try re-provision: undo ap-id 3 then re-add on AC2 and wait 60s", flush=True)
s = connect('AC2')
cmd(s, 'system-view', 2); cmd(s, 'wlan', 2)
cmd(s, 'undo ap-id 3', 3.0)
cmd(s, 'ap-id 3 type-id 45 ap-mac 00e0-fcf8-32e0', 3.0)
cmd(s, 'ap-name AP3', 2.0)
cmd(s, 'ap-group default', 2.0)
cmd(s, 'quit', 2.0); cmd(s, 'quit', 2.0); cmd(s, 'return', 2.0)
s.close()
time.sleep(60)
s = connect('AC2')
print(cmd(s, 'display ap all', 6.0)[-400:], flush=True)
s.close()
print("\n[DONE]", flush=True)
