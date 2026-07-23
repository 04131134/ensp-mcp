# -*- coding: utf-8 -*-
"""Probe LSW1 (retry, longer wait) and AC1 current running config essentials."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def send_read(name, cmd, wait=5.0):
    port = PORTS[name]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect(('127.0.0.1', port))
    time.sleep(0.5)
    s.settimeout(0.5)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass
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
    s.close()
    return buf.decode('gbk', errors='ignore')

print("===== LSW1 display version (wait 5s) =====", flush=True)
print(send_read('LSW1', 'display version', 5.0)[-600:], flush=True)

print("\n===== AC1 display ip interface brief =====", flush=True)
print(send_read('AC1', 'display ip interface brief', 5.0)[-1200:], flush=True)

print("\n===== AC1 display vlan =====", flush=True)
print(send_read('AC1', 'display vlan', 5.0)[-1500:], flush=True)

print("\n===== AC1 display interface brief =====", flush=True)
print(send_read('AC1', 'display interface brief', 5.0)[-1500:], flush=True)
print("\n[DONE]", flush=True)
