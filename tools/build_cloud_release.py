from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_SKILL_STATUSES = {"active", "beta"}
BASE_PATHS = (
    "backend/app",
    "backend/requirements-runtime.txt",
    "backend/feishu_bot_runner.py",
    "frontend/dist",
    "business-skills",
    "config",
    "deploy",
    "tools/check_cloud_release.py",
    "tools/check_feishu_deployment.py",
    "README.md",
    "AGENTS.md",
    "CHANGELOG.md",
    ".env.local.example",
)
EXTRA_RUNTIME_PATHS = (
    "05-经验池-预警数据/【经验池】【模板勿动】-管勘智算.xlsx",
    "05-经验池-预警数据/experience-field-preferences-【codex】.json",
    "03-【匹配规则】-勘察测绘知识库-匹配规则提炼/【术语归并】术语归并与匹配放宽规则表.xlsx",
)
FORBIDDEN_FILE_NAMES = {
    ".env.local",
    "cloud-deployment-credentials.json",
    "knowledge-memory.sqlite3",
    "runner.out.log",
    "runner.err.log",
}
FORBIDDEN_SUFFIXES = {".log", ".sqlite", ".sqlite3", ".pyc"}
FRONTEND_ASSET_PATTERN = re.compile(r'(?:src|href)="([^"]+\.(?:js|css))"')


def npm_command() -> str:
    return "npm.cmd" if sys.platform.startswith("win") else "npm"


def detect_version(project_root: Path) -> str:
    package = json.loads((project_root / "package.json").read_text(encoding="utf-8"))
    version = str(package.get("version") or "").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"package.json 版本号无效：{version or '空'}")
    return f"v{version}"


def run(command: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def ignore_generated(_: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache", ".env.local", "Codex-Temp"}
    return {name for name in names if name in ignored or name.endswith((".pyc", ".log"))}


def resolve_project_path(project_root: Path, relative: str) -> tuple[Path, Path]:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"发布资产必须使用项目内相对路径：{relative}")
    source = (project_root / relative_path).resolve(strict=True)
    source.relative_to(project_root.resolve())
    return source, relative_path


def reject_escaping_symlinks(source: Path, project_root: Path) -> None:
    paths = [source] if source.is_file() else source.rglob("*")
    for path in paths:
        if path.is_symlink():
            path.resolve(strict=True).relative_to(project_root.resolve())


def copy_project_path(project_root: Path, release_root: Path, relative: str) -> None:
    source, relative_path = resolve_project_path(project_root, relative)
    reject_escaping_symlinks(source, project_root)
    target = release_root / relative_path
    if source.is_dir():
        shutil.copytree(
            source,
            target,
            dirs_exist_ok=True,
            ignore=ignore_generated,
        )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def iter_asset_values(assets: dict[str, Any]) -> Iterable[str]:
    for raw_value in assets.values():
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        for value in values:
            if isinstance(value, str) and value.strip():
                yield value.strip()


def active_skill_asset_paths(project_root: Path) -> list[str]:
    paths: set[str] = set()
    for manifest_path in sorted((project_root / "business-skills").glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(manifest.get("status") or "").strip() not in ACTIVE_SKILL_STATUSES:
            continue
        assets = manifest.get("assets")
        if not isinstance(assets, dict) or not assets:
            raise ValueError(f"已上线专业能力没有声明资产：{manifest_path}")
        paths.update(iter_asset_values(assets))
    return sorted(paths)


def configured_knowledge_paths(project_root: Path) -> list[str]:
    config_path = project_root / "config/knowledge-qa-libraries.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    paths: set[str] = set()
    for library in payload.get("libraries", []):
        if not isinstance(library, dict) or library.get("kind") != "static":
            continue
        for value in library.get("paths", []):
            if isinstance(value, str) and value.strip():
                paths.add(value.strip())
    return sorted(paths)


def validate_frontend_assets(release_root: Path) -> list[str]:
    dist_root = release_root / "frontend/dist"
    index_path = dist_root / "index.html"
    html = index_path.read_text(encoding="utf-8")
    refs = FRONTEND_ASSET_PATTERN.findall(html)
    errors: list[str] = []
    if not refs:
        errors.append("frontend/dist/index.html 未引用任何 JS 或 CSS")
    for reference in refs:
        if "://" in reference:
            continue
        target = dist_root / reference.split("?", 1)[0].lstrip("/")
        if not target.is_file():
            errors.append(f"首页引用资源不存在：{reference}")
    return errors


def forbidden_release_paths(release_root: Path) -> list[str]:
    errors: list[str] = []
    for path in release_root.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(release_root)
        if (
            path.name in FORBIDDEN_FILE_NAMES
            or (path.name.startswith(".env") and path.name != ".env.local.example")
            or path.suffix.lower() in FORBIDDEN_SUFFIXES
            or tuple(relative.parts[:2]) == ("Codex-Temp", "runtime")
        ):
            errors.append(relative.as_posix())
    return sorted(errors)


def run_release_gate(release_root: Path) -> None:
    run(
        [
            sys.executable,
            str(release_root / "tools/check_cloud_release.py"),
            "--release-root",
            str(release_root),
        ],
        cwd=release_root,
    )


def assemble_release(project_root: Path, release_root: Path) -> None:
    if release_root.exists():
        raise FileExistsError(f"输出目录已存在，拒绝覆盖：{release_root}")
    release_root.mkdir(parents=True)
    paths = set(BASE_PATHS)
    paths.update(EXTRA_RUNTIME_PATHS)
    paths.update(active_skill_asset_paths(project_root))
    paths.update(configured_knowledge_paths(project_root))
    for relative in sorted(paths):
        copy_project_path(project_root, release_root, relative)

    frontend_errors = validate_frontend_assets(release_root)
    forbidden = forbidden_release_paths(release_root)
    errors = [*frontend_errors, *(f"发布包包含禁止文件：{path}" for path in forbidden)]
    if errors:
        raise RuntimeError("\n".join(errors))
    run_release_gate(release_root)


def create_utf8_archive(release_root: Path, archive_path: Path) -> str:
    if archive_path.exists():
        raise FileExistsError(f"归档文件已存在，拒绝覆盖：{archive_path}")
    with tarfile.open(archive_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(release_root.rglob("*")):
            archive.add(path, arcname=path.relative_to(release_root).as_posix(), recursive=False)
    digest = hashlib.sha256()
    with archive_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成完整、安全、UTF-8 保真的造价智算云端发布包。")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="本次独立输出目录；默认写入 Codex-Temp/cloud-deploy/<时间>-<版本>-cloud-release。",
    )
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="复用现有 frontend/dist；只用于已单独完成前端构建的场景。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    version = detect_version(project_root)
    if not args.skip_frontend_build:
        run([npm_command(), "run", "frontend:build"], cwd=project_root)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_dir or Path(
        f"Codex-Temp/cloud-deploy/{timestamp}-{version}-cloud-release"
    )
    output_root = (
        output_dir.resolve()
        if output_dir.is_absolute()
        else (project_root / output_dir).resolve()
    )
    release_root = output_root / "release"
    archive_path = output_root / f"zaojiazhisuan-cloud-{version}-utf8.tar.gz"

    assemble_release(project_root, release_root)
    sha256 = create_utf8_archive(release_root, archive_path)
    print(f"release_root={release_root}")
    print(f"archive={archive_path}")
    print(f"sha256={sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
