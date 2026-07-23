# -*- coding: utf-8 -*-
"""1) Restore AC1 Vlanif10 (undo shutdown from cold test).
2) Probe underlay state of LSW1/AR1/AR2/AR3 to know what's actually configured.
Uses raw socket with auto-YES to be safe against [Y/N] prompts."""
import sys, time, socket, re
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
    return s

def cmd(s, c, w=4.0, auto_yes=True):
    s.settimeout(10); s.send((c + '\r\n').encode())
    buf = b''; end = time.time() + w; s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536); buf += d
            if auto_yes and (b'[Y/N]' in buf or b'Whether to continue' in buf or b'continue? [Y/N]' in buf.lower()):
                s.send(b'YES\r\n'); time.sleep(0.4)
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

print(">> Restore AC1 Vlanif10", flush=True)
s = connect('AC1')
print(cmd(s, 'system-view', 2))
print(cmd(s, 'interface Vlanif 10', 2))
print(cmd(s, 'undo shutdown', 2))
print(cmd(s, 'return', 2))
time.sleep(2)
print("AC1 Vlanif10:", cmd(s, 'display interface Vlanif 10 | include Internet', 3)[-120:], flush=True)
s.close()

def probe(name, cmds):
    print("\n" + "="*60, "\n### %s" % name, flush=True)
    s = connect(name)
    for c in cmds:
        out = cmd(s, c, 4.0)
        print("----- %s -----" % c, flush=True)
        print(out[-900:], flush=True)
    s.close()

probe('LSW1', ['display ip interface brief | include Vlanif',
               'display ospf peer brief',
               'display ip pool | include Pool',
               'display vlan | include 10|20|30|40'])
probe('AR1', ['display ip interface brief | include Vlanif', 'display ospf peer brief'])
probe('AR2', ['display ip interface brief | include Vlanif', 'display ospf peer brief'])
probe('AR3', ['display ip interface brief | include Vlanif', 'display ospf peer brief'])
print("\n[DONE]", flush=True)
