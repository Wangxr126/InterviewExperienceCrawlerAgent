@echo off
REM 面经Agent启动脚本
REM 自动激活conda环境并启动后端

echo ========================================
echo 面经Agent启动脚本
echo ========================================
echo.

echo [1/2] 激活Conda环境: NewCoderAgent
call conda activate NewCoderAgent
if errorlevel 1 (
    echo 错误: 无法激活环境 NewCoderAgent
    echo 请确保已创建此环境: conda create -n NewCoderAgent python=3.10
    pause
    exit /b 1
)

echo [2/2] 启动后端服务...
echo.
python run.py

pause
