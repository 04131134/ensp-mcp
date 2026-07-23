# -*- coding: utf-8 -*-
"""Per-device underlay status check (independent connection each, real-time print)."""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

PORTS = {
    'LSW1': 2003, 'AR1': 2000, 'AR2': 2001, 'AR3': 2002,
}

def check(name):
    port = PORTS[name]
    try:
        c = TelnetConnection('127.0.0.1', port)
        c.connect()
        c.send_cmd('screen-length 0 temporary'); time.sleep(0.3)
        out = []
        out.append(f"\n##### {name} #####")
        for cmd in ['display vlan summary', 'display ip interface brief',
                    'display current-configuration | include trunk|vlan|dhcp|ospf|ip address|ip pool']:
            o = c.send_cmd(cmd)
            out.append(f"--- {name} {cmd} ---\n{o[:1500]}")
        c.close()
        return "\n".join(out)
    except Exception as e:
        return f"\n##### {name} ERROR: {e}"

for n in PORTS:
    print(check(n), flush=True)
print("\n[CHECK DONE]", flush=True)
