@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM novel-create-hermes 环境初始化脚本 (Windows)
REM 支持多小说项目共享 .venv
REM ============================================================
REM 用法:
REM   setup_env.bat                        # 在 CWD 创建 .venv
REM   setup_env.bat novels/                # 在 novels/ 下创建 .venv
REM ============================================================

REM === 解析目标目录（%1）===
if "%~1"=="" (
    set "TARGET_DIR=%CD%"
) else (
    set "TARGET_DIR=%~1"
)
cd /d "!TARGET_DIR!" || (
    echo [错误] 目录不存在: !TARGET_DIR!
    pause
    exit /b 1
)

echo ========================================
echo novel-create-hermes 环境初始化
echo ========================================
echo 目标目录: !TARGET_DIR!
echo.

REM === 检测 Python 来源: 系统 Python -> conda Python ===

REM 1. 先检测系统 Python
python --version >nul 2>&1
if not errorlevel 1 (
    echo [检测] 使用系统 Python
    python --version
    echo.
    goto :check_venv
)

REM 2. 检测 conda 中的 Python
conda --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python 或 conda
    echo   - 安装 Python 3.8+: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [检测] 使用 conda base 中的 Python
conda run -n base python --version
echo.
set "USE_CONDA=1"
goto :check_venv

:check_venv
REM 检查是否已有虚拟环境
if exist ".venv" (
    echo [提示] 虚拟环境已存在
    echo.
    choice /M "是否重新创建"
    if errorlevel 2 goto :activate
    if errorlevel 1 goto :recreate
)

:recreate
echo [1/3] 创建虚拟环境...
if defined USE_CONDA (
    conda run -n base python -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 (
    echo [错误] 虚拟环境创建失败
    pause
    exit /b 1
)

:activate
echo [2/3] 激活虚拟环境...
call .venv\Scripts\activate.bat

echo [3/3] 安装依赖...
REM requirements.txt 位于本脚本同级目录
set "SCRIPT_DIR=%~dp0"
pip install -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 环境初始化完成！
echo ========================================
echo.
echo 小说项目根目录: !TARGET_DIR!
echo .venv 位置:      !TARGET_DIR!\.venv
echo.
echo 使用方式:
echo   1. 激活环境: call .venv\Scripts\activate.bat
echo   2. 验证环境: python .opencode/skills/novel-env-setup/scripts/setup.py
echo   3. 新建小说: python .opencode/skills/novel-project-manager/scripts/init.py new "小说名" "类型"
echo.
echo 多个小说项目共享此 .venv，无需重复创建。
echo.
pause
