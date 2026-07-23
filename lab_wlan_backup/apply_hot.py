# -*- coding: utf-8 -*-
"""实验二：AC 双机热备(HSB) — AC6005 真实语法
注意: AC6005 的 ac protect 命令与方案(AC6605)不同:
  - 全局: ac protect enable / ac protect priority <0-7> / ac protect protect-ac <对端IP>
  - AP 级: ap-id 下用 ac-list <对端IP> 指定双归属对端 (无 ap protect enable / priority 子命令)
  - 无 ac source ip 命令
  - type-id: AC1 上 56=AP3030DN; AC2 上 45=AP3030DN(两台类型表不同), 故各用各的正确 id
SSID = Office-HSB
"""
import sys, os, time
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
from mcpensp1.connection import TelnetConnection

def apply(name, port, cmds):
    print(f'\n===== 配置 {name} (:{port}) =====')
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    c.send_cmd('system-view')
    errs = []
    for raw in cmds:
        cmd = raw.strip()
        if not cmd:
            continue
        r = c.send_cmd(cmd)
        time.sleep(0.5)
        if 'Error:' in r and 'already' not in r:
            errs.append((cmd, r.strip()[-180:]))
            print(f'  [ERR] {cmd}: {r.strip()[-160:]}')
    c.send_cmd('return')
    c.close()
    return errs

# 共用业务模板(更新 SSID 为 Office-HSB)
def wlan_common():
    return [
        'wlan',
        'ssid-profile name office',
        'ssid Office-HSB',
        'quit',
        'security-profile name sec1',
        'security wpa-wpa2 psk pass-phrase Huawei@123 aes',
        'quit',
        'vap-profile name vap1',
        'ssid-profile office',
        'security-profile sec1',
        'service-vlan vlan-id 10',
        'forward-mode direct-forward',
        'quit',
        'regulatory-domain-profile name domain1',
        'country-code cn',
        'quit',
        'ap-group name default',
        'regulatory-domain-profile domain1',
        'radio 0',
        'vap-profile vap1 wlan 1',
        'quit',
        'radio 1',
        'vap-profile vap1 wlan 1',
        'quit',
        'quit',
    ]

AC1 = wlan_common() + [
    'ac protect enable',
    'ac protect priority 7',
    'ac protect protect-ac 10.1.1.2',
    'ap-id 1 ap-mac 00e0-fc1b-3720',
    'ap-name AP1',
    'ap-group default',
    'ac-list 10.1.1.2',
    'quit',
    'ap-id 2 ap-mac 00e0-fcdb-0400',
    'ap-name AP2',
    'ap-group default',
    'ac-list 10.1.1.2',
    'quit',
    'ap-id 3 ap-mac 00e0-fcf8-32e0',
    'ap-name AP3',
    'ap-group default',
    'ac-list 10.1.1.2',
    'quit',
    'quit',
]

AC2 = wlan_common() + [
    'ac protect enable',
    'ac protect priority 5',
    'ac protect protect-ac 10.1.1.1',
    'ap-id 1 ap-mac 00e0-fc1b-3720',
    'ap-name AP1',
    'ap-group default',
    'ac-list 10.1.1.1',
    'quit',
    'ap-id 2 ap-mac 00e0-fcdb-0400',
    'ap-name AP2',
    'ap-group default',
    'ac-list 10.1.1.1',
    'quit',
    'ap-id 3 ap-mac 00e0-fcf8-32e0',
    'ap-name AP3',
    'ap-group default',
    'ac-list 10.1.1.1',
    'quit',
    'quit',
]

if __name__ == '__main__':
    e1 = apply('AC1', 2004, AC1)
    e2 = apply('AC2', 2005, AC2)
    print('\n===== 错误汇总 =====')
    for d, e in [('AC1', e1), ('AC2', e2)]:
        if e:
            print(f'{d}: {len(e)} 错误')
            for cmd, m in e:
                print(f'  - {cmd} :: {m}')
        else:
            print(f'{d}: 无 Error')
