# -*- coding: utf-8 -*-
"""修复：把 AC1/AC2 上联口 GE0/0/1 划入 VLAN 10，使 Vlanif10 变 up。"""
import sys, os
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
from mcpensp1.connection import TelnetConnection

def fix(name, port):
    print(f'\n===== {name} (:{port}) =====')
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    c.send_cmd('system-view')
    for cmd in ['interface GigabitEthernet0/0/1', 'port link-type access', 'port default vlan 10', 'quit', 'return']:
        r = c.send_cmd(cmd)
        if 'Error' in r and 'already' not in r:
            print(f'  [ERR] {cmd}: {r.strip()[-160:]}')
    c.close()

fix('AC1', 2004)
fix('AC2', 2005)
print('\nAC 上联口修复完成。')
