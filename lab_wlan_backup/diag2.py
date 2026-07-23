# -*- coding: utf-8 -*-
"""Robust diagnostic: probe AC1 and LSW1 only (avoid AP consoles that may hang),
flush output, isolate each device so one bad box can't stall the rest."""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS, show

def probe(name, cmds):
    print(f"\n========== {name} ==========", flush=True)
    try:
        for c, o in show(name, cmds):
            print(f"--- {c} ---", flush=True)
            print(o, flush=True)
    except Exception as e:
        print(f"[{name}] ERROR: {e}", flush=True)

probe('AC1', ['display ip interface brief', 'display vlan', 'display interface brief'])
probe('LSW1', ['display ip interface brief', 'display vlan', 'display interface brief'])
print("\n[DONE]", flush=True)
