import sys, time
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import show

for dev in ['AC1','AC2']:
    print(f'\n===== {dev} =====')
    for s in ['display ap all', 'display radio all', 'display vap all', 'display ac protect']:
        print(f'\n--- {s} ---')
        try:
            out = show(dev, [s], delay=8 if 'ap all' in s else 5)
            print(out[-2000:] if len(out)>2000 else out)
        except Exception as e:
            print(f'ERROR: {e}')
