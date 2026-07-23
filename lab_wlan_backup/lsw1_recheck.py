import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

port = 2003
c = TelnetConnection('127.0.0.1', port)
c.connect()
c.sock.send(b'\r\n'); time.sleep(1)
c.sock.settimeout(2)
try:
    d = c.sock.recv(4096)
    print('RAW prompt:', d[:200])
except Exception as e:
    print('no initial prompt:', e)
for s in ['display vlan', 'display interface brief', 'display ip interface brief', 'display current-configuration | include port']:
    c.sock.send((s+'\r\n').encode()); time.sleep(2)
    c.sock.settimeout(2)
    try:
        d = c.sock.recv(16384)
        print(f'\n--- {s} ---')
        print(d.decode(errors='replace')[-1500:])
    except Exception as e:
        print(f'{s}: timeout/no data')
c.close()
