# -*- coding: utf-8 -*-
"""根治 AC2 射频起不来: 根因 = AC2 上 type-id 56 被映射成 AP6050DN,
而物理 AP 是 AP3030DN(本机 type-id 45=AP3030DN)。类型不匹配 -> 射频模板对不上 -> idle。
AC2 不支持 undo ap-id, 故清空配置重启到出厂, 再用 type-id 45 重建。
注意: reboot 的保存提示用裸 socket 回答 n (不保存旧配置), 否则旧 ap-id 会回来。
"""
import sys, os, time, socket
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
AC2 = 2005

def raw_reboot_to_factory():
    s = socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', AC2)); time.sleep(1.5)
    def read():
        data=b''; s.settimeout(1.0)
        try:
            while True:
                d=s.recv(65536)
                if not d: break
                data+=d
        except Exception: pass
        return data
    read(); time.sleep(0.5)
    s.send(b'\r\n'); time.sleep(0.6); read(); time.sleep(0.5)
    # 清空启动配置
    s.send(b'reset saved-configuration\r\n'); time.sleep(1.2); r=read()
    if b'Y/N' in r or b'[Y/N]' in r: s.send(b'y\r\n'); time.sleep(1.0); read()
    # 重启 (保存提示答 n, 继续提示答 y)
    s.send(b'reboot\r\n'); time.sleep(1.2); r=read()
    for _ in range(6):
        if b'Y/N' in r or b'[Y/N]' in r:
            if b'save' in r.lower(): s.send(b'n\r\n')
            else: s.send(b'y\r\n')
            time.sleep(1.2); r=read()
        else:
            break
    s.close()
    print('AC2 已重置并重启到出厂')

def cfg(port, cmds, pre=None, delay=0.8):
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

def wait_connect(port, tries=30):
    for i in range(tries):
        try:
            c = TelnetConnection('127.0.0.1', port); c.connect(); c.close(); return True
        except Exception:
            time.sleep(5)
    return False

# 1) 重置并重启
raw_reboot_to_factory()
print('等待 130s 让 AC2 出厂启动 ...')
time.sleep(130)
print('等待 AC2 控制台可连 ...')
wait_connect(AC2, 30)

# 2) 重建基础连通性 (AC2)
print('== 重建 AC2 基础配置 ==')
cfg(AC2, [
    'vlan 10', 'quit',
    'interface Vlanif10', 'ip address 10.1.1.2 24', 'quit',
    'interface GigabitEthernet0/0/1', 'port link-type access', 'port default vlan 10', 'quit',
    'capwap source interface Vlanif10',
], pre=['system-view'])

# 3) 重建 WLAN (type-id 45 = AP3030DN)
print('== 重建 AC2 WLAN (type-id 45) ==')
cfg(AC2, [
    'wlan',
    'ssid-profile name office','ssid Office-Cold','quit',
    'security-profile name sec1','security wpa-wpa2 psk pass-phrase Huawei@123 aes','quit',
    'vap-profile name vap1','service-vlan vlan-id 10','ssid-profile office','security-profile sec1','quit',
    'regulatory-domain-profile name domain1','country-code cn','quit',
    'ap-group name default','regulatory-domain-profile domain1',
    'radio 0','vap-profile vap1 wlan 1','quit',
    'radio 1','vap-profile vap1 wlan 1','quit','quit',
    'ap auth-mode no-auth',
    'ap-id 1 type-id 45 ap-mac 00e0-fc1b-3720','ap-name AP1','ap-group default','quit',
    'ap-id 2 type-id 45 ap-mac 00e0-fcdb-0400','ap-name AP2','ap-group default','quit',
    'ap-id 3 type-id 45 ap-mac 00e0-fcf8-32e0','ap-name AP3','ap-group default','quit',
    'provision-ap','quit',
], pre=['system-view'])

print('等待 70s 让 AP 注册 + 射频起来 ...')
time.sleep(70)
txt = 'AC2 用 type-id 45 重建后核查\n' + grab(AC2, ['display ap all','display radio all','display ap-type all | include 45'])
open(os.path.join(LOG,'cold_ac2_type45.txt'),'w',encoding='utf-8').write(txt)
print(txt)
