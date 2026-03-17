"""
自动同步脚本：将 opn worktree 的修改同步到实际项目目录
运行此脚本后，所有修改会自动复制到 E:\Agent\AgentProject\wxr_agent
"""
import os
import shutil
from pathlib import Path

# 源目录（opn worktree）
SOURCE_DIR = Path(r"C:\Users\Wangxr\.cursor\worktrees\wxr_agent\opn")

# 目标目录（实际项目）
TARGET_DIR = Path(r"E:\Agent\AgentProject\wxr_agent")

# 需要同步的文件和目录
SYNC_ITEMS = [
    "backend/services/crawler/nowcoder_crawler.py",
    "backend/services/crawler/question_extractor.py",
    "backend/services/finetune_service.py",
    "backend/services/sqlite_service.py",
    "backend/main.py",
    "web/src/views/FinetuneView.vue",
    "web/src/components/QuestionDialog.vue",
    "test4.py",
    "test_nowcoder_full.py",
]

def sync_file(rel_path):
    """同步单个文件"""
    source = SOURCE_DIR / rel_path
    target = TARGET_DIR / rel_path
    
    if not source.exists():
        print(f"[SKIP] 源文件不存在: {rel_path}")
        return False
    
    # 确保目标目录存在
    target.parent.mkdir(parents=True, exist_ok=True)
    
    # 复制文件
    shutil.copy2(source, target)
    print(f"[OK] 已同步: {rel_path}")
    return True

def main():
    print("="*80)
    print("开始同步 opn worktree 到实际项目目录")
    print("="*80)
    print(f"源目录: {SOURCE_DIR}")
    print(f"目标目录: {TARGET_DIR}")
    print("="*80)
    
    success_count = 0
    fail_count = 0
    
    for item in SYNC_ITEMS:
        if sync_file(item):
            success_count += 1
        else:
            fail_count += 1
    
    print("="*80)
    print(f"同步完成: 成功 {success_count} 个, 失败 {fail_count} 个")
    print("="*80)
    
    if success_count > 0:
        print("\n[提示] 如果修改了前端文件，请运行:")
        print("  cd E:\\Agent\\AgentProject\\wxr_agent\\web")
        print("  npm run build")

if __name__ == "__main__":
    main()
