import socket, time, sys
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import PORTS, show

def ap_session(port, label, cmds, read_after=None, wait=8):
    print(f"\n===== {label} (port {port}) =====", flush=True)
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=6)
    except Exception as e:
        print("CONN_FAIL:", e, flush=True); return None
    s.settimeout(2)
    time.sleep(1.0)
    def cmd(c, w=4):
        try: s.sendall((c+"\r\n").encode())
        except Exception as ex: print("SEND_ERR", ex, flush=True)
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
    for c in cmds:
        out = cmd(c, w=4)
        print(f"> {c}\n  {out.strip()}", flush=True)
    if read_after:
        time.sleep(read_after)
        print("-- read --")
        print(cmd(read_after_cmd if False else "display ip interface brief", w=6), flush=True)
    return s

# AP1: put uplink into VLAN10 + manual IPv4 mgmt IP (no IPv6)
cmds1 = [
    "system-view",
    "interface GigabitEthernet0/0/0",
    "port link-type trunk",
    "port trunk pvid vlan 10",
    "port trunk allow-pass vlan 10",
    "quit",
    "interface Vlanif1",
    "ip address 10.1.1.11 255.255.255.0",
    "quit",
    "quit",
]
s = ap_session(PORTS['AP1'], 'AP1', cmds1)
if s:
    print("\n-- waiting 30s for CAPWAP registration --", flush=True)
    time.sleep(30)
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
    print("-- AP1 ip --"); print(b.decode(errors='replace'), flush=True)
    s.close()

print("\n=== AC1 display ap all ===", flush=True)
print(show('AC1', ['display ap all'], delay=10), flush=True)
