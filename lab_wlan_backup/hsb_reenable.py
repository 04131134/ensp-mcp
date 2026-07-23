import sys, time
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import cfg, show

# Enable HSB on AC1 (priority 7 -> AC2) and AC2 (priority 5 -> AC1)
# Then add ac-list under ap-id 3 on both.

AC1_CMDS = [
    'system-view',
    'ac protect enable',
    'ac protect priority 7',
    'ac protect protect-ac 10.1.1.2',
    'wlan',
    'ap-id 3',
    'ac-list 10.1.1.2',
    'return',
]

AC2_CMDS = [
    'system-view',
    'ac protect enable',
    'ac protect priority 5',
    'ac protect protect-ac 10.1.1.1',
    'wlan',
    'ap-id 3',
    'ac-list 10.1.1.1',
    'return',
]

print('=== AC1 HSB re-enable ===')
out1 = cfg('AC1', AC1_CMDS, delay=3, verbose=False)
print(out1[-1500:] if len(out1)>1500 else out1)

print('\n=== AC2 HSB re-enable ===')
out2 = cfg('AC2', AC2_CMDS, delay=3, verbose=False)
print(out2[-1500:] if len(out2)>1500 else out2)

print('\nWaiting 90s for AP3 HSB negotiation...')
time.sleep(90)

for dev in ['AC1','AC2']:
    print(f'\n===== {dev} after HSB =====')
    for s in ['display ap all', 'display ac protect']:
        print(f'\n--- {s} ---')
        out = show(dev, [s], delay=8 if 'ap all' in s else 4)
        print(out[-1500:] if len(out)>1500 else out)
