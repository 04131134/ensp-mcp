import socket, time, sys
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import PORTS, show

def ap_ip(port, label):
    print(f"\n===== {label} (port {port}) =====")
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=6)
    except Exception as e:
        print("CONN_FAIL:", e); return
    s.settimeout(2)
    time.sleep(1.0)
    try: s.sendall(b"screen-length 0 temporary\r\n")
    except: pass
    time.sleep(1)
    try: s.sendall(b"display ip interface brief\r\n")
    except: pass
    time.sleep(5)
    b=b""
    end=time.time()+6
    while time.time()<end:
        try:
            d=s.recv(4096)
            if not d: break
            b+=d
        except socket.timeout: break
        except Exception: break
    print(b.decode(errors='replace'))
    s.close()

ap_ip(PORTS['AP1'], 'AP1')
ap_ip(PORTS['AP2'], 'AP2')

print("\n=== AC1 display ap all ===")
print(show('AC1', ['display ap all'], delay=10))

print("\n=== AC1 display vap all ===")
print(show('AC1', ['display vap all'], delay=10))
