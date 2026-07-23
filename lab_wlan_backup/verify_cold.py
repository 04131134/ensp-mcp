# -*- coding: utf-8 -*-
"""实验一验证：冷备初始状态
- AC1: display ap all 应看到 AP1/2/3 normal
- AC2: display ap all 应为空(冷备不配 ap-id)
- 两边 display station all
结果写入 logs/cold_verify.txt 并打印。
"""
import sys, os
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
from mcpensp1.connection import TelnetConnection

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG, exist_ok=True)

def grab(port, cmds):
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    out = []
    for cmd in cmds:
        out.append(f'--- {cmd} ---\n' + c.send_cmd(cmd).rstrip())
    c.close()
    return '\n'.join(out)

ac1 = grab(2004, ['display ap all', 'display station all', 'display capwap link'])
ac2 = grab(2005, ['display ap all', 'display station all'])
txt = '===== AC1 (主) =====\n' + ac1 + '\n\n===== AC2 (备) =====\n' + ac2 + '\n'
open(os.path.join(LOG, 'cold_verify.txt'), 'w', encoding='utf-8').write(txt)
print(txt)
