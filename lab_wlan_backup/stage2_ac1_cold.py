# -*- coding: utf-8 -*-
"""Stage 2: AC1 = main AC (cold backup role). Configure WLAN + pre-provision 3 APs
(AP3030DN -> type-id 45 on both ACs). mac-auth so APs register ONLY to AC1 (cold:
AC2 has no ap-id, so it won't accept them). SSID=Office-Cold, PSK Huawei@123,
service-vlan 40, direct-forward.
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg, show, save_log

AC1 = [
    'system-view', 'sysname AC1', 'vlan batch 10 40',
    'interface Vlanif10', 'ip address 10.1.1.1 24',
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
    'ap-id 1 type-id 45 ap-mac 00e0-fc1b-3720', 'ap-name AP1', 'ap-group default', 'quit',
    'ap-id 2 type-id 45 ap-mac 00e0-fcdb-0400', 'ap-name AP2', 'ap-group default', 'quit',
    'ap-id 3 type-id 45 ap-mac 00e0-fcf8-32e0', 'ap-name AP3', 'ap-group default', 'quit',
    'return',
]

print("=== Configuring AC1 (main) ===")
cfg('AC1', AC1, verbose=False)

# wait for APs to register
print("Waiting 60s for APs to obtain IP + CAPWAP register to AC1 ...")
time.sleep(60)

out = []
out.append("===== AC1 display ap all =====")
for cmd,o in show('AC1', ['display ap all']):
    out.append(o)
out.append("\n===== AC1 display radio all =====")
for cmd,o in show('AC1', ['display radio all']):
    out.append(o)
out.append("\n===== AC1 display vap 0/1 =====")
for cmd,o in show('AC1', ['display vap 0']):
    out.append(o)

text = "\n".join(out)
print(text)
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/ac1_cold_verify.txt', text)
print("\n[saved] logs/ac1_cold_verify.txt")
