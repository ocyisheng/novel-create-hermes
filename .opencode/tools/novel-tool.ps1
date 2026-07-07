# novel-tool.ps1 — PowerShell 兼容层
# 用法: .\novel-tool.ps1 '{json-string}'
# 确保用 .venv 的 Python

param(
    [Parameter(Mandatory=$true, ValueFromPipeline=$true)]
    [string]$JsonArg
)

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ToolScript = Join-Path $ProjectRoot ".opencode\shared\tools\novel_tool.py"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

# 用 stdin 传 JSON 避免引号转义问题
$JsonArg | & $Python $ToolScript 2>&1
