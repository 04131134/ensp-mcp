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
            d=c.sock.recv(8192)
            txt=d.decode(errors='replace')
        except Exception:
            txt='(timeout)'
        # answer Y/N if lingering
        if '[Y/N]' in txt or '(Y/N)' in txt:
            c.sock.send(b'YES\r\n'); time.sleep(0.8)
            try:
                d2=c.sock.recv(8192); txt+=d2.decode(errors='replace')
            except: pass
        print(f'[{label}] {cmd} -> {txt[-120:].strip()}')
    c.close()

# Undo HSB on both ACs (inside wlan view)
for name,port in [('AC1',2004),('AC2',2005)]:
    print(f'\n===== undo HSB {name} =====')
    send_block(port, [
        'system-view','wlan',
        'undo ac protect enable',
        'undo ac protect priority',
        'ap-id 3','undo ac-list 10.1.1.2' if name=='AC1' else 'undo ac-list 10.1.1.1',
        'return',
    ], name)

# Reboot AP1/AP2 via their consoles (alive)
for name,port in [('AP1',2006),('AP2',2007)]:
    print(f'\n===== reboot {name} =====')
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    c.sock.send(b'reboot\r\n'); time.sleep(1.0)
    c.sock.settimeout(3)
    try:
        d=c.sock.recv(8192); print(f'[{name}] reboot -> {d.decode(errors="replace")[-160:]}')
    except Exception as e:
        print(f'[{name}] reboot -> (timeout)')
    # answer Y/N if present
    c.sock.send(b'Y\r\n'); time.sleep(1.0)
    try:
        d=c.sock.recv(4096); print(f'[{name}] confirm -> {d.decode(errors="replace")[-120:]}')
    except: pass
    c.close()

print('\nWaiting 120s for APs to reboot + re-register clean...')
time.sleep(120)

for ac,p in [('AC1',2004),('AC2',2005)]:
    print(f'\n===== {ac} state =====')
    c = TelnetConnection('127.0.0.1', p); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    for s in ['display ap all','display radio all','display vap all','display ac protect']:
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
        print(buf.decode(errors='replace')[-1400:])
    c.close()
