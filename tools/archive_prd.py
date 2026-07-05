from __future__ import annotations

import argparse
import shutil
from datetime import date
from pathlib import Path


def next_archive_dir(archive_root: Path, date_text: str) -> Path:
    index = 1
    while True:
        candidate = archive_root / f"{date_text}-v{index}"
        if not candidate.exists():
            return candidate
        index += 1


def should_copy(path: Path, prd_root: Path) -> bool:
    relative = path.relative_to(prd_root).as_posix()
    if relative.startswith("archive/"):
        return False
    return path.is_file() and path.suffix.lower() == ".md"


def archive_prd(project_root: Path, date_text: str) -> Path:
    prd_root = project_root / "00-PRD"
    if not prd_root.exists():
        raise FileNotFoundError(f"PRD directory not found: {prd_root}")

    archive_root = prd_root / "archive"
    archive_dir = next_archive_dir(archive_root, date_text)
    archive_dir.mkdir(parents=True, exist_ok=False)

    copied = 0
    for source in sorted(prd_root.rglob("*.md")):
        if not should_copy(source, prd_root):
            continue
        target = archive_dir / source.relative_to(prd_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1

    manifest = archive_dir / "README.md"
    manifest.write_text(
        "\n".join(
            [
                "# PRD 备份说明",
                "",
                f"- 备份日期：{date_text}",
                f"- 备份文件数：{copied}",
                "- 说明：本目录为修改 PRD 前的旧版快照，日常开发默认不读取 archive。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return archive_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive current PRD markdown files.")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    archive_dir = archive_prd(project_root, args.date.strip())
    print(f"archive_dir={archive_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
