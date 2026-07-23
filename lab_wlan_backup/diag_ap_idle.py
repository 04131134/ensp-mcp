# -*- coding: utf-8 -*-
"""Diagnose why 3 APs are stuck idle on AC1: check AC1 Vlanif10 + uplink VLAN,
and AP reachability to AC1."""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import show

print("===== AC1: ip interface brief =====")
for c,o in show('AC1', ['display ip interface brief']):
    print(o)

print("\n===== AC1: interface brief =====")
for c,o in show('AC1', ['display interface brief']):
    print(o)

print("\n===== AC1: vlan =====")
for c,o in show('AC1', ['display vlan']):
    print(o)

print("\n===== AC1: ping AP1 (10.1.1.253) =====")
for c,o in show('AC1', ['ping -c 3 10.1.1.253']):
    print(o)

print("\n===== AP1: ip interface brief =====")
for c,o in show('AP1', ['display ip interface brief']):
    print(o)

print("\n===== AP1: ping AC1 (10.1.1.1) =====")
for c,o in show('AP1', ['ping -c 3 10.1.1.1']):
    print(o)
