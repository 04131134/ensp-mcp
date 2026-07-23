# -*- coding: utf-8 -*-
"""实验二故障模拟 + 自动切换 + 恢复(HSB)
前置: apply_hot 已配置双机热备; AC1 Vlanif10 应处于 up。
流程:
  0) 安全: 确保 AC1 Vlanif10 up (若被冷备测试 shutdown 过则恢复)
  1) 基线: AC1/AC2 display ac-protect + display ap all (应 Active/Standby, AP 双隧道)
  2) 模拟 AC1 故障: shutdown AC1 Vlanif10
  3) 等待 -> AC2 自动升 Active, APs 在 AC2 保持 normal (业务不中断)
  4) 恢复 AC1: undo shutdown Vlanif10
  5) 等待 -> AC1 回 Standby(不抢占), AC2 保持 Active, APs 仍 normal
日志写入 logs/hot_failover.txt
"""
import sys, os, time
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
from mcpensp1.connection import TelnetConnection

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG, exist_ok=True)

def send(port, cmds, pre=None, delay=0.8):
    c = TelnetConnection('127.0.0.1', port)
    c.connect(); c.send_cmd('screen-length 0 temporary')
    if pre:
        for x in pre: c.send_cmd(x)
    for cmd in cmds:
        if cmd.strip(): c.send_cmd(cmd); time.sleep(delay)
    c.close()

def grab(port, cmds):
    c = TelnetConnection('127.0.0.1', port)
    c.connect(); c.send_cmd('screen-length 0 temporary')
    out=[]
    for cmd in cmds:
        out.append(f'--- {cmd} ---\n'+c.send_cmd(cmd).rstrip()); time.sleep(0.6)
    c.close(); return '\n'.join(out)

buf=[]; t0=time.strftime('%Y-%m-%d %H:%M:%S')

# 0) 安全恢复 AC1
buf.append('[0] 确保 AC1 Vlanif10 up\n')
send(2004, ['interface Vlanif10','undo shutdown'], pre=['system-view'])

# 1) 基线
buf.append('\n'+'='*20+' 基线 (HSB 正常) '+'='*20+'\n')
buf.append(grab(2004, ['display ac-protect','display ap all']))
buf.append(grab(2005, ['display ac-protect','display ap all']))

# 2) 模拟 AC1 故障
buf.append('\n'+'='*20+' 模拟 AC1 故障: shutdown Vlanif10 '+'='*20+'\n')
send(2004, ['interface Vlanif10','shutdown'], pre=['system-view'])
buf.append('已 shutdown AC1 Vlanif10\n')

# 3) 等待 + 验证自动接管
buf.append('\n'+'='*20+' 等待 35s (AC2 探测并自动接管) '+'='*20+'\n')
time.sleep(35)
buf.append(grab(2004, ['display ac-protect','display ap all']))
buf.append(grab(2005, ['display ac-protect','display ap all','display station all']))

# 4) 恢复 AC1
buf.append('\n'+'='*20+' 恢复 AC1: undo shutdown Vlanif10 '+'='*20+'\n')
send(2004, ['interface Vlanif10','undo shutdown'], pre=['system-view'])
buf.append('已 undo shutdown AC1 Vlanif10\n')

# 5) 等待 + 验证恢复(不抢占)
buf.append('\n'+'='*20+' 等待 45s (AC1 回 Standby, AC2 保持 Active) '+'='*20+'\n')
time.sleep(45)
buf.append(grab(2004, ['display ac-protect','display ap all']))
buf.append(grab(2005, ['display ac-protect','display ap all']))

txt=('WLAN AC 双机热备 — 故障切换/恢复日志\n生成时间: %s\n'%t0)+''.join(buf)
open(os.path.join(LOG,'hot_failover.txt'),'w',encoding='utf-8').write(txt)
print(txt)
