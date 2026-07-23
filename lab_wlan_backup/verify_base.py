# -*- coding: utf-8 -*-
"""只读核验基础连通性是否真正生效。"""
import sys, os
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
from mcpensp1.connection import TelnetConnection

def sess(port):
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    return c

def show(c, cmd):
    return c.send_cmd(cmd)

def dump(name, port, cmds):
    print('\n' + '='*60)
    print(f'{name} (:{port})')
    print('='*60)
    c = sess(port)
    for cmd in cmds:
        r = show(c, cmd)
        print(f'\n--- {cmd} ---')
        print(r.rstrip())
    c.close()

dump('LSW1', 2003, ['display ip interface brief', 'display port vlan', 'display ip pool name ap-mgmt'])
dump('AR1', 2000, ['display port vlan', 'display current-configuration | include Ethernet0/0/0'])
dump('AC1', 2004, ['display ip interface brief', 'display capwap configuration'])
dump('AP1', 2006, ['display ip interface brief', 'display capwap link'])
