# -*- coding: utf-8 -*-
"""
Campus network lab configuration via eNSP MCP service (app.py HTTP API).
Topology: E:/东北大学拓扑/东北大学拓扑.topo
Word reference: 校园网综合设计实训报告(2024).docx

MSTP: instance1(10/100/101), instance2(20/30/40), huawei rev16
VRRP: SW1 master 10/101 backup 20/30/40; SW2 reverse
DHCP: pools for vlan10/20/30/40/101, dns 192.168.0.1
LACP: SW1<->SW2 Eth-Trunk1 (GE0/0/10+11)
OSPF: SW1/SW2/FW1 with silent interfaces
Interconnect: VLAN520(192.168.50.0/24), VLAN521(192.168.51.0/24)
FW: admin/Admin@123, trust/untrust/dmz, server-only-accessed policy
WLAN: SSID=wlan-2024, PSK=zz1234567
Buildings: LSW5=dorm(10), LSW6=teaching(20), LSW7=library(30), LSW8=admin(40)
"""
import urllib.request, json, time, sys

BASE = 'http://127.0.0.1:5000'
DNS_SERVER = '192.168.0.1'

# Port -> device path mapping
PATHS = {
    'AR1': '127.0.0.1:2000', 'FW1': '127.0.0.1:2001',
    'LSW1': '127.0.0.1:2012', 'LSW2': '127.0.0.1:2013',
    'LSW3': '127.0.0.1:2014', 'LSW4': '127.0.0.1:2015',
    'LSW5': '127.0.0.1:2016', 'LSW6': '127.0.0.1:2017',
    'LSW7': '127.0.0.1:2018', 'LSW8': '127.0.0.1:2019',
    'LSW9': '127.0.0.1:2020', 'LSW10': '127.0.0.1:2021',
    'AC1': '127.0.0.1:2022',
}


def cmd(path, command, wait=0.1):
    """Send a command to a device via the service API."""
    time.sleep(wait)
    req = urllib.request.Request(
        f'{BASE}/api/devices/command',
        json.dumps({'path': path, 'command': command}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            return resp.get('output', '')
    except Exception as e:
        return f'ERROR: {e}'


def cmd_batch(path, commands, wait=0.1, label=''):
    """Send a batch of commands to a device."""
    for c in commands:
        out = cmd(path, c, wait=wait)
        if c.strip() and c not in ('quit', 'return', ''):
            print(f'  [{label}] {c}')


def banner(title):
    print(f'\n{"="*60}\n  {title}\n{"="*60}')


# ============================================================
#  Device configuration functions
# ============================================================

def config_sw_common(path, name):
    """Common switch config: VLANs, MSTP region, DHCP enable."""
    cmd_batch(path, [
        'system-view', 'undo info-center enable', f'sysname {name}',
        'stp mode mstp', 'stp enable', 'dhcp enable', 'drop illegal-mac alarm',
        'vlan batch 10 20 30 40 100 to 101 520 521',
        'stp region-configuration',
        ' region-name huawei', ' revision-level 16',
        ' instance 1 vlan 10 100 to 101',
        ' instance 2 vlan 20 30 40',
        ' active region-configuration',
    ], wait=0.1, label=name)


def config_sw1(path):
    banner('Configuring SW1')
    config_sw_common(path, 'SW1')
    cmd_batch(path, [
        'system-view',
        'stp instance 1 root primary',
        'stp instance 2 root secondary',
        # DHCP pools
        'ip pool vlan10', ' gateway-list 192.168.1.254',
        ' network 192.168.1.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan20', ' gateway-list 192.168.2.254',
        ' network 192.168.2.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan30', ' gateway-list 192.168.3.254',
        ' network 192.168.3.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan40', ' gateway-list 192.168.4.254',
        ' network 192.168.4.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan101', ' gateway-list 192.168.101.254',
        ' network 192.168.101.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        # VRRP (SW1: master 10/101, backup 20/30/40)
        'interface Vlanif10',
        ' ip address 192.168.1.100 255.255.255.0',
        ' vrrp vrid 10 virtual-ip 192.168.1.254',
        ' vrrp vrid 10 priority 120',
        ' dhcp select global', ' quit',
        'interface Vlanif20',
        ' ip address 192.168.2.100 255.255.255.0',
        ' vrrp vrid 20 virtual-ip 192.168.2.254',
        ' dhcp select global', ' quit',
        'interface Vlanif30',
        ' ip address 192.168.3.100 255.255.255.0',
        ' vrrp vrid 30 virtual-ip 192.168.3.254',
        ' dhcp select global', ' quit',
        'interface Vlanif40',
        ' ip address 192.168.4.100 255.255.255.0',
        ' vrrp vrid 40 virtual-ip 192.168.4.254',
        ' dhcp select global', ' quit',
        'interface Vlanif100',
        ' ip address 192.168.100.100 255.255.255.0',
        ' dhcp select interface', ' quit',
        'interface Vlanif101',
        ' ip address 192.168.101.100 255.255.255.0',
        ' vrrp vrid 101 virtual-ip 192.168.101.254',
        ' vrrp vrid 101 priority 120',
        ' dhcp select global', ' quit',
        # Interconnect VLAN520 to FW1
        'interface Vlanif520',
        ' ip address 192.168.50.1 255.255.255.0', ' quit',
        # Trunk uplinks
        'interface GigabitEthernet0/0/1',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface GigabitEthernet0/0/2',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface GigabitEthernet0/0/3',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        # LACP aggregate to SW2
        'interface GigabitEthernet0/0/10', ' eth-trunk 1', ' quit',
        'interface GigabitEthernet0/0/11', ' eth-trunk 1', ' quit',
        'interface Eth-Trunk 1',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094',
        ' mode lacp-static', ' quit',
        # AC trunk
        'interface GigabitEthernet0/0/19',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        # OSPF with silent interfaces
        'ospf 1 router-id 1.1.1.1',
        ' area 0.0.0.0',
        '  network 192.168.0.0 0.0.255.255',
        '  silent-interface Vlanif10',
        '  silent-interface Vlanif20',
        '  silent-interface Vlanif30',
        '  silent-interface Vlanif40',
        '  silent-interface Vlanif100',
        '  silent-interface Vlanif101', ' quit',
    ], wait=0.1, label='SW1')


def config_sw2(path):
    banner('Configuring SW2')
    config_sw_common(path, 'SW2')
    cmd_batch(path, [
        'system-view',
        'stp instance 1 root secondary',
        'stp instance 2 root primary',
        # DHCP pools
        'ip pool vlan10', ' gateway-list 192.168.1.254',
        ' network 192.168.1.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan20', ' gateway-list 192.168.2.254',
        ' network 192.168.2.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan30', ' gateway-list 192.168.3.254',
        ' network 192.168.3.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan40', ' gateway-list 192.168.4.254',
        ' network 192.168.4.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        'ip pool vlan101', ' gateway-list 192.168.101.254',
        ' network 192.168.101.0 mask 255.255.255.0',
        f' dns-list {DNS_SERVER}', ' quit',
        # VRRP (SW2: master 20/30/40, backup 10/101)
        'interface Vlanif10',
        ' ip address 192.168.1.200 255.255.255.0',
        ' vrrp vrid 10 virtual-ip 192.168.1.254',
        ' dhcp select global', ' quit',
        'interface Vlanif20',
        ' ip address 192.168.2.200 255.255.255.0',
        ' vrrp vrid 20 virtual-ip 192.168.2.254',
        ' vrrp vrid 20 priority 120',
        ' dhcp select global', ' quit',
        'interface Vlanif30',
        ' ip address 192.168.3.200 255.255.255.0',
        ' vrrp vrid 30 virtual-ip 192.168.3.254',
        ' vrrp vrid 30 priority 120',
        ' dhcp select global', ' quit',
        'interface Vlanif40',
        ' ip address 192.168.4.200 255.255.255.0',
        ' vrrp vrid 40 virtual-ip 192.168.4.254',
        ' vrrp vrid 40 priority 120',
        ' dhcp select global', ' quit',
        'interface Vlanif101',
        ' ip address 192.168.101.200 255.255.255.0',
        ' vrrp vrid 101 virtual-ip 192.168.101.254',
        ' dhcp select global', ' quit',
        # Interconnect VLAN521 to FW1
        'interface Vlanif521',
        ' ip address 192.168.51.1 255.255.255.0', ' quit',
        # Trunk uplinks
        'interface GigabitEthernet0/0/1',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface GigabitEthernet0/0/2',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface GigabitEthernet0/0/3',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        # LACP aggregate to SW1
        'interface GigabitEthernet0/0/10', ' eth-trunk 1', ' quit',
        'interface GigabitEthernet0/0/11', ' eth-trunk 1', ' quit',
        'interface Eth-Trunk 1',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094',
        ' mode lacp-static', ' quit',
        # OSPF
        'ospf 1 router-id 2.2.2.2',
        ' area 0.0.0.0',
        '  network 192.168.0.0 0.0.255.255',
        '  silent-interface Vlanif10',
        '  silent-interface Vlanif20',
        '  silent-interface Vlanif30',
        '  silent-interface Vlanif40',
        '  silent-interface Vlanif101', ' quit',
    ], wait=0.1, label='SW2')


def config_agg_switch(path, name, up1, up2, access_ports):
    """Aggregation switch: trunk to core, access for downstream."""
    banner(f'Configuring {name}')
    cmd_batch(path, [
        'system-view', 'undo info-center enable', f'sysname {name}',
        'vlan batch 10 20 30 40 100 to 101',
        f'interface {up1}',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        f'interface {up2}',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
    ], wait=0.1, label=name)
    for intf, vlan in access_ports:
        cmd_batch(path, [
            f'interface {intf}',
            ' port link-type access',
            f' port default vlan {vlan}', ' quit',
        ], wait=0.1, label=name)


def config_building_switch(path, name, pc_intfs, vlan):
    """Building access switch: access ports for PCs."""
    banner(f'Configuring {name} (VLAN {vlan})')
    cmd_batch(path, [
        'system-view', 'undo info-center enable', f'sysname {name}',
        f'vlan batch {vlan}',
    ], wait=0.1, label=name)
    for intf in pc_intfs:
        cmd_batch(path, [
            f'interface {intf}',
            ' port link-type access',
            f' port default vlan {vlan}', ' quit',
        ], wait=0.1, label=name)


def config_ac(path):
    banner('Configuring AC1')
    cmd_batch(path, [
        'system-view', 'undo info-center enable', 'sysname AC',
        'vlan batch 100 to 101', 'dhcp enable',
        'interface Vlanif100',
        ' ip address 192.168.100.1 255.255.255.0',
        ' dhcp select interface', ' quit',
        'interface GigabitEthernet0/0/19',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        # WLAN config
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
        '  radio 0', '   vap-profile vap wlan 1',
        '  radio 1', '   vap-profile vap wlan 1',
        ' ap-group name default',
        'quit',
    ], wait=0.1, label='AC1')


def config_fw(path):
    banner('Configuring FW1')
    cmd_batch(path, [
        'system-view', 'undo info-center enable', 'sysname FW',
        # Interfaces
        'interface GigabitEthernet0/0/0',
        ' undo shutdown', ' ip address 192.168.0.1 255.255.255.0', ' quit',
        'interface GigabitEthernet1/0/0',
        ' undo shutdown', ' ip address 192.168.0.254 255.255.255.0', ' quit',
        'interface GigabitEthernet1/0/1',
        ' undo shutdown', ' ip address 200.1.1.1 255.255.255.0', ' quit',
        'interface GigabitEthernet1/0/2',
        ' undo shutdown', ' ip address 192.168.50.2 255.255.255.0', ' quit',
        'interface GigabitEthernet1/0/3',
        ' undo shutdown', ' ip address 192.168.51.2 255.255.255.0', ' quit',
        # Zones
        'firewall zone trust',
        ' set priority 85',
        ' add interface GigabitEthernet0/0/0',
        ' add interface GigabitEthernet1/0/2',
        ' add interface GigabitEthernet1/0/3', ' quit',
        'firewall zone untrust',
        ' set priority 5',
        ' add interface GigabitEthernet1/0/1', ' quit',
        'firewall zone dmz',
        ' set priority 50',
        ' add interface GigabitEthernet1/0/0', ' quit',
        # Admin account
        'aaa',
        ' manager-user admin',
        ' password cipher Admin@123',
        ' level 15', ' quit', ' quit',
        # OSPF
        'ospf 1 router-id 3.3.3.3',
        ' default-route-advertise',
        ' area 0.0.0.0',
        '  network 192.168.0.0 0.0.255.255', ' quit',
        'ip route-static 0.0.0.0 0.0.0.0 200.1.1.2',
        # Security policy
        'security-policy',
        ' rule name trust_to_dmz_untrust',
        '  source-zone trust',
        '  destination-zone dmz',
        '  destination-zone untrust',
        '  action permit', ' quit',
        ' rule name untrust_to_dmz',
        '  source-zone untrust',
        '  destination-zone dmz',
        '  action permit', ' quit',
        ' rule name deny_dmz_out',
        '  source-zone dmz',
        '  action deny', ' quit',
    ], wait=0.1, label='FW1')


def config_r1(path):
    banner('Configuring AR1/R1')
    cmd_batch(path, [
        'system-view', 'undo info-center enable', 'sysname R1',
        'interface GigabitEthernet0/0/0',
        ' ip address 200.1.1.2 255.255.255.0', ' quit',
        'interface GigabitEthernet0/0/1',
        ' ip address 201.1.1.254 255.255.255.0', ' quit',
        'ip route-static 0.0.0.0 0.0.0.0 200.1.1.1',
    ], wait=0.1, label='R1')


def config_lsw9(path):
    banner('Configuring LSW9 (server access)')
    cmd_batch(path, [
        'system-view', 'undo info-center enable', 'sysname LSW9',
        'vlan batch 1000',
        'interface GigabitEthernet0/0/1',
        ' port link-type trunk', ' port trunk allow-pass vlan 2 to 4094', ' quit',
        'interface Ethernet0/0/1',
        ' port link-type access', ' port default vlan 1000', ' quit',
        'interface Ethernet0/0/2',
        ' port link-type access', ' port default vlan 1000', ' quit',
        'interface Ethernet0/0/3',
        ' port link-type access', ' port default vlan 1000', ' quit',
    ], wait=0.1, label='LSW9')


def config_lsw10(path):
    banner('Configuring LSW10 (external)')
    cmd_batch(path, [
        'system-view', 'undo info-center enable', 'sysname LSW10',
        'vlan batch 2011',
        'interface GigabitEthernet0/0/1',
        ' port link-type access', ' port default vlan 2011', ' quit',
        'interface Ethernet0/0/2',
        ' port link-type access', ' port default vlan 2011', ' quit',
        'interface Ethernet0/0/3',
        ' port link-type access', ' port default vlan 2011', ' quit',
    ], wait=0.1, label='LSW10')


# ============================================================
#  Main execution
# ============================================================
def main():
    banner('Campus Network Configuration via MCP Service')
    t0 = time.time()

    # Layer 2 + aggregation
    config_sw1(PATHS['LSW1'])
    config_sw2(PATHS['LSW2'])
    config_agg_switch(PATHS['LSW3'], 'LSW3', 'GigabitEthernet0/0/1', 'GigabitEthernet0/0/2',
                      [('GigabitEthernet0/0/4', 10), ('GigabitEthernet0/0/5', 20)])
    config_agg_switch(PATHS['LSW4'], 'LSW4', 'GigabitEthernet0/0/1', 'GigabitEthernet0/0/2',
                      [('GigabitEthernet0/0/4', 30), ('GigabitEthernet0/0/5', 40)])

    # Building access switches
    config_building_switch(PATHS['LSW5'], 'LSW5', ['Ethernet0/0/2', 'Ethernet0/0/3'], 10)
    config_building_switch(PATHS['LSW6'], 'LSW6', ['Ethernet0/0/2', 'Ethernet0/0/3'], 20)
    config_building_switch(PATHS['LSW7'], 'LSW7', ['Ethernet0/0/2', 'Ethernet0/0/3'], 30)
    config_building_switch(PATHS['LSW8'], 'LSW8', ['Ethernet0/0/2', 'Ethernet0/0/3'], 40)

    # Server/external switches
    config_lsw9(PATHS['LSW9'])
    config_lsw10(PATHS['LSW10'])

    # Wireless
    config_ac(PATHS['AC1'])

    # Firewall + Router
    config_fw(PATHS['FW1'])
    config_r1(PATHS['AR1'])

    elapsed = round(time.time() - t0, 1)
    banner(f'Configuration complete in {elapsed}s')
    print('  Next: run verify_campus_lab_api.py to validate')


if __name__ == '__main__':
    main()

