# -*- coding: utf-8 -*-
"""Finalize HSB: apply correct 'ac-list ip-address <peer>' under each ap-id on both ACs.
Improved cmd(): send YES at most ONCE per command (no re-send corruption).
Then wait for AP3 to establish dual CAPWAP tunnels."""
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

def cfg_seq(s, cmds, w=4.0):
    for c in cmds:
        r = cmd(s, c, w)
        if 'Error' in r and 'already' not in r:
            print("  [ERR] %s : %s" % (c, r.strip()[-160:]), flush=True)

log = []
for ac, peer in [('AC1','10.1.1.2'), ('AC2','10.1.1.1')]:
    print(">> configure %s ac-list -> %s" % (ac, peer), flush=True)
    s = connect(ac)
    cfg_seq(s, ['system-view','wlan',
                'ap-id 1','ac-list ip-address %s' % peer,'quit',
                'ap-id 2','ac-list ip-address %s' % peer,'quit',
                'ap-id 3','ac-list ip-address %s' % peer,'quit',
                'quit','return'])
    s.close()

print("    waiting 90s for AP3 to establish dual CAPWAP tunnels ...", flush=True); time.sleep(90)

def snap(label):
    out = ["\n##### %s #####" % label]
    for ac in ['AC1','AC2']:
        s = connect(ac)
        for c in ['display ac protect','display ap all','display radio all','display vap all']:
            o = cmd(s, c, 5.0)
            out.append("[%s] %s:\n%s" % (ac, c, o[-700:]))
        s.close()
    txt = "\n".join(out)
    print(txt, flush=True); log.append(txt)

snap("HSB INITIAL (expect AP3 normal/dual on both, AC1 Active)")
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/hsb_initial.txt', "\n".join(log))
print("\n[saved] logs/hsb_initial.txt\n[DONE]", flush=True)
