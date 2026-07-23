# -*- coding: utf-8 -*-
"""Configure AC2 (backup) with the SAME encrypted WLAN + same 3 APs as AC1,
and enable AC6005 dual-link cold-standby backup (ac protect) pointing at AC1.
AC2 Vlanif10 = 10.1.1.2; no DHCP (LSW1 handles AP mgmt).
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg

SSID = 'Office-Cold'
PSK  = 'Huawei@123'

AC2 = [
    'system-view', 'sysname AC2', 'vlan batch 10 40',
    'interface GigabitEthernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Vlanif10', 'ip address 10.1.1.2 24',
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
    # register same 3 APs; ac-list points each AP at AC1 as its backup AC
    'ap-id 1 type-id 45 ap-mac 00e0-fc1b-3720', 'ap-name AP1', 'ap-group default', 'ac-list 10.1.1.1', 'quit',
    'ap-id 2 type-id 45 ap-mac 00e0-fcdb-0400', 'ap-name AP2', 'ap-group default', 'ac-list 10.1.1.1', 'quit',
    'ap-id 3 type-id 45 ap-mac 00e0-fcf8-32e0', 'ap-name AP3', 'ap-group default', 'ac-list 10.1.1.1', 'quit',
    'quit',  # exit wlan view -> system-view
    # dual-link cold-standby backup (AC2 is lower priority = backup)
    'ac protect enable', 'ac protect priority 1', 'ac protect protect-ac 10.1.1.1',
    'return',
]

print("=== Configuring AC2 (encrypted WLAN + cold-standby backup) ===")
cfg('AC2', AC2, verbose=True)
print("\n[AC2 config pushed.]", flush=True)
