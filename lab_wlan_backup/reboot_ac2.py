# -*- coding: utf-8 -*-
"""重启 AC2 清除卡死的 WLAN 运行时态，再重新下发冷备配置并验证。
AC2 控制台 2005。reboot 后 AP 重新发现 AC2 并注册，期望射频起来 -> normal。
"""
import sys, os, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

def send(port, cmds, pre=None, delay=0.8):
    c = TelnetConnection('127.0.0.1', port)
    c.connect(); c.send_cmd('screen-length 0 temporary')
    if pre:
        for x in pre: c.send_cmd(x)
    for cmd in cmds:
        if cmd.strip():
            c.send_cmd(cmd); time.sleep(delay)
    c.close()

def grab(port, cmds):
    c = TelnetConnection('127.0.0.1', port)
    c.connect(); c.send_cmd('screen-length 0 temporary')
    out=[]
    for cmd in cmds:
        out.append(f'--- {cmd} ---\n'+c.send_cmd(cmd).rstrip()); time.sleep(0.7)
    c.close(); return '\n'.join(out)

# 1) 重启 AC2
print('== 重启 AC2 ==')
send(2005, ['reboot'])
time.sleep(5)
print('已发送 reboot，等待 140s 让 AC2 启动 + AP 重新发现 ...')
time.sleep(140)

# 2) 重新下发冷备配置 (idempotent; 若配置丢失则补齐, 若仍在则无害)
COLD_AC2 = [
    'wlan',
    'ssid-profile name office','ssid Office-Cold','quit',
    'security-profile name sec1','security wpa-wpa2 psk pass-phrase Huawei@123 aes','quit',
    'vap-profile name vap1','service-vlan vlan-id 10','ssid-profile office','security-profile sec1','quit',
    'regulatory-domain-profile name domain1','country-code cn','quit',
    'ap-group name default','regulatory-domain-profile domain1',
    'radio 0','vap-profile vap1 wlan 1','quit',
    'radio 1','vap-profile vap1 wlan 1','quit','quit',
    'ap auth-mode no-auth',
    'ap-id 1 type-id 56 ap-mac 00e0-fc1b-3720','ap-name AP1','ap-group default','quit',
    'ap-id 2 type-id 56 ap-mac 00e0-fcdb-0400','ap-name AP2','ap-group default','quit',
    'ap-id 3 type-id 56 ap-mac 00e0-fcf8-32e0','ap-name AP3','ap-group default','quit',
    'provision-ap','quit',
]
print('== 重新下发 AC2 冷备配置 ==')
send(2005, COLD_AC2, pre=['system-view'])
print('等待 60s 让 AP 注册 + 射频起来 ...')
time.sleep(60)

txt = 'AC2 重启后重新下发配置核查\n' + grab(2005, ['display ap all','display radio all'])
open(os.path.join(LOG, 'cold_ac2_reboot_restore.txt'), 'w', encoding='utf-8').write(txt)
print(txt)
