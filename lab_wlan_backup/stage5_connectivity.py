# -*- coding: utf-8 -*-
"""Stage 5: full connectivity (全网通). Ping across VLANs from the routers/switch
which have CLIs: STA1(192.168.10.100) / STA2(192.168.20.100) / STA3(wireless DHCP).
Also pings between router gateways to confirm OSPF backbone.
"""
import sys, re, time
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import cfg, show, save_log

# discover STA3 wireless IP from AC1/AC2 station table
sta3_ip = None
for dev in ['AC1','AC2']:
    for c,o in show(dev, ['display station all']):
        m = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+\d+\s+\S+\s+\S+\s+\S+\s+([0-9A-Fa-f:]{17})', o)
        # simpler: grab first 192.168.40.x
        mm = re.findall(r'192\.168\.40\.\d+', o)
        if mm:
            sta3_ip = mm[0]; break
    if sta3_ip: break
print(f"STA3 wireless IP discovered: {sta3_ip}")

def ping(src, ip):
    res=[]
    for c,o in show(src, [f'ping -c 3 {ip}']):
        ok = 'Success' if '5 packet(s) received' in o or '100%' not in o and 'received' in o else ('FAIL' if '0 packet' in o or '100% packet loss' in o else '?')
        # count received
        mrec = re.search(r'(\d+) packet', o)
        res.append((ip, 'OK' if ('5 packet(s) transmitted' in o and '0 packet(s) received' not in o) else 'FAIL', o.split('\n')[-3:]))
    return res

log=[f"STA3 wireless IP = {sta3_ip}"]
targets = {'STA1': '192.168.10.100', 'STA2': '192.168.20.100'}
if sta3_ip: targets['STA3'] = sta3_ip

tests = [
    ('AR1', ['192.168.20.100','192.168.40.254'] + ([sta3_ip] if sta3_ip else [])),
    ('AR2', ['192.168.10.100','192.168.40.254'] + ([sta3_ip] if sta3_ip else [])),
    ('LSW1', ['192.168.10.100','192.168.20.100'] + ([sta3_ip] if sta3_ip else [])),
    ('AR3', ['192.168.10.100','192.168.20.100'] + ([sta3_ip] if sta3_ip else [])),
]
for src, ips in tests:
    for ip in ips:
        for c,o in show(src, [f'ping -c 3 {ip}']):
            transmitted = '5 packet(s) transmitted' in o
            received0 = '0 packet(s) received' in o
            status = 'OK' if (transmitted and not received0) else 'FAIL'
            log.append(f"[{src}] ping {ip} -> {status}")
            print(f"[{src}] ping {ip} -> {status}")
        time.sleep(0.5)

text="\n".join(log)
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/connectivity.txt', text)
print("\n[saved] logs/connectivity.txt")
