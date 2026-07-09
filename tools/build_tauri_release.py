from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from build_green_release import build_release, detect_version, sha256


TAURI_RELEASE_KIND = "Tauri桌面壳MVP"
TAURI_EXE_NAME = "造价智算-Tauri-MVP.exe"
TAURI_PACKAGE_KIND = "Tauri桌面版"


def run(command: list[str], cwd: Path) -> None:
    print(f"[run] {cwd}> {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def npm_command() -> str:
    return "npm.cmd" if sys.platform.startswith("win") else "npm"


def build_green_stage(project_root: Path, args: argparse.Namespace) -> Path:
    green_args = argparse.Namespace(
        project_root=str(project_root),
        version=args.version,
        date=args.date,
        output_dir=args.output_dir,
        clean=True,
        skip_frontend_install=args.skip_frontend_install,
        skip_wheelhouse=args.skip_wheelhouse,
        skip_python_libs=args.skip_python_libs,
        no_zip=True,
    )
    release_root, _ = build_release(green_args)
    return release_root


def find_tauri_exe(project_root: Path) -> Path:
    release_dir = project_root / "src-tauri" / "target" / "release"
    preferred = [
        release_dir / "guankanzhisuan-desktop.exe",
        release_dir / "造价智算.exe",
    ]
    for path in preferred:
        if path.exists():
            return path
    candidates = sorted(
        (
            path
            for path in release_dir.glob("*.exe")
            if path.is_file() and not path.name.endswith(".pdb")
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"未找到 Tauri release exe：{release_dir}")
    return candidates[0]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if path.suffix.lower() == ".ps1" else "utf-8"
    path.write_text(text, encoding=encoding, newline="\n")


def write_tauri_launcher(release_root: Path) -> None:
    write_text(
        release_root / "启动造价智算-Tauri桌面版.bat",
        f"""@echo off
setlocal
chcp 65001 >nul
set "GUANKAN_APP_ROOT=%~dp0"
start "" "%~dp0{TAURI_EXE_NAME}"
""",
    )


def write_tauri_stop_launcher(release_root: Path) -> None:
    write_text(
        release_root / "停止造价智算-Tauri桌面版.bat",
        """@echo off
setlocal
chcp 65001 >nul
set "APP_ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_ROOT%停止造价智算-Tauri桌面版.ps1"
echo.
echo 按任意键关闭本窗口。
pause >nul
""",
    )
    write_text(
        release_root / "停止造价智算-Tauri桌面版.ps1",
        r'''$ErrorActionPreference = "Continue"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $ProjectDir ".runtime"
$PidPath = Join-Path $RuntimeDir "tauri-backend.pid"

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
    if (-not $RootPid -or $RootPid -eq $PID) {
        return
    }
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
        ProcessId = [int]$connection.OwningProcess
        Name = if ($process) { $process.Name } else { "" }
        CommandLine = if ($process) { $process.CommandLine } else { "" }
        ExecutablePath = if ($process) { $process.ExecutablePath } else { "" }
    }
}

function Test-IsCurrentPackageProcess {
    param([object]$Owner)
    if (-not $Owner) {
        return $false
    }
    $needle = $ProjectDir.TrimEnd("\")
    return (
        ($Owner.CommandLine -and $Owner.CommandLine.Contains($needle)) -or
        ($Owner.ExecutablePath -and $Owner.ExecutablePath.Contains($needle))
    )
}

if (Test-Path -LiteralPath $PidPath) {
    try {
        $savedPid = [int](Get-Content -LiteralPath $PidPath -Encoding UTF8 | Select-Object -First 1)
        if ($savedPid) {
            Stop-PidTree -RootPid $savedPid
        }
    }
    catch {
        Write-Host "[提醒] PID 文件读取失败：$($_.Exception.Message)"
    }
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
}

$owner = Get-PortOwner -Port 8000
if ($owner -and (Test-IsCurrentPackageProcess $owner)) {
    Stop-PidTree -RootPid $owner.ProcessId
}
elseif ($owner) {
    Write-Host "[提醒] 8000 端口仍被其他进程占用，未自动结束。PID=$($owner.ProcessId) $($owner.Name)"
}
else {
    Write-Host "8000 端口未占用。"
}

Write-Host "停止操作完成。"
''',
    )


def write_desktop_readme(release_root: Path, version: str, build_date: str, copied_env: bool) -> None:
    key_note = (
        "本包已随包携带 `.env.local`，问问智算会直接读取其中的大模型 Key。"
        if copied_env
        else "本包未携带 `.env.local`，如需问问智算，请双击 `配置大模型Key.bat` 后重启应用。"
    )
    write_text(
        release_root / "README-Tauri桌面版.md",
        f"""# 造价智算 Tauri 桌面版

版本：{version}
构建日期：{build_date}

## 启动

双击：

```text
{TAURI_EXE_NAME}
```

或双击：

```text
启动造价智算-Tauri桌面版.bat
```

首次启动会自动拉起本地后端 `127.0.0.1:8000`，然后在桌面窗口中打开造价智算页面。关闭窗口时，会结束本次由桌面壳启动的后端进程。

异常退出或强制结束 exe 后，如果 8000 端口仍被占用，可双击：

```text
停止造价智算-Tauri桌面版.bat
```

## 运行环境

- 目标 Windows 电脑不需要安装 Python。
- 目标 Windows 电脑不需要安装 Node / npm。
- 目标 Windows 电脑不需要安装 Rust / Cargo。
- 需要系统具备 WebView2；Windows 10/11 通常已内置或随 Edge 安装。

## 大模型 Key

{key_note}

未配置 Key 时，Excel 匹配、Excel 下载、Word 报告、经验池预警和工作量抓取仍可运行；知识库问答、风险报告等大模型能力会提示配置 Key。
""",
    )


def zip_release(release_root: Path, output_zip: Path) -> Path:
    if output_zip.exists():
        output_zip.unlink()
    with ZipFile(output_zip, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(release_root.rglob("*")):
            if path.is_file():
                relative = path.relative_to(release_root.parent)
                if ".runtime" in relative.parts:
                    continue
                archive.write(path, relative.as_posix())
    return output_zip


def copy_frontend_dist(project_root: Path, release_root: Path) -> None:
    source = project_root / "frontend" / "dist"
    if not (source / "index.html").exists():
        raise FileNotFoundError(f"未找到前端静态构建产物：{source}")
    target = release_root / "frontend" / "dist"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def copy_local_env(project_root: Path, release_root: Path) -> bool:
    env_path = project_root / ".env.local"
    if not env_path.exists():
        return False
    shutil.copy2(env_path, release_root / ".env.local")
    return True


def slim_desktop_runtime(release_root: Path) -> None:
    for relative in (
        "runtime/node",
        "runtime/wheels",
        "frontend/node_modules",
    ):
        target = release_root / relative
        if target.exists():
            shutil.rmtree(target)
    for filename in (
        "启动造价智算.bat",
        "停止造价智算.bat",
        "检查造价智算状态.bat",
        "README-绿色版.md",
        "造价智算传统启动器.ps1",
    ):
        target = release_root / filename
        if target.exists():
            target.unlink()


def to_tauri_release_root(project_root: Path, green_root: Path, version: str, build_date: str, output_dir: str) -> Path:
    archive_dir = (project_root / output_dir).resolve()
    release_root = archive_dir / f"造价智算-{TAURI_PACKAGE_KIND}-{build_date}-{version}"
    if release_root.exists():
        shutil.rmtree(release_root)
    if green_root.resolve() == release_root.resolve():
        return release_root
    shutil.move(str(green_root), str(release_root))
    return release_root


def build_tauri_release(args: argparse.Namespace) -> tuple[Path, Path | None]:
    project_root = Path(args.project_root).resolve()
    version = args.version or detect_version(project_root)
    green_root = build_green_stage(project_root, args)

    if not args.skip_npm_install and not (project_root / "node_modules").exists():
        run([npm_command(), "install"], cwd=project_root)
    run([npm_command(), "run", "tauri:build"], cwd=project_root)

    release_root = to_tauri_release_root(project_root, green_root, version, args.date, args.output_dir)
    copy_frontend_dist(project_root, release_root)
    copied_env = copy_local_env(project_root, release_root)
    slim_desktop_runtime(release_root)

    tauri_exe = find_tauri_exe(project_root)
    target_exe = release_root / TAURI_EXE_NAME
    shutil.copy2(tauri_exe, target_exe)
    write_tauri_launcher(release_root)
    write_tauri_stop_launcher(release_root)
    write_desktop_readme(release_root, version, args.date, copied_env)

    manifest_path = release_root / "RELEASE_MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {}
    manifest["release_kind"] = TAURI_PACKAGE_KIND
    manifest["version"] = version
    manifest["date"] = args.date
    manifest.setdefault("entrypoints", [])
    manifest["entrypoints"] = []
    for entrypoint in ("启动造价智算-Tauri桌面版.bat", "停止造价智算-Tauri桌面版.bat", "停止造价智算-Tauri桌面版.ps1", TAURI_EXE_NAME):
        if entrypoint not in manifest["entrypoints"]:
            manifest["entrypoints"].append(entrypoint)
    manifest["urls"] = {
        "backend": "http://127.0.0.1:8000/",
        "frontend": "http://127.0.0.1:8000/",
    }
    manifest["bundled_secret_env_file"] = copied_env
    manifest["notes"] = [
        "Tauri 桌面版直接双击 exe 启动或复用后端 8000，并在 WebView 中打开 http://127.0.0.1:8000/。",
        "runtime/python 内置 Python，runtime/python-libs 内置后端依赖。",
        "frontend/dist 已随包带入，由 FastAPI 静态托管。",
        "不携带 runtime/node、frontend/node_modules、Rust 或 Cargo。",
    ]
    manifest["tauri_notes"] = [
        "Tauri 桌面版直接双击 exe 启动，不依赖目标电脑安装 Python、Node、npm、Rust 或 Cargo。",
        "后端使用 runtime/python 和 runtime/python-libs。",
        "前端使用 frontend/dist，由本地 FastAPI 后端静态托管。",
        "当前桌面版不携带 runtime/node 和 frontend/node_modules。",
    ]
    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

    output_zip: Path | None = None
    if not args.no_zip:
        archive_dir = (project_root / args.output_dir).resolve()
        output_zip = archive_dir / f"造价智算-{TAURI_PACKAGE_KIND}-{args.date}-{version}.zip"
        zip_release(release_root, output_zip)
        print(f"zip={output_zip}")
        print(f"zip_sha256={sha256(output_zip)}")

    print(f"release_dir={release_root}")
    print(f"tauri_exe={target_exe}")
    return release_root, output_zip


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成造价智算 Tauri 桌面壳开发/验证目录。")
    parser.add_argument("--project-root", default=".", help="项目根目录，默认当前目录。")
    parser.add_argument("--version", default="", help="版本号，例如 v5.0.0；默认从 README.md 识别。")
    parser.add_argument("--date", default=date.today().isoformat(), help="日期，默认今天。")
    parser.add_argument("--output-dir", default="04-输出版本存档", help="输出目录。")
    parser.add_argument("--skip-npm-install", action="store_true", help="跳过根目录 npm install。")
    parser.add_argument("--skip-frontend-install", action="store_true", help="绿色版阶段跳过 npm install。")
    parser.add_argument("--skip-wheelhouse", action="store_true", help="绿色版阶段不下载离线 wheels。")
    parser.add_argument("--skip-python-libs", action="store_true", help="绿色版阶段不预装 runtime/python-libs。")
    parser.add_argument("--no-zip", action="store_true", help="只生成绿色目录，不压缩。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    build_tauri_release(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
