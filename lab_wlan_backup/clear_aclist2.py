import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

def clear_ac(name, port):
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(1.0)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    # clear any lingering prompt
    c.sock.send(b'YES\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    c.sock.send(b'return\r\n'); time.sleep(0.8)
    try: c.sock.recv(4096)
    except: pass
    # enter wlan view
    for cmd in ['system-view','wlan']:
        c.sock.send((cmd+'\r\n').encode()); time.sleep(0.8)
        c.sock.settimeout(3)
        try: c.sock.recv(8192)
        except: pass
    # clear ac-list on ap-id 1/2/3
    for aid in [1,2,3]:
        c.sock.send(f'ap-id {aid}\r\n'.encode()); time.sleep(0.8)
        c.sock.settimeout(3)
        try: c.sock.recv(8192)
        except: pass
        c.sock.send(b'undo ac-list\r\n'); time.sleep(1.0)
        c.sock.settimeout(3)
        try:
            d=c.sock.recv(8192); txt=d.decode(errors='replace')
        except: txt=''
        if '[Y/N]' in txt:
            c.sock.send(b'YES\r\n'); time.sleep(0.8)
            try: c.sock.recv(8192)
            except: pass
        print(f'[{name}] ap-id {aid} undo ac-list done')
    c.sock.send(b'return\r\n'); time.sleep(0.5)
    try: c.sock.recv(4096)
    except: pass
    c.close()

for name,port in [('AC1',2004),('AC2',2005)]:
    print(f'===== {name} =====')
    clear_ac(name, port)

print('\n===== reboot AP1/AP2 =====')
for name,port in [('AP1',2006),('AP2',2007)]:
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    c.sock.send(b'reboot\r\n'); time.sleep(1.0)
    c.sock.settimeout(3)
    try: print(f'[{name}] reboot -> {c.sock.recv(8192).decode(errors="replace")[-100:]}')
    except: print(f'[{name}] reboot -> (timeout)')
    c.sock.send(b'Y\r\n'); time.sleep(1.0)
    try: c.sock.recv(4096)
    except: pass
    c.close()

print('\nWaiting 120s...')
time.sleep(120)

def ap_state(ac, port):
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    c.sock.send(b'display ap all\r\n'); time.sleep(3)
    c.sock.settimeout(4); buf=b''
    try:
        while True:
            d=c.sock.recv(8192)
            if not d: break
            buf+=d
            if buf.rstrip().endswith(b'>'): break
    except: pass
    c.close()
    return buf.decode(errors='replace')

print('\n===== Final state =====')
print('AC1:\n', ap_state('AC1',2004)[-650:])
print('AC2:\n', ap_state('AC2',2005)[-650:])
