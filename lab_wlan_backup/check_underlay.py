# -*- coding: utf-8 -*-
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import show

print("===== LSW1: Vlanif IP + DHCP used + OSPF peers =====")
for cmd,o in show('LSW1', ['display ip interface brief | include Vlanif',
                            'display ip pool name vlan10 used',
                            'display ip pool name vlan40 used',
                            'display ospf peer brief']):
    print(f"[LSW1] {cmd}:\n{o}\n")

print("===== AR1 / AR2 / AR3: Vlanif IP + OSPF peers =====")
for r in ['AR1','AR2','AR3']:
    for cmd,o in show(r, ['display ip interface brief | include Vlanif',
                          'display ospf peer brief']):
        print(f"[{r}] {cmd}:\n{o}\n")

print("===== AP1/2/3: IP (expect 10.1.1.x) =====")
for ap in ['AP1','AP2','AP3']:
    for cmd,o in show(ap, ['display ip int brief | include Vlanif']):
        print(f"[{ap}] {cmd}:\n{o}\n")
