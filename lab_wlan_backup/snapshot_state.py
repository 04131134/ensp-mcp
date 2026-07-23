# -*- coding: utf-8 -*-
"""只读快照 v2：用项目自带 connection.TelnetConnection（提示符驱动/自动翻页）抓取设备状态。"""
import sys, os, time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
from mcpensp1.connection import TelnetConnection

PORTS = {
    'AR1': 2000,
    'AR2': 2001,
    'AR3': 2002,
    'LSW1': 2003,
    'AC1': 2004,
    'AC2': 2005,
}

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state')
os.makedirs(STATE_DIR, exist_ok=True)

def main():
    for name, port in PORTS.items():
        print(f'=== 快照 {name} (port {port}) ===')
        c = TelnetConnection('127.0.0.1', port)
        c.connect()
        # 关掉干扰输出
        c.send_cmd('screen-length 0 temporary')
        parts = []
        parts.append('===== display current-configuration =====')
        parts.append(c.send_cmd('display current-configuration'))
        parts.append('\n===== display interface brief =====')
        parts.append(c.send_cmd('display interface brief'))
        parts.append('\n===== display ip interface brief =====')
        parts.append(c.send_cmd('display ip interface brief'))
        parts.append('\n===== display vlan summary =====')
        parts.append(c.send_cmd('display vlan summary'))
        if name in ('AC1', 'AC2'):
            parts.append('\n===== display ap all =====')
            parts.append(c.send_cmd('display ap all'))
            parts.append('\n===== display ac protect =====')
            parts.append(c.send_cmd('display ac protect'))
            parts.append('\n===== display capwap link =====')
            parts.append(c.send_cmd('display capwap link'))
        out = '\n'.join(parts)
        path = os.path.join(STATE_DIR, f'{name}.txt')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'  保存 {len(out)} 字符 -> {path}')
        c.close()
    print('全部快照完成。')

if __name__ == '__main__':
    main()
