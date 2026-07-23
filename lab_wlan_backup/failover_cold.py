# -*- coding: utf-8 -*-
"""实验一 故障模拟 + 冷备手动切换（CLI 全驱动）
流程:
  1) 基线快照 (AC1 有 3 AP normal, AC2 空)
  2) 模拟 AC1 宕机: shutdown AC1 Vlanif10 (CAPWAP 源消失)
  3) 等待 -> 验证 AC1 AP 故障 / AC2 仍空 (业务中断)
  4) 冷备手动切换: 在 AC2 添加 ap-id(真实MAC)+provision-ap
  5) 等待 -> 验证 AP 重新注册到 AC2 (AC1 仍故障)
日志写入 logs/cold_failover.txt
"""
import sys, os, time
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
from mcpensp1.connection import TelnetConnection

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG, exist_ok=True)
OUT = os.path.join(LOG, 'cold_failover.txt')

def send(port, cmds, pre=None):
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    if pre:
        for x in pre:
            c.send_cmd(x)
    for cmd in cmds:
        if cmd.strip():
            c.send_cmd(cmd)
            time.sleep(0.7)
    c.close()

def grab(port, cmds):
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    out = []
    for cmd in cmds:
        out.append(f'--- {cmd} ---\n' + c.send_cmd(cmd).rstrip())
        time.sleep(0.5)
    c.close()
    return '\n'.join(out)

def section(title):
    return '\n' + '=' * 22 + ' ' + title + ' ' + '=' * 22 + '\n'

buf = []
t0 = time.strftime('%Y-%m-%d %H:%M:%S')

# ---- 1. 基线快照 ----
buf.append(section('T0 冷备基线 (AC1 主/AC2 备)') )
buf.append(grab(2004, ['display ap all']))
buf.append(grab(2005, ['display ap all']))

# ---- 2. 模拟 AC1 宕机 ----
buf.append(section('T1 模拟 AC1 故障: shutdown Vlanif10') )
send(2004, ['interface Vlanif10', 'shutdown'], pre=['system-view'])
buf.append('已对 AC1 执行: interface Vlanif10 -> shutdown\n')

# ---- 3. 等待 + 验证中断 ----
buf.append(section('T2 等待 50s (AP 探测隧道断开)') )
time.sleep(50)
buf.append(grab(2004, ['display ap all']))
buf.append(grab(2005, ['display ap all']))

# ---- 4. 冷备手动切换: AC2 接管 ----
buf.append(section('T3 冷备手动切换: 在 AC2 添加 ap-id 并 provision') )
send(2005, [
    'wlan',
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
], pre=['system-view'])
buf.append('已在 AC2 下发 ap-id 1/2/3 + provision-ap\n')

# ---- 5. 等待 + 验证接管 ----
buf.append(section('T4 等待 55s (AP 重新注册到 AC2)') )
time.sleep(55)
buf.append(grab(2004, ['display ap all']))
buf.append(grab(2005, ['display ap all']))

txt = ('WLAN AC 双机冷备 — 故障切换日志\n生成时间: %s\n' % t0) + ''.join(buf)
open(OUT, 'w', encoding='utf-8').write(txt)
print(txt)
