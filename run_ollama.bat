@echo off
chcp 65001 >nul
REM 以模型常驻显存方式启动 Ollama（OLLAMA_KEEP_ALIVE=-1）
REM 首次使用前请先拉取模型：ollama pull qwen2.5:1.5b
cd /d "%~dp0"
set OLLAMA_KEEP_ALIVE=-1

REM 尝试常见 Ollama 路径（Windows 默认 %LOCALAPPDATA%\Programs\Ollama）
set OLLAMA_EXE=
where ollama >nul 2>&1 && set OLLAMA_EXE=ollama
if "%OLLAMA_EXE%"=="" if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe
if "%OLLAMA_EXE%"=="" (
    echo.
    echo [错误] 未找到 ollama 命令
    echo   1. 请确认已安装 Ollama: https://ollama.com/download
    echo   2. 若已安装，请重启终端或电脑使 PATH 生效
    echo   3. 或手动将 Ollama 安装目录加入系统 PATH
    echo.
    pause
    exit /b 1
)

echo [启动] Ollama 模型常驻显存模式 ^(OLLAMA_KEEP_ALIVE=-1^)
echo.
"%OLLAMA_EXE%" serve 2>&1
if errorlevel 1 (
    echo.
    echo [提示] 若提示端口 11434 已被占用，说明 Ollama 已在运行。
    echo   如需模型常驻显存：设置系统环境变量 OLLAMA_KEEP_ALIVE=-1 后重启 Ollama 即可。
    echo.
)
pause
