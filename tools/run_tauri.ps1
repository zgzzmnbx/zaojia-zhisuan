param(
    [ValidateSet("dev", "build")]
    [string]$Mode = "dev"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $ProjectDir

function Add-CargoPath {
    $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    if ((Test-Path -LiteralPath (Join-Path $cargoBin "cargo.exe")) -and ($env:Path -notlike "*$cargoBin*")) {
        $env:Path = "$cargoBin;$env:Path"
    }
}

function Import-VsDevEnvironment {
    if (Get-Command link.exe -ErrorAction SilentlyContinue) {
        return
    }

    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $vswhere)) {
        return
    }

    $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $installPath) {
        return
    }

    $devCmd = Join-Path $installPath "Common7\Tools\VsDevCmd.bat"
    if (-not (Test-Path -LiteralPath $devCmd)) {
        return
    }

        Write-Host "Loading Visual Studio C++ build environment..."
    $environment = cmd /s /c "`"$devCmd`" -arch=x64 -host_arch=x64 >nul && set"
    foreach ($line in $environment) {
        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
        }
    }
}

function Require-Command {
    param(
        [string]$Name,
        [string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "[ERROR] $Name is not available."
        Write-Host $InstallHint
        exit 1
    }
}

function Test-Backend {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
        return ($response.status -eq "ok" -and $response.service -eq "guankanzhisuan")
    }
    catch {
        return $false
    }
}

function Get-PortOwner {
    param([int]$Port)

    $connection = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $connection) {
        $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
    }
    if (-not $connection) {
        return $null
    }
    return $connection.OwningProcess
}

function Start-DevBackend {
    if (Test-Backend) {
        Write-Host "Backend already running: http://127.0.0.1:8000"
        return $null
    }

    $owner = Get-PortOwner 8000
    if ($owner) {
        Write-Host "[ERROR] Port 8000 is occupied, but it is not a healthy 造价智算 backend. PID=$owner"
        exit 1
    }

    $logDir = Join-Path $ProjectDir ".runtime\logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stdout = Join-Path $logDir "tauri-dev-backend.log"
    $stderr = Join-Path $logDir "tauri-dev-backend-error.log"
    $frontendDist = Join-Path $ProjectDir "frontend\dist"

    $env:GUANKAN_FRONTEND_DIR = $frontendDist
    $env:PYTHONUTF8 = "1"
    $backendPath = Join-Path $ProjectDir "backend"
    $pythonLibs = Join-Path $ProjectDir "runtime\python-libs"
    if (Test-Path -LiteralPath $pythonLibs) {
        $env:PYTHONPATH = "$pythonLibs;$backendPath;$env:PYTHONPATH"
    }
    else {
        $env:PYTHONPATH = "$backendPath;$env:PYTHONPATH"
    }

    Write-Host "Starting backend for Tauri dev: http://127.0.0.1:8000"
    $process = Start-Process -FilePath "python" -ArgumentList @(
        "-m", "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--app-dir", "backend"
    ) -WorkingDirectory $ProjectDir -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

    $deadline = (Get-Date).AddSeconds(75)
    do {
        if (Test-Backend) {
            Write-Host "Backend ready. PID=$($process.Id)"
            return $process
        }
        if ($process.HasExited) {
            Write-Host "[ERROR] Backend exited before health check passed. See $stderr"
            exit 1
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    Write-Host "[ERROR] Backend did not become healthy within 75 seconds. See $stderr"
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

Add-CargoPath
Import-VsDevEnvironment

Require-Command "cargo.exe" "Install Rust or add $env:USERPROFILE\.cargo\bin to PATH. Recommended: winget install Rustlang.Rustup"
Require-Command "link.exe" "Install Visual Studio Build Tools with C++ tools. Recommended: winget install Microsoft.VisualStudio.2022.BuildTools --override `"--wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended`""

if (-not $env:CARGO_HTTP_TIMEOUT) {
    $env:CARGO_HTTP_TIMEOUT = "600"
}
if (-not $env:CARGO_HTTP_LOW_SPEED_LIMIT) {
    $env:CARGO_HTTP_LOW_SPEED_LIMIT = "0"
}

Write-Host "Rust: $(& cargo --version)"
Write-Host "C++ linker: $((Get-Command link.exe).Source)"
Write-Host "Mode: tauri $Mode"
Write-Host ""

npm run frontend:build
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$devBackend = $null
if ($Mode -eq "dev") {
    $devBackend = Start-DevBackend
}

$tauriCli = Join-Path $ProjectDir "node_modules\.bin\tauri.cmd"
if (-not (Test-Path -LiteralPath $tauriCli)) {
    npm install
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

try {
    & $tauriCli $Mode
    exit $LASTEXITCODE
}
finally {
    if ($devBackend -and -not $devBackend.HasExited) {
        Write-Host "Stopping Tauri dev backend. PID=$($devBackend.Id)"
        Stop-Process -Id $devBackend.Id -Force -ErrorAction SilentlyContinue
    }
}
