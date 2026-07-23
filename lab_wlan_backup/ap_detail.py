import socket, time, sys
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import PORTS

def ap_full(port, label):
    print(f"\n===== {label} (port {port}) =====")
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=6)
    except Exception as e:
        print("CONN_FAIL:", e); return
    s.settimeout(2)
    time.sleep(1.0)
    def cmd(c, w=6):
        try: s.sendall((c+"\r\n").encode())
        except Exception: pass
        time.sleep(w)
        b=b""
        end=time.time()+w
        while time.time()<end:
            try:
                d=s.recv(4096)
                if not d: break
                b+=d
            except socket.timeout: break
            except Exception: break
        return b.decode(errors='replace')
    print("-- screen-length --"); cmd("screen-length 0 temporary", 2)
    print("-- display ip interface brief --")
    print(cmd("display ip interface brief", 6))
    print("-- display interface brief --")
    print(cmd("display interface brief", 6))
    print("-- display capwap status --")
    out = cmd("display capwap status", 6)
    print(out if out.strip() else "(no output / cmd may not exist)")
    s.close()

ap_full(PORTS['AP1'], 'AP1')
ap_full(PORTS['AP2'], 'AP2')
