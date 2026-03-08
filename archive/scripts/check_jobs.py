from backend.services.scheduler_service import scheduler_service

jobs = scheduler_service.list_jobs()
print(f'Total jobs: {len(jobs)}')
for j in jobs:
    print(f'  - {j["job_name"]} ({j["job_id"][:8]}...) - {"Enabled" if j["enabled"] else "Disabled"}')
