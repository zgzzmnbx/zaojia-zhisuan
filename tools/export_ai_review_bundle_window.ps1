param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $ProjectRoot) {
    $ProjectRoot = Join-Path $PSScriptRoot ".."
}

try {
    $ProjectRoot = $ProjectRoot.Trim().Trim('"')
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
}
catch {
    Write-Host ""
    Write-Host "ERROR: Cannot resolve project root."
    Write-Host $ProjectRoot
    Write-Host $_.Exception.Message
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

try {
    Set-Location -LiteralPath $ProjectRoot
}
catch {
    Write-Host ""
    Write-Host "ERROR: Cannot enter project root."
    Write-Host $ProjectRoot
    Write-Host $_.Exception.Message
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "================================================"
Write-Host " Zaojia Zhisuan - export AI review bundle"
Write-Host "================================================"
Write-Host ""
Write-Host "Project root:"
Write-Host $ProjectRoot
Write-Host ""

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$pythonArgs = @()
if (-not $pythonCommand) {
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
    $pythonArgs = @("-3")
}

if (-not $pythonCommand) {
    Write-Host "ERROR: Python was not found."
    Write-Host "Please install Python or add it to PATH."
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Python:"
Write-Host $pythonCommand.Source
Write-Host ""

$scriptPath = Join-Path $ProjectRoot "tools\export_ai_review_bundle.py"
if (-not (Test-Path -LiteralPath $scriptPath)) {
    Write-Host "ERROR: export script was not found."
    Write-Host $scriptPath
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

$allArgs = @()
$allArgs += $pythonArgs
$allArgs += @($scriptPath)

& $pythonCommand.Source @allArgs
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "DONE."
    Write-Host "Output folder is under:"
    Write-Host (Join-Path $ProjectRoot "04-输出版本存档")
    Write-Host ""
    Write-Host "Folder name pattern:"
    Write-Host "给其他AI查看-核心代码与规则-yyyy-mm-dd"
}
else {
    Write-Host "ERROR: Export failed. Exit code: $exitCode"
    Write-Host "Please send this window text to the maintainer."
}

Write-Host ""
Read-Host "Press Enter to close"
exit $exitCode
