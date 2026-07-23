import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

c = TelnetConnection('127.0.0.1', 2001); c.connect()
c.sock.send(b'\r\n'); time.sleep(0.8)
c.sock.settimeout(2)
try: c.sock.recv(4096)
except: pass

cmds = [
    'system-view',
    'interface Ethernet0/0/0',
    'undo port default vlan',
    'port link-type trunk',
    'port trunk pvid vlan 10',
    'port trunk allow-pass vlan 10 20 30 40',
    'return',
    'display current-configuration interface Ethernet0/0/0',
]
for cmd in cmds:
    c.sock.send((cmd+'\r\n').encode()); time.sleep(1.0)
    c.sock.settimeout(3)
    try:
        d=c.sock.recv(8192)
        print(f'[{cmd}] -> {d.decode(errors="replace")[-200:].strip()}')
    except Exception as e:
        print(f'[{cmd}] -> (timeout)')
c.close()
