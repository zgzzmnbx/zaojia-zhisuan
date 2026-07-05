from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


WORKFLOW_ARCHIVE_COPY_DIR = Path(
    r"D:\Desktop\01-工作流-【造价】\工作流\260612-【ai大赛】-管勘智算-V2.0\04-输出版本存档"
)
INCLUDE_DIRS = (
    "backend",
    "frontend",
    "docs",
    "tools",
    "scripts",
    "src-tauri",
    "00-PRD",
    "01-assets/01-UI参考图",
)
INCLUDE_FILES = (
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "package-lock.json",
    "package.json",
    "README.md",
    "TASKS.md",
    "03-【匹配规则】-勘察测绘知识库-匹配规则提炼/【重要匹配规则】项目以及总体匹配规则介绍.md",
    "管勘智算启动器-【codex】.ps1",
    "检查管勘智算状态-【codex】.bat",
    "启动管勘智算-【codex】.bat",
    "启动管勘智算-Tauri-MVP.bat",
    "导出给其他AI查看-核心代码与规则.bat",
    "备份代码.bat",
    "备份PRD.bat",
)
EXCLUDE_PREFIXES = (
    "frontend/node_modules/",
    "frontend/dist/",
    "Codex-Temp/",
    "04-输出版本存档/",
    ".pytest_cache/",
    "node_modules/",
    "src-tauri/target/",
    "src-tauri/gen/",
    "00-比赛要求与目标/",
    "01-weagent部分成果/",
    "03-知识库-二维数据库制作/",
    "07-汇报PPT 和 演示素材/",
    "01-assets/01-UI参考图/01-assets/",
    "01-assets/01-UI参考图/00-reference/",
    "00-PRD/PRD-Claude建议包-2026年7月3日/claude的界面建议-",
)


def detect_version(project_root: Path) -> str:
    readme = project_root / "README.md"
    if not readme.exists():
        raise FileNotFoundError(f"未找到 README.md，无法自动识别版本：{readme}")
    text = readme.read_text(encoding="utf-8")
    patterns = [
        r"当前版本[：:]\s*`?([vV]\d+(?:\.\d+)+)`?",
        r"version[：:]\s*`?([vV]\d+(?:\.\d+)+)`?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).lower()
    raise ValueError("README.md 中未找到形如 v2.02 的当前版本号")


def to_archive_name(path: Path, project_root: Path) -> str:
    return path.relative_to(project_root).as_posix()


def should_exclude(entry_name: str) -> bool:
    if entry_name == ".env.local":
        return True
    if any(entry_name.startswith(prefix) for prefix in EXCLUDE_PREFIXES):
        return True
    if "/__pycache__/" in f"/{entry_name}/":
        return True
    if entry_name.endswith((".pyc", ".tsbuildinfo", ".zip")):
        return True
    generated_frontend_configs = {
        "frontend/vite.config.js",
        "frontend/vite.config.d.ts",
    }
    return entry_name in generated_frontend_configs


def iter_code_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for dirname in INCLUDE_DIRS:
        root = project_root / dirname
        if root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())
    for filename in INCLUDE_FILES:
        path = project_root / filename
        if path.exists() and path.is_file():
            files.append(path)

    unique = sorted(set(files), key=lambda item: to_archive_name(item, project_root).lower())
    return [
        path
        for path in unique
        if not should_exclude(to_archive_name(path, project_root))
    ]


def create_manifest(
    project_root: Path,
    version: str,
    date_text: str,
    files: list[Path],
) -> dict[str, object]:
    return {
        "project": "造价智算",
        "archive_type": "code-only",
        "version": version,
        "date": date_text,
        "include_dirs": list(INCLUDE_DIRS),
        "include_files": list(INCLUDE_FILES),
        "exclude_prefixes": list(EXCLUDE_PREFIXES),
        "file_count": len(files),
        "files": [to_archive_name(path, project_root) for path in files],
    }


def create_archive(
    project_root: Path,
    archive_dir: Path,
    version: str,
    date_text: str,
    overwrite: bool = True,
) -> Path:
    project_root = project_root.resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"造价智算-{date_text}-{version}.zip"
    if archive_path.exists():
        if not overwrite:
            raise FileExistsError(f"压缩包已存在：{archive_path}")
        archive_path.unlink()

    files = iter_code_files(project_root)
    manifest = create_manifest(project_root, version, date_text, files)
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, to_archive_name(path, project_root))
        archive.writestr(
            "ARCHIVE_MANIFEST.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
    return archive_path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def copy_to_workflow_archive(archive_path: Path) -> Path:
    WORKFLOW_ARCHIVE_COPY_DIR.mkdir(parents=True, exist_ok=True)
    target_path = WORKFLOW_ARCHIVE_COPY_DIR / archive_path.name
    if archive_path.resolve() != target_path.resolve():
        shutil.copy2(archive_path, target_path)
    return target_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成造价智算代码版版本存档。")
    parser.add_argument("--project-root", default=".", help="项目根目录，默认当前目录。")
    parser.add_argument("--archive-dir", default="04-输出版本存档", help="输出目录。")
    parser.add_argument("--version", default="", help="版本号，例如 v2.02；默认从 README.md 识别。")
    parser.add_argument("--date", default=date.today().isoformat(), help="日期，默认今天。")
    parser.add_argument("--no-overwrite", action="store_true", help="如果同名压缩包已存在则报错。")
    parser.add_argument("--dry-run", action="store_true", help="只列出将被打包的文件，不生成压缩包。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    project_root = Path(args.project_root).resolve()
    archive_dir = (project_root / args.archive_dir).resolve()
    version = args.version.strip() or detect_version(project_root)
    date_text = args.date.strip()
    files = iter_code_files(project_root)

    if args.dry_run:
        print(f"project_root={project_root}")
        print(f"version={version}")
        print(f"date={date_text}")
        print(f"file_count={len(files)}")
        for path in files:
            print(to_archive_name(path, project_root))
        return 0

    archive_path = create_archive(
        project_root=project_root,
        archive_dir=archive_dir,
        version=version,
        date_text=date_text,
        overwrite=not args.no_overwrite,
    )
    workflow_archive_copy = copy_to_workflow_archive(archive_path)
    size_mb = archive_path.stat().st_size / 1024 / 1024
    print(f"archive={archive_path}")
    print(f"workflow_archive_copy={workflow_archive_copy}")
    print(f"size_mb={size_mb:.3f}")
    print(f"sha256={sha256(archive_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
