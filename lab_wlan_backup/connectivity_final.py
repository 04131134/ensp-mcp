import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

# Targets: management VLAN10 + each STA subnet gateway
TARGETS = {
    'AC1(V10)': '10.1.1.1',
    'AC2(V10)': '10.1.1.2',
    'AR1(V10)': '10.1.1.11',
    'AR2(V10)': '10.1.1.12',
    'AR3(V10)': '10.1.1.3',
    'STA1gw': '192.168.10.1',
    'STA2gw': '192.168.20.1',
    'STA3gw': '192.168.40.1',
}
# Sources: device -> port
SOURCES = [('AR1',2000),('AR2',2001),('AR3',2002),('AC1',2004),('AC2',2005),('LSW1',2003)]

def ping(src_name, src_port, target_ip):
    c = TelnetConnection('127.0.0.1', src_port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.6)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    c.sock.send(('ping -c 5 -a ' + target_ip + '\r\n').encode()); time.sleep(6)
    c.sock.settimeout(6); buf=b''
    try:
        while True:
            d=c.sock.recv(16384)
            if not d: break
            buf+=d
            if b'---- More ----' in buf: c.sock.send(b' '); buf=buf.replace(b'---- More ----',b'')
            # stop when prompt returns (after ping stats)
            if b'packet(s) received' in buf: break
            if buf.rstrip().endswith(b'>'): break
    except: pass
    c.close()
    txt = buf.decode(errors='replace')
    received = txt.count('Reply from')
    return received, txt

print('CONNECTIVITY MATRIX (rows=source, cols=target). Value = Reply-from count /5\n')
header = 'SRC\\TGT'.ljust(8) + ''.join(t[:7].rjust(9) for t in TARGETS)
print(header)
results = {}
for sname, sport in SOURCES:
    row = sname.ljust(8)
    results[sname] = {}
    for tname, tip in TARGETS.items():
        if sname.startswith(tname.split('(')[0]) and TARGETS[tname]==tip:
            # skip self-ping of own interface? still fine
            pass
        try:
            rcv, _ = ping(sname, sport, tip)
        except Exception as e:
            rcv = -1
        results[sname][tname] = rcv
        row += str(rcv).rjust(9)
    print(row)
    time.sleep(0.3)

# Save
import os
os.makedirs('logs', exist_ok=True)
with open('logs/connectivity_final.txt','w',encoding='utf-8') as f:
    f.write(header+'\n')
    for sname,_ in SOURCES:
        f.write(sname.ljust(8)+''.join(str(results[sname][t]).rjust(9) for t in TARGETS)+'\n')
print('\nSaved logs/connectivity_final.txt')
