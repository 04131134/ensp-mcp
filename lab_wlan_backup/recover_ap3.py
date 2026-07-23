# -*- coding: utf-8 -*-
"""Recover AP3: undo 'ac protect enable' on both ACs (HSB was destabilizing AP3 in
eNSP), then wait for AP3 to re-register in plain single-home mode (proven earlier)."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS, save_log

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
    time.sleep(0.6); drain(s, 0.6)
    s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.6); drain(s, 0.6)
    return s

def cmd(s, c, w=5.0):
    s.settimeout(10); s.send((c + '\r\n').encode())
    buf = b''; end = time.time() + w; sent_yes = False
    s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536); buf += d
            tail = buf[-40:].lower()
            if (not sent_yes) and (b'[y/n]' in tail or b'whether to continue' in tail):
                s.send(b'YES\r\n'); sent_yes = True; time.sleep(0.6)
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

log = []
for ac in ['AC1','AC2']:
    print(">> undo ac protect enable on %s" % ac, flush=True)
    s = connect(ac)
    # may already be in wlan-view from prior session; be safe:
    r = cmd(s, 'system-view', 2)
    r += cmd(s, 'wlan', 2)
    r += cmd(s, 'undo ac protect enable', 4.0)
    print(r[-200:], flush=True)
    log.append("[%s] undo ac protect: %s" % (ac, r[-120:]))
    s.close()

print("    waiting 120s for AP3 to re-register ...", flush=True); time.sleep(120)

for ac in ['AC1','AC2']:
    s = connect(ac)
    o = cmd(s, 'display ap all', 6.0)
    print("[%s] %s" % (ac, o[-300:]), flush=True)
    log.append("[%s] ap all: %s" % (ac, o[-200:]))
    s.close()

text = "\n".join(log)
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/recover_ap3.txt', text)
print("\n[saved] logs/recover_ap3.txt\n[DONE]", flush=True)
