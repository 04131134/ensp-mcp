# -*- coding: utf-8 -*-
"""基础连通性配置（实验一/二公共底层）：
- LSW1: 端口 GE0/0/1-5 access vlan 10; Vlanif10=10.1.1.254; DHCP 全局池(排除AC/IP)
- AR1/AR2/AR3: 两口均 access vlan 10 (二层桥)
- AC1: Vlanif10=10.1.1.1; capwap source Vlanif10
- AC2: Vlanif10=10.1.1.2; capwap source Vlanif10
"""
import sys, os, time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
from mcpensp1.connection import TelnetConnection

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

def apply(name, port, cmds):
    print(f'\n===== 配置 {name} (:{port}) =====')
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    c.send_cmd('system-view')
    errors = []
    for cmd in cmds:
        if cmd.strip() in ('', 'system-view', 'return', 'quit'):
            if cmd.strip() == 'return':
                c.send_cmd('return')
            continue
        r = c.send_cmd(cmd)
        if 'Error:' in r:
            # 忽略无害提示：端口已是二层
            if 'already a L2 interface' in r:
                continue
            errors.append((cmd, r.strip()[-200:]))
            print(f'  [ERROR] {cmd}')
    c.send_cmd('return')
    c.close()
    return errors

LSW1 = [
    'undo info-center enable',
    'vlan batch 10',
    'dhcp enable',
    'ip pool ap-mgmt',
    ' gateway-list 10.1.1.254',
    ' network 10.1.1.0 mask 255.255.255.0',
    ' excluded-ip-address 10.1.1.1 10.1.1.2',
    'quit',
    'interface GigabitEthernet0/0/1',
    ' port link-type access',
    ' port default vlan 10',
    'interface GigabitEthernet0/0/2',
    ' port link-type access',
    ' port default vlan 10',
    'interface GigabitEthernet0/0/3',
    ' port link-type access',
    ' port default vlan 10',
    'interface GigabitEthernet0/0/4',
    ' port link-type access',
    ' port default vlan 10',
    'interface GigabitEthernet0/0/5',
    ' port link-type access',
    ' port default vlan 10',
    'interface Vlanif10',
    ' ip address 10.1.1.254 255.255.255.0',
    ' dhcp select global',
    'quit',
]

AR = [
    'undo info-center enable',
    'vlan batch 10',
    'interface Ethernet0/0/0',
    ' portswitch',
    ' port link-type access',
    ' port default vlan 10',
    'interface Ethernet0/0/1',
    ' portswitch',
    ' port link-type access',
    ' port default vlan 10',
    'quit',
]

AC1 = [
    'undo info-center enable',
    'vlan batch 10',
    'interface Vlanif10',
    ' ip address 10.1.1.1 255.255.255.0',
    'quit',
    'capwap source interface Vlanif10',
]

AC2 = [
    'undo info-center enable',
    'vlan batch 10',
    'interface Vlanif10',
    ' ip address 10.1.1.2 255.255.255.0',
    'quit',
    'capwap source interface Vlanif10',
]

def main():
    all_err = {}
    all_err['LSW1'] = apply('LSW1', 2003, LSW1)
    all_err['AR1'] = apply('AR1', 2000, AR)
    all_err['AR2'] = apply('AR2', 2001, AR)
    all_err['AR3'] = apply('AR3', 2002, AR)
    all_err['AC1'] = apply('AC1', 2004, AC1)
    all_err['AC2'] = apply('AC2', 2005, AC2)
    print('\n===== 错误汇总 =====')
    any_err = False
    for dev, errs in all_err.items():
        if errs:
            any_err = True
            print(f'{dev}: {len(errs)} 个错误')
            for cmd, msg in errs:
                print(f'  - {cmd} :: {msg}')
    if not any_err:
        print('无 Error 输出。')
    # 保存错误汇总
    with open(os.path.join(LOG_DIR, 'base_errors.txt'), 'w', encoding='utf-8') as f:
        for dev, errs in all_err.items():
            for cmd, msg in errs:
                f.write(f'{dev}|{cmd}|{msg}\n')

if __name__ == '__main__':
    main()
