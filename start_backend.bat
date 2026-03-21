@echo off
REM 面经 Agent 快速启动脚本（Windows）
REM 用法：双击运行或在 PowerShell 中执行

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║         面经 Agent 快速启动脚本                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM 检查 conda 环境
echo 🔍 检查 conda 环境...
where conda >nul 2>&1
if errorlevel 1 (
    echo ❌ 找不到 conda，请先安装 Anaconda
    pause
    exit /b 1
)

REM 激活环境
echo 🔄 激活 NewCoderAgent 环境...
call conda activate NewCoderAgent
if errorlevel 1 (
    echo ❌ 环境激活失败
    pause
    exit /b 1
)

REM 进入项目目录
cd /d "%~dp0"
if errorlevel 1 (
    echo ❌ 无法进入项目目录
    pause
    exit /b 1
)

REM 检查 Ollama
echo.
echo 🌐 检查 Ollama...
netstat -ano | findstr :11434 >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Ollama 未运行！
    echo.
    echo 请在新终端运行：ollama serve
    echo.
    pause
    exit /b 1
) else (
    echo ✅ Ollama 已运行
)

REM 启动后端
echo.
echo 🚀 启动后端服务...
echo.
python run.py --reload

pause
