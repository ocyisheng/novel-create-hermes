@echo off
REM novel-tool.bat — Windows cmd.exe 兼容层
REM 用法: novel-tool.bat <operation> [params...]
REM 把参数拼成 JSON 然后传给 Python 脚本

setlocal enabledelayedexpansion

set "ROOT=%~dp0..\.."
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "SCRIPT=%ROOT%\.opencode\shared\tools\novel_tool.py"

REM 构建 JSON 对象，从第一个参数开始当 operation
set "JSON={\"operation\":\"%~1\""
set "I=2"

:loop
if "%~2"=="" goto endloop
set "JSON=%JSON%,\"%~2\":\"%~3\""
shift
shift
goto loop
:endloop

set "JSON=%JSON%}"

"%PYTHON%" "%SCRIPT%" "%JSON%"
