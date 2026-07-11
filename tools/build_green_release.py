from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_NAME = "造价智算"
RELEASE_KIND = "绿色版"
BACKEND_PORT = 8000
FRONTEND_PORT = 5174
PYTHON_EMBED_VERSION = "3.14.3"
PYTHON_EMBED_ZIP = f"python-{PYTHON_EMBED_VERSION}-embed-amd64.zip"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_EMBED_VERSION}/{PYTHON_EMBED_ZIP}"
NODE_VERSION = "24.14.1"
NODE_ZIP = f"node-v{NODE_VERSION}-win-x64.zip"
NODE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_ZIP}"
PROJECT_DEFAULT_SETTINGS_RELATIVE_PATH = Path("config/project-default-settings.json")
DEFAULT_PREVIEW_CELL_MAX_DISPLAY_CHARS = 8
DEFAULT_CORE_PREVIEW_LABELS = [
    "要素1",
    "要素2",
    "要素3",
    "要素4",
    "要素5",
    "单位",
    "单价",
    "实物工作费调整系数",
    "技术工作费调整系数",
    "预警参数",
    "预警细节",
]


LAUNCHER_PS1 = r'''param(
    [switch]$StatusOnly,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendUrl = "http://127.0.0.1:8000/api/health"
$FrontendUrl = "http://127.0.0.1:5174"
$RuntimeDir = Join-Path $ProjectDir ".runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$BackendPidPath = Join-Path $RuntimeDir "backend-shell.pid"
$FrontendPidPath = Join-Path $RuntimeDir "frontend-shell.pid"

function Write-Trace {
    param([string]$Message)
    try {
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
        Add-Content -LiteralPath (Join-Path $LogDir "traditional-launcher-trace.log") -Encoding UTF8 -Value "$((Get-Date).ToString('s')) $Message"
    }
    catch {
    }
}

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
        ExecutablePath = if ($process) { $process.ExecutablePath } else { "" }
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
    if ($owner -and $owner.CommandLine -and $owner.CommandLine.Contains($ProjectDir)) {
        return $true
    }

    try {
        $response = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -ge 200 -and ($response.Content -match "<title>管勘智算</title>" -or $response.Content -match "<title>造价智算</title>"))
    }
    catch {
        return $false
    }
}

function Test-IsCurrentReleaseProcess {
    param([object]$Owner)
    return ($Owner -and $Owner.CommandLine -and $Owner.CommandLine.Contains($ProjectDir))
}

function Test-IsKnownProjectProcess {
    param([object]$Owner)
    if (-not $Owner -or -not $Owner.CommandLine) {
        return $false
    }
    return (
        $Owner.CommandLine.Contains("uvicorn app.main:app") -or
        $Owner.CommandLine.Contains("vite") -or
        $Owner.CommandLine.Contains("npm") -or
        $Owner.CommandLine.Contains("node")
    )
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

function Stop-PidTree {
    param([int]$RootPid)
    $ids = @($RootPid)
    $ids += Get-ChildProcessIds -ParentProcessId $RootPid
    $ids = $ids | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique -Descending
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

function Stop-PortOwner {
    param([object]$Owner)
    if ($Owner) {
        Stop-PidTree -RootPid ([int]$Owner.ProcessId)
    }
}

function Stop-App {
    foreach ($pidPath in @($BackendPidPath, $FrontendPidPath)) {
        if (Test-Path -LiteralPath $pidPath) {
            $savedPid = [int](Get-Content -LiteralPath $pidPath -Encoding UTF8 | Select-Object -First 1)
            if ($savedPid) {
                Stop-PidTree -RootPid $savedPid
            }
            Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        }
    }

    foreach ($owner in @((Get-PortOwner 8000), (Get-PortOwner 5174))) {
        if ($owner -and (Test-IsKnownProjectProcess $owner)) {
            Stop-PortOwner $owner
        }
    }
    Write-Host "停止操作完成。"
}

function Resolve-PythonExe {
    $portablePython = Join-Path $ProjectDir "runtime\python\python.exe"
    if (-not (Test-Path -LiteralPath $portablePython)) {
        throw "runtime\python\python.exe 不存在。请重新解压完整绿色版。"
    }
    return $portablePython
}

function Resolve-NpmCmd {
    $npmCmd = Join-Path $ProjectDir "runtime\node\npm.cmd"
    if (-not (Test-Path -LiteralPath $npmCmd)) {
        throw "runtime\node\npm.cmd 不存在。请重新解压完整绿色版。"
    }
    return $npmCmd
}

function Prepare-Env {
    $env:PYTHONUTF8 = "1"
    $env:GUANKAN_FRONTEND_DIR = ""

    $pythonLibs = Join-Path $ProjectDir "runtime\python-libs"
    $backendPath = Join-Path $ProjectDir "backend"
    if (Test-Path -LiteralPath $pythonLibs) {
        $env:PYTHONPATH = "$pythonLibs;$backendPath"
    }
    else {
        $env:PYTHONPATH = $backendPath
    }

    $nodeDir = Join-Path $ProjectDir "runtime\node"
    if (Test-Path -LiteralPath $nodeDir) {
        $env:PATH = "$nodeDir;$env:PATH"
    }
}

function Ensure-PortsReady {
    $backendOwner = Get-PortOwner 8000
    $frontendOwner = Get-PortOwner 5174
    $backendOk = Test-Backend
    $frontendOk = Test-Frontend

    if ($backendOwner -and (Test-IsCurrentReleaseProcess $backendOwner) -and $backendOk -and
        $frontendOwner -and (Test-IsCurrentReleaseProcess $frontendOwner) -and $frontendOk) {
        return "already-current"
    }

    $owners = @($backendOwner, $frontendOwner) | Where-Object { $_ }
    if (-not $owners) {
        return "free"
    }

    Write-Host "[提醒] 检测到固定端口已被占用。"
    Write-PortOwner "后端端口" $backendOwner
    Write-PortOwner "前端端口" $frontendOwner

    $unknownOwners = @($owners | Where-Object { -not (Test-IsKnownProjectProcess $_) })
    if ($unknownOwners.Count -gt 0) {
        Write-Host "端口被其他程序占用。为避免误杀进程，请先手动关闭上面显示的程序后再启动。"
        throw "端口被非造价智算程序占用。"
    }

    Write-Host "检测到旧版或其他目录的造价智算服务，正在结束后启动当前输出版..."
    foreach ($owner in $owners) {
        Stop-PortOwner $owner
    }
    Start-Sleep -Seconds 2
    return "restarted"
}

function Show-Status {
    Import-LocalEnv
    $backendOk = Test-Backend
    $frontendOk = Test-Frontend
    $backendOwner = Get-PortOwner 8000
    $frontendOwner = Get-PortOwner 5174

    Write-Host "造价智算绿色版状态"
    Write-Host "目录: $ProjectDir"
    Write-Host "页面: $FrontendUrl"
    Write-Host "后端: $(if ($backendOk) { '已启动' } else { '未启动' })"
    Write-PortOwner "后端端口" $backendOwner
    Write-Host "前端: $(if ($frontendOk) { '已启动' } else { '未启动' })"
    Write-PortOwner "前端端口" $frontendOwner
    Write-Host "Python: $(Resolve-PythonExe)"
    Write-Host "Node/npm: $(Resolve-NpmCmd)"
}

function Start-App {
    Write-Trace "Start-App:start"
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir "backend\app\main.py"))) {
        throw "backend\app\main.py 不存在，请确认目录完整。"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir "frontend\package.json"))) {
        throw "frontend\package.json 不存在，请确认目录完整。"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir "frontend\node_modules"))) {
        throw "frontend\node_modules 不存在，请重新生成绿色版。"
    }

    Import-LocalEnv
    Prepare-Env
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

    $portState = Ensure-PortsReady
    if ($portState -eq "already-current") {
        Write-Host "当前输出版已经在运行，正在打开网页..."
        Start-Process $FrontendUrl
        return
    }

    $python = Resolve-PythonExe
    $npm = Resolve-NpmCmd

    Write-Host "正在启动造价智算绿色版..."
    Write-Host "后端: http://127.0.0.1:8000"
    Write-Host "前端: http://127.0.0.1:5174"

    $backendCommand = @"
`$ErrorActionPreference='Stop'
Set-Location -LiteralPath '$ProjectDir'
`$env:PYTHONUTF8='1'
`$env:PYTHONPATH='$env:PYTHONPATH'
`$env:PATH='$env:PATH'
& '$python' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
"@
    $backendProcess = Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", $backendCommand
    ) -WorkingDirectory $ProjectDir -PassThru
    Set-Content -LiteralPath $BackendPidPath -Value $backendProcess.Id -Encoding UTF8

    $frontendCommand = @"
`$ErrorActionPreference='Stop'
Set-Location -LiteralPath '$ProjectDir\frontend'
`$env:PATH='$env:PATH'
& '$npm' run dev -- --host 127.0.0.1 --port 5174
"@
    $frontendProcess = Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", $frontendCommand
    ) -WorkingDirectory (Join-Path $ProjectDir "frontend") -PassThru
    Set-Content -LiteralPath $FrontendPidPath -Value $frontendProcess.Id -Encoding UTF8

    Write-Host "等待服务就绪..."
    $deadline = (Get-Date).AddSeconds(75)
    do {
        if ((Test-Backend) -and (Test-Frontend)) {
            Start-Process $FrontendUrl
            Write-Host "已打开网页: $FrontendUrl"
            return
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    Write-Host "[提醒] 服务没有在 75 秒内完整就绪。"
    Show-Status
    throw "启动失败，请查看两个服务窗口中的错误信息。"
}

try {
    if ($Stop) {
        Stop-App
    }
    elseif ($StatusOnly) {
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
'''


START_BAT = r'''@echo off
setlocal
chcp 65001 >nul
set "PROJECT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%造价智算传统启动器.ps1"
echo.
echo 按任意键关闭本窗口。后端和前端服务窗口需要保持打开；停止请双击 停止造价智算.bat。
pause >nul
'''


STOP_BAT = r'''@echo off
setlocal
chcp 65001 >nul
set "PROJECT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%造价智算传统启动器.ps1" -Stop
echo.
echo 按任意键关闭本窗口。
pause >nul
'''


STATUS_BAT = r'''@echo off
setlocal
chcp 65001 >nul
set "PROJECT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%造价智算传统启动器.ps1" -StatusOnly
echo.
echo 按任意键关闭本窗口。
pause >nul
'''


CONFIG_LLM_BAT = r'''@echo off
setlocal
chcp 65001 >nul
set "PROJECT_DIR=%~dp0"
set "ENV_FILE=%PROJECT_DIR%.env.local"
set "ENV_EXAMPLE=%PROJECT_DIR%.env.local.example"

if not exist "%ENV_FILE%" (
  if exist "%ENV_EXAMPLE%" (
    copy "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
  ) else (
    (
      echo # 造价智算本地可选配置
      echo # 官方 DeepSeek
      echo DEEPSEEK_API_KEY=
      echo.
      echo # 硅基流动兼容模式
      echo SILICONFLOW_API_KEY=
    ) > "%ENV_FILE%"
  )
)

echo 已打开配置文件：%ENV_FILE%
echo.
echo 请填写 DEEPSEEK_API_KEY=你的Key 后保存。
echo 如果程序已经启动，请先双击 停止造价智算.bat，再重新启动。
echo.
start "" notepad "%ENV_FILE%"
pause
'''


def detect_version(project_root: Path) -> str:
    text = (project_root / "README.md").read_text(encoding="utf-8")
    match = re.search(r"当前版本[：:]\s*`?([vV]\d+(?:\.\d+)+)`?", text)
    if not match:
        raise ValueError("README.md 中未找到当前版本号")
    return match.group(1).lower()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def run(command: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def npm_command() -> str:
    return "npm.cmd" if sys.platform.startswith("win") else "npm"


def copy_file(project_root: Path, release_root: Path, relative: str) -> None:
    source = project_root / relative
    if not source.exists() or not source.is_file():
        print(f"[skip] missing file: {relative}")
        return
    target = release_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def ignore_python_generated(_: str, names: list[str]) -> set[str]:
    return {name for name in names if name in {"__pycache__", ".pytest_cache"} or name.endswith(".pyc")}


def copy_tree(source: Path, target: Path, ignore=None) -> None:
    if not source.exists():
        print(f"[skip] missing dir: {source}")
        return
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=ignore)


def copy_glob(project_root: Path, release_root: Path, base: str, pattern: str) -> None:
    base_path = project_root / base
    if not base_path.exists():
        return
    for source in base_path.glob(pattern):
        if source.is_file() and not source.name.startswith("~$"):
            relative = source.relative_to(project_root)
            target = release_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if path.suffix.lower() == ".ps1" else "utf-8"
    path.write_text(text, encoding=encoding)


def install_portable_python(project_root: Path, release_root: Path) -> None:
    cache_dir = project_root / ".build-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / PYTHON_EMBED_ZIP
    if not zip_path.exists():
        print(f"download={PYTHON_EMBED_URL}")
        urllib.request.urlretrieve(PYTHON_EMBED_URL, zip_path)

    python_dir = release_root / "runtime" / "python"
    if python_dir.exists():
        shutil.rmtree(python_dir)
    python_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as archive:
        archive.extractall(python_dir)

    pth_files = sorted(python_dir.glob("python*._pth"))
    if not pth_files:
        raise FileNotFoundError(f"未找到 embeddable Python _pth 文件：{python_dir}")
    pth_path = pth_files[0]
    lines = pth_path.read_text(encoding="utf-8").splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "#import site":
            cleaned.append("import site")
        elif stripped == "import site":
            cleaned.append(line)
        elif stripped in {"..\\python-libs", "../python-libs"}:
            continue
        else:
            cleaned.append(line)
    if "import site" not in [line.strip() for line in cleaned]:
        cleaned.append("import site")
    cleaned.insert(max(0, len(cleaned) - 1), "..\\python-libs")
    pth_path.write_text("\n".join(cleaned) + "\n", encoding="utf-8")

    run([str(python_dir / "python.exe"), "-c", "import sys; print(sys.version)"], cwd=release_root)


def install_portable_node(project_root: Path, release_root: Path) -> None:
    cache_dir = project_root / ".build-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / NODE_ZIP
    if not zip_path.exists():
        print(f"download={NODE_URL}")
        urllib.request.urlretrieve(NODE_URL, zip_path)

    node_runtime = release_root / "runtime" / "node"
    if node_runtime.exists():
        shutil.rmtree(node_runtime)
    node_runtime.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = release_root / "runtime" / "_node_extract"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as archive:
        archive.extractall(temp_dir)
    extracted_dirs = [path for path in temp_dir.iterdir() if path.is_dir() and path.name.startswith("node-v")]
    if not extracted_dirs:
        raise FileNotFoundError(f"未找到 Node 解压目录：{temp_dir}")
    shutil.move(str(extracted_dirs[0]), str(node_runtime))
    shutil.rmtree(temp_dir)
    run([str(node_runtime / "node.exe"), "-v"], cwd=release_root)
    run([str(node_runtime / "npm.cmd"), "-v"], cwd=release_root)


def quick_start_text(version: str, build_date: str, copied_env: bool) -> str:
    key_note = (
        "本包已随包携带 `.env.local`，问问智算会直接读取其中的大模型 Key。"
        if copied_env
        else "本包未携带 `.env.local`；需要问问智算、知识库问答或风险报告时，双击 `配置大模型Key.bat` 填写。"
    )
    return f"""# 造价智算 Windows 绿色版说明

版本：{version}
构建日期：{build_date}

## 启动

双击：

```text
启动造价智算.bat
```

程序会按传统开发方式启动两个本地服务：

```text
后端：http://127.0.0.1:{BACKEND_PORT}
前端：http://127.0.0.1:{FRONTEND_PORT}
```

启动成功后会自动打开前端网页。使用期间请保持后端和前端两个服务窗口打开。

## 停止

双击：

```text
停止造价智算.bat
```

## 目标电脑环境

目标 Windows 电脑不需要安装 Python、Node 或 npm：

- `runtime/python/` 内置 Python。
- `runtime/python-libs/` 内置后端依赖。
- `runtime/node/` 内置 Node/npm。
- `frontend/node_modules/` 已随包带入。

## 大模型 Key

核心 Excel / Word / 预警 / 工作量抓取流程不依赖大模型 Key。

{key_note}

如需新增或修改 Key，双击：

```text
配置大模型Key.bat
```

保存 `.env.local` 后，先停止再重新启动。
"""


def copy_local_env(project_root: Path, release_root: Path) -> bool:
    env_path = project_root / ".env.local"
    if not env_path.exists():
        return False
    shutil.copy2(env_path, release_root / ".env.local")
    return True


def default_project_settings_payload() -> dict[str, object]:
    return {
        "version": 2,
        "updated_at": date.today().isoformat(),
        "_说明": [
            "这是造价智算的项目默认设置文件，可以手动修改。",
            "JSON 标准不支持 // 或 /* */ 注释；需要说明时请使用以下划线开头的说明字段。",
            "程序只读取 previewColumns、zhisuanWindow、inputMapping、workloadCapture 内的有效配置项，未知说明字段会被忽略。",
            "修改后请保持 JSON 格式合法；如果格式错误，程序会回退到代码内置默认值。",
        ],
        "previewColumns": {
            "_说明": "表格预览默认设置：控制默认显示列、各 sheet 表头行、单元格最大显示字符数和手动列宽。",
            "defaultLabels": DEFAULT_CORE_PREVIEW_LABELS,
            "sheetOverrides": {},
            "headerRows": {},
            "maxDisplayChars": DEFAULT_PREVIEW_CELL_MAX_DISPLAY_CHARS,
            "columnWidths": {},
        },
        "zhisuanWindow": {
            "_说明": "问问智算窗口的项目默认设置：聊天区、右侧 Dock、欢迎语、显示项和快捷指令都统一从这里读取；设置页内调整只在当前会话生效。",
            "chatHeight": 430,
            "dockWidth": 400,
            "useViewportHeight": False,
            "quickSettings": {
                "_说明": "enabledIds 控制启用的内置快捷指令；customPrompts 是逐行显示的自定义快捷指令；autoHide 控制快捷指令是否默认收起。",
                "enabledIds": [
                    "batch-match",
                    "experience-warning",
                    "risk-report",
                    "download-excel",
                    "download-word",
                ],
                "customPrompts": ["@知识库："],
                "autoHide": True,
                "version": 2,
            },
            "dockVisibility": {
                "rowReview": False,
                "conclusion": False,
                "review": False,
                "warning": False,
                "ruleNotice": False,
                "debugInfo": False,
            },
            "welcomeMessage": "你好，我是智算。你把 Excel 拖进来，我负责盯住字段、转换、预警、报告和每一行复核。价格还是由结构化规则裁决，我只做解释、总结和提醒。",
            "dockStyle": "default",
        },
        "inputMapping": {
            "_说明": "主填价模块的列映射默认设置。",
            "headerRow": 4,
            "outputMatchReport": True,
            "onlyMatchRowsWithValue": True,
            "matchValueFilterField": "数量",
            "mergeVerticalCells": True,
            "mergeHorizontalCells": True,
            "fieldPreferences": {
                "要素1": ["要素1", "项目名称", "项目", "专业"],
                "要素2": ["要素2", "工作内容", "作业内容", "内容"],
                "要素3": ["要素3", "类别", "类别名称"],
                "要素4": ["要素4", "比例尺", "规格", "方法"],
                "要素5": ["要素5", "复杂程度", "等级"],
                "单位": ["单位", "计量单位"],
                "输出-价格列": ["单价匹配-测试", "基价测试列", "基价", "单价", "价格"],
                "输出-实物工作费调整系数": ["实物工作费调整系数", "输出-实物工作费调整系数"],
                "输出-技术工作费调整系数": ["技术工作费调整系数", "输出-技术工作费调整系数"],
            },
        },
        "workloadCapture": {
            "_说明": "工作量抓取模块的默认设置。",
            "selectedFields": [
                "数量(信息抓取)",
                "实物工作费调整系数(信息抓取)",
                "技术工作费调整系数(信息抓取)",
                "委托方备注(信息抓取)",
            ],
            "writeMode": "conservative",
            "onlyCaptureRowsWithValue": True,
            "valueFilterField": "数量",
            "source": {
                "adjacentFallbackEnabled": True,
                "elementSequenceEnabled": True,
                "fieldPreferences": {},
            },
            "target": {
                "adjacentFallbackEnabled": True,
                "elementSequenceEnabled": False,
                "fieldPreferences": {},
            },
        },
    }


def copy_project_default_settings(project_root: Path, release_root: Path) -> bool:
    source = project_root / PROJECT_DEFAULT_SETTINGS_RELATIVE_PATH
    target = release_root / PROJECT_DEFAULT_SETTINGS_RELATIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.exists() and source.is_file():
        shutil.copy2(source, target)
        return True
    target.write_text(
        json.dumps(default_project_settings_payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return False


def copy_runtime_assets(project_root: Path, release_root: Path) -> None:
    copy_tree(project_root / "backend" / "app", release_root / "backend" / "app", ignore=ignore_python_generated)
    copy_file(project_root, release_root, "backend/requirements-runtime.txt")
    copy_file(project_root, release_root, "backend/requirements.txt")
    copy_file(project_root, release_root, "backend/feishu_bot_runner.py")
    copy_file(project_root, release_root, "启动飞书第二层机器人.bat")

    copy_tree(project_root / "frontend", release_root / "frontend")
    dist_dir = release_root / "frontend" / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    for relative in (
        "AGENTS.md",
        "README.md",
        "CHANGELOG.md",
        ".env.local.example",
        "docs/绿色版说明.md",
        "00-PRD/00-产品总览.md",
        "03-知识库-二维数据库制作/【数据库】【导入】.xlsx",
        "03-知识库-二维数据库制作/输入100 和 空单价100.xlsx",
    ):
        copy_file(project_root, release_root, relative)

    copy_tree(
        project_root / "03-知识库-二维数据库制作" / "01-报告模板-招标控制价报告模板",
        release_root / "03-知识库-二维数据库制作" / "01-报告模板-招标控制价报告模板",
    )
    copy_glob(project_root, release_root, "03-知识库-二维数据库制作", "*输入测试-空单价100*.xlsx")
    copy_glob(project_root, release_root, "03-知识库-二维数据库制作/04-【归档】输入测试", "*输入测试-空单价100*.xlsx")
    copy_glob(project_root, release_root, "03-知识库-二维数据库制作", "【委托方例子】【工作量信息抓取】*.xlsx")
    copy_glob(project_root, release_root, "03-知识库-二维数据库制作", "【项目例子】【测试输入】*.xlsx")

    for relative in (
        "05-经验池-预警数据/【经验池】【模板勿动】-管勘智算.xlsx",
        "05-经验池-预警数据/【经验池】-管勘智算-【codex】.xlsx",
        "05-经验池-预警数据/experience-field-preferences-【codex】.json",
        "05-经验池-预警数据/experience-warning-settings-【codex】.json",
    ):
        copy_file(project_root, release_root, relative)

    rule_base = "03-【匹配规则】-勘察测绘知识库-匹配规则提炼"
    for relative in (
        f"{rule_base}/【重要匹配规则】项目以及总体匹配规则介绍.md",
        f"{rule_base}/【重要匹配规则】要素1-5和单位的匹配模式介绍.md",
        f"{rule_base}/【重要匹配规则】【第一层】-标准规则命中表-说人话版-v1.0.xlsx",
        f"{rule_base}/【术语归并】术语归并与匹配放宽规则表.xlsx",
        f"{rule_base}/03-给深度研究的提示词和交付/20260614-深度研究【交付】-长输管道勘察测量调整系数规则交付稿.md",
    ):
        copy_file(project_root, release_root, relative)
    copy_glob(project_root, release_root, f"{rule_base}/01-原始资料", "财建[2009]17号-测绘生产成本费用定额*.md")
    copy_glob(project_root, release_root, f"{rule_base}/01-原始资料", "计价格[2002]10号-工程勘察设计收费标准使用手册*.md")
    copy_glob(project_root, release_root, f"{rule_base}/01-原始资料", "财建[2009]17号-测绘生产成本费用定额*批注*.xlsx")
    copy_glob(project_root, release_root, f"{rule_base}/01-原始资料", "计价格[2002]10号-工程勘察设计收费标准使用手册*批注*.xlsx")
    copied_project_defaults = copy_project_default_settings(project_root, release_root)
    if copied_project_defaults:
        print(f"copied={PROJECT_DEFAULT_SETTINGS_RELATIVE_PATH.as_posix()}")
    else:
        print(f"generated={PROJECT_DEFAULT_SETTINGS_RELATIVE_PATH.as_posix()}")


def build_release(args: argparse.Namespace) -> tuple[Path, Path | None]:
    project_root = Path(args.project_root).resolve()
    version = args.version or detect_version(project_root)
    build_date = args.date
    release_name = f"{PROJECT_NAME}-{RELEASE_KIND}-{build_date}-{version}"
    archive_dir = (project_root / args.output_dir).resolve()
    release_root = archive_dir / release_name

    if args.clean and release_root.exists():
        shutil.rmtree(release_root)
    release_root.mkdir(parents=True, exist_ok=True)

    if not args.skip_frontend_install:
        run([npm_command(), "install"], cwd=project_root / "frontend")
    if not (project_root / "frontend" / "node_modules").exists():
        raise FileNotFoundError("frontend/node_modules 不存在，无法生成绿色版。")

    copy_runtime_assets(project_root, release_root)
    install_portable_node(project_root, release_root)

    if not args.skip_wheelhouse:
        wheels_dir = release_root / "runtime" / "wheels"
        wheels_dir.mkdir(parents=True, exist_ok=True)
        run([sys.executable, "-m", "pip", "download", "-r", str(project_root / "backend" / "requirements-runtime.txt"), "-d", str(wheels_dir)], cwd=project_root)

    if not args.skip_python_libs:
        libs_dir = release_root / "runtime" / "python-libs"
        if libs_dir.exists():
            shutil.rmtree(libs_dir)
        libs_dir.mkdir(parents=True, exist_ok=True)
        wheels_dir = release_root / "runtime" / "wheels"
        install_command = [sys.executable, "-m", "pip", "install", "--target", str(libs_dir)]
        if wheels_dir.exists():
            install_command.extend(["--no-index", "--find-links", str(wheels_dir)])
        install_command.extend(["-r", str(project_root / "backend" / "requirements-runtime.txt")])
        run(install_command, cwd=project_root)

    install_portable_python(project_root, release_root)
    copied_env = copy_local_env(project_root, release_root)

    write_text(release_root / "造价智算传统启动器.ps1", LAUNCHER_PS1)
    write_text(release_root / "启动造价智算.bat", START_BAT)
    write_text(release_root / "停止造价智算.bat", STOP_BAT)
    write_text(release_root / "检查造价智算状态.bat", STATUS_BAT)
    write_text(release_root / "配置大模型Key.bat", CONFIG_LLM_BAT)
    write_text(release_root / "README-绿色版.md", quick_start_text(version, build_date, copied_env))

    manifest = {
        "project": PROJECT_NAME,
        "release_kind": RELEASE_KIND,
        "version": version,
        "date": build_date,
        "entrypoints": ["启动造价智算.bat", "停止造价智算.bat", "检查造价智算状态.bat", "配置大模型Key.bat"],
        "urls": {
            "backend": f"http://127.0.0.1:{BACKEND_PORT}/",
            "frontend": f"http://127.0.0.1:{FRONTEND_PORT}/",
        },
        "bundled_secret_env_file": copied_env,
        "notes": [
            "传统网页启动：后端 8000，前端 Vite 5174。",
            "runtime/python 内置 Python，runtime/node 内置 Node/npm。",
            "frontend/node_modules 已随包带入，目标电脑不需要安装 Node。",
            "不使用桌面壳，不使用后端静态 web 作为主入口。",
        ],
    }
    write_text(release_root / "RELEASE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    zip_path: Path | None = None
    if not args.no_zip:
        zip_path = archive_dir / f"{release_name}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(release_root.rglob("*")):
                if path.is_file():
                    if ".runtime" in path.relative_to(release_root).parts:
                        continue
                    archive.write(path, path.relative_to(archive_dir).as_posix())
        print(f"zip={zip_path}")
        print(f"zip_sha256={sha256(zip_path)}")
    return release_root, zip_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成造价智算 Windows 绿色版。")
    parser.add_argument("--project-root", default=".", help="项目根目录，默认当前目录。")
    parser.add_argument("--output-dir", default="04-输出版本存档", help="输出目录。")
    parser.add_argument("--version", default="", help="版本号，默认从 README.md 读取。")
    parser.add_argument("--date", default=date.today().isoformat(), help="构建日期，默认今天。")
    parser.add_argument("--skip-frontend-install", action="store_true", help="不运行 npm install，直接复制现有 frontend/node_modules。")
    parser.add_argument("--skip-wheelhouse", action="store_true", help="不下载离线 Python 依赖包。")
    parser.add_argument("--skip-python-libs", action="store_true", help="不预装 runtime/python-libs。")
    parser.add_argument("--no-zip", action="store_true", help="只生成目录，不压缩。")
    parser.add_argument("--no-clean", dest="clean", action="store_false", help="不清理已有同名目录。")
    parser.set_defaults(clean=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    release_root, zip_path = build_release(args)
    print(f"release_dir={release_root}")
    if zip_path:
        print(f"zip_size_mb={zip_path.stat().st_size / 1024 / 1024:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
