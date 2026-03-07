import asyncio
import logging
import sys
import os

# 1. 配置日志输出到控制台，方便你看到 Agent 的思考过程
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("MainCLI")

# 2. 引入编排器 (确保 backend 包在 Python 路径下)
# 如果报错 ModuleNotFoundError，请确保你在项目根目录运行，或者取消下面注释
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.agents.orchestrator import get_orchestrator


async def main():
    print("\n" + "=" * 50)
    print("🚀 启动纯后端测试模式 (No API)")
    print("=" * 50 + "\n")

    # --- 1. 初始化系统 ---
    logger.info("正在初始化 Orchestrator...")
    orchestrator = get_orchestrator()
    print("✅ 系统初始化完成！\n")

    # ==========================================
    # 场景 A: 离线入库 (模拟 "资源猎人" + "知识架构师")
    # ==========================================
    print("--- [场景 A] 测试数据抓取与入库 ---")

    # 这里换成你想测试的真实 URL (比如牛客网的面经贴)
    # 如果不想测爬虫，可以把这一段注释掉
    test_url = "https://www.nowcoder.com/discuss/532345638411059200"
    user_id_admin = "admin_001"

    # print(f"👉 正在尝试抓取: {test_url}")
    # try:
    #     report = await orchestrator.ingest_instant(test_url, user_id_admin)
    #     print(f"\n📄 入库报告:\n{report}")
    # except Exception as e:
    #     print(f"❌ 入库测试失败: {e}")

    print("\n" + "-" * 30 + "\n")

    # ==========================================
    # 场景 B: 在线面试 (模拟 "金牌面试官")
    # ==========================================
    print("--- [场景 B] 测试面试对话 ---")

    user_id_student = "student_xiaoming"

    # 第一轮：开场
    msg1 = "你好，我想复习一下 Redis 的知识。"
    print(f"👤 用户: {msg1}")
    reply1 = await orchestrator.chat(user_id_student, msg1)
    print(f"👩‍🏫 面试官:\n{reply1}\n")

    # 第二轮：模拟回答 (假设面试官问了持久化)
    msg2 = "Redis 有 RDB 和 AOF 两种持久化方式。RDB 是快照，AOF 是日志。"
    print(f"👤 用户: {msg2}")
    reply2 = await orchestrator.chat(user_id_student, msg2)
    print(f"👩‍🏫 面试官:\n{reply2}\n")


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())