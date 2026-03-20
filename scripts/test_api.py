import urllib.request, json

r = urllib.request.urlopen('http://localhost:8000/api/user/Wangxr/chat/history', timeout=10)
d = json.loads(r.read())
msgs = d.get('messages', [])

print('Total msgs:', len(msgs))
print('Session:', d.get('session_id'))
print('With thinking:', sum(1 for m in msgs if m.get('thinking')))
print()
print('First 5:')
for m in msgs[:5]:
    print(f'  [{m["role"]}] {m.get("timestamp","")[:19]} | {repr(str(m.get("content",""))[:70])}')
print('Last 5:')
for m in msgs[-5:]:
    print(f'  [{m["role"]}] {m.get("timestamp","")[:19]} | {repr(str(m.get("content",""))[:70])}')
