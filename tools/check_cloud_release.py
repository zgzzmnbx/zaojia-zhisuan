from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_CLOUD_PATHS = (
    Path("backend/app/main.py"),
    Path("backend/requirements-runtime.txt"),
    Path("frontend/dist/index.html"),
    Path("config/project-default-settings.json"),
    Path("deploy/install_cloud_runtime_guard.sh"),
    Path("business-skills"),
)
ACTIVE_SKILL_STATUSES = {"active", "beta"}


def _asset_values(assets: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for asset_name, raw_value in assets.items():
        raw_paths = raw_value if isinstance(raw_value, list) else [raw_value]
        for raw_path in raw_paths:
            if isinstance(raw_path, str) and raw_path.strip():
                values.append((asset_name, raw_path.strip()))
            else:
                values.append((asset_name, ""))
    return values


def collect_release_errors(release_root: Path) -> list[str]:
    root = release_root.resolve()
    errors: list[str] = []

    for relative_path in REQUIRED_CLOUD_PATHS:
        if not (root / relative_path).exists():
            errors.append(f"云端发布包缺少必需路径：{relative_path.as_posix()}")

    skills_root = root / "business-skills"
    if not skills_root.is_dir():
        return errors

    manifest_paths = sorted(skills_root.glob("*/manifest.json"))
    if not manifest_paths:
        errors.append("云端发布包没有可读取的专业能力 manifest.json")
        return errors

    for manifest_path in manifest_paths:
        relative_manifest = manifest_path.relative_to(root).as_posix()
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"专业能力清单无法读取：{relative_manifest}（{exc}）")
            continue

        status = str(manifest.get("status") or "").strip()
        if status not in ACTIVE_SKILL_STATUSES:
            continue

        assets = manifest.get("assets")
        if not isinstance(assets, dict) or not assets:
            errors.append(f"已上线专业能力没有声明资产：{relative_manifest}")
            continue

        for asset_name, asset_path in _asset_values(assets):
            if not asset_path:
                errors.append(f"专业能力资产引用为空：{relative_manifest} -> {asset_name}")
                continue
            relative_asset = Path(asset_path)
            if relative_asset.is_absolute() or ".." in relative_asset.parts:
                errors.append(
                    f"专业能力资产引用超出发布根目录：{relative_manifest} -> {asset_name} -> {asset_path}"
                )
                continue
            try:
                resolved_asset = (root / relative_asset).resolve(strict=True)
                resolved_asset.relative_to(root)
            except (OSError, ValueError):
                errors.append(
                    f"专业能力资产未随云端包发布：{relative_manifest} -> {asset_name} -> {asset_path}"
                )

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="在上传和切换前检查云端发布包必需文件及全部已上线专业 Skill 资产。",
    )
    parser.add_argument(
        "--release-root",
        type=Path,
        default=Path.cwd(),
        help="待发布目录；默认检查当前目录。",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    release_root = args.release_root.resolve()
    errors = collect_release_errors(release_root)
    if errors:
        print(f"[FAIL] 云端发布包检查失败：{release_root}")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"[OK] 云端发布包必需文件与专业 Skill 资产完整：{release_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
