# -*- coding: utf-8 -*-
"""Shared helpers for the WLAN AC dual-backup experiment.
Reliable block-command sender over eNSP telnet (uses project TelnetConnection).
"""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

PORTS = {
    'AR1': 2000, 'AR2': 2001, 'AR3': 2002, 'LSW1': 2003,
    'AC1': 2004, 'AC2': 2005, 'AP1': 2006, 'AP2': 2007, 'AP3': 2008,
}

def cfg(name, cmds, delay=0.45, verbose=True):
    """Send a block of config/exec commands to device <name>; return list of (cmd, output)."""
    port = PORTS[name]
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    time.sleep(0.3)
    results = []
    for cmd in cmds:
        if cmd.strip() == '':
            continue
        out = c.send_cmd(cmd)
        time.sleep(delay)
        results.append((cmd, out))
        if verbose:
            print(f"[{name}] $ {cmd}")
    c.close()
    return results

def show(name, cmds, delay=0.6):
    """Read-only probe; prints outputs."""
    port = PORTS[name]
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    time.sleep(0.3)
    out = []
    for cmd in cmds:
        o = c.send_cmd(cmd)
        time.sleep(delay)
        out.append((cmd, o))
    c.close()
    return out

def save_log(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
