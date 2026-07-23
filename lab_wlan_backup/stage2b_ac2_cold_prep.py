# -*- coding: utf-8 -*-
"""Stage 2b: AC2 cold-prep. Same WLAN business templates as AC1 (so APs can serve
once they fail over), but NO ap-id (cold: AC2 must not accept APs until manual switch).
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg, show, save_log

AC2 = [
    'system-view', 'sysname AC2', 'vlan batch 10 40',
    'interface Vlanif10', 'ip address 10.1.1.2 24',
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
print("=== Configuring AC2 (cold-prep, no ap-id) ===")
cfg('AC2', AC2, verbose=False)
print("done")
