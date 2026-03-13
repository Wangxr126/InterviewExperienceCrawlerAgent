@echo off
chcp 65001 >nul
echo ========================================
echo 面经 Agent 修复后测试启动
echo ========================================
echo.
echo 正在启动后端（4个worker进程）...
echo 请观察日志是否只打印一次（不重复）
echo.
echo 启动后请测试：
echo 1. 发送消息，观察对话框是否实时刷新
echo 2. 切换到其他页面再回来，观察会话是否保留
echo.
echo 按 Ctrl+C 停止服务
echo ========================================
echo.

cd /d "%~dp0"
call conda activate NewCoderAgent
python run.py --workers 4
