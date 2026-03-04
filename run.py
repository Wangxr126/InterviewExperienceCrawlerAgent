"""
面经 Agent 后端启动脚本

使用方式（三选一，效果一样）：
  1. 直接双击本文件（自动使用 NewCoderAgent 环境）
  2. 在任意终端：python run.py
  3. 开发模式（代码改动自动重启）：python run.py --reload

NewCoderAgent 环境路径固定写死，无需 conda activate。
"""
import sys
import os
import subprocess

# ── 固定使用 NewCoderAgent conda 环境 ──────────────────────────
CONDA_ENV_PYTHON = r"C:\Users\Wangxr\.conda\envs\NewCoderAgent\python.exe"

# 如果当前解释器不是目标环境，用目标环境重新启动本脚本
if os.path.abspath(sys.executable).lower() != os.path.abspath(CONDA_ENV_PYTHON).lower():
    if not os.path.exists(CONDA_ENV_PYTHON):
        print(f"❌ 找不到 NewCoderAgent 环境: {CONDA_ENV_PYTHON}")
        print("   请确认路径正确，或修改 run.py 中的 CONDA_ENV_PYTHON 变量")
        sys.exit(1)
    print(f"🔄 切换到 NewCoderAgent 环境: {CONDA_ENV_PYTHON}")
    result = subprocess.run([CONDA_ENV_PYTHON] + sys.argv, env={**os.environ,
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    sys.exit(result.returncode)

# ── 已在正确环境中运行 ──────────────────────────────────────────
# Windows GBK 终端 emoji 兼容
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"


def check_deps():
    missing = []
    for pkg in ["uvicorn", "fastapi"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"❌ 缺少依赖: {missing}")
        print(f"   请运行: {CONDA_ENV_PYTHON} -m pip install {' '.join(missing)}")
        sys.exit(1)


def check_neo4j():
    """检查 Neo4j 是否可连接（提前给出提示）"""
    try:
        import socket
        sock = socket.create_connection(("localhost", 7687), timeout=2)
        sock.close()
        print("✅ Neo4j (localhost:7687) 连接正常")
    except Exception:
        print("⚠️  Neo4j (localhost:7687) 未就绪")
        print("   → 请先运行: docker compose up -d")
        print("   → 等待约 30 秒后服务启动完成")
        print("   → 浏览器打开 http://localhost:7474 可查看知识图谱")


def main():
    check_deps()

    host = "0.0.0.0"
    port = 8000
    reload = False

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        if arg == "--host" and i + 1 < len(args):
            host = args[i + 1]
        if arg == "--reload":
            reload = True

    check_neo4j()

    print(f"""
╔══════════════════════════════════════════════════════╗
║            面经 Agent 后端已启动                      ║
╠══════════════════════════════════════════════════════╣
║  Python 环境：NewCoderAgent                          ║
║  API 地址  ：http://localhost:{port}
║  API 文档  ：http://localhost:{port}/docs
║  【前端-生产】：直接访问 http://localhost:{port}
║  【前端-开发】：cd web && npm run dev  → localhost:5173
║  Neo4j 管理：http://localhost:7474
║  退出      ：Ctrl+C
╚══════════════════════════════════════════════════════╝
    """)

    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

    cmd = [sys.executable, "-m", "uvicorn", "backend.main:app",
           "--host", host, "--port", str(port)]
    if reload:
        cmd.append("--reload")

    subprocess.run(cmd, env=env)


if __name__ == "__main__":
    main()
