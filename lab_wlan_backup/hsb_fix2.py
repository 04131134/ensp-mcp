import sys, time
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

PORTS = {'AC1': 2004, 'AC2': 2005}

def send_block(name, port, cmds, wait=0.6):
    """Send commands, auto-answer [Y/N] with YES (uppercase)."""
    c = TelnetConnection('127.0.0.1', port)
    c.connect()
    c.send_cmd('screen-length 0 temporary')
    time.sleep(0.3)
    log = []
    for cmd in cmds:
        out = c.send_cmd(cmd)
        # If a [Y/N] prompt is lingering, answer YES
        if b'[Y/N]' in out.encode() or b'(Y/N)' in out.encode():
            c.sock.send(b'YES\r\n')
            time.sleep(0.6)
            more = c.send_cmd('')  # flush response / reach next prompt
            out = out + more
        log.append((cmd, out))
        print(f'[{name}] {cmd}')
        time.sleep(wait)
    c.close()
    return log

AC1 = ['system-view', 'wlan',
       'ac protect enable', 'ac protect priority 7',
       'ac protect protect-ac 10.1.1.2',
       'ap-id 3', 'ac-list 10.1.1.2', 'return']

AC2 = ['system-view', 'wlan',
       'ac protect enable', 'ac protect priority 5',
       'ac protect protect-ac 10.1.1.1',
       'ap-id 3', 'ac-list 10.1.1.1', 'return']

print('===== AC1 HSB (wlan view) =====')
send_block('AC1', PORTS['AC1'], AC1)
print('\n===== AC2 HSB (wlan view) =====')
send_block('AC2', PORTS['AC2'], AC2)

print('\nWaiting 100s for AP3 to re-establish dual tunnels...')
time.sleep(100)

for dev in ['AC1', 'AC2']:
    print(f'\n===== {dev} state =====')
    c = TelnetConnection('127.0.0.1', PORTS[dev])
    c.connect()
    c.send_cmd('screen-length 0 temporary'); time.sleep(0.3)
    for s in ['display ap all', 'display ac protect']:
        o = c.send_cmd(s)
        print(f'--- {s} ---')
        print(o[-1400:] if len(o) > 1400 else o)
    c.close()
