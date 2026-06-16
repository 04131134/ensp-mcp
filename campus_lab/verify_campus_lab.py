# -*- coding: utf-8 -*-
"""
Campus lab verification script aligned with Word section 4.1~4.8.
Requires manual server service configuration on eNSP (DNS/HTTP/FTP).
"""
import sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ensp_utils import connect, send_cmd, banner, ping_ok, close_all

PORTS = {
    'LSW1': 2012,
    'LSW2': 2013,
    'LSW5': 2016,
    'LSW6': 2017,
    'LSW7': 2018,
    'LSW8': 2019,
    'FW1': 2001,
    'AR1': 2000,
}

INTERNAL_TARGETS = [
    ('LSW5 -> PC5 (192.168.2.10)', '192.168.2.10'),
    ('LSW6 -> PC7 (192.168.3.10)', '192.168.3.10'),
    ('LSW7 -> PC9 (192.168.4.10)', '192.168.4.10'),
]

SERVER_TARGETS = [
    ('to Server1 DNS (192.168.0.1)', '192.168.0.1'),
    ('to Server2 WEB (192.168.0.2)', '192.168.0.2'),
    ('to Server3 FTP (192.168.0.3)', '192.168.0.3'),
]

DNS_NAMES = [
    ('www.jz.com', '192.168.0.2'),
    ('www.fzm.com', '192.168.0.3'),
]


def check_sw1(sw1):
    banner('Verify SW1/VRRP/DHCP (section 4.1~4.2)')
    cmds = [
        'display ip interface brief',
        'display vrrp brief',
        'display ip pool',
        'display stp brief',
    ]
    outputs = []
    for c in cmds:
        out = send_cmd(sw1, c, wait=1.5)
        outputs.append((c, out))
        print(f'\n[{c}]\n{out[:2000]}')
    return outputs


def check_internal_routes(sw):
    banner('Verify internal reachability from switch')
    results = []
    for desc, ip in INTERNAL_TARGETS + SERVER_TARGETS:
        results.append((desc, ping_ok(sw, ip, desc, wait=10)))
    return results


def check_dns_from_sw(sw):
    banner('Verify DNS resolution (section 4.4)')
    results = []
    for name, expect_ip in DNS_NAMES:
        out = send_cmd(sw, f'ping {name}', wait=10)
        ok = (expect_ip in out) and ('Reply' in out)
        print(f'  {name}: {"PASS" if ok else "FAIL"}')
        results.append((name, ok))
    return results


def check_external_ping(r1):
    banner('Verify external PC1/PC2 reachability (section 4.5)')
    results = []
    for desc, ip in [('R1->PC1', '201.1.1.1'), ('R1->PC2', '201.1.1.2')]:
        results.append((desc, ping_ok(r1, ip, desc, wait=10)))
    return results


def summarize(results):
    banner('Verification summary')
    passed = 0
    for label, ok in results:
        print(f'  {label}: {"PASS" if ok else "FAIL"}')
        if ok:
            passed += 1
    total = len(results)
    print(f'\nTotal {passed}/{total} passed.')


def main():
    banner('Campus lab verification')
    conns = {name: connect(port) for name, port in PORTS.items()}

    all_results = []
    all_results.extend(check_sw1(conns['LSW1']))
    all_results.extend(check_internal_routes(conns['LSW5']))
    all_results.extend(check_internal_routes(conns['LSW6']))
    all_results.extend(check_internal_routes(conns['LSW7']))
    all_results.extend(check_dns_from_sw(conns['LSW5']))
    all_results.extend(check_external_ping(conns['AR1']))
    summarize(all_results)

    close_all(conns.values())


if __name__ == '__main__':
    main()
