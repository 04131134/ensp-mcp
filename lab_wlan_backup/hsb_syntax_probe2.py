import sys
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import cfg

# Try ac ? in various views
for dev in ['AC1','AC2']:
    print(f'\n===== {dev} =====')
    
    print('\n--- system-view: a? ---')
    out = cfg(dev, ['system-view', 'a?', 'return'], delay=2, verbose=False)
    print(out)
    
    print('\n--- wlan-view: ac ? ---')
    out = cfg(dev, ['system-view', 'wlan', 'ac ?', 'return'], delay=2, verbose=False)
    print(out)
    
    print('\n--- wlan-view: ac-protect ? ---')
    out = cfg(dev, ['system-view', 'wlan', 'ac-protect ?', 'return'], delay=2, verbose=False)
    print(out)
