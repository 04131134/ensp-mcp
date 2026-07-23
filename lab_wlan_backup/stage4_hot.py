# -*- coding: utf-8 -*-
"""Stage 4: HOT backup (HSB) on AC6005.
Modify both ACs to dual-home APs: global `ac protect enable` + priority + protect-ac,
and per-AP `ac-list <peer>`. AC1=main(pri7), AC2=backup(pri5). Verify roles, then
simulate AC1 failure (shutdown Vlanif10) -> AC2 auto becomes Active; recover -> AC1
rejoins as Standby (no preempt).
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg, show, save_log

# Bring AC1 back up if it was shut down by the cold test
cfg('AC1', ['system-view','interface Vlanif10','undo shutdown','return'], verbose=False)
time.sleep(3)

AC1_HOT = [
    'system-view','wlan',
    'ac protect enable','ac protect priority 7','ac protect protect-ac 10.1.1.2',
    'ssid-profile name office','ssid Office-HSB','quit',
    'ap-id 1','ac-list 10.1.1.2','quit',
    'ap-id 2','ac-list 10.1.1.2','quit',
    'ap-id 3','ac-list 10.1.1.2','quit',
    'return',
]
AC2_HOT = [
    'system-view','wlan',
    'ac protect enable','ac protect priority 5','ac protect protect-ac 10.1.1.1',
    'ap-id 1','ac-list 10.1.1.1','quit',
    'ap-id 2','ac-list 10.1.1.1','quit',
    'ap-id 3','ac-list 10.1.1.1','quit',
    'return',
]
print("=== Configuring AC1 HSB (main) ==="); cfg('AC1', AC1_HOT, verbose=False)
print("=== Configuring AC2 HSB (backup) ==="); cfg('AC2', AC2_HOT, verbose=False)
print("    waiting 60s for APs to dual-home ..."); time.sleep(60)

def snap(label):
    out=[f"\n##### {label} #####"]
    for c,o in show('AC1',['display ac-protect','display ap all']): out.append(f"[AC1] {c}:\n{o}")
    for c,o in show('AC2',['display ac-protect','display ap all']): out.append(f"[AC2] {c}:\n{o}")
    return out

log=[]
log += snap("INITIAL (AC1=main, AC2=backup)")
print("\n".join(log[-40:]))

print("\n>>> [HOT] shutdown AC1 Vlanif10 (simulate AC1 failure)")
cfg('AC1', ['system-view','interface Vlanif10','shutdown','return'], verbose=False)
print("    waiting 35s for AC2 to take over ..."); time.sleep(35)
log += snap("AFTER AC1 FAILURE (expect AC2 Active, APs still normal/online)")
print("\n".join(log[-40:]))

print("\n>>> [HOT] recover AC1 (undo shutdown Vlanif10)")
cfg('AC1', ['system-view','interface Vlanif10','undo shutdown','return'], verbose=False)
print("    waiting 45s for AC1 to rejoin as Standby ..."); time.sleep(45)
log += snap("AFTER AC1 RECOVERY (expect AC2 still Active, AC1 Standby, no preempt)")
print("\n".join(log[-40:]))

text="\n".join(log)
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/hot_verify.txt', text)
print("\n[saved] logs/hot_verify.txt")
