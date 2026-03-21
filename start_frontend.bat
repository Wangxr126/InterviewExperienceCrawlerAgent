@echo off
REM 面经 Agent 前端启动脚本（Windows）

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║         面经 Agent 前端启动脚本                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM 进入前端目录
cd /d "%~dp0web"
if errorlevel 1 (
    echo ❌ 无法进入前端目录
    pause
    exit /b 1
)

REM 检查 node_modules
if not exist "node_modules" (
    echo 📦 安装依赖...
    call npm install
    if errorlevel 1 (
        echo ❌ 依赖安装失败
        pause
        exit /b 1
    )
)

REM 启动前端
echo.
echo 🚀 启动前端开发服务器...
echo.
echo 打开浏览器访问：http://localhost:5173
echo.
call npm run dev

pause
