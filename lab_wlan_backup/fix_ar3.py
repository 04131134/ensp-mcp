import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

def cfg(port, cmds, label):
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    for cmd in cmds:
        c.sock.send((cmd+'\r\n').encode()); time.sleep(0.7)
        c.sock.settimeout(3)
        try:
            d=c.sock.recv(8192); print(f'[{label}] {cmd} -> {d.decode(errors="replace")[-90:].strip()}')
        except: print(f'[{label}] {cmd} -> (timeout)')
    c.close()

print('===== Fix AR3: add Vlanif40 + OSPF + DHCP pool =====')
cfg(2002, [
    'system-view',
    'interface Vlanif40',
    'ip address 192.168.40.1 255.255.255.0',
    'dhcp select global',
    'ospf 1',
    'area 0.0.0.0',
    'network 192.168.40.0 0.0.0.255',
    'return',
    'ip pool sta3',
    'gateway-list 192.168.40.1',
    'network 192.168.40.0 mask 255.255.255.0',
    'return',
], 'AR3')

print('\n===== Verify AR1/AR2/AR3 DHCP pools + OSPF =====')
for name,port in [('AR1',2000),('AR2',2001),('AR3',2002)]:
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    c.sock.send(b'display ip pool\n'); time.sleep(1.5)
    c.sock.settimeout(3); buf=b''
    try:
        while True:
            d=c.sock.recv(8192)
            if not d: break
            buf+=d
            if b'---- More ----' in buf: c.sock.send(b' '); buf=buf.replace(b'---- More ----',b'')
            if buf.rstrip().endswith(b'>'): break
    except: pass
    print(f'\n--- {name} display ip pool ---')
    print(buf.decode(errors='replace')[-900:])
    c.close()

print('\nWaiting 15s for OSPF convergence...')
time.sleep(15)

# Re-test the previously-failing target
c = TelnetConnection('127.0.0.1', 2000); c.connect()
c.send_cmd('screen-length 0 temporary'); time.sleep(0.3)
for tip in ['192.168.40.1','192.168.20.1','10.1.1.1']:
    o=c.send_cmd('ping -c 3 '+tip)
    rcv=o.count('Reply from')
    print(f'AR1 -> {tip}: Reply={rcv}')
c.close()
