# -*- coding: utf-8 -*-
"""HOT standby (HSB) test on AC6005.
- AC1 (pri7, active) + AC2 (pri5, standby) dual-home AP3 via ac-list.
- SSID switched to Office-HSB per scheme.
- Verify roles, then shutdown AC1 Vlanif10 -> AC2 auto Active; recover -> AC2 stays Active (no preempt).
Robust raw-socket with auto-YES against [Y/N] prompts.
Only AP3 can participate (AP1/AP2 stuck idle, telnet-unrebootable in eNSP).
"""
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

def cmd(s, c, w=5.0, auto=True):
    s.settimeout(10); s.send((c + '\r\n').encode())
    buf = b''; end = time.time() + w; s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536); buf += d
            low = buf.lower()
            if auto and (b'[y/n]' in low or b'whether to continue' in low):
                s.send(b'YES\r\n'); time.sleep(0.5)
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

def cfg_seq(s, cmds, w=4.0):
    for c in cmds:
        r = cmd(s, c, w)
        if 'Error' in r and 'already' not in r:
            print("  [ERR] %s : %s" % (c, r.strip()[-150:]), flush=True)

log = []
def snap(label):
    out = ["\n##### %s #####" % label]
    for ac in ['AC1','AC2']:
        s = connect(ac)
        for c in ['display ac-protect','display ap all','display station all']:
            o = cmd(s, c, 5.0)
            out.append("[%s] %s:\n%s" % (ac, c, o[-700:]))
        s.close()
    txt = "\n".join(out)
    print(txt, flush=True)
    log.append(txt)
    return txt

print(">> [HSB] configure AC1 (active, pri7)", flush=True)
s = connect('AC1')
cfg_seq(s, ['system-view','wlan',
            'ssid-profile name office','ssid Office-HSB','quit',
            'ac protect enable','ac protect priority 7','ac protect protect-ac 10.1.1.2',
            'ap-id 1','ac-list 10.1.1.2','quit',
            'ap-id 2','ac-list 10.1.1.2','quit',
            'ap-id 3','ac-list 10.1.1.2','quit',
            'quit','return'])
s.close()

print(">> [HSB] configure AC2 (standby, pri5)", flush=True)
s = connect('AC2')
cfg_seq(s, ['system-view','wlan',
            'ssid-profile name office','ssid Office-HSB','quit',
            'ac protect enable','ac protect priority 5','ac protect protect-ac 10.1.1.1',
            'ap-id 1','ac-list 10.1.1.1','quit',
            'ap-id 2','ac-list 10.1.1.1','quit',
            'ap-id 3','ac-list 10.1.1.1','quit',
            'quit','return'])
s.close()

print("    waiting 70s for AP3 dual-home ...", flush=True); time.sleep(70)
snap("INITIAL: AC1=Active(pri7) AC2=Standby(pri5), AP3 dual-homed")

print(">> [HSB] simulate AC1 failure: shutdown Vlanif10", flush=True)
s = connect('AC1'); cfg_seq(s, ['system-view','interface Vlanif 10','shutdown','return']); s.close()
print("    waiting 40s for AC2 to take over ...", flush=True); time.sleep(40)
snap("AFTER AC1 FAILURE: expect AC2 Active, AP3 still normal")

print(">> [HSB] recover AC1: undo shutdown Vlanif10", flush=True)
s = connect('AC1'); cfg_seq(s, ['system-view','interface Vlanif 10','undo shutdown','return']); s.close()
print("    waiting 50s for AC1 to rejoin as Standby (no preempt) ...", flush=True); time.sleep(50)
snap("AFTER AC1 RECOVERY: expect AC2 still Active, AC1 Standby")

text = "\n".join(log)
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/hot_verify.txt', text)
print("\n[saved] logs/hot_verify.txt\n[DONE]", flush=True)
