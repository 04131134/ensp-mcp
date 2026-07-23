import socket, time, sys
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import PORTS

def ap_config(port, label):
    print(f"\n===== {label} (port {port}) =====")
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=6)
    except Exception as e:
        print("CONN_FAIL:", e); return
    s.settimeout(2)
    time.sleep(1.0)
    def cmd(c, w=6, auto_yes=False):
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
                if auto_yes and b'Y/N' in b or b'Continue' in b or b'[Y/N]' in b:
                    try: s.sendall(b"YES\r\n")
                    except: pass
            except socket.timeout: break
            except Exception: break
        return b.decode(errors='replace')
    cmds = [
        "screen-length 0 temporary",
        "system-view",
        "interface GigabitEthernet0/0/0",
        "port link-type trunk",
        "port trunk pvid vlan 10",
        "port trunk allow-pass vlan 10",
        "return",
    ]
    for c in cmds:
        out = cmd(c, w=3, auto_yes=True)
        print(f"> {c} -> {out.strip()[-120:] if out.strip() else '(empty)'}")
    print("-- waiting 45s for DHCP renewal --")
    time.sleep(45)
    print("-- display ip interface brief --")
    print(cmd("display ip interface brief", 6))
    s.close()

ap_config(PORTS['AP1'], 'AP1')
ap_config(PORTS['AP2'], 'AP2')
