import sys
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import show, cfg

print('=== AC1: ac ? in system-view ===')
# Enter system-view, query ac ?, return
out = cfg('AC1', ['system-view', 'ac ?', 'return'], delay=2, verbose=False)
print(out)

print('\n=== AC1: display version ===')
out = show('AC1', ['display version'], delay=3)
print(out)

print('\n=== AC2: ac ? in system-view ===')
out = cfg('AC2', ['system-view', 'ac ?', 'return'], delay=2, verbose=False)
print(out)

print('\n=== AC2: display version ===')
out = show('AC2', ['display version'], delay=3)
print(out)
