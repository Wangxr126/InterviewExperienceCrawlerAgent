import time
import requests

for i in range(6):
    r = requests.get('http://localhost:8000/api/crawler/extraction-status', timeout=5)
    d = r.json()
    fetched = d.get('fetched', 0)
    done = d.get('done', 0)
    error = d.get('error', 0)
    processing = d.get('processing', d.get('in_progress', 0))
    print(f'[{i*10}s] fetched={fetched} done={done} error={error} processing={processing}')
    print(f'       raw: {d}')
    if i < 5:
        time.sleep(10)
