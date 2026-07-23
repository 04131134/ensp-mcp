# -*- coding: utf-8 -*-
"""Fix AC2: it got wedged at a pending [Y/N] (regulatory-domain bind resets AP).
Answer YES, then bind vap1 to ap-group default radios 0/1, then verify."""
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

def send_wait(s, cmd, wait=1.3):
    s.settimeout(10); s.send((cmd + '\r\n').encode())
    buf = b''; end = time.time() + wait
    s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

s = connect_dev('AC2')
# clear any pending prompt
s.settimeout(10); s.send(b'YES\r\n'); time.sleep(1.0); drain(s, 1.0)
s.settimeout(10); s.send(b'\r\n'); time.sleep(0.5); drain(s, 0.5)

# ensure in wlan ap-group default and bind vap
for c in ['system-view', 'wlan', 'ap-group name default',
          'vap-profile vap1 wlan 1 radio 0', 'vap-profile vap1 wlan 1 radio 1', 'quit', 'quit']:
    print(f"> {c}", flush=True)
    o = send_wait(s, c, 1.3)
    print(o[-140:], flush=True)
    if 'Y/N' in o:
        s.settimeout(10); s.send(b'YES\r\n'); time.sleep(1.0); drain(s, 1.0)
        print("  YES sent", flush=True)
    time.sleep(0.3)

print("\n--- verify ap-group default ---", flush=True)
print(send_wait(s, 'display ap-group name default', 4.0)[-900:], flush=True)
print("\n--- verify Vlanif10 / capwap ---", flush=True)
print(send_wait(s, 'display ip interface brief', 3.0)[-500:], flush=True)
print(send_wait(s, 'display capwap configuration', 3.0)[-300:], flush=True)
s.close()
print("\n[DONE]", flush=True)
