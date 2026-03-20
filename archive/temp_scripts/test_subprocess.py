import subprocess
import sys
import os
from pathlib import Path

log_path = Path(r'E:\Agent\AgentProject\wxr_agent\backend\logs\batch_extract.log')
task_ids = ['TASK-0308441770']
cmd = [sys.executable, '-m', 'backend.services.scheduling.batch_extract_worker'] + task_ids

print('Starting:', ' '.join(cmd))
print('Log:', log_path)

with open(log_path, 'a', encoding='utf-8') as logf:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        cwd=r'E:\Agent\AgentProject\wxr_agent',
        env=os.environ,
    )
    for line in iter(proc.stdout.readline, b''):
        text = line.decode('utf-8', errors='replace')
        logf.write(text)
        logf.flush()
        print(text, end='')
    proc.wait()
    print(f'Process exited with code: {proc.returncode}')
