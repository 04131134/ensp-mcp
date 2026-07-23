# -*- coding: utf-8 -*-
"""实验一：AC 双机冷备（AC6005 正确语法）
- AC1(主): 全套 WLAN 业务模板 + ap-id(AP1/2/3 真实MAC)  -> AP 在此注册
- AC2(备): 仅业务模板, 不配 ap-id, 默认 mac-auth          -> 冷备关键(拒绝 AP)
SSID = Office-Cold
AP MAC / type-id 56 (AP3030DN):
  AP1 00e0-fc1b-3720
  AP2 00e0-fcdb-0400
  AP3 00e0-fcf8-32e0
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
        time.sleep(0.6)
        if 'Error:' in r and not any(k in r for k in ('already', 'not found', 'does not exist', 'unrecognized')):
            # 仅记录真正的意外错误
            if 'Error:' in r:
                errs.append((cmd, r.strip()[-180:]))
                print(f'  [ERR] {cmd}: {r.strip()[-160:]}')
    c.send_cmd('return')
    c.close()
    return errs

# 先清理上一轮可能残缺的 wlan 配置
RESET = [
    'wlan',
    'undo ap-id 1',
    'undo ap-id 2',
    'undo ap-id 3',
    'ap-group name default',
    'radio 0',
    'undo vap-profile',
    'quit',
    'radio 1',
    'undo vap-profile',
    'quit',
    'quit',
    'undo security-profile name sec1',
    'undo ssid-profile name office',
    'undo vap-profile name vap1',
    'quit',
]

# AC1 主：业务模板 + ap-id + no-auth(确保 AP 注册) + provision
AC1 = [
    'wlan',
    'ssid-profile name office',
    'ssid Office-Cold',
    'quit',
    'security-profile name sec1',
    'security wpa-wpa2 psk pass-phrase Huawei@123 aes',
    'quit',
    'vap-profile name vap1',
    'service-vlan vlan-id 10',
    'ssid-profile office',
    'security-profile sec1',
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
    'ap auth-mode no-auth',
    'ap-id 1 type-id 56 ap-mac 00e0-fc1b-3720',
    'ap-name AP1',
    'ap-group default',
    'quit',
    'ap-id 2 type-id 56 ap-mac 00e0-fcdb-0400',
    'ap-name AP2',
    'ap-group default',
    'quit',
    'ap-id 3 type-id 56 ap-mac 00e0-fcf8-32e0',
    'ap-name AP3',
    'ap-group default',
    'quit',
    'provision-ap',
    'quit',
]

# AC2 备：仅业务模板, 不配 ap-id (默认 mac-auth 拒绝 AP)
AC2 = [
    'wlan',
    'ssid-profile name office',
    'ssid Office-Cold',
    'quit',
    'security-profile name sec1',
    'security wpa-wpa2 psk pass-phrase Huawei@123 aes',
    'quit',
    'vap-profile name vap1',
    'service-vlan vlan-id 10',
    'ssid-profile office',
    'security-profile sec1',
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

if __name__ == '__main__':
    for dev, port, cmds in [('AC1', 2004, RESET + AC1), ('AC2', 2005, RESET + AC2)]:
        e = apply(dev, port, cmds)
        print(f'{dev}: {"无意外错误" if not e else str(len(e))+" 个错误"}')
        for cmd, m in e:
            print(f'  - {cmd} :: {m}')
