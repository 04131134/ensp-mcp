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
            d=c.sock.recv(8192); print(f'[{label}] {cmd} -> {d.decode(errors="replace")[-80:].strip()}')
        except: print(f'[{label}] {cmd} -> (timeout)')
    c.close()

# AR1: STA1 subnet 192.168.10.0/24, gateway Vlanif20
print('===== AR1 DHCP for STA1 =====')
cfg(2000, [
    'system-view','dhcp enable',
    'ip pool sta1','gateway-list 192.168.10.1','network 192.168.10.0 mask 255.255.255.0',
    'interface Vlanif20','dhcp select global','return',
], 'AR1')

# AR2: STA2 subnet 192.168.20.0/24, gateway Vlanif30
print('\n===== AR2 DHCP for STA2 =====')
cfg(2001, [
    'system-view','dhcp enable',
    'ip pool sta2','gateway-list 192.168.20.1','network 192.168.20.0 mask 255.255.255.0',
    'interface Vlanif30','dhcp select global','return',
], 'AR2')

# AR3: STA3 subnet 192.168.40.0/24, gateway Vlanif40
print('\n===== AR3 DHCP for STA3 =====')
cfg(2002, [
    'system-view','dhcp enable',
    'ip pool sta3','gateway-list 192.168.40.1','network 192.168.40.0 mask 255.255.255.0',
    'interface Vlanif40','dhcp select global','return',
], 'AR3')

print('\n===== Verify pools =====')
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
    print(f'--- {name} ---')
    print(buf.decode(errors='replace')[-600:])
    c.close()
