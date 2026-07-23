import sys, time
sys.path.insert(0, r'E:\eNSP-MCP\lab_wlan_backup')
from wlib import show

print("Waiting 90s for APs to re-register after reboot...")
time.sleep(90)

print("\n=== AC1 display ap all ===")
print(show('AC1', ['display ap all'], delay=10))

print("\n=== AC1 display radio all ===")
print(show('AC1', ['display radio all'], delay=10))

print("\n=== AC1 display vap all ===")
print(show('AC1', ['display vap all'], delay=10))
