# -*- coding: utf-8 -*-
"""
校园网综合设计实训 - eNSP MCP API 批量配置脚本
"""
import urllib.request, json, time, sys

API = "http://127.0.0.1:5000"

DEVICES = {
    "LSW1":  2004, "LSW2":  2003, "LSW3":  2006, "LSW4":  2008,
    "LSW5":  2000, "LSW6":  2002, "LSW7":  2011, "LSW8":  2012,
    "LSW9":  2013, "LSW10": 2014, "FW1":   2001, "AR1":   2009, "AC1":  2005,
}

def batch_cmd(device, commands, auto_view=True, auto_undo_tm=True):
    """Send batch commands to device"""
    port = DEVICES[device]
    url = f"{API}/api/devices/batch-command"
    data = json.dumps({
        "path": f"127.0.0.1:{port}",
        "commands": commands,
        "auto_view": auto_view,
        "auto_undo_tm": auto_undo_tm,
        "wait": 0.05
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            result = json.loads(r.read())
            success = result.get("success", False)
            executed = result.get("executed", 0)
            failed = result.get("failed", 0)
            print(f"  {device}: {executed}/{len(commands)} commands OK" + (f" ({failed} failed)" if failed else ""))
            return result
    except Exception as e:
        print(f"  {device}: ERROR - {e}")
        return None

def configure_all():
    print("=" * 60)
    print("校园网综合设计实训 - 批量配置")
    print("=" * 60)

    # 1. SW1 (LSW1) - 核心交换机1
    print("\n[1] 配置 LSW1 (核心交换机1)...")
    batch_cmd("LSW1", [
        "vlan batch 10 20 30 40 100 to 101 520 521",
        # MSTP
        "stp mode mstp", "stp enable",
        "stp region-configuration",
        "region-name huawei", "revision-level 16",
        "instance 1 vlan 10 100 101", "instance 2 vlan 20 30 40",
        "active region-configuration", "quit",
        "stp instance 1 root primary", "stp instance 2 root secondary",
        # DHCP
        "dhcp enable",
        "ip pool vlan10", "gateway-list 192.168.1.254", "network 192.168.1.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        "ip pool vlan20", "gateway-list 192.168.2.254", "network 192.168.2.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        "ip pool vlan30", "gateway-list 192.168.3.254", "network 192.168.3.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        "ip pool vlan40", "gateway-list 192.168.4.254", "network 192.168.4.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        "ip pool vlan101", "gateway-list 192.168.101.254", "network 192.168.101.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        # VRRP - 主 10/101, 备 20/30/40
        "interface Vlanif10", "ip address 192.168.1.100 255.255.255.0",
        "vrrp vrid 10 virtual-ip 192.168.1.254", "vrrp vrid 10 priority 120", "dhcp select global", "quit",
        "interface Vlanif20", "ip address 192.168.2.100 255.255.255.0",
        "vrrp vrid 20 virtual-ip 192.168.2.254", "dhcp select global", "quit",
        "interface Vlanif30", "ip address 192.168.3.100 255.255.255.0",
        "vrrp vrid 30 virtual-ip 192.168.3.254", "dhcp select global", "quit",
        "interface Vlanif40", "ip address 192.168.4.100 255.255.255.0",
        "vrrp vrid 40 virtual-ip 192.168.4.254", "dhcp select global", "quit",
        "interface Vlanif101", "ip address 192.168.101.100 255.255.255.0",
        "vrrp vrid 101 virtual-ip 192.168.101.254", "vrrp vrid 101 priority 120", "dhcp select global", "quit",
        # 服务器区 VLANIF
        "interface Vlanif100", "ip address 192.168.0.254 255.255.255.0", "quit",
        # 互联 VLANIF
        "interface Vlanif520", "ip address 192.168.50.1 255.255.255.0", "quit",
        "interface Vlanif521", "ip address 192.168.51.1 255.255.255.0", "quit",
        # LACP
        "interface Eth-Trunk1", "mode lacp-static",
        "port link-type trunk", "port trunk allow-pass vlan 2 to 4094", "quit",
        "interface GigabitEthernet0/0/10", "eth-trunk 1", "quit",
        "interface GigabitEthernet0/0/11", "eth-trunk 1", "quit",
        # 端口: GE0/0/1->FW1
        "interface GigabitEthernet0/0/1", "port link-type trunk",
        "port trunk allow-pass vlan 2 to 4094", "quit",
        # 端口: GE0/0/2->LSW9
        "interface GigabitEthernet0/0/2", "port link-type trunk",
        "port trunk allow-pass vlan 100", "quit",
        # 端口: GE0/0/3->LSW10
        "interface GigabitEthernet0/0/3", "port link-type trunk",
        "port trunk allow-pass vlan 100", "quit",
        # OSPF
        "ospf 1 router-id 1.1.1.1",
        "area 0.0.0.0", "network 192.168.0.0 0.0.255.255", "quit",
        "silent-interface Vlanif10", "silent-interface Vlanif20",
        "silent-interface Vlanif30", "silent-interface Vlanif40",
        "silent-interface Vlanif101", "quit",
    ])

    # 2. SW2 (LSW2) - 核心交换机2
    print("[2] 配置 LSW2 (核心交换机2)...")
    batch_cmd("LSW2", [
        "vlan batch 10 20 30 40 100 to 101 520 521",
        # MSTP
        "stp mode mstp", "stp enable",
        "stp region-configuration",
        "region-name huawei", "revision-level 16",
        "instance 1 vlan 10 100 101", "instance 2 vlan 20 30 40",
        "active region-configuration", "quit",
        "stp instance 1 root secondary", "stp instance 2 root primary",
        # DHCP
        "dhcp enable",
        "ip pool vlan10", "gateway-list 192.168.1.254", "network 192.168.1.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        "ip pool vlan20", "gateway-list 192.168.2.254", "network 192.168.2.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        "ip pool vlan30", "gateway-list 192.168.3.254", "network 192.168.3.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        "ip pool vlan40", "gateway-list 192.168.4.254", "network 192.168.4.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        "ip pool vlan101", "gateway-list 192.168.101.254", "network 192.168.101.0 mask 255.255.255.0", "dns-list 192.168.0.1", "quit",
        # VRRP - 主 20/30/40, 备 10/101
        "interface Vlanif10", "ip address 192.168.1.200 255.255.255.0",
        "vrrp vrid 10 virtual-ip 192.168.1.254", "dhcp select global", "quit",
        "interface Vlanif20", "ip address 192.168.2.200 255.255.255.0",
        "vrrp vrid 20 virtual-ip 192.168.2.254", "vrrp vrid 20 priority 120", "dhcp select global", "quit",
        "interface Vlanif30", "ip address 192.168.3.200 255.255.255.0",
        "vrrp vrid 30 virtual-ip 192.168.3.254", "vrrp vrid 30 priority 120", "dhcp select global", "quit",
        "interface Vlanif40", "ip address 192.168.4.200 255.255.255.0",
        "vrrp vrid 40 virtual-ip 192.168.4.254", "vrrp vrid 40 priority 120", "dhcp select global", "quit",
        "interface Vlanif101", "ip address 192.168.101.200 255.255.255.0",
        "vrrp vrid 101 virtual-ip 192.168.101.254", "dhcp select global", "quit",
        # 服务器区 VLANIF
        "interface Vlanif100", "ip address 192.168.0.253 255.255.255.0", "quit",
        # 互联 VLANIF
        "interface Vlanif520", "ip address 192.168.50.2 255.255.255.0", "quit",
        "interface Vlanif521", "ip address 192.168.51.2 255.255.255.0", "quit",
        # LACP
        "interface Eth-Trunk1", "mode lacp-static",
        "port link-type trunk", "port trunk allow-pass vlan 2 to 4094", "quit",
        "interface GigabitEthernet0/0/10", "eth-trunk 1", "quit",
        "interface GigabitEthernet0/0/11", "eth-trunk 1", "quit",
        # 端口: GE0/0/1->FW1
        "interface GigabitEthernet0/0/1", "port link-type trunk",
        "port trunk allow-pass vlan 2 to 4094", "quit",
        # OSPF
        "ospf 1 router-id 2.2.2.2",
        "area 0.0.0.0", "network 192.168.0.0 0.0.255.255", "quit",
        "silent-interface Vlanif10", "silent-interface Vlanif20",
        "silent-interface Vlanif30", "silent-interface Vlanif40",
        "silent-interface Vlanif101", "quit",
    ])

    # 3. LSW3 - 汇聚交换机
    print("[3] 配置 LSW3 (汇聚交换机)...")
    batch_cmd("LSW3", [
        "vlan batch 10 20 30 40 100 to 101",
        "stp mode mstp", "stp enable",
        "stp region-configuration",
        "region-name huawei", "revision-level 16",
        "instance 1 vlan 10 100 101", "instance 2 vlan 20 30 40",
        "active region-configuration", "quit",
        # GE0/0/1->LSW1
        "interface GigabitEthernet0/0/1", "port link-type trunk",
        "port trunk allow-pass vlan 10 20 30 40 100 to 101", "quit",
        # GE0/0/2->LSW2
        "interface GigabitEthernet0/0/2", "port link-type trunk",
        "port trunk allow-pass vlan 10 20 30 40 100 to 101", "quit",
        # GE0/0/3->AP1 (trunk pvid 100)
        "interface GigabitEthernet0/0/3", "port link-type trunk",
        "port trunk pvid vlan 100", "port trunk allow-pass vlan 100 to 101", "quit",
        # GE0/0/4->LSW5
        "interface GigabitEthernet0/0/4", "port link-type trunk",
        "port trunk allow-pass vlan 10", "quit",
        # GE0/0/5->LSW6
        "interface GigabitEthernet0/0/5", "port link-type trunk",
        "port trunk allow-pass vlan 20", "quit",
        # LACP to LSW4
        "interface Eth-Trunk2", "mode lacp-static",
        "port link-type trunk", "port trunk allow-pass vlan 2 to 4094", "quit",
        "interface GigabitEthernet0/0/10", "eth-trunk 2", "quit",
        "interface GigabitEthernet0/0/11", "eth-trunk 2", "quit",
    ])

    # 4. LSW4 - 汇聚交换机
    print("[4] 配置 LSW4 (汇聚交换机)...")
    batch_cmd("LSW4", [
        "vlan batch 10 20 30 40 100 to 101",
        "stp mode mstp", "stp enable",
        "stp region-configuration",
        "region-name huawei", "revision-level 16",
        "instance 1 vlan 10 100 101", "instance 2 vlan 20 30 40",
        "active region-configuration", "quit",
        # GE0/0/1->LSW3
        "interface GigabitEthernet0/0/1", "port link-type trunk",
        "port trunk allow-pass vlan 10 20 30 40 100 to 101", "quit",
        # GE0/0/2->LSW2
        "interface GigabitEthernet0/0/2", "port link-type trunk",
        "port trunk allow-pass vlan 10 20 30 40 100 to 101", "quit",
        # GE0/0/4->LSW8
        "interface GigabitEthernet0/0/4", "port link-type trunk",
        "port trunk allow-pass vlan 40", "quit",
        # GE0/0/5->AP2 (trunk pvid 100)
        "interface GigabitEthernet0/0/5", "port link-type trunk",
        "port trunk pvid vlan 100", "port trunk allow-pass vlan 100 to 101", "quit",
        # LACP to LSW3
        "interface Eth-Trunk2", "mode lacp-static",
        "port link-type trunk", "port trunk allow-pass vlan 2 to 4094", "quit",
        "interface GigabitEthernet0/0/10", "eth-trunk 2", "quit",
        "interface GigabitEthernet0/0/11", "eth-trunk 2", "quit",
    ])

    # 5. 接入层交换机
    print("[5] 配置接入层交换机...")
    batch_cmd("LSW5", [
        "vlan batch 10",
        "interface Ethernet0/0/1", "port link-type access", "port default vlan 10", "quit",
        "interface Ethernet0/0/2", "port link-type access", "port default vlan 10", "quit",
        "interface Ethernet0/0/3", "port link-type access", "port default vlan 10", "quit",
    ])
    batch_cmd("LSW6", [
        "vlan batch 20",
        "interface Ethernet0/0/1", "port link-type access", "port default vlan 20", "quit",
        "interface Ethernet0/0/2", "port link-type access", "port default vlan 20", "quit",
        "interface Ethernet0/0/3", "port link-type access", "port default vlan 20", "quit",
    ])
    batch_cmd("LSW7", [
        "vlan batch 30",
        "interface Ethernet0/0/1", "port link-type access", "port default vlan 30", "quit",
        "interface Ethernet0/0/2", "port link-type access", "port default vlan 30", "quit",
        "interface Ethernet0/0/3", "port link-type access", "port default vlan 30", "quit",
    ])
    batch_cmd("LSW8", [
        "vlan batch 40",
        "interface Ethernet0/0/1", "port link-type access", "port default vlan 40", "quit",
        "interface Ethernet0/0/2", "port link-type access", "port default vlan 40", "quit",
        "interface Ethernet0/0/3", "port link-type access", "port default vlan 40", "quit",
    ])

    # 6. LSW9/LSW10
    print("[6] 配置 LSW9/LSW10...")
    batch_cmd("LSW9", [
        "vlan batch 100",
        "interface Ethernet0/0/1", "port link-type access", "port default vlan 100", "quit",
        "interface Ethernet0/0/2", "port link-type access", "port default vlan 100", "quit",
        "interface Ethernet0/0/3", "port link-type access", "port default vlan 100", "quit",
        "interface GigabitEthernet0/0/1", "port link-type trunk",
        "port trunk allow-pass vlan 100", "quit",
    ])
    batch_cmd("LSW10", [
        "vlan batch 100",
        "interface Ethernet0/0/1", "port link-type access", "port default vlan 100", "quit",
        "interface GigabitEthernet0/0/1", "port link-type access", "port default vlan 100", "quit",
    ])

    # 7. 防火墙
    print("[7] 配置 FW1 (防火墙)...")
    batch_cmd("FW1", [
        # 接口IP
        "interface GigabitEthernet1/0/0", "ip address 192.168.0.1 255.255.255.0",
        "undo shutdown", "service-manage ping permit", "quit",
        "interface GigabitEthernet1/0/1", "ip address 200.1.1.1 255.255.255.0",
        "undo shutdown", "service-manage ping permit", "quit",
        "interface GigabitEthernet1/0/2", "ip address 192.168.50.254 255.255.255.0",
        "undo shutdown", "service-manage ping permit", "quit",
        "interface GigabitEthernet1/0/3", "ip address 192.168.51.254 255.255.255.0",
        "undo shutdown", "service-manage ping permit", "quit",
        # 区域
        "firewall zone trust", "add interface GigabitEthernet1/0/2", "add interface GigabitEthernet1/0/3", "quit",
        "firewall zone untrust", "set priority 5", "add interface GigabitEthernet1/0/1", "quit",
        "firewall zone dmz", "set priority 50", "add interface GigabitEthernet1/0/0", "quit",
        # 安全策略
        "security-policy",
        "rule name trust_to_dmz", "source-zone trust", "destination-zone dmz", "action permit", "quit",
        "rule name trust_to_untrust", "source-zone trust", "destination-zone untrust", "action permit", "quit",
        "rule name untrust_to_dmz", "source-zone untrust", "destination-zone dmz", "action permit", "quit",
        "rule name dmz_deny_all", "source-zone dmz", "action deny", "quit",
        "quit",
        # 路由
        "ip route-static 0.0.0.0 0.0.0.0 200.1.1.2",
        "ospf 1 router-id 3.3.3.3",
        "area 0.0.0.0", "network 192.168.50.0 0.0.0.255", "network 192.168.51.0 0.0.0.255",
        "default-route-advertise", "quit", "quit",
    ])

    # 8. AR1 路由器
    print("[8] 配置 AR1 (路由器)...")
    batch_cmd("AR1", [
        "interface GigabitEthernet0/0/0", "ip address 200.1.1.2 255.255.255.0", "quit",
        "interface GigabitEthernet0/0/1", "ip address 201.1.1.1 255.255.255.0", "quit",
        "ip route-static 0.0.0.0 0.0.0.0 200.1.1.1",
        "ip route-static 192.168.0.0 255.255.0.0 200.1.1.1",
    ])

    # 9. AC1 无线控制器
    print("[9] 配置 AC1 (无线控制器)...")
    batch_cmd("AC1", [
        "vlan batch 100 to 101", "dhcp enable",
        "interface Vlanif100", "ip address 192.168.100.1 255.255.255.0",
        "dhcp select interface", "quit",
        "interface GigabitEthernet0/0/19", "port link-type trunk",
        "port trunk allow-pass vlan 2 to 4094", "quit",
        "capwap source interface Vlanif100",
        "wlan",
        "security-profile name sec",
        "security wpa-wpa2 psk pass-phrase zz1234567 aes",
        "quit",
        "ssid-profile name ssid",
        "ssid wlan-2024",
        "quit",
        "vap-profile name vap",
        "forward-mode direct-forward",
        "service-vlan vlan-id 101",
        "security-profile sec",
        "ssid-profile ssid",
        "quit",
        "ap-group name ap",
        "radio 0", "vap-profile vap wlan 1", "quit",
        "radio 1", "vap-profile vap wlan 1", "quit",
        "quit",
        "ap-id 1 ap-mac 00e0-fc3f-6920 ap-sn 210235448310076D7959",
        "ap-name ap1", "ap-group ap",
        "quit",
        "ap-id 2 ap-mac 00e0-fc75-3280 ap-sn 2102354483100E48CA09",
        "ap-name ap2", "ap-group ap",
        "quit",
        "quit", "quit",
    ])

    print("\n" + "=" * 60)
    print("配置完成！")
    print("=" * 60)
    print("\n手动验证步骤：")
    print("1. Server1: 配置 DNS 服务 (192.168.0.1)")
    print("2. Server2: 开启 Web 服务")
    print("3. Server3: 开启 FTP 服务")
    print("4. 检查 AP 是否上线: display ap all")
    print("5. PC 测试 DHCP 获取 IP")

if __name__ == "__main__":
    configure_all()
