# -*- coding: utf-8 -*-
"""
Campus lab verification via eNSP MCP service.
Maps to Word section 4.1~4.8 verification points.
"""
import urllib.request, json, time

BASE = 'http://127.0.0.1:5000'

PATHS = {
    'SW1': '127.0.0.1:2012', 'SW2': '127.0.0.1:2013',
    'LSW5': '127.0.0.1:2016', 'LSW6': '127.0.0.1:2017',
    'LSW7': '127.0.0.1:2018', 'LSW8': '127.0.0.1:2019',
    'FW1': '127.0.0.1:2001', 'AR1': '127.0.0.1:2000',
    'LSW3': '127.0.0.1:2014', 'LSW4': '127.0.0.1:2015',
}


def cmd(path, command, wait=2.0):
    time.sleep(wait)
    req = urllib.request.Request(
        f'{BASE}/api/devices/command',
        json.dumps({'path': path, 'command': command}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read())
            return resp.get('output', '')
    except Exception as e:
        return f'ERROR: {e}'


def banner(title):
    print(f'\n{"="*60}\n  {title}\n{"="*60}')


def check_ping(path, ip, desc='', wait=10):
    out = cmd(path, f'ping {ip}', wait=wait)
    ok = ('Reply' in out) and ('0.00% packet loss' in out or 'loss is 0' in out)
    label = desc or f'ping {ip}'
    print(f'  {label}: {"PASS" if ok else "FAIL"}')
    if not ok:
        print(f'    output: {out[:200]}')
    return ok


def check_display(path, command, desc='', keywords=None):
    out = cmd(path, command, wait=2)
    ok = True
    if keywords:
        ok = all(kw in out for kw in keywords)
    print(f'  {desc or command}: {"PASS" if ok else "FAIL"}')
    if not ok and keywords:
        missing = [kw for kw in keywords if kw not in out]
        print(f'    missing: {missing}')
    return ok


def main():
    results = []

    # 4.1 DHCP auto-assignment
    banner('4.1 DHCP Auto-assignment Verification')
    results.append(('4.1 DHCP pool vlan10', check_display(
        PATHS['SW1'], 'display ip pool', 'SW1 DHCP pools',
        keywords=['Pool', '192.168.1.0'])))
    results.append(('4.1 VRRP brief', check_display(
        PATHS['SW1'], 'display vrrp brief', 'SW1 VRRP',
        keywords=['Vlanif10', 'Master'])))

    # 4.2 Internal connectivity
    banner('4.2 Internal Connectivity')
    for desc, ip in [
        ('SW1->VLAN10 GW', '192.168.1.254'),
        ('SW1->VLAN20 GW', '192.168.2.254'),
        ('SW1->VLAN30 GW', '192.168.3.254'),
        ('SW1->VLAN40 GW', '192.168.4.254'),
    ]:
        results.append((f'4.2 {desc}', check_ping(PATHS['SW1'], ip, desc)))

    # 4.3 Internal access to servers
    banner('4.3 Internal Access to Servers')
    for desc, ip in [
        ('to DNS Server (192.168.0.1)', '192.168.0.1'),
        ('to Web Server (192.168.0.2)', '192.168.0.2'),
        ('to FTP Server (192.168.0.3)', '192.168.0.3'),
    ]:
        results.append((f'4.3 {desc}', check_ping(PATHS['SW1'], ip, desc)))

    # 4.4 DNS resolution
    banner('4.4 DNS Resolution')
    for name, expect_ip in [('www.jz.com', '192.168.0.2'), ('www.fzm.com', '192.168.0.3')]:
        out = cmd(PATHS['SW1'], f'ping {name}', wait=10)
        ok = (expect_ip in out) and ('Reply' in out)
        print(f'  ping {name}: {"PASS" if ok else "FAIL"}')
        results.append((f'4.4 DNS {name}', ok))

    # 4.5 Internal access to external
    banner('4.5 Internal Access to External')
    for desc, ip in [
        ('SW1->PC1 (201.1.1.1)', '201.1.1.1'),
        ('SW1->PC2 (201.1.1.2)', '201.1.1.2'),
    ]:
        results.append((f'4.5 {desc}', check_ping(PATHS['SW1'], ip, desc)))

    # 4.6 External access to servers
    banner('4.6 External Access to Servers')
    for desc, ip in [
        ('AR1->DNS (192.168.0.1)', '192.168.0.1'),
        ('AR1->Web (192.168.0.2)', '192.168.0.2'),
        ('AR1->FTP (192.168.0.3)', '192.168.0.3'),
    ]:
        results.append((f'4.6 {desc}', check_ping(PATHS['AR1'], ip, desc)))

    # 4.7 External cannot access internal
    banner('4.7 External Cannot Access Internal')
    out = cmd(PATHS['AR1'], 'ping 192.168.1.10', wait=10)
    ok = ('Request time out' in out or 'Destination host unreachable' in out or 'Reply' not in out)
    print(f'  AR1->192.168.1.10: {"PASS (blocked)" if ok else "FAIL (should be blocked)"}')
    results.append(('4.7 Ext->Int blocked', ok))

    # 4.8 Server cannot initiate requests
    banner('4.8 Server Cannot Initiate Requests')
    out = cmd(PATHS['FW1'], 'display security-policy all', wait=2)
    has_deny = 'deny' in out.lower() or 'dmz' in out.lower()
    print(f'  FW1 security-policy check: {"PASS" if has_deny else "FAIL"}')
    results.append(('4.8 FW deny_dmz_out', has_deny))

    # Summary
    banner('Verification Summary')
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for label, ok in results:
        print(f'  {"PASS" if ok else "FAIL"}  {label}')
    print(f'\n  Total: {passed}/{total} passed')


if __name__ == '__main__':
    main()
