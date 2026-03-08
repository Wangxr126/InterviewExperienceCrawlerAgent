"""分析项目中文件的使用情况"""
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

def find_references(filename, search_dirs):
    """在指定目录中搜索文件名的引用"""
    references = []
    pattern = re.compile(rf'\b{re.escape(filename)}\b')
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding='utf-8')
                if pattern.search(content):
                    references.append(str(py_file.relative_to(PROJECT_ROOT)))
            except Exception as e:
                pass
    return references

# 检查的文件列表
files_to_check = [
    "hunter_pipeline.py",
    "run_xhs_worker.py",
    "orchestrator.py",
    "fix_log_path.py",
    "fix_newline.py", 
    "fix_llm_log.py",
]

search_dirs = [
    PROJECT_ROOT / "backend",
    PROJECT_ROOT,
]

print("=" * 80)
print("文件使用情况分析")
print("=" * 80)

for filename in files_to_check:
    print(f"\n检查文件: {filename}")
    refs = find_references(filename.replace('.py', ''), search_dirs)
    if refs:
        print(f"  找到 {len(refs)} 处引用:")
        for ref in refs:
            print(f"    - {ref}")
    else:
        print(f"  ❌ 未找到引用（可能未使用）")

# 列出所有 fix_*.py 文件
print("\n" + "=" * 80)
print("所有 fix_*.py 临时修复脚本:")
print("=" * 80)
fix_files = list(PROJECT_ROOT.glob("fix_*.py"))
for f in fix_files:
    print(f"  - {f.name}")

# 列出所有旧的 prompt 文件
print("\n" + "=" * 80)
print("backend/prompts/ 目录下的文件:")
print("=" * 80)
prompts_dir = PROJECT_ROOT / "backend" / "prompts"
if prompts_dir.exists():
    for f in prompts_dir.iterdir():
        if f.is_file():
            print(f"  - {f.name}")
