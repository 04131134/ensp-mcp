# -*- coding: utf-8 -*-
"""
eNSP 实验脚本共享工具模块
提供设备连接、命令发送、验证等通用功能
"""
import socket
import time
import sys

# 默认端口映射（可按实验覆盖）
DEFAULT_HOST = '127.0.0.1'


def connect(port, host=DEFAULT_HOST, timeout=5, drain=True):
    """连接到 eNSP 设备并清理欢迎信息。
    
    Args:
        port: 设备端口号
        host: 主机地址
        timeout: 连接超时(秒)
        drain: 是否清除连接后的欢迎信息
    Returns:
        socket 对象
    """
    s = socket.socket()
    s.settimeout(timeout)
    s.connect((host, port))
    s.send(b'\r\n')
    time.sleep(0.3)
    if drain:
        try:
            s.recv(8192)
        except Exception:
            pass
    return s


def send_cmd(sock, cmd, wait=1.5, bufsize=65536, encoding='gbk'):
    """发送单条命令并返回输出。
    
    Args:
        sock: socket 对象
        cmd: 命令字符串
        wait: 等待响应时间(秒)
        bufsize: 接收缓冲区大小
        encoding: 解码编码
    Returns:
        命令输出字符串
    """
    sock.send((cmd + '\r\n').encode())
    time.sleep(wait)
    try:
        data = sock.recv(bufsize).decode(encoding, errors='ignore')
    except Exception:
        data = ''
    return data


def run_cmds(sock, cmds, wait=0.8, name='', verbose=True):
    """批量执行命令列表。
    
    Args:
        sock: socket 对象
        cmds: 命令列表
        wait: 每条命令等待时间(秒)
        name: 设备名称（用于日志）
        verbose: 是否打印执行过程
    Returns:
        输出列表
    """
    results = []
    for cmd in cmds:
        r = send_cmd(sock, cmd, wait)
        results.append(r)
        if verbose and cmd and cmd not in ('quit', 'return', 'system-view', ''):
            label = f'[{name}] ' if name else ''
            print(f'  {label}{cmd}')
    return results


def ping_ok(src, dst_ip, desc='', wait=10, verbose=True):
    """执行 ping 并判断是否连通。
    
    Args:
        src: 源设备 socket
        dst_ip: 目标 IP
        desc: 描述（用于日志）
        wait: ping 等待时间(秒)
        verbose: 是否打印结果
    Returns:
        True 如果连通
    """
    r = send_cmd(src, f'ping {dst_ip}', wait)
    ok = ('Reply' in r) and ('0.00% packet loss' in r or 'loss is 0' in r)
    if verbose:
        label = desc or f'ping {dst_ip}'
        print(f'  {label}: {"PASS" if ok else "FAIL"}')
        if not ok:
            print(f'    output: {r[:240]}')
    return ok


def tcp_check(host, port, timeout=6):
    """TCP 端口连通性检查。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def banner(title):
    """打印标题横幅。"""
    print('\n' + '=' * 60)
    print(f'  {title}')
    print('=' * 60)


def show_pass(label, ok):
    """打印 PASS/FAIL 结果。"""
    print(f'  {label}: {"PASS" if ok else "FAIL"}')


def connect_devices(ports, host=DEFAULT_HOST):
    """批量连接多台设备。
    
    Args:
        ports: 端口号列表或字典 {name: port}
        host: 主机地址
    Returns:
        如果 ports 是列表，返回 socket 列表
        如果 ports 是字典，返回 {name: socket} 字典
    """
    if isinstance(ports, dict):
        result = {}
        for name, port in ports.items():
            result[name] = connect(port, host)
            print(f'  Connected: {name} -> {host}:{port}')
        return result
    else:
        result = []
        for port in ports:
            result.append(connect(port, host))
            print(f'  Connected: {host}:{port}')
        return result


def close_all(sockets):
    """关闭所有 socket 连接。"""
    if isinstance(sockets, dict):
        sockets = sockets.values()
    for s in sockets:
        try:
            s.close()
        except Exception:
            pass


def screen_length_zero(sock):
    """设置 screen-length 0 temporary 避免分页。"""
    send_cmd(sock, 'screen-length 0 temporary', wait=0.8)
    try:
        sock.recv(4096)
    except Exception:
        pass


if __name__ == '__main__':
    # 快速测试：连接并查看设备信息
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = 2000
    print(f'Connecting to {DEFAULT_HOST}:{port} ...')
    s = connect(port)
    print('Connected!')
    r = send_cmd(s, 'display version')
    print(r[:500])
    s.close()
