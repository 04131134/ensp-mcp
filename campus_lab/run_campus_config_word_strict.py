# -*- coding: utf-8 -*-
"""
Campus lab configuration (Word-strict, final).
Implements: MSTP instances, VRRP master/backup, VLAN520/521 interconnects,
WLAN with SSID=wlan-2024 + PSK, and security policy: servers only accessed.
Building VLANs: dorm=10, teaching=20, library=30, admin=40.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ensp_utils import connect, send_cmd, run_cmds, banner, close_all

PORTS = {
    'AR1': 2000, 'FW1': 2001, 'LSW9': 2020, 'AC1': 2022,
    'LSW1': 2012, 'LSW2': 2013, 'LSW3': 2014, 'LSW4': 2015,
    'LSW5': 2016, 'LSW6': 2017, 'LSW7': 2018, 'LSW8': 2019, 'LSW10': 2021,
}

DNS_SERVER = '192.168.0.1'


def apply_sw_common(sw, name):
    run_cmds(sw, [
        'system-view', 'undo info-center enable', f'sysname {name}',
        'stp mode mstp', 'stp enable', 'dhcp enable', 'drop illegal-mac alarm',
        'vlan batch 10 20 30 40 100 to 101 520 521',
        'stp region-configuration',
        ' region-name huawei', ' revision-level 16',
        ' instance 1 vlan 10 100 to 101',
        ' instance 2 vlan 20 30 40',
        ' active region-configuration',
    ], wait=0.7, name=name)


def apply_sw1(sw):
    banner('SW1 (final)')
    apply_sw_common(sw, 'SW1')
    run_cmds(sw, [
        'system-view',
        'stp instance 1 root primary',
        'stp instance 2 root secondary',
        # DHCP pools
        'ip pool vlan10', ' gateway-list 192.168.1.254', ' network 192.168.1.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan20', ' gateway-list 192.168.2.254', ' network 192.168.2.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan30', ' gateway-list 192.168.3.254', ' network 192.168.3.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan40', ' gateway-list 192.168.4.254', ' network 192.168.4.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan101', ' gateway-list 192.168.101.254', ' network 192.168.101.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        # VRRP
        'interface Vlanif10', ' ip address 192.168.1.100 255.255.255.0', ' vrrp vrid 10 virtual-ip 192.168.1.254', ' vrrp vrid 10 priority 120', ' dhcp select global', ' quit',
        'interface Vlanif20', ' ip address 192.168.2.100 255.255.255.0', ' vrrp vrid 20 virtual-ip 192.168.2.254', ' dhcp select global', ' quit',
        'interface Vlanif30', ' ip address 192.168.3.100 255.255.255.0', ' vrrp vrid 30 virtual-ip 192.168.3.254', ' dhcp select global', ' quit',
        'interface Vlanif40', ' ip address 192.168.4.100 255.255.255.0', ' vrrp vrid 40 virtual-ip 192.168.4.254', ' dhcp select global', ' quit',
        'interface Vlanif100', ' ip address 192.168.100.100 255.255.255.0', ' dhcp select interface', ' quit',
        'interface Vlanif101', ' ip address 192.168.101.100 255.255.255.0', ' vrrp vrid 101 virtual-ip 192.168.101.254', ' vrrp vrid 101 priority 120', ' dhcp select global', ' quit',
        # Interconnect VLAN 520
        'interface Vlanif520', ' ip address 192.168.50.1 255.255.255.0', ' quit',
        # Uplinks
        'interface GigabitEthernet0/0/1', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface GigabitEthernet0/0/2', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface GigabitEthernet0/0/3', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        # LACP
        'interface GigabitEthernet0/0/10', ' eth-trunk 1', ' quit',
        'interface GigabitEthernet0/0/11', ' eth-trunk 1', ' quit',
        'interface Eth-Trunk 1', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' mode lacp-static', ' quit',
        # AC trunk
        'interface GigabitEthernet0/0/19', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        # OSPF
        'ospf 1 router-id 1.1.1.1', ' area 0.0.0.0', '  network 192.168.0.0 0.0.255.255',
        '  silent-interface Vlanif10', '  silent-interface Vlanif20', '  silent-interface Vlanif30', '  silent-interface Vlanif40', '  silent-interface Vlanif100', '  silent-interface Vlanif101', ' quit',
    ], wait=0.7, name='SW1')


def apply_sw2(sw):
    banner('SW2 (final)')
    apply_sw_common(sw, 'SW2')
    run_cmds(sw, [
        'system-view',
        'stp instance 1 root secondary', 'stp instance 2 root primary',
        # DHCP pools
        'ip pool vlan10', ' gateway-list 192.168.1.254', ' network 192.168.1.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan20', ' gateway-list 192.168.2.254', ' network 192.168.2.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan30', ' gateway-list 192.168.3.254', ' network 192.168.3.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan40', ' gateway-list 192.168.4.254', ' network 192.168.4.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan101', ' gateway-list 192.168.101.254', ' network 192.168.101.0 mask 255.255.255.0', f' dns-list {DNS_SERVER}', ' quit',
        # VRRP
        'interface Vlanif10', ' ip address 192.168.1.200 255.255.255.0', ' vrrp vrid 10 virtual-ip 192.168.1.254', ' dhcp select global', ' quit',
        'interface Vlanif20', ' ip address 192.168.2.200 255.255.255.0', ' vrrp vrid 20 virtual-ip 192.168.2.254', ' vrrp vrid 20 priority 120', ' dhcp select global', ' quit',
        'interface Vlanif30', ' ip address 192.168.3.200 255.255.255.0', ' vrrp vrid 30 virtual-ip 192.168.3.254', ' vrrp vrid 30 priority 120', ' dhcp select global', ' quit',
        'interface Vlanif40', ' ip address 192.168.4.200 255.255.255.0', ' vrrp vrid 40 virtual-ip 192.168.4.254', ' vrrp vrid 40 priority 120', ' dhcp select global', ' quit',
        'interface Vlanif101', ' ip address 192.168.101.200 255.255.255.0', ' vrrp vrid 101 virtual-ip 192.168.101.254', ' dhcp select global', ' quit',
        # Interconnect VLAN 521
        'interface Vlanif521', ' ip address 192.168.51.1 255.255.255.0', ' quit',
        # Uplinks
        'interface GigabitEthernet0/0/1', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface GigabitEthernet0/0/2', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface GigabitEthernet0/0/3', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        # LACP
        'interface GigabitEthernet0/0/10', ' eth-trunk 1', ' quit',
        'interface GigabitEthernet0/0/11', ' eth-trunk 1', ' quit',
        'interface Eth-Trunk 1', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' mode lacp-static', ' quit',
        # OSPF
        'ospf 1 router-id 2.2.2.2', ' area 0.0.0.0', '  network 192.168.0.0 0.0.255.255',
        '  silent-interface Vlanif10', '  silent-interface Vlanif20', '  silent-interface Vlanif30', '  silent-interface Vlanif40', '  silent-interface Vlanif101', ' quit',
    ], wait=0.7, name='SW2')


def apply_agg(sw, name, up1, up2, access_list):
    banner(f'{name} (final)')
    cmds = ['system-view', 'undo info-center enable', f'sysname {name}', 'vlan batch 10 20 30 40 100 to 101',
            f'interface {up1}', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
            f'interface {up2}', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit']
    for intf, vlan in access_list:
        cmds += [f'interface {intf}', ' port link-type access', f' port default vlan {vlan}', ' quit']
    run_cmds(sw, cmds, wait=0.7, name=name)


def apply_building_switch(sw, name, pc_intfs, vlan, gw_last_octet):
    banner(f'{name} (final building VLAN {vlan})')
    cmds = [
        'system-view', 'undo info-center enable', f'sysname {name}',
        f'vlan batch {vlan}',
    ]
    for intf in pc_intfs:
        cmds += [f'interface {intf}', ' port link-type access', f' port default vlan {vlan}', ' quit']
    run_cmds(sw, cmds, wait=0.7, name=name)


def apply_ac(ac):
    banner('AC (WLAN final)')
    run_cmds(ac, [
        'system-view', 'undo info-center enable', 'sysname AC',
        'vlan batch 100 to 101', 'dhcp enable',
        'interface Vlanif100', ' ip address 192.168.100.1 255.255.255.0', ' dhcp select interface', ' quit',
        'interface GigabitEthernet0/0/19', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        # WLAN profiles (Word snippet + SSID=wlan-2024, PSK=zz1234567)
        'wlan',
        ' traffic-profile name default',
        ' security-profile name sec',
        '  security wpa-wpa2 psk pass-phrase zz1234567 aes',
        ' security-profile name default',
        ' ssid-profile name ssid',
        '  ssid wlan-2024',
        ' vap-profile name vap',
        '  service-vlan vlan-id 101',
        '  ssid-profile ssid',
        '  security-profile sec',
        ' ap-group name ap',
        '  radio 0', '   vap-profile vap wlan 1', '  radio 1', '   vap-profile vap wlan 1',
        ' ap-group name default',
        'quit',
    ], wait=0.7, name='AC1')


def apply_lsw9(sw):
    banner('LSW9 (server access)')
    run_cmds(sw, [
        'system-view', 'undo info-center enable', 'sysname LSW9', 'vlan batch 1000',
        'interface GigabitEthernet0/0/1', ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface Ethernet0/0/1', ' port link-type access', ' port default vlan 1000', ' quit',
        'interface Ethernet0/0/2', ' port link-type access', ' port default vlan 1000', ' quit',
        'interface Ethernet0/0/3', ' port link-type access', ' port default vlan 1000', ' quit',
    ], wait=0.7, name='LSW9')


def apply_lsw10(sw):
    banner('LSW10 (external)')
    run_cmds(sw, [
        'system-view', 'undo info-center enable', 'sysname LSW10', 'vlan batch 2011',
        'interface GigabitEthernet0/0/1', ' port link-type access', ' port default vlan 2011', ' quit',
        'interface Ethernet0/0/2', ' port link-type access', ' port default vlan 2011', ' quit',
        'interface Ethernet0/0/3', ' port link-type access', ' port default vlan 2011', ' quit',
    ], wait=0.7, name='LSW10')


def apply_fw(fw):
    banner('FW1 (final)')
    run_cmds(fw, [
        'system-view', 'undo info-center enable', 'sysname FW',
        'interface GigabitEthernet0/0/0', ' undo shutdown', ' ip address 192.168.0.1 255.255.255.0', ' quit',
        'interface GigabitEthernet1/0/0', ' undo shutdown', ' ip address 192.168.0.254 255.255.255.0', ' quit',
        'interface GigabitEthernet1/0/1', ' undo shutdown', ' ip address 200.1.1.1 255.255.255.0', ' quit',
        'interface GigabitEthernet1/0/2', ' undo shutdown', ' ip address 192.168.50.2 255.255.255.0', ' quit',
        'interface GigabitEthernet1/0/3', ' undo shutdown', ' ip address 192.168.51.2 255.255.255.0', ' quit',
        'firewall zone trust', ' set priority 85', ' add interface GigabitEthernet0/0/0', ' add interface GigabitEthernet1/0/2', ' add interface GigabitEthernet1/0/3', ' quit',
        'firewall zone untrust', ' set priority 5', ' add interface GigabitEthernet1/0/1', ' quit',
        'firewall zone dmz', ' set priority 50', ' add interface GigabitEthernet1/0/0', ' quit',
        # admin account
        'aaa', ' manager-user admin', ' password cipher Admin@123', ' level 15', ' quit', ' quit',
        # OSPF
        'ospf 1 router-id 3.3.3.3', ' default-route-advertise', ' area 0.0.0.0', '  network 192.168.0.0 0.0.255.255', ' quit',
        'ip route-static 0.0.0.0 0.0.0.0 200.1.1.2',
        # Security policy
        'security-policy',
        ' rule name trust_to_dmz_untrust', '  source-zone trust', '  destination-zone dmz', '  destination-zone untrust', '  action permit', ' quit',
        ' rule name untrust_to_dmz', '  source-zone untrust', '  destination-zone dmz', '  action permit', ' quit',
        ' rule name deny_dmz_out', '  source-zone dmz', '  action deny', ' quit',
    ], wait=0.7, name='FW1')


def apply_r1(r):
    banner('AR1/R1 (final)')
    run_cmds(r, [
        'system-view', 'undo info-center enable', 'sysname R1',
        'interface GigabitEthernet0/0/0', ' ip address 200.1.1.2 255.255.255.0', ' quit',
        'interface GigabitEthernet0/0/1', ' ip address 201.1.1.254 255.255.255.0', ' quit',
        'ip route-static 0.0.0.0 0.0.0.0 200.1.1.1',
    ], wait=0.7, name='R1')


def main():
    conns = {k: connect(v) for k, v in PORTS.items()}

    # Core/aggregation
    apply_lsw9(conns['LSW9'])
    apply_lsw10(conns['LSW10'])
    apply_sw1(conns['LSW1'])
    apply_sw2(conns['LSW2'])
    apply_agg(conns['LSW3'], 'LSW3', 'GigabitEthernet0/0/1', 'GigabitEthernet0/0/2',
              [('GigabitEthernet0/0/4', 10), ('GigabitEthernet0/0/5', 20)])
    apply_agg(conns['LSW4'], 'LSW4', 'GigabitEthernet0/0/1', 'GigabitEthernet0/0/2',
              [('GigabitEthernet0/0/4', 30), ('GigabitEthernet0/0/5', 40)])

    # Building switches (correct VLAN assignment)
    apply_building_switch(conns['LSW5'], 'LSW5', ['Ethernet0/0/2','Ethernet0/0/3'], 10, 252)
    apply_building_switch(conns['LSW6'], 'LSW6', ['Ethernet0/0/2','Ethernet0/0/3'], 20, 253)
    apply_building_switch(conns['LSW7'], 'LSW7', ['Ethernet0/0/2','Ethernet0/0/3'], 30, 250)
    apply_building_switch(conns['LSW8'], 'LSW8', ['Ethernet0/0/2','Ethernet0/0/3'], 40, 251)

    # Wireless + firewall + router
    apply_ac(conns['AC1'])
    apply_fw(conns['FW1'])
    apply_r1(conns['AR1'])

    close_all(conns.values())


if __name__ == '__main__':
    main()
