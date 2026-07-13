param(
    [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendUrl = "http://127.0.0.1:8000/api/health"
$FrontendUrl = "http://127.0.0.1:5174"

function Import-LocalEnv {
    $envPath = Join-Path $ProjectDir ".env.local"
    if (-not (Test-Path -LiteralPath $envPath)) {
        return
    }

    Get-Content -LiteralPath $envPath -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }

        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
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

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction SilentlyContinue
    [pscustomobject]@{
        Port = $Port
        ProcessId = $connection.OwningProcess
        Name = if ($process) { $process.Name } else { "" }
        CommandLine = if ($process) { $process.CommandLine } else { "" }
    }
}

function Test-Backend {
    try {
        $response = Invoke-RestMethod -Uri $BackendUrl -TimeoutSec 2
        return ($response.status -eq "ok" -and $response.service -eq "guankanzhisuan")
    }
    catch {
        return $false
    }
}

function Test-Frontend {
    $owner = Get-PortOwner 5174
    if ($owner -and $owner.CommandLine -and $owner.CommandLine.Contains((Join-Path $ProjectDir "frontend"))) {
        return $true
    }

    try {
        $response = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -ge 200 -and $response.Content -match "<title>管勘智算</title>")
    }
    catch {
        return $false
    }
}

function Get-FeishuBotProcess {
    return Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "python*.exe" -and $_.CommandLine -and $_.CommandLine.Contains("feishu_bot_runner.py") } |
        Select-Object -First 1
}

function Test-FeishuBotConfigured {
    $settingsPath = Join-Path $ProjectDir "Codex-Temp\runtime\feishu-robot-settings.json"
    $legacySettingsPath = Join-Path $ProjectDir "Codex-Temp\runtime\feishu-app-settings.json"
    $controlPath = Join-Path $ProjectDir "Codex-Temp\runtime\feishu-bot\control.json"
    $defaultsPath = Join-Path $ProjectDir "config\project-default-settings.json"
    if (-not (Test-Path -LiteralPath $settingsPath) -and (Test-Path -LiteralPath $legacySettingsPath)) {
        $settingsPath = $legacySettingsPath
    }
    if (-not (Test-Path -LiteralPath $settingsPath) -or -not (Test-Path -LiteralPath $defaultsPath)) {
        return $false
    }
    try {
        $settings = Get-Content -LiteralPath $settingsPath -Encoding UTF8 -Raw | ConvertFrom-Json
        $defaults = Get-Content -LiteralPath $defaultsPath -Encoding UTF8 -Raw | ConvertFrom-Json
        $credentialStore = if ($settings.app_bot) { $settings.app_bot } else { $settings }
        $appId = [string]$credentialStore.app_id
        $appSecret = [string]$credentialStore.app_secret
        if ($credentialStore.profiles) {
            $activeProfile = [string]$credentialStore.active_profile
            $profile = $credentialStore.profiles.PSObject.Properties[$activeProfile].Value
            if ($profile) {
                $appId = [string]$profile.app_id
                $appSecret = [string]$profile.app_secret
            }
        }
        $enabled = $defaults.feishuAppBot.enabled -eq $true
        if (Test-Path -LiteralPath $controlPath) {
            $control = Get-Content -LiteralPath $controlPath -Encoding UTF8 -Raw | ConvertFrom-Json
            $enabled = $control.enabled -eq $true
        }
        return (
            $enabled -and
            -not [string]::IsNullOrWhiteSpace($appId) -and
            -not [string]::IsNullOrWhiteSpace($appSecret)
        )
    }
    catch {
        Write-Host "[提醒] 第二层机器人配置无法读取，已跳过自动启动。"
        return $false
    }
}

function Start-FeishuBot {
    if (-not (Test-FeishuBotConfigured)) {
        Write-Host "第二层机器人未启用或未配置，已跳过。"
        return
    }
    $running = Get-FeishuBotProcess
    if ($running) {
        Write-Host "第二层机器人已经在运行，PID: $($running.ProcessId)"
        return
    }
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-Command", "Set-Location -LiteralPath '$ProjectDir'; python backend\feishu_bot_runner.py"
    )
    Write-Host "已打开第二层飞书机器人窗口。"
}

function Write-PortOwner {
    param(
        [string]$Label,
        [object]$Owner
    )

    if (-not $Owner) {
        Write-Host "${Label}: 端口未占用"
        return
    }

    Write-Host "${Label}: 端口 $($Owner.Port) 已被占用"
    Write-Host "  PID: $($Owner.ProcessId)"
    Write-Host "  进程: $($Owner.Name)"
    if ($Owner.CommandLine) {
        Write-Host "  命令: $($Owner.CommandLine)"
    }
}

function Test-IsProjectProcess {
    param([object]$ProcessInfo)

    if (-not $ProcessInfo -or -not $ProcessInfo.CommandLine) {
        return $false
    }

    return (
        $ProcessInfo.CommandLine.Contains($ProjectDir) -or
        $ProcessInfo.CommandLine.Contains("uvicorn app.main:app") -or
        ($ProcessInfo.CommandLine.Contains("vite") -and $ProcessInfo.CommandLine.Contains("--port 5174"))
    )
}

function Get-ChildProcessIds {
    param([int]$ParentProcessId)

    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentProcessId" -ErrorAction SilentlyContinue)
    $ids = @()
    foreach ($child in $children) {
        $ids += [int]$child.ProcessId
        $ids += Get-ChildProcessIds -ParentProcessId ([int]$child.ProcessId)
    }
    return $ids
}

function Stop-PortOwner {
    param([object]$Owner)

    if (-not $Owner) {
        return
    }

    $ids = @([int]$Owner.ProcessId)
    $ids += Get-ChildProcessIds -ParentProcessId ([int]$Owner.ProcessId)

    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($Owner.ProcessId)" -ErrorAction SilentlyContinue
    if (Test-IsProjectProcess $processInfo) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($processInfo.ParentProcessId)" -ErrorAction SilentlyContinue
        if (Test-IsProjectProcess $parent) {
            $ids += [int]$parent.ProcessId
            $ids += Get-ChildProcessIds -ParentProcessId ([int]$parent.ProcessId)
        }
    }

    $ids = $ids | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique
    foreach ($id in $ids) {
        try {
            Stop-Process -Id $id -Force -ErrorAction Stop
            Write-Host "已结束进程 PID: $id"
        }
        catch {
            Write-Host "[提醒] 无法结束 PID $id：$($_.Exception.Message)"
        }
    }
}

function Confirm-PortRestart {
    param(
        [bool]$BackendOk,
        [bool]$FrontendOk,
        [object]$BackendOwner,
        [object]$FrontendOwner
    )

    if (-not $BackendOwner -and -not $FrontendOwner) {
        return $true
    }

    Write-Host "[提醒] 检测到固定端口已被占用。"
    Write-Host ""
    Write-PortOwner "后端端口" $BackendOwner
    Write-Host ""
    Write-PortOwner "前端端口" $FrontendOwner
    Write-Host ""

    if ($BackendOk -and $FrontendOk) {
        Write-Host "检测到管勘智算已经在后台运行。"
        Write-Host "请选择："
        Write-Host "  O = 打开现有网页，不重启"
        Write-Host "  R = 结束当前占用进程，然后重启应用"
        Write-Host "  Q = 退出"
        $choice = Read-Host "请输入 O/R/Q，直接回车默认 O"
        if (-not $choice) {
            $choice = "O"
        }
        switch ($choice.Trim().ToUpperInvariant()) {
            "R" { }
            "Q" { return $false }
            default {
                Start-FeishuBot
                Start-Process $FrontendUrl
                Write-Host "已打开现有网页: $FrontendUrl"
                return $false
            }
        }
    }
    else {
        Write-Host "端口被占用，程序无法直接启动，也不会自动换端口。"
        Write-Host "请选择："
        Write-Host "  R = 结束上面显示的占用进程，然后启动应用"
        Write-Host "  Q = 退出"
        $choice = Read-Host "请输入 R/Q，直接回车默认 Q"
        if (-not $choice -or $choice.Trim().ToUpperInvariant() -ne "R") {
            Write-Host "已取消启动。"
            return $false
        }
    }

    Stop-PortOwner $BackendOwner
    Stop-PortOwner $FrontendOwner
    Start-Sleep -Seconds 2
    return $true
}

function Show-Status {
    $backendOk = Test-Backend
    $frontendOk = Test-Frontend
    $backendOwner = Get-PortOwner 8000
    $frontendOwner = Get-PortOwner 5174
    $feishuBot = Get-FeishuBotProcess

    Write-Host "管勘智算运行状态"
    Write-Host "项目目录: $ProjectDir"
    Write-Host ""
    Write-Host "后端: $(if ($backendOk) { '已启动，服务身份正确' } else { '未检测到管勘智算后端' })"
    Write-PortOwner "后端端口" $backendOwner
    Write-Host ""
    Write-Host "前端: $(if ($frontendOk) { '已启动，网页身份正确' } else { '未检测到管勘智算前端' })"
    Write-PortOwner "前端端口" $frontendOwner
    Write-Host ""
    Write-Host "第二层飞书机器人: $(if ($feishuBot) { "已启动，PID: $($feishuBot.ProcessId)" } elseif (Test-FeishuBotConfigured) { '已配置但未启动' } else { '未启用或未配置' })"
    Write-Host ""
    if ($backendOk -and $frontendOk) {
        Write-Host "程序已经在运行，可以访问: $FrontendUrl"
    }
    elseif (($backendOwner -and -not $backendOk) -or ($frontendOwner -and -not $frontendOk)) {
        Write-Host "检测到端口被占用，但不是当前程序的完整服务。启动器不会自动换端口。"
        Write-Host "请先关闭上面显示的占用进程，或把占用信息交给 Codex 排查。"
    }
    else {
        Write-Host "程序未完整启动。可以双击桌面快捷方式：管勘智算-启动"
    }
}

function Start-App {
    if (-not (Test-Path (Join-Path $ProjectDir "backend\app\main.py"))) {
        throw "backend\app\main.py 不存在，请确认启动器位于项目根目录。"
    }
    if (-not (Test-Path (Join-Path $ProjectDir "frontend\package.json"))) {
        throw "frontend\package.json 不存在，请确认启动器位于项目根目录。"
    }
    if (-not (Test-Path (Join-Path $ProjectDir "frontend\node_modules"))) {
        throw "frontend\node_modules 不存在，请先运行：cd frontend; npm install"
    }
    Import-LocalEnv

    $backendOk = Test-Backend
    $frontendOk = Test-Frontend
    $backendOwner = Get-PortOwner 8000
    $frontendOwner = Get-PortOwner 5174

    Write-Host "启动管勘智算"
    Write-Host "项目目录: $ProjectDir"
    Write-Host ""

    if ($backendOwner -or $frontendOwner) {
        $shouldStart = Confirm-PortRestart `
            -BackendOk $backendOk `
            -FrontendOk $frontendOk `
            -BackendOwner $backendOwner `
            -FrontendOwner $frontendOwner
        if (-not $shouldStart) {
            return
        }

        $backendOk = Test-Backend
        $frontendOk = Test-Frontend
    }

    if ($backendOk) {
        Write-Host "后端已经在运行。"
    }
    else {
        Start-Process powershell -ArgumentList @(
            "-NoExit",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command",
            "Set-Location -LiteralPath '$ProjectDir'; python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend"
        )
        Write-Host "已打开后端服务窗口。"
    }

    if ($frontendOk) {
        Write-Host "前端已经在运行。"
    }
    else {
        Start-Process powershell -ArgumentList @(
            "-NoExit",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command",
            "Set-Location -LiteralPath '$ProjectDir\frontend'; npm run dev -- --host 127.0.0.1 --port 5174"
        )
        Write-Host "已打开前端服务窗口。"
    }

    Write-Host "等待服务就绪..."
    $deadline = (Get-Date).AddSeconds(45)
    do {
        $backendOk = Test-Backend
        $frontendOk = Test-Frontend
        if ($backendOk -and $frontendOk) {
            break
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    if ($backendOk -and $frontendOk) {
        Start-FeishuBot
        Start-Process $FrontendUrl
        Write-Host "已打开网页: $FrontendUrl"
    }
    else {
        Write-Host "[提醒] 服务没有在 45 秒内完整就绪。"
        Show-Status
        exit 2
    }
}

try {
    if ($StatusOnly) {
        Show-Status
    }
    else {
        Start-App
    }
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)"
    exit 1
}
