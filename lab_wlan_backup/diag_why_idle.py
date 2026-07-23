# -*- coding: utf-8 -*-
"""Diagnose WHY AP1/AP2 stay idle on AC1: fail record, unauthorized record,
capwap config, and current ap details."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def drain(s, t=0.5):
    s.settimeout(0.5)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass

def connect_dev(name):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10); s.connect(('127.0.0.1', PORTS[name]))
    time.sleep(0.6); drain(s)
    s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8); drain(s)
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

s = connect_dev('AC1')
for label, cmd, w in [
    ('display ap online-fail-record', 'display ap online-fail-record', 5.0),
    ('display ap unauthorized-record', 'display ap unauthorized-record', 5.0),
    ('display capwap configuration', 'display capwap configuration', 4.0),
    ('display ap all', 'display ap all', 4.0),
]:
    print(f"\n===== {label} =====", flush=True)
    print(read_cmd(s, cmd, w)[-1500:], flush=True)
s.close()
print("\n[DONE]", flush=True)
