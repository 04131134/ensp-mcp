# -*- coding: utf-8 -*-
"""Rebuild underlay from factory default (eNSP WLAN AC experiment).
Clean, self-consistent version based on the verified stage1+fix_* scripts,
with the DHCP conflicts removed:
  - AP mgmt DHCP (VLAN10): LSW1 Vlanif10 (10.1.1.254), option43 -> 10.1.1.1 (AC1)
  - STA DHCP (VLAN40): AR3 Vlanif40 (192.168.40.1) ONLY (LSW1 no longer serves VLAN40)
  - AR access port to AP: trunk pvid vlan 10 allow-pass 10 20 30 40 (the old idle root cause)
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg, show, save_log

LSW1 = [
    'system-view', 'sysname LSW1', 'vlan batch 10 20 30 40',
    'interface GigabitEthernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface GigabitEthernet0/0/2', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface GigabitEthernet0/0/3', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface GigabitEthernet0/0/4', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface GigabitEthernet0/0/5', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Vlanif10', 'ip address 10.1.1.254 24',
    'dhcp enable',
    'ip pool vlan10', 'gateway-list 10.1.1.254', 'network 10.1.1.0 mask 24',
    'excluded-ip-address 10.1.1.1 10.1.1.3', 'excluded-ip-address 10.1.1.254',
    'option 43 sub-option 3 ascii 10.1.1.1',
    'interface Vlanif10', 'dhcp select global',
    'ospf 1 router-id 10.1.1.254', 'area 0', 'network 10.1.1.0 0.0.0.255',
    'return',
]

AR1 = [
    'system-view', 'sysname AR1', 'vlan batch 10 20 30 40',
    'interface Ethernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Ethernet0/0/0', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Vlanif10', 'ip address 10.1.1.11 24',
    'interface Vlanif20', 'ip address 192.168.10.1 24',
    'dhcp enable',
    'ip pool sta1', 'gateway-list 192.168.10.1', 'network 192.168.10.0 mask 24',
    'interface Vlanif20', 'dhcp select global',
    'ospf 1 router-id 10.1.1.11', 'area 0', 'network 10.1.1.0 0.0.0.255', 'network 192.168.10.0 0.0.0.255',
    'return',
]

AR2 = [
    'system-view', 'sysname AR2', 'vlan batch 10 20 30 40',
    'interface Ethernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Ethernet0/0/0', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Vlanif10', 'ip address 10.1.1.12 24',
    'interface Vlanif30', 'ip address 192.168.20.1 24',
    'dhcp enable',
    'ip pool sta2', 'gateway-list 192.168.20.1', 'network 192.168.20.0 mask 24',
    'interface Vlanif30', 'dhcp select global',
    'ospf 1 router-id 10.1.1.12', 'area 0', 'network 10.1.1.0 0.0.0.255', 'network 192.168.20.0 0.0.0.255',
    'return',
]

AR3 = [
    'system-view', 'sysname AR3', 'vlan batch 10 20 30 40',
    'interface Ethernet0/0/1', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Ethernet0/0/0', 'port link-type trunk', 'port trunk pvid vlan 10', 'port trunk allow-pass vlan 10 20 30 40',
    'interface Vlanif10', 'ip address 10.1.1.3 24',
    'interface Vlanif40', 'ip address 192.168.40.1 24',
    'dhcp enable',
    'ip pool sta3', 'gateway-list 192.168.40.1', 'network 192.168.40.0 mask 24',
    'interface Vlanif40', 'dhcp select global',
    'ospf 1 router-id 10.1.1.3', 'area 0', 'network 10.1.1.0 0.0.0.255', 'network 192.168.40.0 0.0.0.255',
    'return',
]

print("=== Configuring LSW1 ===", flush=True); cfg('LSW1', LSW1, verbose=True)
print("=== Configuring AR1 ===", flush=True);  cfg('AR1', AR1, verbose=True)
print("=== Configuring AR2 ===", flush=True);  cfg('AR2', AR2, verbose=True)
print("=== Configuring AR3 ===", flush=True);  cfg('AR3', AR3, verbose=True)
print("\n[DONE underlay config pushed]", flush=True)
