#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目清理脚本 - 归档旧文件和临时脚本
执行前会显示将要执行的操作，需要用户确认
"""

import sys
import os
from pathlib import Path
import shutil

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent

# 定义要清理的文件
FILES_TO_ARCHIVE = {
    "旧版 Prompt": [
        "backend/prompts/miner_prompt_old.py",
    ],
    "临时修复脚本": [
        "fix_log_path.py",
        "fix_indent.py",
        "fix_newline.py", 
        "fix_llm_log.py",
    ],
}

FILES_TO_DELETE = {
    "重复的 OCR 服务（旧版）": [
        "backend/services/crawler/ocr_service.py",
    ],
}

# hunter_pipeline 和 run_xhs_worker 正在被使用，不删除
FILES_IN_USE = {
    "backend/services/hunter_pipeline.py": "被 orchestrator.py 使用",
    "backend/services/crawler/run_xhs_worker.py": "XHS Worker（暂时保留）",
}

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def check_file_exists(file_path):
    """检查文件是否存在"""
    full_path = PROJECT_ROOT / file_path
    return full_path.exists()

def preview_operations():
    """预览将要执行的操作"""
    print_section("📋 清理预览")
    
    # 归档操作
    print("\n📦 将要归档的文件:")
    archive_count = 0
    for category, files in FILES_TO_ARCHIVE.items():
        print(f"\n  [{category}]")
        for file in files:
            if check_file_exists(file):
                print(f"    ✓ {file}")
                archive_count += 1
            else:
                print(f"    ✗ {file} (不存在)")
    
    # 删除操作
    print("\n🗑️  将要删除的文件:")
    delete_count = 0
    for category, files in FILES_TO_DELETE.items():
        print(f"\n  [{category}]")
        for file in files:
            if check_file_exists(file):
                print(f"    ✓ {file}")
                delete_count += 1
            else:
                print(f"    ✗ {file} (不存在)")
    
    # 保留的文件
    print("\n✅ 保留的文件（正在使用）:")
    for file, reason in FILES_IN_USE.items():
        if check_file_exists(file):
            print(f"    ✓ {file} - {reason}")
    
    print(f"\n📊 统计:")
    print(f"    - 归档: {archive_count} 个文件")
    print(f"    - 删除: {delete_count} 个文件")
    print(f"    - 保留: {len([f for f in FILES_IN_USE if check_file_exists(f)])} 个文件")
    
    return archive_count + delete_count > 0

def create_archive_dirs():
    """创建归档目录"""
    dirs = [
        "archive/prompts",
        "archive/services",
        "archive/scripts",
        "scripts/fixes",
    ]
    for d in dirs:
        (PROJECT_ROOT / d).mkdir(parents=True, exist_ok=True)
    print("✅ 归档目录已创建")

def archive_files():
    """归档文件"""
    print_section("📦 开始归档")
    
    for category, files in FILES_TO_ARCHIVE.items():
        print(f"\n[{category}]")
        for file in files:
            src = PROJECT_ROOT / file
            if not src.exists():
                print(f"  ⚠️  跳过 {file} (不存在)")
                continue
            
            # 确定目标目录
            if "prompt" in file.lower():
                dest_dir = PROJECT_ROOT / "archive" / "prompts"
            elif file.startswith("fix_"):
                dest_dir = PROJECT_ROOT / "scripts" / "fixes"
            else:
                dest_dir = PROJECT_ROOT / "archive" / "scripts"
            
            dest = dest_dir / src.name
            
            try:
                shutil.move(str(src), str(dest))
                print(f"  ✅ {file} → {dest.relative_to(PROJECT_ROOT)}")
            except Exception as e:
                print(f"  ❌ 归档失败 {file}: {e}")

def delete_files():
    """删除文件"""
    print_section("🗑️  开始删除")
    
    for category, files in FILES_TO_DELETE.items():
        print(f"\n[{category}]")
        for file in files:
            src = PROJECT_ROOT / file
            if not src.exists():
                print(f"  ⚠️  跳过 {file} (不存在)")
                continue
            
            try:
                src.unlink()
                print(f"  ✅ 已删除 {file}")
            except Exception as e:
                print(f"  ❌ 删除失败 {file}: {e}")

def main():
    print_section("🧹 项目清理工具")
    print("\n此脚本将:")
    print("  1. 归档旧版本文件到 archive/ 目录")
    print("  2. 移动临时脚本到 scripts/fixes/ 目录")
    print("  3. 删除重复的旧文件")
    print("  4. 保留正在使用的文件")
    
    # 预览操作
    has_operations = preview_operations()
    
    if not has_operations:
        print("\n✅ 没有需要清理的文件")
        return
    
    # 确认
    print("\n" + "="*60)
    response = input("是否继续执行清理? (yes/no): ").strip().lower()
    
    if response not in ['yes', 'y']:
        print("❌ 已取消清理")
        return
    
    # 执行清理
    create_archive_dirs()
    archive_files()
    delete_files()
    
    print_section("✅ 清理完成")
    print("\n归档位置:")
    print("  - archive/prompts/     - 旧版 prompt")
    print("  - scripts/fixes/       - 临时修复脚本")
    print("\n建议:")
    print("  1. 检查归档文件是否正确")
    print("  2. 重启服务验证功能正常: python run.py")
    print("  3. 如果一切正常，可以删除 archive/ 目录")

if __name__ == "__main__":
    main()
