"""
项目清理脚本 - 归档未使用的文件

功能：
1. 将临时修复脚本移动到 archived/temp_fixes/
2. 将未使用的服务移动到 archived/unused_services/
3. 将旧的 Prompt 移动到 archived/old_prompts/
4. 将分析工具移动到 archived/tools/

使用方式：
    python cleanup_project.py

注意：
- 会先显示将要移动的文件，询问确认后才执行
- 所有操作都是移动（不是删除），可以随时恢复
"""
import os
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent

# 定义归档规则
ARCHIVE_RULES = {
    "temp_fixes": {
        "description": "临时修复脚本（已完成使命）",
        "files": [
            "fix_log_path.py",
            "fix_newline.py",
            "fix_llm_log.py",
            "fix_indent.py",
        ]
    },
    "unused_services": {
        "description": "未使用的服务",
        "files": [
            "backend/services/hunter_pipeline.py",
            "backend/services/crawler/ocr_service.py",
        ]
    },
    "old_prompts": {
        "description": "旧的 Prompt 文件",
        "files": [
            "backend/prompts/knowledge_manager_prompt.py",
        ]
    },
    "tools": {
        "description": "临时分析工具",
        "files": [
            "analyze_usage.py",
            "cleanup.py",  # 如果存在
        ]
    }
}


def print_banner(text):
    """打印带边框的标题"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)


def check_files_exist():
    """检查哪些文件实际存在"""
    existing_files = {}
    for category, info in ARCHIVE_RULES.items():
        existing = []
        for file_path in info["files"]:
            full_path = PROJECT_ROOT / file_path
            if full_path.exists():
                existing.append(file_path)
        if existing:
            existing_files[category] = {
                "description": info["description"],
                "files": existing
            }
    return existing_files


def preview_changes(existing_files):
    """预览将要执行的操作"""
    print_banner("将要归档的文件")
    
    total_files = 0
    for category, info in existing_files.items():
        print(f"\n[{category}] {info['description']} -> archived/{category}/")
        for file_path in info["files"]:
            print(f"   + {file_path}")
            total_files += 1
    
    print(f"\n共 {total_files} 个文件将被移动到 archived/ 目录")
    return total_files


def create_archive_dirs():
    """创建归档目录结构"""
    archive_root = PROJECT_ROOT / "archived"
    archive_root.mkdir(exist_ok=True)
    
    # 创建 README
    readme_path = archive_root / "README.md"
    if not readme_path.exists():
        readme_content = f"""# 归档文件

本目录存放已不再使用的代码文件，保留用于参考。

**归档时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 目录说明

- `temp_fixes/`：临时修复脚本（已完成使命）
- `unused_services/`：未使用的服务模块
- `old_prompts/`：旧版 Prompt 文件
- `tools/`：临时分析工具

## 恢复文件

如需恢复某个文件，只需将其移回原位置即可。
"""
        readme_path.write_text(readme_content, encoding="utf-8")
    
    # 创建子目录
    for category in ARCHIVE_RULES.keys():
        (archive_root / category).mkdir(exist_ok=True)
    
    print("[OK] 归档目录结构已创建")


def move_files(existing_files):
    """移动文件到归档目录"""
    archive_root = PROJECT_ROOT / "archived"
    moved_count = 0
    
    for category, info in existing_files.items():
        target_dir = archive_root / category
        
        for file_path in info["files"]:
            source = PROJECT_ROOT / file_path
            # 保持原有的目录结构
            relative_path = Path(file_path)
            if len(relative_path.parts) > 1:
                # 如果是子目录中的文件，保持目录结构
                target = target_dir / relative_path.name
            else:
                target = target_dir / relative_path.name
            
            try:
                shutil.move(str(source), str(target))
                print(f"   [OK] 已移动: {file_path} -> archived/{category}/{target.name}")
                moved_count += 1
            except Exception as e:
                print(f"   [FAIL] 移动失败: {file_path} - {e}")
    
    return moved_count


def main():
    print_banner("项目清理工具")
    print("\n本工具将归档以下类型的文件：")
    print("  - 临时修复脚本（fix_*.py）")
    print("  - 未使用的服务（hunter_pipeline.py, ocr_service.py）")
    print("  - 旧的 Prompt 文件")
    print("  - 临时分析工具")
    print("\n所有文件将被移动到 archived/ 目录，不会删除。")
    
    # 检查文件
    existing_files = check_files_exist()
    
    if not existing_files:
        print("\n[OK] 没有需要归档的文件，项目已经很干净了！")
        return
    
    # 预览
    total_files = preview_changes(existing_files)
    
    # 确认
    print("\n" + "-" * 80)
    response = input("确认执行归档操作？(yes/no): ").strip().lower()
    
    if response not in ["yes", "y"]:
        print("\n已取消操作。")
        return
    
    # 执行
    print_banner("开始归档")
    create_archive_dirs()
    moved_count = move_files(existing_files)
    
    # 总结
    print_banner("归档完成")
    print(f"\n[OK] 成功移动 {moved_count}/{total_files} 个文件到 archived/ 目录")
    print(f"[OK] 如需恢复，可在 archived/ 目录中找到这些文件")
    print(f"\n建议：查看 SYSTEM_FLOW_ANALYSIS.md 了解完整的系统流程")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消操作。")
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
