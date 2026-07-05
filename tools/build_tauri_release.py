from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from build_judge_release import build_release, detect_version, sha256


TAURI_RELEASE_KIND = "Tauri桌面壳MVP"
TAURI_EXE_NAME = "造价智算-Tauri-MVP.exe"


def run(command: list[str], cwd: Path) -> None:
    print(f"[run] {cwd}> {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def npm_command() -> str:
    return "npm.cmd" if sys.platform.startswith("win") else "npm"


def build_judge_stage(project_root: Path, args: argparse.Namespace) -> Path:
    judge_args = argparse.Namespace(
        version=args.version,
        date=args.date,
        output_dir=args.output_dir,
        clean=True,
        skip_frontend_build=args.skip_frontend_build,
        skip_wheelhouse=args.skip_wheelhouse,
        skip_python_libs=args.skip_python_libs,
        skip_portable_python=args.skip_portable_python,
        no_zip=True,
    )
    release_root, _ = build_release(judge_args)
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
    path.write_text(text, encoding="utf-8", newline="\n")


def write_tauri_launcher(release_root: Path) -> None:
    write_text(
        release_root / "启动造价智算-Tauri-MVP.bat",
        f"""@echo off
setlocal
chcp 65001 >nul
set "GUANKAN_APP_ROOT=%~dp0"
start "" "%~dp0{TAURI_EXE_NAME}"
""",
    )


def zip_release(release_root: Path, output_zip: Path) -> Path:
    if output_zip.exists():
        output_zip.unlink()
    with ZipFile(output_zip, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(release_root.rglob("*")):
            if path.is_file():
                relative = path.relative_to(release_root)
                if ".runtime" in relative.parts:
                    continue
                archive.write(path, relative.as_posix())
    return output_zip


def build_tauri_release(args: argparse.Namespace) -> tuple[Path, Path | None]:
    project_root = Path(args.project_root).resolve()
    version = args.version or detect_version(project_root)
    release_root = build_judge_stage(project_root, args)

    if not args.skip_npm_install and not (project_root / "node_modules").exists():
        run([npm_command(), "install"], cwd=project_root)
    run([npm_command(), "run", "tauri:build"], cwd=project_root)

    tauri_exe = find_tauri_exe(project_root)
    target_exe = release_root / TAURI_EXE_NAME
    shutil.copy2(tauri_exe, target_exe)
    write_tauri_launcher(release_root)

    manifest_path = release_root / "RELEASE_MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {}
    manifest["release_kind"] = TAURI_RELEASE_KIND
    manifest["version"] = version
    manifest.setdefault("entrypoints", [])
    for entrypoint in ("启动造价智算-Tauri-MVP.bat", TAURI_EXE_NAME):
        if entrypoint not in manifest["entrypoints"]:
            manifest["entrypoints"].append(entrypoint)
    manifest["tauri_notes"] = [
        "Tauri 壳只负责启动或复用 127.0.0.1:8000 后端并承载现有 React 页面。",
        "后端、web、便携 Python 和业务资料复用评委运行版绿色目录。",
        "目标电脑不需要安装 Node；如 runtime/python 完整，也不需要单独安装 Python。",
    ]
    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

    output_zip: Path | None = None
    if not args.no_zip:
        archive_dir = (project_root / args.output_dir).resolve()
        output_zip = archive_dir / f"造价智算-{TAURI_RELEASE_KIND}-{args.date}-{version}.zip"
        zip_release(release_root, output_zip)
        print(f"zip={output_zip}")
        print(f"zip_sha256={sha256(output_zip)}")

    print(f"release_dir={release_root}")
    print(f"tauri_exe={target_exe}")
    return release_root, output_zip


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成造价智算 Tauri 桌面壳 MVP 绿色目录。")
    parser.add_argument("--project-root", default=".", help="项目根目录，默认当前目录。")
    parser.add_argument("--version", default="", help="版本号，例如 v5.0.0；默认从 README.md 识别。")
    parser.add_argument("--date", default=date.today().isoformat(), help="日期，默认今天。")
    parser.add_argument("--output-dir", default="04-输出版本存档", help="输出目录。")
    parser.add_argument("--skip-npm-install", action="store_true", help="跳过根目录 npm install。")
    parser.add_argument("--skip-frontend-build", action="store_true", help="评委阶段跳过 frontend 构建。")
    parser.add_argument("--skip-wheelhouse", action="store_true", help="评委阶段不下载离线 wheels。")
    parser.add_argument("--skip-python-libs", action="store_true", help="评委阶段不预装 runtime/python-libs。")
    parser.add_argument("--skip-portable-python", action="store_true", help="评委阶段不内置 runtime/python。")
    parser.add_argument("--no-zip", action="store_true", help="只生成绿色目录，不压缩。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    build_tauri_release(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
