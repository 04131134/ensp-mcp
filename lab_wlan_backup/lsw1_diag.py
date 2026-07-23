# -*- coding: utf-8 -*-
"""Test whether LSW1 is still forwarding (L3 backbone). Fix bytes bug."""
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
    return b''

def connect(name):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10); s.connect(('127.0.0.1', PORTS[name]))
    time.sleep(0.6); drain(s, 0.6)
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

print("### L3 backbone via LSW1", flush=True)
s = connect('AR1')
for ip in ['10.1.1.254','192.168.20.1','10.1.1.3','10.1.1.12','10.1.1.2']:
    out = cmd(s, 'ping -c 2 %s' % ip, 9.0)
    line = [l for l in out.splitlines() if 'packet' in l]
    ok = 'OK' if line and '0 packet(s) received' not in line[-1] else 'FAIL'
    print("AR1 ping %-14s -> %s | %s" % (ip, ok, line[-1] if line else out[-100:]), flush=True)
s.close()

print("\n### AR3 -> LSW1 Vlanif40 gateway (STA subnet)", flush=True)
s = connect('AR3')
out = cmd(s, 'ping -c 2 192.168.40.254', 9.0)
line = [l for l in out.splitlines() if 'packet' in l]
print("AR3 ping 192.168.40.254 ->", line[-1] if line else out[-100:], flush=True)
s.close()
print("\n[DONE]", flush=True)
