from __future__ import annotations

import argparse
import shutil
from datetime import date
from pathlib import Path


OUTPUT_ROOT = "04-输出版本存档"
DEFAULT_DIR_PREFIX = "给其他AI查看-核心代码与规则"
PRD_ROOT = "00-PRD"

FIRST_TIER_FILES = [
    "AGENTS.md",
    "README.md",
    "CHANGELOG.md",
    "项目介绍-给人看的版本-【codex】.md",
    "03-【匹配规则】-勘察测绘知识库-匹配规则提炼/【重要匹配规则】项目以及总体匹配规则介绍.md",
    "03-【匹配规则】-勘察测绘知识库-匹配规则提炼/【重要匹配规则】要素1-5和单位的匹配模式介绍.md",
    "03-【匹配规则】-勘察测绘知识库-匹配规则提炼/【重要匹配规则】【第一层】-标准规则命中表-说人话版-v1.0.xlsx",
    "backend/app/main.py",
    "backend/app/fill_engine.py",
    "backend/app/adjustment_rules.py",
    "backend/app/knowledge_base.py",
    "backend/app/normalization.py",
    "frontend/src/App.tsx",
    "frontend/src/styles.css",
]

FRONTEND_COMBINE_FILES = [
    "frontend/src/main.tsx",
    "frontend/src/App.tsx",
    "frontend/src/styles.css",
    "frontend/src/vite-env.d.ts",
    "frontend/package.json",
]

BACKEND_COMBINE_FILES = [
    "backend/app/__init__.py",
    "backend/app/main.py",
    "backend/app/schemas.py",
    "backend/app/normalization.py",
    "backend/app/knowledge_base.py",
    "backend/app/adjustment_rules.py",
    "backend/app/fill_engine.py",
    "backend/app/experience_warning.py",
    "backend/app/workload_capture.py",
    "backend/app/workload_term_rules.py",
    "backend/app/formula_resolver.py",
    "backend/app/excel_recalc.py",
    "backend/app/report.py",
    "backend/app/knowledge_qa.py",
    "backend/app/llm.py",
    "backend/app/rules/manual_review_rules.csv",
    "backend/app/rules/physical_factor_rules.csv",
    "backend/app/rules/physical_factor_overrides.csv",
    "backend/app/rules/technical_fee_rules.csv",
    "backend/requirements.txt",
    "backend/requirements-runtime.txt",
]


def copy_file(project_root: Path, output_dir: Path, relative: str, missing: list[str]) -> None:
    source = project_root / relative
    if not source.exists() or not source.is_file():
        missing.append(relative)
        return
    target = output_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def language_for(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".tsx": "tsx",
        ".ts": "ts",
        ".css": "css",
        ".json": "json",
        ".csv": "csv",
        ".txt": "text",
        ".md": "markdown",
    }.get(suffix, "text")


def read_text_lossy(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").rstrip()


def write_combined_code(project_root: Path, output_path: Path, title: str, files: list[str]) -> list[str]:
    missing: list[str] = []
    lines: list[str] = [
        f"# {title}",
        "",
        f"生成日期：{date.today().isoformat()}",
        "",
        "说明：本文件由脚本自动合并，仅用于给其他 AI 快速审阅；真实代码仍以原目录文件为准。",
        "",
    ]
    for relative in files:
        source = project_root / relative
        if not source.exists() or not source.is_file():
            missing.append(relative)
            continue
        lines.extend(
            [
                "",
                f"## {relative}",
                "",
                f"```{language_for(relative)}",
                read_text_lossy(source),
                "```",
            ]
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return missing


def collect_current_prd_files(project_root: Path) -> list[Path]:
    prd_root = project_root / PRD_ROOT
    if not prd_root.exists() or not prd_root.is_dir():
        return []

    files: list[Path] = []
    for path in prd_root.rglob("*.md"):
        relative = path.relative_to(prd_root)
        if any(part.lower() == "archive" for part in relative.parts):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(project_root).as_posix())


def write_combined_prd(project_root: Path, output_path: Path) -> list[str]:
    prd_files = collect_current_prd_files(project_root)
    if not prd_files:
        output_path.write_text(
            "\n".join(
                [
                    "# PRD合并",
                    "",
                    f"生成日期：{date.today().isoformat()}",
                    "",
                    f"未找到当前 PRD Markdown 文件。请检查 `{PRD_ROOT}/` 是否存在。",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return [PRD_ROOT]

    lines: list[str] = [
        "# PRD合并",
        "",
        f"生成日期：{date.today().isoformat()}",
        "",
        "说明：本文件由脚本自动合并当前 PRD，仅用于给其他 AI 快速审阅；真实 PRD 仍以 `00-PRD/` 下各模块文件为准。",
        "",
        "合并范围：包含 `00-PRD/` 下当前 Markdown 文件；不包含 `00-PRD/archive/` 历史快照，避免新旧需求混淆。",
        "",
        "## 文件目录",
        "",
    ]
    for path in prd_files:
        relative = path.relative_to(project_root).as_posix()
        lines.append(f"- `{relative}`")

    for path in prd_files:
        relative = path.relative_to(project_root).as_posix()
        lines.extend(
            [
                "",
                "---",
                "",
                f"## 文件：{relative}",
                "",
                read_text_lossy(path),
            ]
        )

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return []


def write_bundle_readme(output_dir: Path, copied: list[str], missing: list[str]) -> None:
    lines = [
        "# 给其他 AI 查看-核心代码与规则",
        "",
        f"生成日期：{date.today().isoformat()}",
        "",
        "## 内容",
        "",
        "- `第一层级文件/`：按相对路径复制的第一优先级文件。",
        "- `前端代码合并.md`：合并后的前端核心代码。",
        "- `后端代码合并.md`：合并后的后端核心代码与 CSV 规则。",
        "- `PRD合并.md`：合并后的当前 PRD，已排除 `00-PRD/archive/` 历史快照。",
        "- `给其他AI评判项目的重要文件清单.md`：完整建议清单。",
        "",
        "## 已复制文件",
        "",
    ]
    lines.extend(f"- `{item}`" for item in copied)
    if missing:
        lines.extend(["", "## 未找到文件", ""])
        lines.extend(f"- `{item}`" for item in missing)
    output_dir.joinpath("README-给其他AI查看.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_bundle(project_root: Path, date_text: str) -> Path:
    output_dir = project_root / OUTPUT_ROOT / f"{DEFAULT_DIR_PREFIX}-{date_text}"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    first_tier_dir = output_dir / "第一层级文件"
    first_tier_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    for relative in FIRST_TIER_FILES:
        before = len(missing)
        copy_file(project_root, first_tier_dir, relative, missing)
        if len(missing) == before:
            copied.append(relative)

    checklist_source = project_root / OUTPUT_ROOT / "给其他AI评判项目的重要文件清单.md"
    if checklist_source.exists():
        shutil.copy2(checklist_source, output_dir / checklist_source.name)
    else:
        missing.append(str(checklist_source.relative_to(project_root)))

    missing.extend(
        write_combined_code(
            project_root,
            output_dir / "前端代码合并.md",
            "前端代码合并",
            FRONTEND_COMBINE_FILES,
        )
    )
    missing.extend(
        write_combined_code(
            project_root,
            output_dir / "后端代码合并.md",
            "后端代码合并",
            BACKEND_COMBINE_FILES,
        )
    )
    missing.extend(write_combined_prd(project_root, output_dir / "PRD合并.md"))
    write_bundle_readme(output_dir, copied, missing)
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出给其他 AI 查看的一层级核心代码与规则。")
    parser.add_argument("--project-root", default=".", help="项目根目录，默认当前目录。")
    parser.add_argument("--date", default=date.today().isoformat(), help="日期，默认今天。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    output_dir = export_bundle(project_root, args.date.strip())
    print(f"output_dir={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
