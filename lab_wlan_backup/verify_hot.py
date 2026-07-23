# -*- coding: utf-8 -*-
"""实验二验证：热备初始状态(只读)
- AC1/AC2: display ap all (应看到 AP 通过双 CAPWAP 隧道注册, Run/Standby)
- AC1/AC2: display ac-protect (角色 Active/Standby + 对端IP + 优先级)
- 两边 display station all
结果写入 logs/hot_verify.txt 并打印。
"""
import sys, os, time
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
from mcpensp1.connection import TelnetConnection

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG, exist_ok=True)

def grab(port, cmds):
    c = TelnetConnection('127.0.0.1', port)
    c.connect(); c.send_cmd('screen-length 0 temporary')
    out=[]
    for cmd in cmds:
        out.append(f'--- {cmd} ---\n'+c.send_cmd(cmd).rstrip()); time.sleep(0.6)
    c.close(); return '\n'.join(out)

ac1 = grab(2004, ['display ap all','display ac-protect','display station all'])
ac2 = grab(2005, ['display ap all','display ac-protect','display station all'])
txt = '===== AC1 (主) =====\n'+ac1+'\n\n===== AC2 (备) =====\n'+ac2+'\n'
open(os.path.join(LOG,'hot_verify.txt'),'w',encoding='utf-8').write(txt)
print(txt)
