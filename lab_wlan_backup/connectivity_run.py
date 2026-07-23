# -*- coding: utf-8 -*-
"""全网通 test: ping across all subnets from CLI-capable devices.
Sources: AR1, AR2, AR3, AC1, AC2 (LSW1 console wedged -> skipped).
Targets cover: mgmt 10.1.1.0/24, wired STA 192.168.10/20.0/24, wireless gw 192.168.40.0/24.
Parse: OK if 'Reply from' present (packet received)."""
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

def ping(s, ip, w=10.0):
    s.settimeout(10); s.send(('ping -c 3 %s\r\n' % ip).encode())
    buf = b''; end = time.time() + w; s.settimeout(0.5)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    o = buf.decode('gbk', errors='ignore')
    ok = 'Reply from' in o
    # extract summary line
    m = re.findall(r'(\d+) packet\(s\) (transmitted|received)', o)
    summ = ' '.join('%s%s' % (n, t[0]) for n, t in m)
    return ok, summ

TESTS = [
    ('AR1', ['10.1.1.1','10.1.1.2','10.1.1.3','10.1.1.254','192.168.20.1','192.168.20.100','192.168.40.254','192.168.10.100']),
    ('AR2', ['10.1.1.1','10.1.1.2','10.1.1.3','10.1.1.254','192.168.10.1','192.168.10.100','192.168.40.254','192.168.20.100']),
    ('AR3', ['10.1.1.1','10.1.1.2','10.1.1.11','10.1.1.12','10.1.1.254','192.168.10.1','192.168.20.1','192.168.40.254']),
    ('AC1', ['10.1.1.2','10.1.1.3','10.1.1.254','192.168.10.1','192.168.20.1','192.168.40.254']),
    ('AC2', ['10.1.1.1','10.1.1.3','10.1.1.254','192.168.10.1','192.168.20.1','192.168.40.254']),
]

results = []
for src, targets in TESTS:
    s = connect(src)
    print("\n=== %s ===" % src, flush=True)
    for ip in targets:
        ok, summ = ping(s, ip)
        tag = 'OK ' if ok else 'FAIL'
        results.append((src, ip, ok))
        print("  %-15s -> %s  %s" % (ip, tag, summ), flush=True)
        time.sleep(0.3)
    s.close()

# summary
total = len(results); passed = sum(1 for _,_,ok in results)
print("\n##### SUMMARY: %d/%d reachable #####" % (passed, total), flush=True)
text = "全网通连通性测试结果 (%d/%d 可达)\n" % (passed, total)
for src, ip, ok in results:
    text += "%-5s -> %-15s %s\n" % (src, ip, 'OK' if ok else 'FAIL')
save_log('E:/eNSP-MCP/lab_wlan_backup/logs/connectivity.txt', text)
print("\n[saved] logs/connectivity.txt\n[DONE]", flush=True)
