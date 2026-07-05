from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


ENTRY_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
DEFAULT_KEEP = 3


@dataclass(frozen=True)
class ChangelogEntry:
    title: str
    text: str


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_changelog(text: str) -> tuple[str, list[ChangelogEntry]]:
    text = normalize_newlines(text)
    matches = list(ENTRY_RE.finditer(text))
    if not matches:
        preamble = text.strip() or "# CHANGELOG"
        return preamble + "\n\n", []

    preamble = text[: matches[0].start()].strip()
    entries: list[ChangelogEntry] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        entry_text = text[start:end].strip()
        entries.append(ChangelogEntry(title=match.group(1).strip(), text=entry_text))

    return (preamble or "# CHANGELOG") + "\n\n", entries


def render_changelog(preamble: str, entries: list[ChangelogEntry]) -> str:
    parts = [preamble.strip()]
    parts.extend(entry.text.strip() for entry in entries)
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


def merge_archive_entries(
    moved_entries: list[ChangelogEntry],
    archive_entries: list[ChangelogEntry],
) -> list[ChangelogEntry]:
    merged: list[ChangelogEntry] = []
    seen: set[str] = set()
    for entry in [*moved_entries, *archive_entries]:
        key = entry.title.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    return merged


def trim_changelog(
    changelog_path: Path,
    archive_path: Path,
    keep: int,
    dry_run: bool,
) -> tuple[int, int, int]:
    if keep < 1:
        raise ValueError("--keep 必须大于等于 1")
    if not changelog_path.exists():
        raise FileNotFoundError(f"未找到 CHANGELOG：{changelog_path}")

    changelog_text = changelog_path.read_text(encoding="utf-8-sig")
    active_preamble, active_entries = split_changelog(changelog_text)
    kept_entries = active_entries[:keep]
    moved_entries = active_entries[keep:]

    archive_preamble = "# CHANGELOG\n\n"
    archive_entries: list[ChangelogEntry] = []
    if archive_path.exists():
        archive_preamble, archive_entries = split_changelog(
            archive_path.read_text(encoding="utf-8-sig")
        )

    merged_archive_entries = merge_archive_entries(moved_entries, archive_entries)

    if not dry_run:
        changelog_path.write_text(
            render_changelog(active_preamble, kept_entries),
            encoding="utf-8",
            newline="\n",
        )
        archive_path.write_text(
            render_changelog(archive_preamble, merged_archive_entries),
            encoding="utf-8",
            newline="\n",
        )

    return len(active_entries), len(kept_entries), len(moved_entries)


def parse_args() -> argparse.Namespace:
    root = project_root()
    parser = argparse.ArgumentParser(
        description="保留 CHANGELOG.md 前 N 条记录，并把其余记录合并到归档文件。"
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_KEEP,
        help=f"CHANGELOG.md 保留的记录条数，默认 {DEFAULT_KEEP}。",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=root / "CHANGELOG.md",
        help="当前 CHANGELOG 文件路径。",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=root / "CHANGELOG - 【归档】.md",
        help="归档 CHANGELOG 文件路径。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示将移动多少条，不写入文件。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    total, kept, moved = trim_changelog(
        changelog_path=args.changelog,
        archive_path=args.archive,
        keep=args.keep,
        dry_run=args.dry_run,
    )
    action = "预览" if args.dry_run else "完成"
    print(f"{action}：当前记录 {total} 条，保留 {kept} 条，归档 {moved} 条。")
    print(f"CHANGELOG：{args.changelog}")
    print(f"归档文件：{args.archive}")


if __name__ == "__main__":
    main()
