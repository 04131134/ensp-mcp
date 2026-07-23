# -*- coding: utf-8 -*-
"""Configure AC2 as COLD standby: same WLAN templates as AC1 but NO ap-id.
CRITICAL: also put GE0/0/1 in trunk allowing VLAN 10 (same bug AC1 had) so
Vlanif10 (10.1.1.2) comes up and CAPWAP source is reachable."""
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

def send_wait(s, cmd, wait=1.2):
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
cmds = [
    'system-view',
    'sysname AC2',
    'vlan batch 10 40',
    'interface Vlanif10', 'ip address 10.1.1.2 24', 'quit',
    'interface GigabitEthernet0/0/1',
    'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 40',
    'quit',
    'capwap source interface Vlanif10',
    'wlan',
    'ap auth-mode mac-auth',
    'regulatory-domain-profile name domain1', 'country-code CN', 'quit',
    'ssid-profile name office', 'ssid Office-Cold', 'quit',
    'security-profile name sec1', 'security wpa-wpa2 psk pass-phrase Huawei@123 aes', 'quit',
    'vap-profile name vap1', 'ssid-profile office', 'security-profile sec1',
    'service-vlan vlan-id 40', 'forward-mode direct-forward', 'quit',
    'ap-group name default', 'regulatory-domain-profile domain1',
    'vap-profile vap1 wlan 1 radio 0', 'vap-profile vap1 wlan 1 radio 1', 'quit',
    'return',
]
for c in cmds:
    print(f"> {c}", flush=True)
    print(send_wait(s, c, 1.2)[-120:], flush=True)
    time.sleep(0.3)

print("\n--- verify Vlanif10 up on AC2 ---", flush=True)
print(send_wait(s, 'display ip interface brief', 3.0)[-700:], flush=True)
print("\n--- verify capwap source ---", flush=True)
print(send_wait(s, 'display capwap configuration', 3.0)[-400:], flush=True)
s.close()
print("\n[DONE]", flush=True)
