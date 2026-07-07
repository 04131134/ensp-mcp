# -*- coding: utf-8 -*-
"""校园网实验配置脚本 - 通过 Telnet 自动配置 eNSP 中的所有设备。

设备列表:
  - SW1 (port 2008) 核心层 S5700
  - SW2 (port 2015) 核心层 S5700
  - SW3 (port 2007) 汇聚层 S5700
  - SW4 (port 2016) 汇聚层 S5700
  - SW5 (port 2002) 接入层 S3700
  - SW6 (port 2003) 接入层 S3700
  - SW7 (port 2004) 接入层 S3700
  - SW8 (port 2006) 接入层 S3700
  - SW9 (port 2014) 接入层 S3700
  - SW10 (port 2011) 接入层 S3700
  - AC  (port 2010) AC6605
  - AR1 (port 2013) AR3200
  - FW  (port 2009) USG防火墙

连接库: e:\\eNSP-MCP\\mcpensp1\\connection.py 中的 TelnetConnection
"""

import sys
import time

# 将 connection.py 所在目录加入 sys.path
sys.path.insert(0, r'e:\eNSP-MCP\mcpensp1')

from connection import TelnetConnection


# ═══════════════════════════════════════════════════════════════════════════════
# 通用工具函数
# ═══════════════════════════════════════════════════════════════════════════════

FW_PORT = 2009


def connect_device(port):
    """连接设备并返回 TelnetConnection 对象。

    对 FW (port 2009) 做特殊的防火墙登录处理。
    对其他设备使用标准 connect 流程。
    """
    conn = TelnetConnection('127.0.0.1', port)
    conn.connect()

    if port == FW_PORT:
        # 防火墙需要手动登录处理
        print('[FW] 正在处理防火墙登录...')
        time.sleep(1)
        conn.send_cmd('')
        time.sleep(2)

        # 发送用户名
        conn.sock.send(b'admin\r\n')
        time.sleep(2)

        # 发送密码
        conn.sock.send(b'Admin@123\r\n')
        time.sleep(3)

        # 不修改密码 -> 发送 n
        conn.sock.send(b'n\r\n')
        time.sleep(2)

        # 按 Enter
        conn.sock.send(b'\r\n')
        time.sleep(2)

        conn._flush()
        print('[FW] 防火墙登录完成')
    else:
        # 非防火墙设备，尝试标准登录（对普通交换机无影响）
        conn.handle_firewall_login()

    # 关闭终端监视，避免干扰输出
    try:
        conn.send_cmd('undo terminal monitor')
        time.sleep(0.1)
    except Exception:
        pass

    return conn


def send_commands(conn, commands):
    """逐条发送命令列表到设备，每条间隔0.3秒。

    打印每条命令输出的前200字符，方便实时查看配置进度。

    Args:
        conn: TelnetConnection 对象
        commands: 命令字符串列表
    """
    for cmd in commands:
        cmd_stripped = cmd.strip()
        if not cmd_stripped:
            continue
        try:
            output = conn.send_cmd(cmd_stripped)
            preview = output.strip()[:200] if output else '(无输出)'
            print(f'  > {cmd_stripped}')
            if preview:
                print(f'    {preview}')
        except Exception as e:
            print(f'  > {cmd_stripped}  [错误: {e}]')
        time.sleep(0.3)


def disconnect_device(conn):
    """安全断开设备连接。"""
    try:
        if conn:
            conn.close()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# SW1 核心层配置 (port 2008)
# ═══════════════════════════════════════════════════════════════════════════════

def config_sw1():
    """配置核心层交换机 SW1 (port 2008, S5700)。

    - VLAN 10/20/30/40/100/101/520/521
    - MSTP: instance 1 root primary (VLAN 10/100/101), instance 2 root secondary
    - VLANIF: VRRP gateway, VLAN520/521 互联地址
    - Eth-Trunk1 上行到 SW3
    - DHCP Server (vlan10/20/30/40/101)
    - OSPF
    - G0/0/1 access VLAN520, G0/0/2 access VLAN521
    - G0/0/19 trunk to AC
    - G0/0/10-11 加入 Eth-Trunk1
    """
    print('\n===== 开始配置 SW1 (核心层, port 2008) =====')
    conn = connect_device(2008)
    try:
        commands = [
            'system-view',
            'sysname SW1',

            # --- VLAN ---
            'vlan batch 10 20 30 40 100 101 520 521',

            # --- MSTP ---
            'stp region-configuration',
            ' region-name huawei',
            ' revision-level 16',
            ' instance 1 vlan 10 100 101',
            ' instance 2 vlan 20 30 40',
            ' active region-configuration',
            'stp instance 1 root primary',
            'stp instance 2 root secondary',
            'stp enable',

            # --- VLANIF 接口 ---
            'interface Vlanif10',
            ' ip address 192.168.1.100 255.255.255.0',
            ' vrrp vrid 10 virtual-ip 192.168.1.254',
            ' vrrp vrid 10 priority 120',

            'interface Vlanif20',
            ' ip address 192.168.2.100 255.255.255.0',
            ' vrrp vrid 20 virtual-ip 192.168.2.254',

            'interface Vlanif30',
            ' ip address 192.168.3.100 255.255.255.0',
            ' vrrp vrid 30 virtual-ip 192.168.3.254',

            'interface Vlanif40',
            ' ip address 192.168.4.100 255.255.255.0',
            ' vrrp vrid 40 virtual-ip 192.168.4.254',

            'interface Vlanif100',
            ' ip address 192.168.100.254 255.255.255.0',

            'interface Vlanif101',
            ' ip address 192.168.101.100 255.255.255.0',
            ' vrrp vrid 101 virtual-ip 192.168.101.254',
            ' vrrp vrid 101 priority 120',

            'interface Vlanif520',
            ' ip address 10.0.0.1 255.255.255.0',

            'interface Vlanif521',
            ' ip address 10.0.1.1 255.255.255.0',

            # --- Eth-Trunk1 (上行到SW3) ---
            'interface Eth-Trunk1',
            ' port link-type trunk',
            ' port trunk allow-pass vlan 10 20 30 40 100 101',
            ' mode lacp-static',

            # --- 物理接口 ---
            # G0/0/1 互联SW2 (VLAN520)
            'interface GigabitEthernet0/0/1',
            ' port link-type access',
            ' port default vlan 520',

            # G0/0/2 互联SW2 (VLAN521)
            'interface GigabitEthernet0/0/2',
            ' port link-type access',
            ' port default vlan 521',

            # G0/0/19 trunk to AC
            'interface GigabitEthernet0/0/19',
            ' port link-type trunk',
            ' port trunk allow-pass vlan all',

            # Eth-Trunk 成员
            'interface GigabitEthernet0/0/10',
            ' eth-trunk 1',
            'interface GigabitEthernet0/0/11',
            ' eth-trunk 1',

            # --- DHCP ---
            'dhcp enable',
            'ip pool vlan10',
            ' gateway-list 192.168.1.254',
            ' network 192.168.1.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',
            'ip pool vlan20',
            ' gateway-list 192.168.2.254',
            ' network 192.168.2.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',
            'ip pool vlan30',
            ' gateway-list 192.168.3.254',
            ' network 192.168.3.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',
            'ip pool vlan40',
            ' gateway-list 192.168.4.254',
            ' network 192.168.4.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',
            'ip pool vlan101',
            ' gateway-list 192.168.101.254',
            ' network 192.168.101.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',

            # VLANIF 启用 DHCP
            'interface Vlanif10',
            ' dhcp select global',
            'interface Vlanif20',
            ' dhcp select global',
            'interface Vlanif30',
            ' dhcp select global',
            'interface Vlanif40',
            ' dhcp select global',
            'interface Vlanif101',
            ' dhcp select global',

            # --- OSPF ---
            'ospf 1 router-id 1.1.1.1',
            ' area 0.0.0.0',
            '  network 192.168.0.0 0.0.255.255',
            '  network 10.0.0.0 0.0.0.255',
            '  network 10.0.1.0 0.0.0.255',
            '  silent-interface Vlanif10',
            '  silent-interface Vlanif20',
            '  silent-interface Vlanif30',
            '  silent-interface Vlanif40',
            '  silent-interface Vlanif101',

            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[SW1] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print('===== SW1 配置完成 =====\n')


# ═══════════════════════════════════════════════════════════════════════════════
# SW2 核心层配置 (port 2015)
# ═══════════════════════════════════════════════════════════════════════════════

def config_sw2():
    """配置核心层交换机 SW2 (port 2015, S5700)。

    - VLAN 10/20/30/40/100/101/520/521
    - MSTP: instance 1 root secondary, instance 2 root primary (VLAN 20/30/40)
    - VLANIF: VRRP gateway (SW2负责VLAN20/30/40)
    - Eth-Trunk1 上行到 SW4
    - DHCP Server (vlan10/20/30/40/101)
    - OSPF
    - G0/0/1 access VLAN520, G0/0/2 access VLAN521
    - G0/0/10-11 加入 Eth-Trunk1
    """
    print('\n===== 开始配置 SW2 (核心层, port 2015) =====')
    conn = connect_device(2015)
    try:
        commands = [
            'system-view',
            'sysname SW2',

            # --- VLAN ---
            'vlan batch 10 20 30 40 100 101 520 521',

            # --- MSTP ---
            'stp region-configuration',
            ' region-name huawei',
            ' revision-level 16',
            ' instance 1 vlan 10 100 101',
            ' instance 2 vlan 20 30 40',
            ' active region-configuration',
            'stp instance 1 root secondary',
            'stp instance 2 root primary',
            'stp enable',

            # --- VLANIF 接口 ---
            'interface Vlanif10',
            ' ip address 192.168.1.200 255.255.255.0',
            ' vrrp vrid 10 virtual-ip 192.168.1.254',

            'interface Vlanif20',
            ' ip address 192.168.2.200 255.255.255.0',
            ' vrrp vrid 20 virtual-ip 192.168.2.254',
            ' vrrp vrid 20 priority 120',

            'interface Vlanif30',
            ' ip address 192.168.3.200 255.255.255.0',
            ' vrrp vrid 30 virtual-ip 192.168.3.254',
            ' vrrp vrid 30 priority 120',

            'interface Vlanif40',
            ' ip address 192.168.4.200 255.255.255.0',
            ' vrrp vrid 40 virtual-ip 192.168.4.254',
            ' vrrp vrid 40 priority 120',

            'interface Vlanif100',
            ' ip address 192.168.100.254 255.255.255.0',

            'interface Vlanif101',
            ' ip address 192.168.101.200 255.255.255.0',
            ' vrrp vrid 101 virtual-ip 192.168.101.254',

            'interface Vlanif520',
            ' ip address 10.0.0.2 255.255.255.0',

            'interface Vlanif521',
            ' ip address 10.0.1.2 255.255.255.0',

            # --- Eth-Trunk1 (上行到SW4) ---
            'interface Eth-Trunk1',
            ' port link-type trunk',
            ' port trunk allow-pass vlan 10 20 30 40 100 101',
            ' mode lacp-static',

            # --- 物理接口 ---
            # G0/0/1 互联SW1 (VLAN520)
            'interface GigabitEthernet0/0/1',
            ' port link-type access',
            ' port default vlan 520',

            # G0/0/2 互联SW1 (VLAN521)
            'interface GigabitEthernet0/0/2',
            ' port link-type access',
            ' port default vlan 521',

            # Eth-Trunk 成员
            'interface GigabitEthernet0/0/10',
            ' eth-trunk 1',
            'interface GigabitEthernet0/0/11',
            ' eth-trunk 1',

            # --- DHCP ---
            'dhcp enable',
            'ip pool vlan10',
            ' gateway-list 192.168.1.254',
            ' network 192.168.1.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',
            'ip pool vlan20',
            ' gateway-list 192.168.2.254',
            ' network 192.168.2.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',
            'ip pool vlan30',
            ' gateway-list 192.168.3.254',
            ' network 192.168.3.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',
            'ip pool vlan40',
            ' gateway-list 192.168.4.254',
            ' network 192.168.4.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',
            'ip pool vlan101',
            ' gateway-list 192.168.101.254',
            ' network 192.168.101.0 mask 255.255.255.0',
            ' dns-list 192.168.0.1',

            # VLANIF 启用 DHCP
            'interface Vlanif10',
            ' dhcp select global',
            'interface Vlanif20',
            ' dhcp select global',
            'interface Vlanif30',
            ' dhcp select global',
            'interface Vlanif40',
            ' dhcp select global',
            'interface Vlanif101',
            ' dhcp select global',

            # --- OSPF ---
            'ospf 1 router-id 2.2.2.2',
            ' area 0.0.0.0',
            '  network 192.168.0.0 0.0.255.255',
            '  network 10.0.0.0 0.0.0.255',
            '  network 10.0.1.0 0.0.0.255',
            '  silent-interface Vlanif10',
            '  silent-interface Vlanif20',
            '  silent-interface Vlanif30',
            '  silent-interface Vlanif40',
            '  silent-interface Vlanif101',

            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[SW2] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print('===== SW2 配置完成 =====\n')


# ═══════════════════════════════════════════════════════════════════════════════
# SW3 汇聚层配置 (port 2007)
# ═══════════════════════════════════════════════════════════════════════════════

def config_sw3():
    """配置汇聚层交换机 SW3 (port 2007, S5700)。

    - VLAN 10/20/30/40/100/101
    - MSTP: 与核心层一致的 region 配置
    - Eth-Trunk1 上行到 SW1
    - G0/0/3 trunk (pvid vlan 100) 连 AP1
    - G0/0/4 access vlan 10 (宿舍楼)
    - G0/0/5 access vlan 20 (教学楼)
    - G0/0/10-11 加入 Eth-Trunk1
    """
    print('\n===== 开始配置 SW3 (汇聚层, port 2007) =====')
    conn = connect_device(2007)
    try:
        commands = [
            'system-view',
            'sysname SW3',

            # --- VLAN ---
            'vlan batch 10 20 30 40 100 101',

            # --- MSTP ---
            'stp region-configuration',
            ' region-name huawei',
            ' revision-level 16',
            ' instance 1 vlan 10 100 101',
            ' instance 2 vlan 20 30 40',
            ' active region-configuration',
            'stp enable',

            # --- Eth-Trunk1 (上行到SW1) ---
            'interface Eth-Trunk1',
            ' port link-type trunk',
            ' port trunk allow-pass vlan 10 20 30 40 100 101',
            ' mode lacp-static',

            # --- 下行接口 ---
            # G0/0/3 trunk to AP1 (pvid vlan 100)
            'interface GigabitEthernet0/0/3',
            ' port link-type trunk',
            ' port trunk pvid vlan 100',
            ' port trunk allow-pass vlan 100 101',
            ' undo port trunk allow-pass vlan 1',

            # G0/0/4 access vlan 10 (宿舍楼)
            'interface GigabitEthernet0/0/4',
            ' port link-type access',
            ' port default vlan 10',

            # G0/0/5 access vlan 20 (教学楼)
            'interface GigabitEthernet0/0/5',
            ' port link-type access',
            ' port default vlan 20',

            # --- Eth-Trunk 成员 ---
            'interface GigabitEthernet0/0/10',
            ' eth-trunk 1',
            'interface GigabitEthernet0/0/11',
            ' eth-trunk 1',

            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[SW3] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print('===== SW3 配置完成 =====\n')


# ═══════════════════════════════════════════════════════════════════════════════
# SW4 汇聚层配置 (port 2016)
# ═══════════════════════════════════════════════════════════════════════════════

def config_sw4():
    """配置汇聚层交换机 SW4 (port 2016, S5700)。

    - VLAN 10/20/30/40/100/101
    - MSTP: 与核心层一致的 region 配置
    - Eth-Trunk1 上行到 SW2
    - G0/0/3 trunk (pvid vlan 100) 连 AP2
    - G0/0/4 access vlan 30 (图书馆)
    - G0/0/5 access vlan 40 (行政楼)
    - G0/0/10-11 加入 Eth-Trunk1
    """
    print('\n===== 开始配置 SW4 (汇聚层, port 2016) =====')
    conn = connect_device(2016)
    try:
        commands = [
            'system-view',
            'sysname SW4',

            # --- VLAN ---
            'vlan batch 10 20 30 40 100 101',

            # --- MSTP ---
            'stp region-configuration',
            ' region-name huawei',
            ' revision-level 16',
            ' instance 1 vlan 10 100 101',
            ' instance 2 vlan 20 30 40',
            ' active region-configuration',
            'stp enable',

            # --- Eth-Trunk1 (上行到SW2) ---
            'interface Eth-Trunk1',
            ' port link-type trunk',
            ' port trunk allow-pass vlan 10 20 30 40 100 101',
            ' mode lacp-static',

            # --- 下行接口 ---
            # G0/0/3 trunk to AP2 (pvid vlan 100)
            'interface GigabitEthernet0/0/3',
            ' port link-type trunk',
            ' port trunk pvid vlan 100',
            ' port trunk allow-pass vlan 100 101',
            ' undo port trunk allow-pass vlan 1',

            # G0/0/4 access vlan 30 (图书馆)
            'interface GigabitEthernet0/0/4',
            ' port link-type access',
            ' port default vlan 30',

            # G0/0/5 access vlan 40 (行政楼)
            'interface GigabitEthernet0/0/5',
            ' port link-type access',
            ' port default vlan 40',

            # --- Eth-Trunk 成员 ---
            'interface GigabitEthernet0/0/10',
            ' eth-trunk 1',
            'interface GigabitEthernet0/0/11',
            ' eth-trunk 1',

            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[SW4] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print('===== SW4 配置完成 =====\n')


# ═══════════════════════════════════════════════════════════════════════════════
# 接入层交换机 SW5-SW10 配置
# ═══════════════════════════════════════════════════════════════════════════════

def config_access_sw(name, port, vlan_id, desc):
    """通用接入层交换机配置。

    Args:
        name: sysname (如 'SW5')
        port: Telnet 端口
        vlan_id: 所属 VLAN ID
        desc: 描述信息 (如 '宿舍楼')
    """
    print(f'\n===== 开始配置 {name} (接入层, port {port}) =====')
    conn = connect_device(port)
    try:
        commands = [
            'system-view',
            f'sysname {name}',
            f'vlan {vlan_id}',
            'interface GigabitEthernet0/0/1',
            ' port link-type trunk',
            f' port trunk allow-pass vlan {vlan_id}',
            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[{name}] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print(f'===== {name} 配置完成 =====\n')


def config_access_layer():
    """配置所有接入层交换机 SW5 ~ SW10。"""
    # SW5 (port 2002) - VLAN 10 - 宿舍楼
    config_access_sw('SW5', 2002, 10, '宿舍楼')

    # SW6 (port 2003) - VLAN 20 - 教学楼
    config_access_sw('SW6', 2003, 20, '教学楼')

    # SW7 (port 2004) - VLAN 30 - 图书馆
    config_access_sw('SW7', 2004, 30, '图书馆')

    # SW8 (port 2006) - VLAN 40 - 行政楼
    config_access_sw('SW8', 2006, 40, '行政楼')

    # SW9 (port 2014) - VLAN 100 (AP相关) - 只配基本VLAN和上行
    print('\n===== 开始配置 SW9 (接入层, port 2014) =====')
    conn = connect_device(2014)
    try:
        commands = [
            'system-view',
            'sysname SW9',
            'vlan batch 100 101',
            'interface GigabitEthernet0/0/1',
            ' port link-type trunk',
            ' port trunk allow-pass vlan 100 101',
            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[SW9] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print('===== SW9 配置完成 =====\n')

    # SW10 (port 2011) - 接口全down，配置基本VLAN
    print('\n===== 开始配置 SW10 (接入层, port 2011) =====')
    conn = connect_device(2011)
    try:
        commands = [
            'system-view',
            'sysname SW10',
            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[SW10] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print('===== SW10 配置完成 =====\n')


# ═══════════════════════════════════════════════════════════════════════════════
# FW 防火墙配置 (port 2009)
# ═══════════════════════════════════════════════════════════════════════════════

def config_fw():
    """配置 USG 防火墙 FW (port 2009)。

    - 接口 IP 配置
    - 安全区域 (trust/dmz/untrust)
    - 安全策略
    - 默认路由
    - OSPF (发布默认路由)
    """
    print('\n===== 开始配置 FW (防火墙, port 2009) =====')
    conn = connect_device(FW_PORT)
    try:
        commands = [
            'system-view',
            'sysname FW',

            # --- 接口配置 ---
            'interface GigabitEthernet0/0/0',
            ' ip address 192.168.0.1 255.255.255.0',

            'interface GigabitEthernet1/0/0',
            ' ip address 192.168.0.254 255.255.255.0',

            'interface GigabitEthernet1/0/1',
            ' ip address 200.1.1.1 255.255.255.0',

            'interface GigabitEthernet1/0/2',
            ' ip address 192.168.50.2 255.255.255.0',

            'interface GigabitEthernet1/0/3',
            ' ip address 192.168.51.2 255.255.255.0',

            # --- 安全区域 ---
            'firewall zone trust',
            ' add interface GigabitEthernet0/0/0',
            ' add interface GigabitEthernet1/0/2',
            ' add interface GigabitEthernet1/0/3',

            'firewall zone dmz',
            ' add interface GigabitEthernet1/0/0',

            'firewall zone untrust',
            ' add interface GigabitEthernet1/0/1',

            # --- 安全策略 ---
            'security-policy',
            ' rule name trust_to_out',
            '  source-zone trust',
            '  destination-zone dmz',
            '  destination-zone untrust',
            '  action permit',
            ' rule name untrust_to_dmz',
            '  source-zone untrust',
            '  destination-zone dmz',
            '  action permit',

            # --- 默认路由 ---
            'ip route-static 0.0.0.0 0.0.0.0 200.1.1.2',

            # --- OSPF ---
            'ospf 1 router-id 3.3.3.3',
            ' area 0.0.0.0',
            '  network 192.168.0.0 0.0.255.255',
            '  default-route-advertise always',

            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[FW] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print('===== FW 配置完成 =====\n')


# ═══════════════════════════════════════════════════════════════════════════════
# AR1 路由器配置 (port 2013)
# ═══════════════════════════════════════════════════════════════════════════════

def config_ar1():
    """配置出口路由器 AR1 (port 2013, AR3200)。

    - G0/0/0: 200.1.1.2/24 (连 FW)
    - G0/0/1: 201.1.1.254/24 (外网)
    - 默认路由指向 FW
    """
    print('\n===== 开始配置 AR1 (路由器, port 2013) =====')
    conn = connect_device(2013)
    try:
        commands = [
            'system-view',
            'sysname AR1',

            'interface GigabitEthernet0/0/0',
            ' ip address 200.1.1.2 255.255.255.0',

            'interface GigabitEthernet0/0/1',
            ' ip address 201.1.1.254 255.255.255.0',

            'ip route-static 0.0.0.0 0.0.0.0 200.1.1.1',

            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[AR1] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print('===== AR1 配置完成 =====\n')


# ═══════════════════════════════════════════════════════════════════════════════
# AC 无线控制器配置 (port 2010)
# ═══════════════════════════════════════════════════════════════════════════════

def config_ac():
    """配置无线控制器 AC (port 2010, AC6605)。

    - VLAN 100/101
    - VLANIF100: AP管理地址 + DHCP
    - G0/0/19 trunk 连 SW1
    - CAPWAP 源接口
    - WLAN 配置: WMM / SSID / 安全 / VAP / AP组
    - AP 认证 (mac-auth)
    """
    print('\n===== 开始配置 AC (无线控制器, port 2010) =====')
    conn = connect_device(2010)
    try:
        commands = [
            'system-view',
            'sysname AC',

            # --- VLAN ---
            'vlan batch 100 101',

            # --- VLANIF100 (AP管理 + DHCP) ---
            'interface Vlanif100',
            ' ip address 192.168.100.1 255.255.255.0',
            ' dhcp select interface',

            # --- DHCP ---
            'dhcp enable',

            # --- 上行接口 (连接SW1) ---
            'interface GigabitEthernet0/0/19',
            ' port link-type trunk',
            ' port trunk allow-pass vlan 100 101',

            # --- CAPWAP 源接口 ---
            'capwap source interface vlanif 100',

            # --- WLAN 配置 ---
            'wlan',

            # WMM
            ' wmm-profile name wmm1',
            '  wmm enable',

            # SSID
            ' ssid-profile name wlan-2024',
            '  ssid wlan-2024',

            # 安全
            ' security-profile name sec1',
            '  security wpa-wpa2 psk pass-phrase 12345678 aes-tkip',

            # VAP
            ' vap-profile name vap1',
            '  forward-mode tunnel',
            '  service-vlan vlan-id 101',
            '  ssid-profile wlan-2024',
            '  security-profile sec1',
            '  wmm-profile wmm1',

            # AP组
            ' ap-group name ap',
            '  vap-profile vap1 wlan 1 radio all',

            # --- AP 认证 ---
            'ap auth-mode mac-auth',
            'ap-id 1 ap-mac 00e0-fc40-50d0 ap-name AP1',
            'ap-id 2 ap-mac 00e0-fc8c-54e0 ap-name AP2',

            'return',
        ]
        send_commands(conn, commands)
    except Exception as e:
        print(f'[AC] 配置出错: {e}')
    finally:
        disconnect_device(conn)
    print('===== AC 配置完成 =====\n')


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """按顺序配置所有设备: SW1 -> SW2 -> SW3 -> SW4 -> 接入层 -> FW -> AR1 -> AC。

    每台设备配置独立 try/except，出错时打印错误但继续执行下一台设备。
    """
    print('=' * 60)
    print('  校园网实验 - 自动配置脚本')
    print('  配置顺序: SW1 -> SW2 -> SW3 -> SW4 -> 接入层 -> FW -> AR1 -> AC')
    print('=' * 60)

    start_time = time.time()

    # 1. 核心层
    try:
        config_sw1()
    except Exception as e:
        print(f'[异常] SW1 配置失败: {e}\n')

    try:
        config_sw2()
    except Exception as e:
        print(f'[异常] SW2 配置失败: {e}\n')

    # 2. 汇聚层
    try:
        config_sw3()
    except Exception as e:
        print(f'[异常] SW3 配置失败: {e}\n')

    try:
        config_sw4()
    except Exception as e:
        print(f'[异常] SW4 配置失败: {e}\n')

    # 3. 接入层
    try:
        config_access_layer()
    except Exception as e:
        print(f'[异常] 接入层配置失败: {e}\n')

    # 4. 防火墙
    try:
        config_fw()
    except Exception as e:
        print(f'[异常] FW 配置失败: {e}\n')

    # 5. 路由器
    try:
        config_ar1()
    except Exception as e:
        print(f'[异常] AR1 配置失败: {e}\n')

    # 6. AC 无线控制器
    try:
        config_ac()
    except Exception as e:
        print(f'[异常] AC 配置失败: {e}\n')

    elapsed = time.time() - start_time
    print('=' * 60)
    print(f'  所有设备配置完成，总耗时: {elapsed:.1f} 秒')
    print('=' * 60)


if __name__ == '__main__':
    main()
