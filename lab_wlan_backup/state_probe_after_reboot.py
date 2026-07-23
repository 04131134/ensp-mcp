import socket, time, sys
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import PORTS, show

def raw_telnet_probe(port, cmd, wait=5):
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=5)
    except Exception as e:
        return f"CONN_FAIL: {e}"
    s.settimeout(2)
    time.sleep(0.6)
    try:
        s.sendall((cmd + "\r\n").encode())
    except Exception:
        pass
    buf = b""
    end = time.time() + wait
    while time.time() < end:
        try:
            d = s.recv(4096)
            if not d:
                break
            buf += d
        except socket.timeout:
            break
        except Exception:
            break
    s.close()
    return buf.decode(errors='replace')

print("=== AC1 ===")
try:
    print(show('AC1', ['display current-configuration | include sysname',
                       'display current-configuration | include wlan',
                       'display ap all',
                       'display ac protect'], delay=8))
except Exception as e:
    print("AC1 ERR", e)

print("\n=== AC2 ===")
try:
    print(show('AC2', ['display current-configuration | include sysname',
                       'display current-configuration | include wlan',
                       'display ap all',
                       'display ac protect'], delay=8))
except Exception as e:
    print("AC2 ERR", e)

print("\n=== LSW1 raw probe (display vlan) ===")
print(raw_telnet_probe(PORTS['LSW1'], 'display vlan', wait=6))

print("\n=== AR1 sysname+ospf ===")
try:
    print(show('AR1', ['display current-configuration | include sysname',
                       'display current-configuration | include ospf'], delay=8))
except Exception as e:
    print("AR1 ERR", e)
