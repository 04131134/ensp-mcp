# -*- coding: utf-8 -*-
"""Focused re-probe of LSW1 (longer waits) + AP3 state on both ACs after AC1 restore."""
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
    time.sleep(0.5); drain(s, 0.5)
    s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.6); drain(s, 0.6)
    s.settimeout(10); s.send(b'screen-length 0\r\n'); time.sleep(0.5); drain(s, 0.5)
    return s

def cmd(s, c, w=8.0):
    s.settimeout(10); s.send((c + '\r\n').encode())
    buf = b''; end = time.time() + w; s.settimeout(0.5)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

print("### LSW1 (long waits)", flush=True)
s = connect('LSW1')
for c in ['display ip interface brief', 'display ospf peer brief',
          'display ip pool', 'display vlan', 'display current-configuration | include vlan|Vlanif|dhcp|ospf']:
    out = cmd(s, c, 8.0)
    print("===== %s =====" % c, flush=True)
    print(out[-1200:], flush=True)
s.close()

print("\n### AP state check", flush=True)
for ac in ['AC1','AC2']:
    s = connect(ac)
    out = cmd(s, 'display ap all', 6.0)
    print("===== %s display ap all =====" % ac, flush=True)
    print(out[-900:], flush=True)
    s.close()
print("\n[DONE]", flush=True)
