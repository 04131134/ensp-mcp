import httpx, json

r = httpx.get('http://127.0.0.1:5000/api/kb/capabilities')
data = r.json()
if isinstance(data, list):
    print(f'Total entries: {len(data)}')
    for d in data:
        name = d.get('name', d.get('display_name', '?'))
        model = d.get('model', d.get('device_type', '?'))
        v = d.get('verified', d.get('verified_count', 0))
        t = d.get('theoretical', d.get('theoretical_count', 0))
        f = d.get('failed', d.get('failed_count', 0))
        ns = d.get('not_supported', 0)
        print(f'  {name}: {model} | v={v} t={t} f={f} ns={ns}')
elif isinstance(data, dict):
    print('Keys:', list(data.keys()))
    for k, v in data.items():
        if isinstance(v, list):
            print(f'{k}: {len(v)} items')
        elif isinstance(v, dict):
            print(f'{k}: {len(v)} entries')
        else:
            print(f'{k}: {v}')
