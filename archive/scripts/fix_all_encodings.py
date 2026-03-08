#!/usr/bin/env python3
"""
扫描并修复目录下所有非UTF-8编码的文件
"""
import os
import sys
from pathlib import Path
import chardet

def detect_encoding(file_path):
    """检测文件编码"""
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            if not raw_data:
                return None, 0
            result = chardet.detect(raw_data)
            return result['encoding'], result['confidence']
    except Exception as e:
        print(f"[ERROR] 无法读取文件 {file_path}: {e}")
        return None, 0

def convert_to_utf8(file_path, source_encoding):
    """将文件转换为UTF-8编码"""
    try:
        # 读取原始内容
        with open(file_path, 'r', encoding=source_encoding, errors='ignore') as f:
            content = f.read()
        
        # 写入UTF-8编码
        with open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(content)
        
        return True
    except Exception as e:
        print(f"[ERROR] 转换失败 {file_path}: {e}")
        return False

def should_skip(file_path):
    """判断是否应该跳过该文件"""
    skip_dirs = {
        '.git', '__pycache__', 'node_modules', '.venv', 'venv',
        'dist', 'build', '.pytest_cache', '.mypy_cache',
        '牛客图片测试', 'web'  # 跳过图片目录和前端目录
    }
    
    skip_extensions = {
        '.pyc', '.pyo', '.so', '.dll', '.exe', '.bin',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
        '.pdf', '.zip', '.tar', '.gz', '.rar',
        '.mp3', '.mp4', '.avi', '.mov',
        '.db', '.sqlite', '.sqlite3'
    }
    
    # 检查是否在跳过的目录中
    parts = Path(file_path).parts
    if any(skip_dir in parts for skip_dir in skip_dirs):
        return True
    
    # 检查文件扩展名
    if Path(file_path).suffix.lower() in skip_extensions:
        return True
    
    return False

def scan_and_fix_directory(root_dir):
    """扫描并修复目录下所有文件"""
    root_path = Path(root_dir)
    
    print(f"开始扫描目录: {root_path}")
    print("=" * 60)
    
    total_files = 0
    checked_files = 0
    converted_files = 0
    failed_files = 0
    
    for file_path in root_path.rglob('*'):
        if not file_path.is_file():
            continue
        
        total_files += 1
        
        # 跳过不需要检查的文件
        if should_skip(str(file_path)):
            continue
        
        checked_files += 1
        
        # 检测编码
        encoding, confidence = detect_encoding(file_path)
        
        if encoding is None:
            continue
        
        # 如果不是UTF-8编码，进行转换
        if encoding.lower() not in ['utf-8', 'ascii']:
            print(f"\n发现非UTF-8文件:")
            print(f"  文件: {file_path}")
            print(f"  当前编码: {encoding} (置信度: {confidence:.2f})")
            
            if convert_to_utf8(file_path, encoding):
                print(f"  [OK] 已转换为UTF-8")
                converted_files += 1
            else:
                print(f"  [ERROR] 转换失败")
                failed_files += 1
    
    print("\n" + "=" * 60)
    print("扫描完成!")
    print(f"总文件数: {total_files}")
    print(f"检查文件数: {checked_files}")
    print(f"转换文件数: {converted_files}")
    print(f"失败文件数: {failed_files}")
    
    return converted_files, failed_files

if __name__ == "__main__":
    # 获取当前目录
    current_dir = Path(__file__).parent
    
    print("UTF-8编码修复工具")
    print("=" * 60)
    
    # 扫描并修复
    converted, failed = scan_and_fix_directory(current_dir)
    
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)
