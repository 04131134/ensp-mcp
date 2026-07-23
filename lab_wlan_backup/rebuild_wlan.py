# -*- coding: utf-8 -*-
"""Configure AC1 (main) with an ENCRYPTED WLAN (WPA2-PSK) and register the 3 APs.
APs obtain mgmt IP from LSW1 (VLAN10, option43 -> 10.1.1.1) and register to AC1
via mac-auth. Wait for registration, then verify.
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg, show, save_log

SSID = 'Office-Cold'
PSK  = 'Huawei@123'

AC1 = [
    'system-view', 'sysname AC1', 'vlan batch 10 40',
    'interface GigabitEthernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Vlanif10', 'ip address 10.1.1.1 24',
    'capwap source interface Vlanif10',
    'wlan',
    'ap auth-mode mac-auth',
    'regulatory-domain-profile name domain1', 'country-code CN', 'quit',
    f'ssid-profile name office', f'ssid {SSID}', 'quit',
    'security-profile name sec1', f'security wpa-wpa2 psk pass-phrase {PSK} aes', 'quit',
    'vap-profile name vap1', 'ssid-profile office', 'security-profile sec1',
    'service-vlan vlan-id 40', 'forward-mode direct-forward', 'quit',
    'ap-group name default', 'regulatory-domain-profile domain1',
    'vap-profile vap1 wlan 1 radio 0', 'vap-profile vap1 wlan 1 radio 1', 'quit',
    'ap-id 1 type-id 45 ap-mac 00e0-fc1b-3720', 'ap-name AP1', 'ap-group default', 'quit',
    'ap-id 2 type-id 45 ap-mac 00e0-fcdb-0400', 'ap-name AP2', 'ap-group default', 'quit',
    'ap-id 3 type-id 45 ap-mac 00e0-fcf8-32e0', 'ap-name AP3', 'ap-group default', 'quit',
    'return',
]

print("=== Configuring AC1 (encrypted WLAN) ===")
cfg('AC1', AC1, verbose=True)

print("\nWaiting 90s for APs to obtain IP + CAPWAP-register to AC1 ...", flush=True)
time.sleep(90)
print("\n[AC1 config pushed + 90s wait done. Run rebuild_verify.py to check AP status.]", flush=True)
