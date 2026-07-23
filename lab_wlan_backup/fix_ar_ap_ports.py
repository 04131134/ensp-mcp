import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

def cfg_ar(name, port, cmds):
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    for cmd in cmds:
        c.sock.send((cmd+'\r\n').encode()); time.sleep(0.6)
        c.sock.settimeout(2)
        try:
            d=c.sock.recv(4096)
            print(f'[{name}] {cmd} -> {d.decode(errors="replace")[-160:].strip()}')
        except Exception as e:
            print(f'[{name}] {cmd} -> (timeout)')
    c.close()

# AR1: AP1 port Eth0/0/0 -> trunk pvid 10, allow 10 20 30 40
print('===== AR1 fix =====')
cfg_ar('AR1', 2000, [
    'system-view',
    'interface Ethernet0/0/0',
    'undo port default vlan',
    'port link-type trunk',
    'port trunk pvid vlan 10',
    'port trunk allow-pass vlan 10 20 30 40',
    'return',
])

# AR2: AP2 port Eth0/0/0 -> trunk pvid 10, allow 10 20 30 40
print('\n===== AR2 fix =====')
cfg_ar('AR2', 2001, [
    'system-view',
    'interface Ethernet0/0/0',
    'undo port default vlan',
    'port trunk pvid vlan 10',
    'port trunk allow-pass vlan 10 20 30 40',
    'return',
])

print('\nWaiting 90s for AP1/AP2 to obtain VLAN10 IP and register...')
time.sleep(90)

for name, port in [('AR1',2000),('AR2',2001)]:
    print(f'\n===== {name} AP port + DHCP check =====')
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    for s in ['display current-configuration interface Ethernet0/0/0', 'display ip interface brief']:
        c.sock.send((s+'\r\n').encode()); time.sleep(1.2)
        c.sock.settimeout(3); buf=b''
        try:
            while True:
                d=c.sock.recv(8192)
                if not d: break
                buf+=d
                if b'---- More ----' in buf: c.sock.send(b' '); buf=buf.replace(b'---- More ----',b'')
                if buf.rstrip().endswith(b'>'): break
        except: pass
        print(f'\n--- {s} ---')
        print(buf.decode(errors='replace')[-1400:])
    c.close()

for ac, p in [('AC1',2004),('AC2',2005)]:
    print(f'\n===== {ac} AP registration =====')
    c = TelnetConnection('127.0.0.1', p); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    c.sock.send(b'display ap all\r\n'); time.sleep(3)
    c.sock.settimeout(3); buf=b''
    try:
        while True:
            d=c.sock.recv(8192)
            if not d: break
            buf+=d
            if buf.rstrip().endswith(b'>'): break
    except: pass
    print(buf.decode(errors='replace')[-1400:])
    c.close()
