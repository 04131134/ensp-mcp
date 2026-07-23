import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

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

print('=== BEFORE: AC1/AC2 AP state (AP1/AP2 should be normal on AC1) ===')
print('AC1:\n', ap_state('AC1',2004)[-700:])
print('AC2:\n', ap_state('AC2',2005)[-700:])

# Shut AC1 Vlanif10 (CAPWAP source)
print('\n=== Shutting AC1 Vlanif10 (simulate AC1 failure) ===')
c = TelnetConnection('127.0.0.1', 2004); c.connect()
c.sock.send(b'\r\n'); time.sleep(0.8)
c.sock.settimeout(2)
try: c.sock.recv(4096)
except: pass
for cmd in ['system-view','interface Vlanif10','shutdown','return','display interface Vlanif10 | include Vlanif10']:
    c.sock.send((cmd+'\r\n').encode()); time.sleep(1.0)
    c.sock.settimeout(3)
    try:
        d=c.sock.recv(8192); print(f'[{cmd}] -> {d.decode(errors="replace")[-100:].strip()}')
    except: print(f'[{cmd}] -> (timeout)')
c.close()

print('\nWaiting 160s for CAPWAP timeout + AP re-register to AC2...')
time.sleep(160)

print('\n=== AFTER: AC1/AC2 AP state ===')
print('AC1:\n', ap_state('AC1',2004)[-700:])
print('AC2:\n', ap_state('AC2',2005)[-700:])
