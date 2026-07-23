# -*- coding: utf-8 -*-
"""Immediate (no-sleep) state probe of AC1 + AC2: ap all, vlanif, radio, vap."""
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

def read_cmd(s, cmd, w=4.0):
    s.settimeout(10); s.send((cmd + '\r\n').encode())
    buf = b''; end = time.time() + w
    s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

for name in ['AC1', 'AC2']:
    print("="*70, flush=True)
    print("DEVICE:", name, flush=True)
    try:
        s = connect_dev(name)
        for c in ['display ap all', 'display interface Vlanif 10 | include Internet',
                  'display radio all', 'display vap all']:
            out = read_cmd(s, c, 4.0)
            print("----- %s -----" % c, flush=True)
            print(out[-1100:], flush=True)
        s.close()
    except Exception as e:
        print("  ERROR:", e, flush=True)
print("="*70, "\n[DONE]", flush=True)
