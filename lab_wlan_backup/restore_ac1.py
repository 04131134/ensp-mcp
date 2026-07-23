import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

# Restore AC1 Vlanif10
print('=== Restore AC1 Vlanif10 ===')
c = TelnetConnection('127.0.0.1', 2004); c.connect()
c.sock.send(b'\r\n'); time.sleep(0.8)
c.sock.settimeout(2)
try: c.sock.recv(4096)
except: pass
for cmd in ['system-view','interface Vlanif10','undo shutdown','return','display interface Vlanif10 | include current']:
    c.sock.send((cmd+'\r\n').encode()); time.sleep(1.0)
    c.sock.settimeout(3)
    try:
        d=c.sock.recv(8192); print(f'[{cmd}] -> {d.decode(errors="replace")[-90:].strip()}')
    except: print(f'[{cmd}] -> (timeout)')
c.close()

time.sleep(20)

# Reboot AP1/AP2 to re-register to AC1
for name,port in [('AP1',2006),('AP2',2007)]:
    print(f'\n=== reboot {name} ===')
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

print('\nWaiting 120s for AP1/AP2 to re-register to AC1...')
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

print('\n=== Final AC1/AC2 state ===')
print('AC1:\n', ap_state('AC1',2004)[-700:])
print('AC2:\n', ap_state('AC2',2005)[-700:])
