# -*- coding: utf-8 -*-
"""Point LSW1's AP-mgmt DHCP option43 at BOTH ACs (10.1.1.1,10.1.1.2) so the APs
learn the backup AC and can re-register to AC2 if AC1 fails (cold-standby via
CAPWAP re-registration, NOT the eNSP-incompatible dual-tunnel ac protect).
APs keep their 1-day lease, so no immediate flap; WiFi stays up on AC1.
"""
import sys
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg

LSW1 = [
    'system-view',
    'ip pool vlan10',
    'undo option 43',
    'option 43 sub-option 3 ascii 10.1.1.1,10.1.1.2',
    'quit',
    'return',
]

print("=== Updating LSW1 vlan10 option43 to dual-AC (10.1.1.1,10.1.1.2) ===")
cfg('LSW1', LSW1, verbose=True)
print("\n[option43 updated. APs will learn both ACs on next DHCP renew / failover.]", flush=True)
