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
RELEASE_KIND = "评委运行版"
BACKEND_PORT = 8000
PYTHON_EMBED_VERSION = "3.14.3"
PYTHON_EMBED_ZIP = f"python-{PYTHON_EMBED_VERSION}-embed-amd64.zip"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_EMBED_VERSION}/{PYTHON_EMBED_ZIP}"


LAUNCHER_PS1 = r'''param(
    [switch]$StatusOnly,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppUrl = "http://127.0.0.1:8000/"
$HealthUrl = "http://127.0.0.1:8000/api/health"
$RuntimeDir = Join-Path $ProjectDir ".runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$PidPath = Join-Path $RuntimeDir "backend.pid"

function Write-Trace {
    param([string]$Message)
    try {
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
        Add-Content -LiteralPath (Join-Path $LogDir "launcher-trace.log") -Encoding UTF8 -Value "$((Get-Date).ToString('s')) $Message"
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
    }
}

function Test-Backend {
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
        return ($response.status -eq "ok" -and $response.service -eq "guankanzhisuan")
    }
    catch {
        return $false
    }
}

function Find-BasePython {
    $pythonCommands = @(Get-Command python -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -and $_.Source -notlike "*\WindowsApps\*" })
    foreach ($python in $pythonCommands) {
        return [pscustomobject]@{ Exe = $python.Source; PrefixArgs = @() }
    }
    $pyCommands = @(Get-Command py -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -and $_.Source -notlike "*\WindowsApps\*" })
    foreach ($pyLauncher in $pyCommands) {
        return [pscustomobject]@{ Exe = $pyLauncher.Source; PrefixArgs = @("-3") }
    }
    return $null
}

function Invoke-BasePython {
    param(
        [object]$Python,
        [string[]]$Args
    )
    $allArgs = @()
    $allArgs += $Python.PrefixArgs
    $allArgs += $Args
    $process = Start-Process -FilePath $Python.Exe -ArgumentList $allArgs -NoNewWindow -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Python 命令执行失败，退出码 $($process.ExitCode)：$($Python.Exe) $($allArgs -join ' ')"
    }
}

function Ensure-Python {
    Write-Trace "Ensure-Python:start"
    $portablePython = Join-Path $ProjectDir "runtime\python\python.exe"
    if (Test-Path -LiteralPath $portablePython) {
        Write-Trace "Ensure-Python:portable=$portablePython"
        return $portablePython
    }

    $pythonLibs = Join-Path $ProjectDir "runtime\python-libs"
    if (Test-Path -LiteralPath $pythonLibs) {
        $basePython = Find-BasePython
        if (-not $basePython -or $basePython.PrefixArgs.Count -gt 0) {
            throw "未找到可直接运行的 python.exe。请安装 Python 3.11+，或把便携 Python 放入 runtime\python\python.exe。"
        }
        Write-Trace "Ensure-Python:base-with-local-libs=$($basePython.Exe)"
        return $basePython.Exe
    }

    $venvDir = Join-Path $ProjectDir ".runtime\venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        Write-Trace "Ensure-Python:venv-existing=$venvPython"
        return $venvPython
    }
    if (Test-Path -LiteralPath $venvDir) {
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }

    $basePython = Find-BasePython
    if (-not $basePython) {
        throw "未找到 Python。请安装 Python 3.11+，或把便携 Python 放入 runtime\python\python.exe 后再启动。"
    }
    Write-Trace "Ensure-Python:base=$($basePython.Exe)"

    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    Write-Host "首次运行：正在创建本地 Python 运行环境..."
    Write-Trace "Ensure-Python:create-venv"
    Invoke-BasePython -Python $basePython -Args @("-m", "venv", $venvDir)
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Python 虚拟环境创建失败。"
    }
    Write-Trace "Ensure-Python:venv-created"

    $requirements = Join-Path $ProjectDir "backend\requirements-runtime.txt"
    if (-not (Test-Path -LiteralPath $requirements)) {
        $requirements = Join-Path $ProjectDir "backend\requirements.txt"
    }
    $wheels = Join-Path $ProjectDir "runtime\wheels"
    Write-Host "首次运行：正在安装运行依赖..."
    if (Test-Path -LiteralPath $wheels) {
        Write-Trace "Ensure-Python:pip-install-offline"
        & $venvPython -m pip install --no-index --find-links $wheels -r $requirements
    }
    else {
        Write-Trace "Ensure-Python:pip-upgrade-online"
        & $venvPython -m pip install --upgrade pip
        & $venvPython -m pip install -r $requirements
    }
    if ($LASTEXITCODE -ne 0) {
        throw "运行依赖安装失败。请查看网络或 runtime\wheels 离线依赖包。"
    }
    Write-Trace "Ensure-Python:done"
    return $venvPython
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
            Write-Host "已停止 PID: $id"
        }
        catch {
            Write-Host "[提醒] 无法停止 PID $id：$($_.Exception.Message)"
        }
    }
}

function Stop-App {
    if (Test-Path -LiteralPath $PidPath) {
        $savedPid = [int](Get-Content -LiteralPath $PidPath -Encoding UTF8 | Select-Object -First 1)
        if ($savedPid) {
            Stop-PidTree -RootPid $savedPid
        }
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
    }

    $owner = Get-PortOwner 8000
    if ($owner -and (Test-Backend)) {
        Stop-PidTree -RootPid ([int]$owner.ProcessId)
    }
    Write-Host "停止操作完成。"
}

function Show-Status {
    $envPath = Join-Path $ProjectDir ".env.local"
    $envExamplePath = Join-Path $ProjectDir ".env.local.example"
    $backendOk = Test-Backend
    $owner = Get-PortOwner 8000
    Write-Host "造价智算评委版运行状态"
    Write-Host "目录: $ProjectDir"
    Write-Host "页面: $AppUrl"
    Write-Host "后端: $(if ($backendOk) { '已启动，服务身份正确' } else { '未检测到造价智算后端' })"
    if ($owner) {
        Write-Host "端口 8000: 已占用，PID=$($owner.ProcessId)，进程=$($owner.Name)"
        if ($owner.CommandLine) {
            Write-Host "命令: $($owner.CommandLine)"
        }
    }
    else {
        Write-Host "端口 8000: 未占用"
    }
    Write-Host "配置文件 .env.local: $(if (Test-Path -LiteralPath $envPath) { '已找到' } else { '未找到' })"
    if (-not (Test-Path -LiteralPath $envPath) -and (Test-Path -LiteralPath $envExamplePath)) {
        Write-Host "提示：只修改 .env.local.example 不会生效，请复制为 .env.local 后再填写 Key。"
    }
    if ($env:DEEPSEEK_API_KEY) {
        Write-Host "DEEPSEEK_API_KEY: 已读取，长度 $($env:DEEPSEEK_API_KEY.Length)"
    }
    else {
        Write-Host "DEEPSEEK_API_KEY: 未读取"
    }
    if ($env:SILICONFLOW_API_KEY) {
        Write-Host "SILICONFLOW_API_KEY: 已读取，长度 $($env:SILICONFLOW_API_KEY.Length)"
    }
    else {
        Write-Host "SILICONFLOW_API_KEY: 未读取"
    }
    if (-not $env:DEEPSEEK_API_KEY -and -not $env:SILICONFLOW_API_KEY) {
        Write-Host "大模型 API Key: 未配置。核心 Excel/Word 流程不受影响，智算问答会提示不可用。"
    }
    elseif ($backendOk) {
        Write-Host "提示：如果刚刚才修改 Key，但页面仍提示不可用，请先双击 停止造价智算-评委版.bat，再重新启动。"
    }
}

function Start-App {
    Write-Trace "Start-App:start"
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir "backend\app\main.py"))) {
        throw "backend\app\main.py 不存在，请确认评委版目录完整。"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir "web\index.html"))) {
        throw "web\index.html 不存在，请重新生成评委版。"
    }

    Import-LocalEnv
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

    if (Test-Backend) {
        Write-Trace "Start-App:already-running"
        Write-Host "造价智算已经在运行，正在打开浏览器..."
        Start-Process $AppUrl
        return
    }

    $owner = Get-PortOwner 8000
    if ($owner) {
        Write-Trace "Start-App:port-occupied"
        Write-Host "端口 8000 已被占用，启动器不会自动换端口。"
        Write-Host "PID: $($owner.ProcessId)"
        Write-Host "进程: $($owner.Name)"
        if ($owner.CommandLine) {
            Write-Host "命令: $($owner.CommandLine)"
        }
        throw "请先关闭占用 8000 端口的程序，或运行 停止造价智算-评委版.bat。"
    }

    $python = Ensure-Python
    Write-Trace "Start-App:python=$python"
    $logPath = Join-Path $LogDir "backend.log"
    $errLogPath = Join-Path $LogDir "backend-error.log"
    $webDir = Join-Path $ProjectDir "web"
    $env:GUANKAN_FRONTEND_DIR = $webDir
    $env:PYTHONUTF8 = "1"
    $pythonLibs = Join-Path $ProjectDir "runtime\python-libs"
    if (Test-Path -LiteralPath $pythonLibs) {
        $backendPath = Join-Path $ProjectDir "backend"
        if ($env:PYTHONPATH) {
            $env:PYTHONPATH = "$pythonLibs;$backendPath;$env:PYTHONPATH"
        }
        else {
            $env:PYTHONPATH = "$pythonLibs;$backendPath"
        }
        Write-Trace "Start-App:pythonpath=$env:PYTHONPATH"
    }
    Write-Trace "Start-App:start-process"
    $process = Start-Process -FilePath $python -ArgumentList @(
        "-m", "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--app-dir", "backend"
    ) -WorkingDirectory $ProjectDir -RedirectStandardOutput $logPath -RedirectStandardError $errLogPath -WindowStyle Hidden -PassThru
    Write-Trace "Start-App:process-id=$($process.Id)"
    Set-Content -LiteralPath $PidPath -Value $process.Id -Encoding UTF8

    Write-Host "正在启动造价智算评委版..."
    Write-Host "日志: $logPath"
    $deadline = (Get-Date).AddSeconds(75)
    do {
        if (Test-Backend) {
            Start-Process $AppUrl
            Write-Host "已打开页面: $AppUrl"
            if (-not $env:DEEPSEEK_API_KEY -and -not $env:SILICONFLOW_API_KEY) {
                Write-Host "提示：未配置大模型 API Key，核心 Excel/Word 流程仍可使用。"
            }
            return
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    Write-Host "[提醒] 服务没有在 75 秒内就绪。最近日志如下："
    if (Test-Path -LiteralPath $logPath) {
        Get-Content -LiteralPath $logPath -Encoding UTF8 -Tail 80
    }
    if (Test-Path -LiteralPath $errLogPath) {
        Get-Content -LiteralPath $errLogPath -Encoding UTF8 -Tail 80
    }
    throw "启动失败，请把日志发给维护人员。"
}

try {
    if ($Stop) {
        Stop-App
    }
    elseif ($StatusOnly) {
        Import-LocalEnv
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
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%评委版启动器.ps1"
echo.
echo 按任意键关闭本窗口。程序会继续在后台运行；需要停止请双击 停止造价智算-评委版.bat。
pause >nul
'''


STOP_BAT = r'''@echo off
setlocal
chcp 65001 >nul
set "PROJECT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%评委版启动器.ps1" -Stop
echo.
echo 按任意键关闭本窗口。
pause >nul
'''


STATUS_BAT = r'''@echo off
setlocal
chcp 65001 >nul
set "PROJECT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%评委版启动器.ps1" -StatusOnly
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
echo 如果程序已经启动，请先双击 停止造价智算-评委版.bat，再重新启动。
echo.
start "" notepad "%ENV_FILE%"
pause
'''


def detect_version(project_root: Path) -> str:
    readme = project_root / "README.md"
    text = readme.read_text(encoding="utf-8")
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


def ignore_generated(_: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache", "node_modules", "dist"}
    return {name for name in names if name in ignored or name.endswith(".pyc")}


def copy_tree(source: Path, target: Path) -> None:
    if not source.exists():
        print(f"[skip] missing dir: {source}")
        return
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=ignore_generated)


def copy_glob(project_root: Path, release_root: Path, base: str, pattern: str) -> None:
    base_path = project_root / base
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

    python_exe = python_dir / "python.exe"
    if not python_exe.exists():
        raise FileNotFoundError(f"未找到便携 Python：{python_exe}")
    run([str(python_exe), "-c", "import sys; print(sys.version)"], cwd=release_root)


def quick_start_text(version: str, build_date: str) -> str:
    return f"""# 造价智算 Windows 评委快速运行说明

版本：{version}
构建日期：{build_date}

## 怎么启动

1. 解压整个文件夹，不要只解压其中某个文件。
2. 双击 `启动造价智算-评委版.bat`。
3. 程序启动成功后，会自动打开默认浏览器访问：

```text
http://127.0.0.1:{BACKEND_PORT}/
```

## 怎么停止

双击 `停止造价智算-评委版.bat`。

## 怎么检查状态

双击 `检查造价智算状态-评委版.bat`。

## 大模型 API Key

不配置 API Key 也可以完成核心流程：上传 Excel、匹配、预览、下载 Excel、下载 Word、经验池预警、工作量抓取。

如需使用“问问智算”、知识库依据解释或风险报告，双击 `配置大模型Key-评委版.bat`，填写并保存 `.env.local`。

也可以手工把 `.env.local.example` 复制为 `.env.local` 后填写。注意：只修改 `.env.local.example` 不会生效。

```text
DEEPSEEK_API_KEY=你的Key
```

如果程序已经启动，改完 Key 后请先双击 `停止造价智算-评委版.bat`，再重新双击 `启动造价智算-评委版.bat`。

不要把真实 Key 发给他人。

## 目录说明

- `web/`：已构建好的前端页面，不需要安装 Node。
- `backend/`：本地后端和规则执行程序。
- `runtime/python/`：随包内置的便携 Python，评委电脑不需要单独安装 Python。
- `runtime/python-libs/`：随包预装的 Python 运行依赖。
- `03-知识库-二维数据库制作/`：本地二维知识库、报告模板和示例输入。
- `03-【匹配规则】-勘察测绘知识库-匹配规则提炼/`：知识问答和规则解释所需资料。
- `05-经验池-预警数据/`：经验池预警模板、当前经验池和字段偏好设置。
- `.runtime/`：首次启动后自动生成的本机运行环境和日志，可以删除后重新生成。
- `runtime/wheels/`：可选离线依赖包。

## 常见问题

- 如果提示找不到 Python：说明 `runtime/python/python.exe` 被删除或拷贝不完整，请重新解压完整评委版压缩包。
- 如果提示端口 8000 被占用：先关闭其他本地服务，或双击 `停止造价智算-评委版.bat`。
- 如果智算问答提示不可用：先双击 `检查造价智算状态-评委版.bat`，确认 `.env.local` 已找到且 `DEEPSEEK_API_KEY` 已读取；不要只修改 `.env.local.example`。
- 如果启动失败：查看 `.runtime/logs/backend.log`，把日志发给维护人员。
"""


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
    local_runtime = release_root / ".runtime"
    if local_runtime.exists():
        shutil.rmtree(local_runtime)

    if not args.skip_frontend_build:
        run([npm_command(), "run", "build"], cwd=project_root / "frontend")
    copy_tree(project_root / "frontend" / "dist", release_root / "web")

    copy_tree(project_root / "backend" / "app", release_root / "backend" / "app")
    copy_file(project_root, release_root, "backend/requirements-runtime.txt")
    copy_file(project_root, release_root, "backend/requirements.txt")

    for relative in (
        "AGENTS.md",
        "README.md",
        "CHANGELOG.md",
        ".env.local.example",
        "docs/评委运行版说明.md",
        "项目介绍-给人看的版本-【codex】.md",
        "03-知识库-二维数据库制作/【数据库】【导入】.xlsx",
        "03-知识库-二维数据库制作/【委托方例子】【工作量信息抓取】委托方原始工作量和系数的例子.xlsx",
        "03-知识库-二维数据库制作/【项目例子】【测试输入】可行性研究勘察测量控制价计算 -v3.0【批注-完备】 .xlsx",
        "03-知识库-二维数据库制作/【项目例子】【测试无数量】可行性研究勘察测量控制价计算 -v3.0.xlsx",
    ):
        copy_file(project_root, release_root, relative)

    copy_tree(
        project_root / "03-知识库-二维数据库制作" / "01-报告模板-招标控制价报告模板",
        release_root / "03-知识库-二维数据库制作" / "01-报告模板-招标控制价报告模板",
    )
    copy_glob(project_root, release_root, "03-知识库-二维数据库制作", "*输入测试-空单价100*.xlsx")
    copy_glob(project_root, release_root, "03-知识库-二维数据库制作/04-【归档】输入测试", "*输入测试-空单价100*.xlsx")

    for relative in (
        "05-经验池-预警数据/【经验池】【模板勿动】-管勘智算.xlsx",
        "05-经验池-预警数据/【经验池】-管勘智算-【codex】.xlsx",
        "05-经验池-预警数据/experience-field-preferences-【codex】.json",
        "05-经验池-预警数据/experience-warning-settings-【codex】.json",
        "05-经验池-预警数据/workload-field-preferences-【codex】.json",
        "05-经验池-预警数据/workload-target-field-preferences-【codex】.json",
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

    write_text(release_root / "评委版启动器.ps1", LAUNCHER_PS1)
    write_text(release_root / "启动造价智算-评委版.bat", START_BAT)
    write_text(release_root / "停止造价智算-评委版.bat", STOP_BAT)
    write_text(release_root / "检查造价智算状态-评委版.bat", STATUS_BAT)
    write_text(release_root / "配置大模型Key-评委版.bat", CONFIG_LLM_BAT)
    write_text(release_root / "README-评委快速运行.md", quick_start_text(version, build_date))

    if not args.skip_wheelhouse:
        wheels_dir = release_root / "runtime" / "wheels"
        wheels_dir.mkdir(parents=True, exist_ok=True)
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "-r",
                str(project_root / "backend" / "requirements-runtime.txt"),
                "-d",
                str(wheels_dir),
            ],
            cwd=project_root,
        )

    if not args.skip_python_libs:
        libs_dir = release_root / "runtime" / "python-libs"
        if libs_dir.exists():
            shutil.rmtree(libs_dir)
        libs_dir.mkdir(parents=True, exist_ok=True)
        wheels_dir = release_root / "runtime" / "wheels"
        install_command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(libs_dir),
        ]
        if wheels_dir.exists():
            install_command.extend(["--no-index", "--find-links", str(wheels_dir)])
        install_command.extend(["-r", str(project_root / "backend" / "requirements-runtime.txt")])
        run(install_command, cwd=project_root)

    if not args.skip_portable_python:
        install_portable_python(project_root, release_root)

    manifest = {
        "project": PROJECT_NAME,
        "release_kind": RELEASE_KIND,
        "version": version,
        "date": build_date,
        "entrypoints": [
            "启动造价智算-评委版.bat",
            "停止造价智算-评委版.bat",
            "检查造价智算状态-评委版.bat",
            "配置大模型Key-评委版.bat",
        ],
        "url": f"http://127.0.0.1:{BACKEND_PORT}/",
        "notes": [
            "前端已构建到 web/，评委端不需要 Node。",
            "runtime/python/ 内置便携 Python，评委端不需要安装 Python。",
            "未配置 DeepSeek API Key 时，核心 Excel/Word 流程仍可运行。",
            "业务匹配逻辑未为评委版重写。",
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
    parser = argparse.ArgumentParser(description="生成造价智算 Windows 评委绿色运行版。")
    parser.add_argument("--project-root", default=".", help="项目根目录，默认当前目录。")
    parser.add_argument("--output-dir", default="04-输出版本存档", help="输出目录。")
    parser.add_argument("--version", default="", help="版本号，默认从 README.md 读取。")
    parser.add_argument("--date", default=date.today().isoformat(), help="构建日期，默认今天。")
    parser.add_argument("--skip-frontend-build", action="store_true", help="不运行 npm run build，直接复制现有 frontend/dist。")
    parser.add_argument("--skip-wheelhouse", action="store_true", help="不下载离线 Python 依赖包。")
    parser.add_argument("--skip-python-libs", action="store_true", help="不预装 runtime/python-libs 本地依赖目录。")
    parser.add_argument("--skip-portable-python", action="store_true", help="不下载并内置 runtime/python 便携 Python。")
    parser.add_argument("--no-zip", action="store_true", help="只生成目录，不压缩。")
    parser.add_argument("--no-clean", dest="clean", action="store_false", help="不清理已有同名目录。")
    parser.set_defaults(clean=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    release_root, zip_path = build_release(args)
    print(f"release_dir={release_root}")
    if zip_path:
        size_mb = zip_path.stat().st_size / 1024 / 1024
        print(f"zip_size_mb={size_mb:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
