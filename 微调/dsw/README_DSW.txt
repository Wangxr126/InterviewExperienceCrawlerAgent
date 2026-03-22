PAI-DSW 方式一：网页 Terminal 训练（最小同步说明）
================================================

一、本机打包（Windows）
----------------------
在 PowerShell 中执行（可在任意目录）：

  cd E:\Agent\AgentProject\wxr_agent\微调\dsw
  .\pack_for_dsw.ps1

会在本目录生成 finetune_dsw_bundle.zip，内含：
  - train_lora.py
  - training_data_alpaca.jsonl（当前约 1MB，若你本地数据更大 zip 也会变大）
  - dsw/ 下 requirements、setup 脚本与本说明

也可手动拷贝上述文件到 DSW 工作区（如 /mnt/workspace/finetune/），保持「微调」目录结构：
  微调/
    train_lora.py
    training_data_alpaca.jsonl
    dsw/
      requirements-dsw.txt
      setup_dsw.sh
      env_dsw.example

二、DSW 上操作
--------------
1. 上传 finetune_dsw_bundle.zip 到 DSW（侧边栏上传 / OSS / git 均可）。
2. 打开 Terminal：
     unzip -o finetune_dsw_bundle.zip -d finetune
     cd finetune
3. 可选：cp dsw/env_dsw.example dsw/env_dsw.sh 并按需编辑，再 source dsw/env_dsw.sh
4. 安装并开训（推荐：独立 venv，勿对系统 Python 直接 pip install -r，否则会弄乱 protobuf/TensorFlow）：
     bash dsw/setup_dsw.sh
   或分步：
     bash dsw/install_venv_dsw.sh
     source .venv_finetune/bin/activate
     python train_lora.py

若镜像已自带 GPU PyTorch，pip 可能提示 torch 已满足；若 import torch 后 cuda 为 False，
请按 requirements-dsw.txt 顶部注释，用阿里云 cu124 轮子先装 torch 三件套，再 pip install -r requirements-dsw.txt。

pip 报 ConnectTimeout / mirrors.aliyun.com 超时：不是必须用阿里云镜像，可换清华或腾讯云，例如
  export PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
  bash dsw/setup_dsw.sh
或手动：pip install -r dsw/requirements-dsw.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout 300

三、输出位置
------------
脚本默认输出目录（相对 train_lora.py）：
  lora_output/qwen3-4b-miner-lora/

训练结束后可将该目录打包下载到本机。

四、显存与参数
--------------
train_lora.py 内可改：LOAD_IN_4BIT、MAX_SEQ_LENGTH、BATCH_SIZE、GRAD_ACCUM。
单卡 OOM 时优先：BATCH_SIZE=1 或降低 MAX_SEQ_LENGTH。

五、常见错误（DSW）
------------------
• protobuf / MessageFactory / TensorFlow 报错：曾在「系统 Python」里 pip 升级了 protobuf。
  解决：删除旧环境后仅用 install_venv_dsw.sh 新建 .venv_finetune；不要 pip install -r 到 /usr/local。
• ModuleNotFoundError: xformers：需先装与 torch 同 CUDA 版本的 xformers（脚本已从 pytorch.org whl 安装）。
• unsloth 被装成 2024.8：requirements 已约束 unsloth>=2024.12.2，请在 venv 内重装。
• torch 为 cu118 而脚本用 cu121：可 export TORCH_CUDA=cu118 后重新运行 install_venv_dsw.sh。
