import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

for name, port in [('AR1',2000),('AR2',2001),('AR3',2002)]:
    print(f'\n===== {name} (port {port}) =====')
    c = TelnetConnection('127.0.0.1', port); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: print('PROMPT:', c.sock.recv(4096).decode(errors='replace')[:120])
    except Exception as e: print('no prompt', e)
    for s in ['display current-configuration', 'display ip interface brief']:
        c.sock.send((s+'\r\n').encode()); time.sleep(1.5)
        c.sock.settimeout(3)
        buf=b''
        try:
            while True:
                d=c.sock.recv(16384)
                if not d: break
                buf+=d
                if b'---- More ----' in buf:
                    c.sock.send(b' '); buf=buf.replace(b'---- More ----','')
                if buf.rstrip().endswith(b'>') or buf.rstrip().endswith(b']'):
                    break
        except Exception:
            pass
        print(f'\n--- {s} ---')
        print(buf.decode(errors='replace')[-2200:])
    c.close()
