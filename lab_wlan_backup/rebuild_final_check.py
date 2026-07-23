# -*- coding: utf-8 -*-
"""Final 4-dimension verification for the rebuilt encrypted-WLAN cold-standby lab.
Read-only. Checks:
  1) Encrypted WiFi broadcast (VAP ON + WPA/WPA2-PSK) on AC1 & AC2
  2) APs registered / dual-link backup state (display ap all + display ac protect)
  3) AP mgmt IP allocated by LSW1 (option43 -> AC1)
  4) Full-mesh connectivity (OSPF peer Full on LSW1)
"""
import sys
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import show, save_log

out = []
def section(title, dev, cmds):
    out.append(f"\n===== {title} =====")
    for cmd, o in show(dev, cmds):
        out.append(o)

section("AC1 display ap all", 'AC1', ['display ap all'])
section("AC1 display vap ap-group default", 'AC1', ['display vap ap-group default'])
section("AC1 display ac protect", 'AC1', ['display ac protect'])
section("AC1 security-profile sec1", 'AC1', ['display security-profile name sec1'])

section("AC2 display ap all", 'AC2', ['display ap all'])
section("AC2 display vap ap-group default", 'AC2', ['display vap ap-group default'])
section("AC2 display ac protect", 'AC2', ['display ac protect'])

section("LSW1 AP DHCP used (vlan10)", 'LSW1', ['display ip pool name vlan10 used'])
section("LSW1 OSPF peer (Full mesh?)", 'LSW1', ['display ospf peer brief'])

text = "\n".join(out)
print(text, flush=True)
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/rebuild_final_check.txt', text)
print("\n[saved] logs/rebuild_final_check.txt", flush=True)
