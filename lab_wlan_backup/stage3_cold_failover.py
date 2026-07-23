# -*- coding: utf-8 -*-
"""Stage 3: COLD backup failover (manual switch).
Pre: APs registered/normal on AC1. Simulate AC1 failure (shutdown Vlanif10),
APs lose CAPWAP to AC1; manually add ap-ids on AC2 so APs register to AC2.
Verify APs become normal on AC2 and SSID still broadcasts.
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg, show, save_log

print(">>> [COLD] shutdown AC1 Vlanif10 (simulate AC1 failure)")
cfg('AC1', ['system-view','interface Vlanif10','shutdown','return'], verbose=False)
print("    waiting 50s for APs to detect AC1 down ...")
time.sleep(50)

print(">>> [COLD] add ap-ids on AC2 (manual switch)")
cfg('AC2', [
    'system-view','wlan',
    'ap-id 1 type-id 45 ap-mac 00e0-fc1b-3720','ap-name AP1','ap-group default','quit',
    'ap-id 2 type-id 45 ap-mac 00e0-fcdb-0400','ap-name AP2','ap-group default','quit',
    'ap-id 3 type-id 45 ap-mac 00e0-fcf8-32e0','ap-name AP3','ap-group default','quit',
    'return',
], verbose=False)
print("    waiting 60s for APs to register to AC2 ...")
time.sleep(60)

out=[]
out.append("===== AC2 display ap all (expect 3 normal) =====")
for c,o in show('AC2',['display ap all']): out.append(o)
out.append("\n===== AC2 display radio all (expect radios up) =====")
for c,o in show('AC2',['display radio all']): out.append(o)
out.append("\n===== AC2 display vap 0 (expect SSID broadcast) =====")
for c,o in show('AC2',['display vap 0']): out.append(o)
out.append("\n===== AC1 display ap all (expect empty/fault) =====")
for c,o in show('AC1',['display ap all']): out.append(o)

text="\n".join(out)
print(text)
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/cold_failover_verify.txt', text)
print("\n[saved] logs/cold_failover_verify.txt")
