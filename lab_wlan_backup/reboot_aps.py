# -*- coding: utf-8 -*-
"""AP 控制台直连 reboot，强制清干净 CAPWAP 状态后重新发现 AC2。
端口: AP1=2006, AP2=2007, AP3=2008
AC1 Vlanif10 已 shutdown，AP 重启后广播发现只能命中 AC2(10.1.1.2)。
重启后等待 AP 重新注册 + AC2 下发射频配置，再核查 AC2 状态。
"""
import sys, os, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

def reboot_ap(port):
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    c.send_cmd('reboot')
    time.sleep(1)
    c.close()
    print(f'AP@{port}: reboot 已发送')

def grab(port, cmds):
    c = TelnetConnection('127.0.0.1', port)
    c.connect(); c.send_cmd('screen-length 0 temporary')
    out=[]
    for cmd in cmds:
        out.append(f'--- {cmd} ---\n'+c.send_cmd(cmd).rstrip()); time.sleep(0.7)
    c.close(); return '\n'.join(out)

for p in (2006, 2007, 2008):
    reboot_ap(p)

print('等待 100s 让 3 台 AP 重启并重新注册到 AC2 ...')
time.sleep(100)

txt = 'AP reboot 后 AC2 核查\n' + grab(2005, ['display ap all','display radio all'])
open(os.path.join(LOG, 'cold_ac2_after_reboot.txt'), 'w', encoding='utf-8').write(txt)
print(txt)
