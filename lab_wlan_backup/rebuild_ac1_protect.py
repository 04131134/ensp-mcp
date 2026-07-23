# -*- coding: utf-8 -*-
"""Add AC6005 dual-link cold-standby backup (ac protect) to the ALREADY-configured
AC1 so it becomes the primary and the APs build backup tunnels to AC2 (10.1.1.2).
AC1 already has the encrypted WLAN + 3 APs registered; we just layer the backup.
"""
import sys
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg

AC1_PROTECT = [
    'system-view',
    # global dual-link backup (AC1 is higher priority = primary)
    'ac protect enable', 'ac protect priority 0', 'ac protect protect-ac 10.1.1.2',
    'wlan',
    # tell each AP that AC2 (10.1.1.2) is its backup AC
    'ap-id 1', 'ac-list 10.1.1.2', 'quit',
    'ap-id 2', 'ac-list 10.1.1.2', 'quit',
    'ap-id 3', 'ac-list 10.1.1.2', 'quit',
    'quit',  # exit wlan view -> system-view
    'return',
]

print("=== Adding ac protect (cold-standby) to AC1 ===")
cfg('AC1', AC1_PROTECT, verbose=True)
print("\n[AC1 protect config pushed.]", flush=True)
