# -*- coding: utf-8 -*-
"""Recon: probe every device after a config wipe. Reports online/alive,
whether it is at factory default (sysname Huawei / no custom sysname),
and whether it is hung (only returns '#')."""
import sys, time, re
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection
from concurrent.futures import ThreadPoolExecutor

PORTS = {
    'AR1': 2000, 'AR2': 2001, 'AR3': 2002, 'LSW1': 2003,
    'AC1': 2004, 'AC2': 2005, 'AP1': 2006, 'AP2': 2007, 'AP3': 2008,
}

def probe(name):
    port = PORTS[name]
    try:
        c = TelnetConnection('127.0.0.1', port)
        c.connect()
        c.send_cmd('screen-length 0 temporary')
        time.sleep(0.2)
        out = c.send_cmd('display current-configuration | include sysname')
        c.close()
        o = out
        has_prompt = (('<' in o) or ('[' in o))
        names = re.findall(r'sysname\s+(\S+)', o)
        stripped = o.strip()
        dead = (not has_prompt) or (stripped in ('#', '# ', ''))
        return name, {
            'alive': bool(has_prompt) and not dead,
            'sysnames': names,
            'tail': stripped[-160:],
        }
    except Exception as e:
        return name, {'alive': False, 'error': str(e)[:120]}

results = {}
with ThreadPoolExecutor(max_workers=9) as ex:
    for name, r in ex.map(probe, PORTS.keys()):
        results[name] = r

print('=== RECON RESULT ===')
for name in PORTS:
    r = results[name]
    print(f"{name:5s} alive={str(r.get('alive')):5s} sysnames={r.get('sysnames')} "
          f"err={r.get('error','')}")
    if r.get('tail'):
        print(f"        tail: {r['tail']!r}")
print('=== END ===')
