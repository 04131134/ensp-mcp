# -*- coding: utf-8 -*-
"""扫描 eNSP 已启动设备的 console 端口，识别每台设备的型号与 sysname（只读）。"""
import sys, os, time, socket, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ensp_utils import connect, send_cmd, _recv_all, _detect_decode

def is_open(port, host='127.0.0.1', timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def read_prompt(sock):
    """发空行并读取当前提示符，返回形如 'AC1' 的主机名。"""
    sock.send(b'\r\n')
    time.sleep(1.2)
    raw = _recv_all(sock, bufsize=8192, timeout=1.2)
    txt = _detect_decode(raw)
    # 提示符形如 <AC1> 或 [AC1]
    m = re.findall(r'[<\[]([^<\>\]]+)[>\]]', txt)
    if m:
        return m[-1], txt
    return None, txt

MODEL_KEYS = ['AC6605', 'AC6005', 'AR2220', 'AR3260', 'S5700', 'S3700', 'S6700',
              'AP6050', 'AP6010', 'AP3030', 'AP4030', 'AR201', 'FW6000', 'USG6000']

def detect_model(ver):
    for k in MODEL_KEYS:
        if k in ver:
            return k
    return None

def main():
    host = '127.0.0.1'
    print('扫描 2000-2025 端口...')
    open_ports = [p for p in range(2000, 2026) if is_open(p, host)]
    print('开放端口:', open_ports)
    print('=' * 72)

    results = {}
    for port in open_ports:
        try:
            s = connect(port, host)
            send_cmd(s, 'screen-length 0 temporary', wait=0.8)
            name, _ = read_prompt(s)
            ver = send_cmd(s, 'display version', wait=3.0)
            model = detect_model(ver)
            if not model:
                # 兜底：取含 VRP 的那行
                for line in ver.splitlines():
                    if 'VRP' in line:
                        model = line.strip()[:50]
                        break
            results[port] = {'model': model, 'name': name}
            print(f'PORT {port}: model={model}  sysname={name}')
            s.close()
        except Exception as e:
            print(f'PORT {port}: 识别失败 - {e}')

    print('=' * 72)
    print('汇总:')
    for port, info in results.items():
        print(f'  {port} -> {info["model"]} | sysname={info["name"]}')

if __name__ == '__main__':
    main()
