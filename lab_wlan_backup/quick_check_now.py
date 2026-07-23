import sys
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import show

print("=== AC1 display ap all ===")
print(show('AC1', ['display ap all'], delay=10))

print("\n=== AC1 display radio all ===")
print(show('AC1', ['display radio all'], delay=10))

print("\n=== AC1 display vap all ===")
print(show('AC1', ['display vap all'], delay=10))

print("\n=== AC2 display ap all ===")
print(show('AC2', ['display ap all'], delay=10))

print("\n=== AC1 display ip interface brief (confirm IPv4 only) ===")
print(show('AC1', ['display ip interface brief'], delay=8))
