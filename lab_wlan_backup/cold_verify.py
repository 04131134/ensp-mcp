# -*- coding: utf-8 -*-
"""Wait for AP3 to finish re-registering to AC2 after AC1 Vlanif10 shutdown,
then verify AP state on both ACs + radios + vap."""
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

print("Waiting 150s for AP3 to complete re-registration to AC2 ...", flush=True)
time.sleep(150)

s = connect_dev('AC2')
print("\n===== AC2 display ap all =====", flush=True)
print(read_cmd(s, 'display ap all', 4.0)[-1400:], flush=True)
print("\n===== AC2 display radio all =====", flush=True)
print(read_cmd(s, 'display radio all', 4.0)[-800:], flush=True)
print("\n===== AC2 display vap all =====", flush=True)
print(read_cmd(s, 'display vap all', 4.0)[-800:], flush=True)
s.close()

s = connect_dev('AC1')
print("\n===== AC1 display ap all =====", flush=True)
print(read_cmd(s, 'display ap all', 4.0)[-1400:], flush=True)
s.close()
print("\n[DONE]", flush=True)
