# -*- coding: utf-8 -*-
"""Step 1: confirm AC1 Vlanif10 still up + ping AP subnet.
Step 2: ap-reset ap-id 1 & 2 from AC1 wlan-view with YES confirm, then wait+verify."""
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
print("--- Vlanif10 status ---", flush=True)
print(read_cmd(s, 'display ip interface brief', 4.0)[-700:], flush=True)
print("--- ping AP subnet 10.1.1.253/252/251 ---", flush=True)
for ip in ['10.1.1.251','10.1.1.252','10.1.1.253']:
    print(f"ping {ip}:", read_cmd(s, f'ping -c 3 {ip}', 6.0).split('\n')[-3:], flush=True)

# go to wlan view and ap-reset both with YES
print("--- ap-reset ap-id 1 & 2 (YES) ---", flush=True)
s.settimeout(10); s.send(b'system-view\r\n'); time.sleep(0.5); drain(s)
s.settimeout(10); s.send(b'wlan\r\n'); time.sleep(0.5); drain(s)
for apid in [1, 2]:
    s.settimeout(10); s.send(f'ap-reset ap-id {apid}\r\n'.encode()); time.sleep(1.2)
    o = read_cmd(s, '', 1.2)
    print(f"ap-id {apid}:", o[-160], flush=True)
    if 'Y/N' in o:
        s.settimeout(10); s.send(b'YES\r\n'); time.sleep(1.5); drain(s)
        print(f"  YES sent for ap-id {apid}", flush=True)
s.close()

print("Waiting 80s for AP1/AP2 reset + re-register ...", flush=True)
time.sleep(80)

s = connect_dev('AC1')
for label, cmd, w in [
    ('display ap all', 'display ap all', 4.0),
    ('display radio all', 'display radio all', 4.0),
    ('display vap all', 'display vap all', 4.0),
]:
    print(f"\n===== {label} =====", flush=True)
    print(read_cmd(s, cmd, w)[-1700:], flush=True)
s.close()
print("\n[DONE]", flush=True)
