from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


ALLOWED_STATUSES = {"已完成", "进行中", "待开发", "暂缓", "不做"}
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
STATUS_RE = re.compile(r"\[([^\]]+)\]")
CODE_SPAN_RE = re.compile(r"`([^`]+)`")


@dataclass
class AssetCheck:
    asset_type: str
    raw_path: str
    purpose: str
    exists: bool
    resolved: str


@dataclass
class ModuleCheck:
    name: str
    path: Path
    has_demand_list: bool
    has_assets: bool
    has_boundary: bool
    has_acceptance: bool
    demand_count: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    invalid_statuses: list[str] = field(default_factory=list)
    assets: list[AssetCheck] = field(default_factory=list)
    missing_assets: list[AssetCheck] = field(default_factory=list)

    @property
    def issues(self) -> list[str]:
        items: list[str] = []
        if not self.has_demand_list:
            items.append("缺少需求清单")
        if not self.has_assets:
            items.append("缺少关联资产")
        if not self.has_boundary:
            items.append("缺少功能边界")
        if not self.has_acceptance:
            items.append("缺少验收口径")
        if self.invalid_statuses:
            items.append("存在非法状态：" + "、".join(sorted(set(self.invalid_statuses))))
        if self.missing_assets:
            items.append(f"关联资产缺失 {len(self.missing_assets)} 项")
        return items


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def extract_section(text: str, heading: str) -> str:
    matches = list(SECTION_RE.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1).strip() == heading:
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[start:end].strip()
    return ""


def parse_markdown_table(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        rows.append(cells)
    if rows and all(cell in {"状态", "需求", "说明", "验收口径", "类型", "文件", "用途"} for cell in rows[0]):
        return rows[1:]
    return rows


def resolve_asset(project_root_path: Path, raw_path: str) -> Path:
    normalized = raw_path.strip().replace("/", "\\")
    candidate = Path(normalized)
    if candidate.is_absolute():
        return candidate
    return project_root_path / normalized


def check_module(project_root_path: Path, module_file: Path) -> ModuleCheck:
    text = module_file.read_text(encoding="utf-8")
    demand_section = extract_section(text, "需求清单")
    asset_section = extract_section(text, "关联资产")
    boundary_section = extract_section(text, "功能边界")
    acceptance_section = extract_section(text, "验收口径")

    result = ModuleCheck(
        name=module_file.parent.name,
        path=module_file,
        has_demand_list=bool(demand_section),
        has_assets=bool(asset_section),
        has_boundary=bool(boundary_section),
        has_acceptance=bool(acceptance_section),
    )

    for row in parse_markdown_table(demand_section):
        if len(row) < 1:
            continue
        result.demand_count += 1
        status_match = STATUS_RE.search(row[0])
        if not status_match:
            result.invalid_statuses.append(row[0] or "空状态")
            continue
        status = status_match.group(1)
        if status not in ALLOWED_STATUSES:
            result.invalid_statuses.append(status)
            continue
        result.status_counts[status] = result.status_counts.get(status, 0) + 1

    for row in parse_markdown_table(asset_section):
        if len(row) < 3:
            continue
        asset_type, file_cell, purpose = row[0], row[1], row[2]
        paths = CODE_SPAN_RE.findall(file_cell)
        if not paths:
            continue
        for raw in paths:
            resolved = resolve_asset(project_root_path, raw)
            exists = resolved.exists()
            item = AssetCheck(asset_type, raw, purpose, exists, str(resolved))
            result.assets.append(item)
            if not exists:
                result.missing_assets.append(item)

    return result


def scan_old_prd_paths(project_root_path: Path) -> list[str]:
    findings: list[str] = []
    search_files = [
        project_root_path / "README.md",
        project_root_path / "AGENTS.md",
        project_root_path / "CHANGELOG.md",
        project_root_path / "00-PRD" / "00-PRD工作方式说明.md",
    ]
    patterns = ("docs/PRD", "docs\\PRD", "`PRD/", "`PRD\\")
    for path in search_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(pattern in line for pattern in patterns):
                findings.append(f"{path.relative_to(project_root_path)}:{lineno}: {line.strip()}")
    return findings


def status_text(module: ModuleCheck) -> str:
    if module.issues:
        return "部分不一致"
    return "硬检查通过"


def render_report(project_root_path: Path, checks: list[ModuleCheck], old_path_findings: list[str]) -> str:
    total_modules = len(checks)
    issue_modules = [item for item in checks if item.issues]
    missing_asset_count = sum(len(item.missing_assets) for item in checks)
    total_demands = sum(item.demand_count for item in checks)
    total_assets = sum(len(item.assets) for item in checks)

    if not issue_modules and not old_path_findings:
        conclusion = "硬一致性检查通过。PRD 结构、状态标记和关联资产路径未发现明显问题。"
    else:
        conclusion = "部分不一致。请优先处理缺失资产、旧路径残留或非法状态；业务完成度仍需人工复核。"

    lines: list[str] = [
        "# PRD 一致性巡检",
        "",
        f"- 巡检日期：{date.today().isoformat()}",
        f"- 巡检范围：`00-PRD/01-模块PRD/*/PRD.md`",
        f"- 巡检结论：{conclusion}",
        "",
        "## 巡检说明",
        "",
        "- 本脚本只做硬一致性检查：PRD 结构、状态标记、关联资产路径和旧路径残留。",
        "- `[已完成]` 是否真的完成，只能结合 README、CHANGELOG、代码和人工验收继续判断。",
        "- 运行缓存、外部绝对路径或评委材料如不存在，需人工判断是否属于合理缺失。",
        "",
        "## 总览",
        "",
        f"- 模块数：{total_modules}",
        f"- 需求条目：{total_demands}",
        f"- 关联资产：{total_assets}",
        f"- 存在问题模块：{len(issue_modules)}",
        f"- 缺失资产项：{missing_asset_count}",
        f"- 旧 PRD 路径残留：{len(old_path_findings)}",
        "",
        "## 模块巡检表",
        "",
        "| 模块 | 需求清单 | 关联资产 | 状态分布 | 缺失资产 | 结论 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for item in checks:
        status_distribution = "，".join(
            f"{status}{item.status_counts.get(status, 0)}"
            for status in ["已完成", "进行中", "待开发", "暂缓", "不做"]
            if item.status_counts.get(status, 0)
        ) or "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    item.name,
                    "有" if item.has_demand_list else "缺失",
                    "有" if item.has_assets else "缺失",
                    status_distribution,
                    str(len(item.missing_assets)),
                    status_text(item),
                ]
            )
            + " |"
        )

    if issue_modules:
        lines.extend(["", "## 需要处理的问题", ""])
        for item in issue_modules:
            lines.append(f"### {item.name}")
            for issue in item.issues:
                lines.append(f"- {issue}")
            for asset in item.missing_assets:
                lines.append(f"- 缺失资产：`{asset.raw_path}`，用途：{asset.purpose}")

    if old_path_findings:
        lines.extend(["", "## 旧路径残留", ""])
        for finding in old_path_findings:
            lines.append(f"- {finding}")

    lines.extend(
        [
            "",
            "## 人工复核建议",
            "",
            "1. 对 `[已完成]` 需求抽查 README、CHANGELOG、测试记录或实际功能，确认是否真的完成。",
            "2. 对 `[进行中]` 需求决定下一版是继续推进，还是改为 `[已完成]`、`[待开发]` 或 `[暂缓]`。",
            "3. 对缺失资产判断是否为路径错误、运行缓存未生成、外部材料不在当前机器，还是 PRD 引用过度。",
            "4. 下一版开发前，优先从 `[待开发]` 和 `[进行中]` 中选择少量主线，不要一次性展开所有模块。",
            "",
        ]
    )
    return "\n".join(lines)


def run(write: bool) -> tuple[str, int]:
    root = project_root()
    prd_root = root / "00-PRD"
    module_root = prd_root / "01-模块PRD"
    if not module_root.exists():
        raise FileNotFoundError(f"Module PRD directory not found: {module_root}")

    checks = [
        check_module(root, path)
        for path in sorted(module_root.glob("*/PRD.md"), key=lambda item: item.as_posix().lower())
    ]
    old_path_findings = scan_old_prd_paths(root)
    report = render_report(root, checks, old_path_findings)

    if write:
        output = prd_root / "04-PRD一致性巡检.md"
        output.write_text(report, encoding="utf-8")
        print(f"report={output}")
    else:
        print(report)

    issue_count = sum(len(item.issues) for item in checks) + len(old_path_findings)
    return report, issue_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Check PRD hard consistency and optionally write a report.")
    parser.add_argument("--no-write", action="store_true", help="Print report only, do not write 00-PRD/04-PRD一致性巡检.md")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when hard consistency issues are found")
    args = parser.parse_args()

    _, issue_count = run(write=not args.no_write)
    if args.strict and issue_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
