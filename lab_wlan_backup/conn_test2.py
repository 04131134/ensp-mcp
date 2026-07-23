import sys, time, os
sys.path.insert(0, 'E:/eNSP-MCP')
from mcpensp1.connection import TelnetConnection

TARGETS = {
    'AC1': '10.1.1.1', 'AC2': '10.1.1.2', 'AR1': '10.1.1.11',
    'AR2': '10.1.1.12', 'AR3': '10.1.1.3',
    'STA1gw': '192.168.10.1', 'STA2gw': '192.168.20.1', 'STA3gw': '192.168.40.1',
}
SOURCES = [('AR1',2000),('AR2',2001),('AR3',2002),('AC1',2004),('AC2',2005),('LSW1',2003)]

def ping(src_name, src_port, tip):
    c = TelnetConnection('127.0.0.1', src_port); c.connect()
    out = c.send_cmd('screen-length 0 temporary'); time.sleep(0.2)
    out = c.send_cmd('ping -c 5 -a ' + tip)   # send_cmd handles read until prompt
    c.close()
    return out

print('CONNECTIVITY (Reply-from /5  |  received-line)\n')
header = 'SRC\\TGT'.ljust(7) + ''.join(t[:6].rjust(8) for t in TARGETS)
print(header)
results = {}
for sname, sport in SOURCES:
    row = sname.ljust(7); results[sname] = {}
    for tname, tip in TARGETS.items():
        try:
            o = ping(sname, sport, tip)
        except Exception as e:
            o = 'ERR:'+str(e)
        rcv = o.count('Reply from')
        # find received line
        imp = '?'
        for line in o.split('\n'):
            if 'packet(s) received' in line or 'received' in line and '%' in line:
                imp = line.strip()[:40]; break
        results[sname][tname] = (rcv, imp)
        row += f'{rcv}'.rjust(8)
    print(row); time.sleep(0.2)

# detailed dump
os.makedirs('logs', exist_ok=True)
with open('logs/connectivity_final.txt','w',encoding='utf-8') as f:
    f.write(header+'\n')
    for sname,_ in SOURCES:
        f.write(sname.ljust(7)+''.join(str(results[sname][t][0]).rjust(8) for t in TARGETS)+'\n')
    f.write('\n--- detail (received lines) ---\n')
    for sname,_ in SOURCES:
        for tname in TARGETS:
            f.write(f'{sname}->{tname}: rcv={results[sname][tname][0]} | {results[sname][tname][1]}\n')
print('\nSaved logs/connectivity_final.txt')
