# -*- coding: utf-8 -*-
"""LSW1 重配（修 AP 拿不到管理 IP 的根因）。
根因：stage1/apply_base 只配了 GE0/0/1-5 接 AR/AC，AP 接的端口是出厂默认 VLAN1，
瘦 AP 不能手动配 IP/VLAN，只能从 DHCP 自动获取且必须在管理 VLAN10。
本脚本把所有下行口统一 trunk pvid vlan 10 allow 10 20 30 40（覆盖 AP 无论接哪个口），
Vlanif10=10.1.1.254、Vlanif40=192.168.40.254，DHCP 全局池(option43 指向 AC1)，OSPF 全互联。
纯 IPv4，无任何 IPv6。
注意：本脚本需在 LSW1 控制台恢复后（重启 LSW1 或整体重启拓扑后）执行。
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg, show, PORTS, save_log

LSW1 = [
    'system-view',
    'undo info-center enable',
    'vlan batch 10 20 30 40',
    'interface range GigabitEthernet0/0/1 to 0/0/24',
    'port link-type trunk',
    'port trunk pvid vlan 10',
    'port trunk allow-pass vlan 10 20 30 40',
    'quit',
    'interface Vlanif10',
    'ip address 10.1.1.254 24',
    'dhcp select global',
    'interface Vlanif40',
    'ip address 192.168.40.254 24',
    'dhcp select global',
    'dhcp enable',
    'ip pool vlan10',
    'gateway-list 10.1.1.254',
    'network 10.1.1.0 mask 24',
    'excluded-ip-address 10.1.1.1 10.1.1.3',
    'excluded-ip-address 10.1.1.254',
    'option 43 sub-option 3 ascii 10.1.1.1',
    'ip pool vlan40',
    'gateway-list 192.168.40.254',
    'network 192.168.40.0 mask 24',
    'excluded-ip-address 192.168.40.1 192.168.40.3',
    'excluded-ip-address 192.168.40.254',
    'ospf 1 router-id 10.1.1.254',
    'area 0',
    'network 10.1.1.0 0.0.0.255',
    'network 192.168.40.0 0.0.0.255',
    'return',
]
print("=== Configuring LSW1 (all downlinks -> VLAN10 mgmt) ===")
cfg('LSW1', LSW1, verbose=True)
time.sleep(3)
print("\n=== VERIFY LSW1 ===")
for cmd, o in show('LSW1', ['display ip interface brief',
                            'display ip pool name vlan10 used',
                            'display ospf peer brief'], delay=8):
    print(f"[LSW1] {cmd}:\n{o}")
