import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

for name, port in [('AP3', 2008), ('AP1', 2006), ('AP2', 2007)]:
    print(f'\n===== {name} (port {port}) =====')
    try:
        c = TelnetConnection('127.0.0.1', port)
        c.connect()
        # empty to get prompt
        time.sleep(0.5)
        c.sock.send(b'\r\n'); time.sleep(0.5)
        # read whatever
        c.sock.settimeout(2)
        try:
            d = c.sock.recv(4096)
            print('RAW:', d[:300])
        except Exception as e:
            print('no prompt:', e)
        # try a display
        for s in ['display version', 'display ip interface brief', 'display capwap status']:
            c.sock.send((s + '\r\n').encode()); time.sleep(1.5)
            try:
                d = c.sock.recv(8192)
                print(f'\n--- {s} ---')
                print(d.decode(errors='replace')[-1000:])
            except Exception as e:
                print(f'{s}: timeout')
        c.close()
    except Exception as e:
        print(f'CONNECT ERROR: {e}')
