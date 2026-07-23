# -*- coding: utf-8 -*-
"""Clean re-test of ambiguous connectivity targets with robust parser:
count 'X packet(s) received' > 0 => OK. ping -c 5, 15s window."""
import sys, time, socket, re
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS, save_log

def drain(s, t=0.5):
    s.settimeout(t)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass

def connect(name):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10); s.connect(('127.0.0.1', PORTS[name]))
    time.sleep(0.6); drain(s, 0.6)
    s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.6); drain(s, 0.6)
    return s

def ping(s, ip, w=16.0):
    s.settimeout(10); s.send(('ping -c 5 %s\r\n' % ip).encode())
    buf = b''; end = time.time() + w; s.settimeout(0.5)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    o = buf.decode('gbk', errors='ignore')
    m = re.search(r'(\d+)\s+packet\(s\)\s+received', o)
    recv = int(m.group(1)) if m else 0
    return recv, o.splitlines()[-2:] if o.splitlines() else [o[-80:]]

TESTS = [
    ('AR1', ['10.1.1.1','10.1.1.2','192.168.40.254','192.168.20.100']),
    ('AR2', ['10.1.1.1','10.1.1.2','192.168.40.254','192.168.10.100']),
    ('AR3', ['10.1.1.1','10.1.1.2']),
    ('AC1', ['192.168.40.254','192.168.10.100','192.168.20.100']),
    ('AC2', ['192.168.40.254','192.168.10.100','192.168.20.100']),
]

results = []
for src, targets in TESTS:
    s = connect(src)
    print("\n=== %s ===" % src, flush=True)
    for ip in targets:
        recv, last = ping(s, ip)
        ok = 'OK ' if recv > 0 else 'FAIL'
        results.append((src, ip, recv))
        print("  %-15s -> %s  (recv=%d) %s" % (ip, ok, recv, last[-1].strip() if last else ''), flush=True)
        time.sleep(0.3)
    s.close()

total = len(results); passed = sum(1 for _,_,r in results if r > 0)
print("\n##### RETEST SUMMARY: %d/%d reachable #####" % (passed, total), flush=True)
text = "全网通复测 (%d/%d 可达)\n" % (passed, total)
for src, ip, r in results:
    text += "%-5s -> %-15s recv=%d %s\n" % (src, ip, r, 'OK' if r>0 else 'FAIL')
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/connectivity_retest.txt', text)
print("\n[saved] logs/connectivity_retest.txt\n[DONE]", flush=True)
