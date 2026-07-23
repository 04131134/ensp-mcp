# -*- coding: utf-8 -*-
"""RECOVER from broken ac-protect dual-tunnel: remove ac protect + ac-list from
BOTH ACs so the APs stop trying to build (unsupported in eNSP) dual CAPWAP tunnels
and re-establish a single tunnel to AC1 (primary). Cold-standby failover will be
restored later via option43 listing both AC IPs (no dual-tunnel).
"""
import sys
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg

CLEAN = [
    'system-view',
    'undo ac protect',
    'wlan',
    'ap-id 1', 'undo ac-list', 'quit',
    'ap-id 2', 'undo ac-list', 'quit',
    'ap-id 3', 'undo ac-list', 'quit',
    'quit',
    'return',
]

print("=== Cleaning ac protect / ac-list from AC1 ===")
cfg('AC1', CLEAN, verbose=True)
print("\n=== Cleaning ac protect / ac-list from AC2 ===")
cfg('AC2', CLEAN, verbose=True)
print("\n[Dual-tunnel config removed from both ACs. Wait for APs to re-register to AC1.]", flush=True)
