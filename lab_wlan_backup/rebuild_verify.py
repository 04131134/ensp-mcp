# -*- coding: utf-8 -*-
"""Verify AP registration + encrypted WLAN state on AC1 (read-only)."""
import sys, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import show, save_log

out = []
out.append("===== AC1 display ap all =====")
for cmd,o in show('AC1', ['display ap all']):
    out.append(o)
out.append("\n===== AC1 display radio all =====")
for cmd,o in show('AC1', ['display radio all']):
    out.append(o)
out.append("\n===== AC1 display vap (SSID/security/status) =====")
for cmd,o in show('AC1', ['display vap']):
    out.append(o)
out.append("\n===== AC1 security-profile sec1 =====")
for cmd,o in show('AC1', ['display security-profile name sec1']):
    out.append(o)
out.append("\n===== AC1 ssid-profile office =====")
for cmd,o in show('AC1', ['display ssid-profile name office']):
    out.append(o)
out.append("\n===== LSW1 AP DHCP used =====")
for cmd,o in show('LSW1', ['display ip pool name vlan10 used']):
    out.append(o)

text = "\n".join(out)
print(text, flush=True)
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/rebuild_ac1_verify.txt', text)
print("\n[saved] logs/rebuild_ac1_verify.txt", flush=True)
