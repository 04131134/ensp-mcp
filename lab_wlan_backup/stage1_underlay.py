# -*- coding: utf-8 -*-
"""Stage 1: underlay - LSW1 core L3/DHCP + AR1/AR2/AR3 OSPF transit.
Goal: APs get mgmt IP in VLAN10 (LSW1 DHCP), wireless STA gets VLAN40 (LSW1 DHCP),
and OSPF gives full L3 connectivity across 10.1.1.0/24, 192.168.10/20/40.0/24.
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg, show, PORTS, save_log

LSW1 = [
    'system-view', 'sysname LSW1', 'vlan batch 10 20 30 40',
    'interface GigabitEthernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface GigabitEthernet0/0/2', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface GigabitEthernet0/0/3', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface GigabitEthernet0/0/4', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface GigabitEthernet0/0/5', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Vlanif10', 'ip address 10.1.1.254 24',
    'interface Vlanif40', 'ip address 192.168.40.254 24',
    'dhcp enable',
    'ip pool vlan10', 'gateway-list 10.1.1.254', 'network 10.1.1.0 mask 24',
    'excluded-ip-address 10.1.1.1 10.1.1.3', 'excluded-ip-address 10.1.1.254',
    'option 43 sub-option 3 ascii 10.1.1.1',
    'ip pool vlan40', 'gateway-list 192.168.40.254', 'network 192.168.40.0 mask 24',
    'excluded-ip-address 192.168.40.1 192.168.40.3', 'excluded-ip-address 192.168.40.254',
    'interface Vlanif10', 'dhcp select global',
    'interface Vlanif40', 'dhcp select global',
    'ospf 1 router-id 10.1.1.254', 'area 0', 'network 10.1.1.0 0.0.0.255', 'network 192.168.40.0 0.0.0.255',
    'return',
]

AR1 = [
    'system-view', 'sysname AR1', 'vlan batch 10 20',
    'interface Ethernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Ethernet0/0/0', 'port link-type access', 'port default vlan 20',
    'interface Vlanif10', 'ip address 10.1.1.11 24',
    'interface Vlanif20', 'ip address 192.168.10.1 24',
    'ospf 1 router-id 10.1.1.11', 'area 0', 'network 10.1.1.0 0.0.0.255', 'network 192.168.10.0 0.0.0.255',
    'return',
]

AR2 = [
    'system-view', 'sysname AR2', 'vlan batch 10 30',
    'interface Ethernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Ethernet0/0/0', 'port link-type access', 'port default vlan 30',
    'interface Vlanif10', 'ip address 10.1.1.12 24',
    'interface Vlanif30', 'ip address 192.168.20.1 24',
    'ospf 1 router-id 10.1.1.12', 'area 0', 'network 10.1.1.0 0.0.0.255', 'network 192.168.20.0 0.0.0.255',
    'return',
]

AR3 = [
    'system-view', 'sysname AR3', 'vlan batch 10 40',
    'interface Ethernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Ethernet0/0/0', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 40',
    'interface Vlanif10', 'ip address 10.1.1.3 24',
    'ospf 1 router-id 10.1.1.3', 'area 0', 'network 10.1.1.0 0.0.0.255',
    'return',
]

print("=== Configuring LSW1 ==="); cfg('LSW1', LSW1, verbose=False)
print("=== Configuring AR1 ===");  cfg('AR1', AR1, verbose=False)
print("=== Configuring AR2 ===");  cfg('AR2', AR2, verbose=False)
print("=== Configuring AR3 ===");  cfg('AR3', AR3, verbose=False)

# ---- verification ----
time.sleep(3)
print("\n===== VERIFY: AP IPs (should be 10.1.1.x) =====")
for ap in ['AP1','AP2','AP3']:
    for cmd,o in show(ap, ['display ip int brief | include Vlanif1']):
        print(f"[{ap}] {cmd}:\n{o}")

print("\n===== VERIFY: LSW1 DHCP used / OSPF neighbors =====")
for cmd,o in show('LSW1', ['display ip pool name vlan10 used','display ospf peer brief']):
    print(f"[LSW1] {cmd}:\n{o}")

print("\n===== VERIFY: AR1/AR2/AR3 OSPF peers =====")
for r in ['AR1','AR2','AR3']:
    for cmd,o in show(r, ['display ospf peer brief']):
        print(f"[{r}] {cmd}:\n{o}")
