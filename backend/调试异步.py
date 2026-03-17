import asyncio
import sys
sys.stdout.reconfigure(line_buffering=True)  # 强制行缓冲，立刻打印
# 任务1
async def test1():
    print("任务1 开始")
    await asyncio.sleep(1)  # 等待1秒
    print("任务1 结束")

# 任务2
async def test2():
    print("任务2 开始")
    await asyncio.sleep(1)  # 等待1秒
    print("任务2 结束")

# 主函数
async def main():
    # 同时运行两个任务
    t1 = asyncio.create_task(test1(), name="我的任务1")
    t2 = asyncio.create_task(test2(), name="我的任务2")

    await t1
    await t2

# 运行
if __name__ == "__main__":
    asyncio.run(main())