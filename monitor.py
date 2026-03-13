"""
实时监控面经 Agent 后端的进程、线程、内存状态

使用方法：
    conda activate NewCoderAgent
    python monitor.py

按 Ctrl+C 退出
"""
import psutil
import time
import os
from datetime import datetime

def format_bytes(bytes_val):
    """格式化字节数为可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} TB"

def get_python_processes():
    """获取所有 Python 进程"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'num_threads', 'cpu_percent']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return processes

def get_process_info(proc):
    """获取进程详细信息"""
    try:
        cmdline = ' '.join(proc.info['cmdline'] or [])
        # 简化命令行显示
        if 'run.py' in cmdline:
            desc = '🚀 启动脚本 (run.py)'
        elif 'uvicorn' in cmdline:
            desc = '⚡ FastAPI 服务器 (uvicorn)'
        elif 'backend.main:app' in cmdline:
            desc = '🔧 Worker 进程'
        else:
            desc = cmdline[:60] + '...' if len(cmdline) > 60 else cmdline
        
        mem = proc.memory_info()
        return {
            'pid': proc.info['pid'],
            'desc': desc,
            'memory_mb': mem.rss / 1024 / 1024,
            'threads': proc.info['num_threads'],
            'cpu_percent': proc.info['cpu_percent'],
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

def print_header():
    """打印表头"""
    print("\n" + "="*80)
    print(f"{'PID':<8} {'描述':<35} {'内存':<12} {'线程':<6} {'CPU%':<6}")
    print("="*80)

def print_process(info):
    """打印进程信息"""
    print(f"{info['pid']:<8} {info['desc']:<35} {info['memory_mb']:>8.1f} MB  {info['threads']:<6} {info['cpu_percent']:>5.1f}%")

def print_summary(processes):
    """打印汇总信息"""
    total_mem = sum(p['memory_mb'] for p in processes)
    total_threads = sum(p['threads'] for p in processes)
    print("-"*80)
    print(f"{'总计':<8} {len(processes)} 个进程{'':<22} {total_mem:>8.1f} MB  {total_threads:<6}")
    print("="*80)

def monitor_loop():
    """监控主循环"""
    print("\n🔍 面经 Agent 进程监控器")
    print("按 Ctrl+C 退出\n")
    
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            
            print(f"⏰ 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 获取所有 Python 进程
            procs = get_python_processes()
            
            if not procs:
                print("\n❌ 未找到 Python 进程")
                time.sleep(2)
                continue
            
            # 收集进程信息
            proc_infos = []
            for proc in procs:
                info = get_process_info(proc)
                if info:
                    proc_infos.append(info)
            
            # 按内存排序
            proc_infos.sort(key=lambda x: x['memory_mb'], reverse=True)
            
            # 打印表格
            print_header()
            for info in proc_infos:
                print_process(info)
            print_summary(proc_infos)
            
            # 系统整体状态
            cpu_percent = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            print(f"\n💻 系统状态:")
            print(f"   CPU 使用率: {cpu_percent:.1f}%")
            print(f"   内存使用率: {mem.percent:.1f}% ({format_bytes(mem.used)} / {format_bytes(mem.total)})")
            
            # 检查后端是否运行
            backend_running = any('uvicorn' in p['desc'] or 'backend.main' in p['desc'] for p in proc_infos)
            if backend_running:
                print(f"\n✅ 后端服务运行中")
            else:
                print(f"\n⚠️  后端服务未运行")
            
            print("\n刷新间隔: 2秒 | 按 Ctrl+C 退出")
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n\n👋 监控已停止")

if __name__ == "__main__":
    # 检查依赖
    try:
        import psutil
    except ImportError:
        print("❌ 缺少依赖: psutil")
        print("请运行: pip install psutil")
        exit(1)
    
    monitor_loop()
