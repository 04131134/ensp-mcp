import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

print('Waiting 100s for AP1/AP2 registration...')
time.sleep(100)

for ac, p in [('AC1',2004),('AC2',2005)]:
    print(f'\n===== {ac} AP registration =====')
    c = TelnetConnection('127.0.0.1', p); c.connect()
    c.sock.send(b'\r\n'); time.sleep(0.8)
    c.sock.settimeout(2)
    try: c.sock.recv(4096)
    except: pass
    for s in ['display ap all','display radio all','display vap all']:
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
        print(buf.decode(errors='replace')[-1600:])
    c.close()
