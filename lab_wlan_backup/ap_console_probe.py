import socket, time, sys
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import PORTS

def ap_probe(port, label, wait=8):
    print(f"\n===== {label} (port {port}) =====")
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=6)
    except Exception as e:
        print("CONN_FAIL:", e)
        return
    s.settimeout(2)
    time.sleep(1.0)
    # read any banner first
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
    print("BANNER/RAW:", repr(buf[:400]))
    # try a command
    try:
        s.sendall(b"screen-length 0 temporary\r\n")
    except Exception:
        pass
    time.sleep(1)
    try:
        s.sendall(b"display ip interface brief\r\n")
    except Exception:
        pass
    time.sleep(3)
    buf2 = b""
    end = time.time() + 5
    while time.time() < end:
        try:
            d = s.recv(4096)
            if not d:
                break
            buf2 += d
        except socket.timeout:
            break
        except Exception:
            break
    print("AFTER CMD:", repr(buf2[:500]))
    s.close()

ap_probe(PORTS['AP1'], 'AP1')
ap_probe(PORTS['AP2'], 'AP2')
ap_probe(PORTS['AP3'], 'AP3')
