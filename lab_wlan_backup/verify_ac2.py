# -*- coding: utf-8 -*-
"""Clean re-verify of AC2: Vlanif10 up, capwap source, ap-group vap binding."""
import sys, time, socket
sys.path.insert(0, 'E:/eNSP-MCP/lab_wlan_backup')
from wlib import PORTS

def drain(s, t=0.6):
    s.settimeout(t)
    try:
        while True:
            d = s.recv(65536)
            if not d: break
    except socket.timeout:
        pass

def connect_dev(name):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10); s.connect(('127.0.0.1', PORTS[name]))
    time.sleep(0.6); drain(s, 0.6)
    s.settimeout(10); s.send(b'screen-length 0 temporary\r\n'); time.sleep(0.8); drain(s, 0.8)
    return s

def read_cmd(s, cmd, w=4.0):
    s.settimeout(10); s.send((cmd + '\r\n').encode())
    buf = b''; end = time.time() + w
    s.settimeout(0.4)
    try:
        while time.time() < end:
            d = s.recv(65536)
            if d: buf += d
    except socket.timeout:
        pass
    return buf.decode('gbk', errors='ignore')

s = connect_dev('AC2')
print("--- Vlanif10 ---", flush=True)
print(read_cmd(s, 'display ip interface brief', 4.0)[-700:], flush=True)
print("--- capwap configuration ---", flush=True)
print(read_cmd(s, 'display capwap configuration', 4.0)[-400:], flush=True)
print("--- ap-group default (vap bind) ---", flush=True)
print(read_cmd(s, 'display ap-group name default', 4.0)[-500:], flush=True)
s.close()
print("\n[DONE]", flush=True)
