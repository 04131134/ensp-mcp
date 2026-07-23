import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

def send_block(port, cmds, label):
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    for cmd in cmds:
        c.sock.send((cmd+'\r\n').encode()); time.sleep(0.8)
        c.sock.settimeout(3)
        try:
            d=c.sock.recv(8192); txt=d.decode(errors='replace')
        except: txt='(timeout)'
        if '[Y/N]' in txt or '(Y/N)' in txt:
            c.sock.send(b'YES\r\n'); time.sleep(0.8)
            try:
                d2=c.sock.recv(8192); txt+=d2.decode(errors='replace')
            except: pass
        print(f'[{label}] {cmd} -> {txt[-90:].strip()}')
    c.close()

# HSB on AC1 (wlan view)
print('===== AC1 HSB =====')
send_block(2004, [
    'system-view','wlan',
    'ac protect enable','ac protect priority 7','ac protect protect-ac 10.1.1.2',
    'ap-id 1','ac-list 10.1.1.2','ap-id 2','ac-list 10.1.1.2','ap-id 3','ac-list 10.1.1.2',
    'return',
], 'AC1')

# HSB on AC2 (wlan view)
print('\n===== AC2 HSB =====')
send_block(2005, [
    'system-view','wlan',
    'ac protect enable','ac protect priority 5','ac protect protect-ac 10.1.1.1',
    'ap-id 1','ac-list 10.1.1.1','ap-id 2','ac-list 10.1.1.1','ap-id 3','ac-list 10.1.1.1',
    'return',
], 'AC2')

# Reboot AP1/AP2 (alive consoles) to establish dual tunnels
for name,port in [('AP1',2006),('AP2',2007)]:
    print(f'\n===== reboot {name} =====')
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    c.sock.send(b'reboot\r\n'); time.sleep(1.0)
    c.sock.settimeout(3)
    try: print(f'[{name}] reboot -> {c.sock.recv(8192).decode(errors="replace")[-120:]}')
    except: print(f'[{name}] reboot -> (timeout)')
    c.sock.send(b'Y\r\n'); time.sleep(1.0)
    try: print(f'[{name}] confirm -> {c.sock.recv(4096).decode(errors="replace")[-100:]}')
    except: pass
    c.close()

print('\nWaiting 150s for dual-tunnel negotiation...')
time.sleep(150)

for ac,p in [('AC1',2004),('AC2',2005)]:
    print(f'\n===== {ac} state =====')
    c = TelnetConnection('127.0.0.1', p); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    for s in ['display ap all','display ac protect']:
        c.sock.send((s+'\r\n').encode()); time.sleep(3)
        c.sock.settimeout(4); buf=b''
        try:
            while True:
                d=c.sock.recv(8192)
                if not d: break
                buf+=d
                if b'---- More ----' in buf: c.sock.send(b' '); buf=buf.replace(b'---- More ----',b'')
                if buf.rstrip().endswith(b'>'): break
        except: pass
        print(f'\n--- {s} ---')
        print(buf.decode(errors='replace')[-1300:])
    c.close()
