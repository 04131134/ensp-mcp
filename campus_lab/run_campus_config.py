# -*- coding: utf-8 -*-
"""
Campus network lab configuration script (topology-first).
Topology source: E:/东北大学拓扑/东北大学拓扑.topo
Word reference: 校园网综合设计实训报告(2024).docx
"""
import sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ensp_utils import connect, send_cmd, run_cmds, banner, show_pass, ping_ok, close_all

# ========== Port mapping from NEU topo (com_port) ==========
PORTS = {
    'AR1': 2000,
    'FW1': 2001,
    'LSW9': 2020,
    'AC1': 2022,
    'LSW1': 2012,
    'LSW2': 2013,
    'LSW3': 2014,
    'LSW4': 2015,
    'LSW5': 2016,
    'LSW6': 2017,
    'LSW7': 2018,
    'LSW8': 2019,
    'LSW10': 2021,
}

# ========== IP plan (aligned with Word) ==========
DNS_SERVER = '192.168.0.1'
WEB_SERVER = '192.168.0.2'
FTP_SERVER = '192.168.0.3'
SERVER_GW  = '192.168.0.254'

EXTERNAL_PC1 = '201.1.1.1'
EXTERNAL_PC2 = '201.1.1.2'
R1_LAN_IP    = '200.1.1.2'
FW_UNTRUST   = '200.1.1.1'
R1_WAN_GW    = '201.1.1.254'


def apply_sw_vlan_and_mstp_base(sw, name):
    """Create VLANs and MSTP region config (Word section 2.1 + 3.1)."""
    cmds = [
        'system-view',
        'undo info-center enable',
        f'sysname {name}',
        'stp mode mstp',
        'stp enable',
        'drop illegal-mac alarm',
        'dhcp enable',
        'vlan batch 10 20 30 40 100 to 101 520 521',
        'stp region-configuration',
        ' region-name huawei',
        ' revision-level 16',
        ' instance 1 vlan 10 100 to 101',
        ' instance 2 vlan 20 30 40',
        ' active region-configuration',
    ]
    run_cmds(sw, cmds, wait=0.8, name=name)


def apply_sw1(sw):
    """SW1: VRRP master for VLAN10/100~101, secondary for VLAN20/30/40 (Word section 3.1/3.2)."""
    banner('Configure SW1')
    apply_sw_vlan_and_mstp_base(sw, 'SW1')
    cmds = [
        'system-view',
        'stp instance 1 root primary',
        'stp instance 2 root secondary',
        # DHCP pools (Word section 3.1 IP pool block)
        'ip pool vlan10',
        ' gateway-list 192.168.1.254',
        ' network 192.168.1.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        'ip pool vlan20',
        ' gateway-list 192.168.2.254',
        ' network 192.168.2.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        'ip pool vlan30',
        ' gateway-list 192.168.3.254',
        ' network 192.168.3.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        'ip pool vlan40',
        ' gateway-list 192.168.4.254',
        ' network 192.168.4.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        'ip pool vlan101',
        ' gateway-list 192.168.101.254',
        ' network 192.168.101.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        # VLANIF interfaces (Word VRRP addresses on SW1)
        'interface Vlanif10',
        ' ip address 192.168.1.100 255.255.255.0',
        ' vrrp vrid 10 virtual-ip 192.168.1.254',
        ' vrrp vrid 10 priority 120',
        ' dhcp select global',
        ' quit',
        'interface Vlanif20',
        ' ip address 192.168.2.100 255.255.255.0',
        ' vrrp vrid 20 virtual-ip 192.168.2.254',
        ' dhcp select global',
        ' quit',
        'interface Vlanif30',
        ' ip address 192.168.3.100 255.255.255.0',
        ' vrrp vrid 30 virtual-ip 192.168.3.254',
        ' dhcp select global',
        ' quit',
        'interface Vlanif40',
        ' ip address 192.168.4.100 255.255.255.0',
        ' vrrp vrid 40 virtual-ip 192.168.4.254',
        ' dhcp select global',
        ' quit',
        'interface Vlanif100',
        ' ip address 192.168.100.100 255.255.255.0',
        ' dhcp select interface',
        ' quit',
        'interface Vlanif101',
        ' ip address 192.168.101.100 255.255.255.0',
        ' vrrp vrid 101 virtual-ip 192.168.101.254',
        ' vrrp vrid 101 priority 120',
        ' dhcp select global',
        ' quit',
        # VLAN520 towards FW1 (Word section 3.4)
        'interface Vlanif520',
        ' ip address 192.168.50.1 255.255.255.0',
        ' quit',
        # Core uplinks (topology-first: FW1/LSW3/LSW4/AC1/LSW2)
        'interface GigabitEthernet0/0/1',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
        'interface GigabitEthernet0/0/2',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
        'interface GigabitEthernet0/0/3',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
        'interface GigabitEthernet0/0/10',
        ' eth-trunk 1',
        ' quit',
        'interface GigabitEthernet0/0/11',
        ' eth-trunk 1',
        ' quit',
        'interface Eth-Trunk 1',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' mode lacp-static',
        ' quit',
        'interface GigabitEthernet0/0/19',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
        # OSPF (Word section 3.4 silent-interface)
        'ospf 1 router-id 1.1.1.1',
        ' area 0.0.0.0',
        '  network 192.168.0.0 0.0.255.255',
        '  silent-interface Vlanif10',
        '  silent-interface Vlanif20',
        '  silent-interface Vlanif30',
        '  silent-interface Vlanif40',
        '  silent-interface Vlanif100',
        '  silent-interface Vlanif101',
        ' quit',
    ]
    run_cmds(sw, cmds, wait=0.8, name='SW1')


def apply_sw2(sw):
    """SW2: VRRP backup priorities and OSPF (Word section 3.1/3.2)."""
    banner('Configure SW2')
    apply_sw_vlan_and_mstp_base(sw, 'SW2')
    cmds = [
        'system-view',
        'stp instance 1 root secondary',
        'stp instance 2 root primary',
        'ip pool vlan10',
        ' gateway-list 192.168.1.254',
        ' network 192.168.1.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        'ip pool vlan20',
        ' gateway-list 192.168.2.254',
        ' network 192.168.2.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        'ip pool vlan30',
        ' gateway-list 192.168.3.254',
        ' network 192.168.3.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        'ip pool vlan40',
        ' gateway-list 192.168.4.254',
        ' network 192.168.4.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        'ip pool vlan101',
        ' gateway-list 192.168.101.254',
        ' network 192.168.101.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}',
        ' quit',
        'interface Vlanif10',
        ' ip address 192.168.1.200 255.255.255.0',
        ' vrrp vrid 10 virtual-ip 192.168.1.254',
        ' dhcp select global',
        ' quit',
        'interface Vlanif20',
        ' ip address 192.168.2.200 255.255.255.0',
        ' vrrp vrid 20 virtual-ip 192.168.2.254',
        ' vrrp vrid 20 priority 120',
        ' dhcp select global',
        ' quit',
        'interface Vlanif30',
        ' ip address 192.168.3.200 255.255.255.0',
        ' vrrp vrid 30 virtual-ip 192.168.3.254',
        ' vrrp vrid 30 priority 120',
        ' dhcp select global',
        ' quit',
        'interface Vlanif40',
        ' ip address 192.168.4.200 255.255.255.0',
        ' vrrp vrid 40 virtual-ip 192.168.4.254',
        ' vrrp vrid 40 priority 120',
        ' dhcp select global',
        ' quit',
        'interface Vlanif101',
        ' ip address 192.168.101.200 255.255.255.0',
        ' vrrp vrid 101 virtual-ip 192.168.101.254',
        ' dhcp select global',
        ' quit',
        'interface Vlanif521',
        ' ip address 192.168.51.1 255.255.255.0',
        ' quit',
        'interface GigabitEthernet0/0/1',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
        'interface GigabitEthernet0/0/2',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
        'interface GigabitEthernet0/0/3',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
        'interface GigabitEthernet0/0/10',
        ' eth-trunk 1',
        ' quit',
        'interface GigabitEthernet0/0/11',
        ' eth-trunk 1',
        ' quit',
        'interface Eth-Trunk 1',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' mode lacp-static',
        ' quit',
        'ospf 1 router-id 2.2.2.2',
        ' area 0.0.0.0',
        '  network 192.168.0.0 0.0.255.255',
        '  silent-interface Vlanif10',
        '  silent-interface Vlanif20',
        '  silent-interface Vlanif30',
        '  silent-interface Vlanif40',
        '  silent-interface Vlanif101',
        ' quit',
    ]
    run_cmds(sw, cmds, wait=0.8, name='SW2')


def apply_aggregation_sw(sw, name, link_to_sw1_intf, link_to_sw2_intf, access_ports):
    """Aggregation switches: VLAN trunk to core and access ports for downstream (Word section 2.1)."""
    banner(f'Configure {name}')
    cmds = [
        'system-view',
        'undo info-center enable',
        f'sysname {name}',
        'vlan batch 10 20 30 40 100 to 101',
        f'interface {link_to_sw1_intf}',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
        f'interface {link_to_sw2_intf}',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
    ]
    for port, vlan in access_ports:
        cmds += [
            f'interface {port}',
            ' port link-type access',
            f' port default vlan {vlan}',
            ' quit',
        ]
    run_cmds(sw, cmds, wait=0.8, name=name)


def apply_fw(fw):
    """Firewall: zones + OSPF advertise + security policy (Word section 3.4)."""
    banner('Configure FW1')
    cmds = [
        'system-view',
        'undo info-center enable',
        'sysname FW',
        # interfaces
        'interface GigabitEthernet0/0/0',
        ' undo shutdown',
        ' ip address 192.168.0.1 255.255.255.0',
        ' quit',
        'interface GigabitEthernet1/0/0',
        ' undo shutdown',
        ' ip address 192.168.0.254 255.255.255.0',
        ' quit',
        'interface GigabitEthernet1/0/1',
        ' undo shutdown',
        ' ip address 200.1.1.1 255.255.255.0',
        ' quit',
        'interface GigabitEthernet1/0/2',
        ' undo shutdown',
        ' ip address 192.168.50.2 255.255.255.0',
        ' quit',
        'interface GigabitEthernet1/0/3',
        ' undo shutdown',
        ' ip address 192.168.51.2 255.255.255.0',
        ' quit',
        # zones
        'firewall zone trust',
        ' set priority 85',
        ' add interface GigabitEthernet0/0/0',
        ' add interface GigabitEthernet1/0/2',
        ' add interface GigabitEthernet1/0/3',
        ' quit',
        'firewall zone untrust',
        ' set priority 5',
        ' add interface GigabitEthernet1/0/1',
        ' quit',
        'firewall zone dmz',
        ' set priority 50',
        ' add interface GigabitEthernet1/0/0',
        ' quit',
        # OSPF advertise internal supernets (Word section 3.4)
        'ospf 1 router-id 3.3.3.3',
        ' default-route-advertise',
        ' area 0.0.0.0',
        '  network 192.168.0.0 0.0.255.255',
        ' quit',
        'ip route-static 0.0.0.0 0.0.0.0 200.1.1.2',
        # Security policy (Word section 3.4 rule 1/2)
        'security-policy',
        ' rule name trust_to_dmz_untrust',
        '  source-zone trust',
        '  destination-zone dmz',
        '  destination-zone untrust',
        '  action permit',
        ' quit',
        ' rule name untrust_to_dmz',
        '  source-zone untrust',
        '  destination-zone dmz',
        '  action permit',
        ' quit',
    ]
    run_cmds(fw, cmds, wait=0.8, name='FW1')


def apply_r1(r):
    """External router with WAN/LAN interfaces and static default route (Word section 3.3)."""
    banner('Configure AR1/R1')
    cmds = [
        'system-view',
        'undo info-center enable',
        'sysname R1',
        'interface GigabitEthernet0/0/0',
        ' ip address 200.1.1.2 255.255.255.0',
        ' quit',
        'interface GigabitEthernet0/0/1',
        ' ip address 201.1.1.254 255.255.255.0',
        ' quit',
        'ip route-static 0.0.0.0 0.0.0.0 200.1.1.1',
    ]
    run_cmds(r, cmds, wait=0.8, name='R1')


def apply_lsw9(sw):
    """Server access switch with trunk to FW and access ports for servers (topology kept)."""
    banner('Configure LSW9')
    cmds = [
        'system-view',
        'undo info-center enable',
        'sysname LSW9',
        'vlan batch 1000',
        'interface GigabitEthernet0/0/1',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
        'interface Ethernet0/0/1',
        ' port link-type access',
        ' port default vlan 1000',
        ' quit',
        'interface Ethernet0/0/2',
        ' port link-type access',
        ' port default vlan 1000',
        ' quit',
        'interface Ethernet0/0/3',
        ' port link-type access',
        ' port default vlan 1000',
        ' quit',
    ]
    run_cmds(sw, cmds, wait=0.8, name='LSW9')


def apply_lsw10(sw):
    """External access switch for PC1/PC2 (Word section 3.3)."""
    banner('Configure LSW10')
    cmds = [
        'system-view',
        'undo info-center enable',
        'sysname LSW10',
        'interface GigabitEthernet0/0/1',
        ' port link-type access',
        ' port default vlan 2011',
        ' quit',
        'interface Ethernet0/0/2',
        ' port link-type access',
        ' port default vlan 2011',
        ' quit',
        'interface Ethernet0/0/3',
        ' port link-type access',
        ' port default vlan 2011',
        ' quit',
    ]
    run_cmds(sw, cmds, wait=0.8, name='LSW10')


def apply_ac(ac):
    """AC base config: VLANs for management/user WiFi (Word section 3.2)."""
    banner('Configure AC1')
    cmds = [
        'system-view',
        'undo info-center enable',
        'sysname AC',
        'vlan batch 100 to 101',
        'dhcp enable',
        'interface Vlanif100',
        ' ip address 192.168.100.1 255.255.255.0',
        ' dhcp select interface',
        ' quit',
        'interface GigabitEthernet0/0/19',
        ' port link-type trunk',
        ' port trunk allow-pass vlan 2 to 4094',
        ' quit',
    ]
    run_cmds(ac, cmds, wait=0.8, name='AC1')


def main():
    banner('Campus lab config start')
    ports = PORTS
    conns = {name: connect(port) for name, port in ports.items()}

    apply_lsw9(conns['LSW9'])
    apply_lsw10(conns['LSW10'])
    apply_sw1(conns['LSW1'])
    apply_sw2(conns['LSW2'])

    apply_aggregation_sw(
        conns['LSW3'], 'LSW3',
        link_to_sw1_intf='GigabitEthernet0/0/1',
        link_to_sw2_intf='GigabitEthernet0/0/2',
        access_ports=[
            ('GigabitEthernet0/0/4', 10),
            ('GigabitEthernet0/0/5', 20),
        ],
    )
    apply_aggregation_sw(
        conns['LSW4'], 'LSW4',
        link_to_sw1_intf='GigabitEthernet0/0/1',
        link_to_sw2_intf='GigabitEthernet0/0/2',
        access_ports=[
            ('GigabitEthernet0/0/4', 30),
            ('GigabitEthernet0/0/5', 40),
        ],
    )

    for sw_name, port_intf, vlan in [
        ('LSW5', 'Ethernet0/0/2', 10),
        ('LSW5', 'Ethernet0/0/3', 10),
        ('LSW6', 'Ethernet0/0/2', 20),
        ('LSW6', 'Ethernet0/0/3', 20),
        ('LSW7', 'Ethernet0/0/2', 30),
        ('LSW7', 'Ethernet0/0/3', 30),
        ('LSW8', 'Ethernet0/0/2', 40),
        ('LSW8', 'Ethernet0/0/3', 40),
    ]:
        cmds = [
            'system-view',
            'undo info-center enable',
            f'sysname {sw_name}',
            f'vlan batch {vlan}',
            f'interface {port_intf}',
            ' port link-type access',
            f' port default vlan {vlan}',
            ' quit',
        ]
        run_cmds(conns[sw_name], cmds, wait=0.8, name=sw_name)

    apply_ac(conns['AC1'])
    apply_fw(conns['FW1'])
    apply_r1(conns['AR1'])

    banner('Campus lab config finished')
    close_all(conns.values())


if __name__ == '__main__':
    main()
