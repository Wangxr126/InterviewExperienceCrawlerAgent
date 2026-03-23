import os
from dotenv import load_dotenv, dotenv_values

# 强制重新加载
load_dotenv('e:/Agent/AgentProject/wxr_agent/.env', override=True)

# 直接读环境变量
print('os.environ MINER_STAGE2_MODEL:', os.environ.get('MINER_STAGE2_MODEL'))
print('os.environ MINER_STAGE2_API_KEY:', (os.environ.get('MINER_STAGE2_API_KEY') or '')[:20])
print('os.environ MINER_STAGE2_BASE_URL:', os.environ.get('MINER_STAGE2_BASE_URL'))

# 用dotenv_values直接读文件（不走os.environ缓存）
vals = dotenv_values('e:/Agent/AgentProject/wxr_agent/.env')
print()
print('dotenv_values MINER_STAGE2_MODEL:', vals.get('MINER_STAGE2_MODEL'))
print('dotenv_values MINER_STAGE2_API_KEY:', (vals.get('MINER_STAGE2_API_KEY') or '')[:20])
print('dotenv_values MINER_STAGE2_BASE_URL:', vals.get('MINER_STAGE2_BASE_URL'))
