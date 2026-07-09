from __future__ import annotations

import ast
import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".rs",
    ".ps1",
    ".bat",
    ".cmd",
    ".sh",
    ".json",
    ".md",
    ".toml",
    ".css",
}
SCAN_DIRS = (
    "backend/app",
    "backend/tests",
    "frontend/src",
    "src-tauri/src",
    "tools",
    "scripts",
)
SKIP_PARTS = {
    "__pycache__",
    "node_modules",
    "dist",
    "target",
    "Codex-Temp",
    "04-输出版本存档",
    ".pytest_cache",
}
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z]:\\|[A-Za-z]:/)")
WINDOWS_CALL_RE = re.compile(r"\b(os\.startfile|win32|powershell|cmd\.exe)\b", re.IGNORECASE)
FRONTEND_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[^'"]+\s+from\s+)?|export\s+[^'"]+\s+from\s+|import\s*\()\s*['"]([^'"]+)['"]""",
    re.MULTILINE,
)

KNOWN_WINDOWS_ONLY_FILES = {
    "tools/check_platform_compat.py": "兼容性检查脚本自身的 Windows 风险关键字定义",
    "tools/archive_code.py": "按项目约定同步复制到 Windows 工作流目录",
    "tools/build_green_release.py": "生成现有 Windows 绿色版启动器和便携运行目录",
    "tools/run_tauri.ps1": "现有 Windows Tauri 辅助启动脚本",
    "tools/export_ai_review_bundle_window.ps1": "现有 Windows 图形导出辅助脚本",
    "backend/app/excel_recalc.py": "可选调用本机 Excel/COM 重算公式，失败时返回 False",
}
KNOWN_WINDOWS_PATTERNS = {
    "package.json": ("powershell", "现有 Windows 脚本入口"),
}
REQUIRED_RELATIVE_PATHS = (
    "backend/app/main.py",
    "backend/app/paths.py",
    "frontend/package.json",
    "frontend/src/App.tsx",
    "03-知识库-二维数据库制作/【数据库】【导入】.xlsx",
    "05-经验池-预警数据/【经验池】【模板勿动】-管勘智算.xlsx",
    "03-【匹配规则】-勘察测绘知识库-匹配规则提炼/【术语归并】术语归并与匹配放宽规则表.xlsx",
    "tools/archive_code.py",
)


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    path: str
    line: int
    message: str


def iter_scan_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for dirname in SCAN_DIRS:
        root = project_root / dirname
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            rel_parts = set(path.relative_to(project_root).parts)
            if rel_parts.intersection(SKIP_PARTS):
                continue
            files.append(path)
    for rel in ("package.json",):
        path = project_root / rel
        if path.exists():
            files.append(path)
    return sorted(set(files), key=lambda item: item.relative_to(project_root).as_posix().lower())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def is_known_windows_context(relative: str, text: str) -> str:
    if relative in KNOWN_WINDOWS_ONLY_FILES:
        return KNOWN_WINDOWS_ONLY_FILES[relative]
    pattern = KNOWN_WINDOWS_PATTERNS.get(relative)
    if pattern and pattern[0].lower() in text.lower():
        return pattern[1]
    return ""


def scan_windows_paths_and_calls(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_scan_files(project_root):
        relative = path.relative_to(project_root).as_posix()
        if relative == "tools/check_platform_compat.py":
            continue
        text = read_text(path)
        known_context = is_known_windows_context(relative, text)
        for line_number, line in enumerate(text.splitlines(), start=1):
            checks = [
                (WINDOWS_ABSOLUTE_PATH_RE.search(line), "WIN_ABS_PATH", "存在 Windows 绝对路径"),
                (WINDOWS_CALL_RE.search(line), "WIN_CALL", "存在 Windows 专属调用或命令"),
            ]
            for match, code, message in checks:
                if not match:
                    continue
                if known_context:
                    findings.append(Finding("WARN", code, relative, line_number, f"{message}；已知上下文：{known_context}"))
                else:
                    findings.append(Finding("FAIL", code, relative, line_number, message))
    return findings


def frontend_source_files(project_root: Path) -> dict[str, Path]:
    source_root = project_root / "frontend" / "src"
    if not source_root.exists():
        return {}
    return {
        path.relative_to(source_root).as_posix(): path
        for path in source_root.rglob("*")
        if path.is_file()
    }


def resolve_frontend_import(importer: Path, specifier: str) -> Path | None:
    if not specifier.startswith("."):
        return None
    base = (importer.parent / specifier).resolve()
    candidates = [
        base,
        base.with_suffix(".ts"),
        base.with_suffix(".tsx"),
        base.with_suffix(".js"),
        base.with_suffix(".jsx"),
        base / "index.ts",
        base / "index.tsx",
        base / "index.js",
        base / "index.jsx",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return base


def scan_frontend_import_case(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    files_by_rel = frontend_source_files(project_root)
    rel_by_lower: dict[str, str] = {}
    for rel in files_by_rel:
        lower = rel.lower()
        if lower in rel_by_lower and rel_by_lower[lower] != rel:
            findings.append(Finding("FAIL", "CASE_DUPLICATE", rel, 1, f"存在仅大小写不同的前端文件：{rel_by_lower[lower]}"))
        rel_by_lower[lower] = rel

    source_root = project_root / "frontend" / "src"
    for path in files_by_rel.values():
        if path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = read_text(path)
        importer_rel = path.relative_to(project_root).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in FRONTEND_IMPORT_RE.finditer(line):
                specifier = match.group(1)
                if not specifier.startswith("."):
                    continue
                resolved = resolve_frontend_import(path, specifier)
                if resolved is None:
                    continue
                try:
                    actual_rel = resolved.relative_to(source_root).as_posix()
                except ValueError:
                    continue
                normalized_from_import = (path.parent / specifier).resolve()
                try:
                    requested_rel = normalized_from_import.relative_to(source_root).as_posix()
                except ValueError:
                    requested_rel = ""
                possible_requested = [
                    requested_rel,
                    f"{requested_rel}.ts",
                    f"{requested_rel}.tsx",
                    f"{requested_rel}.js",
                    f"{requested_rel}.jsx",
                    f"{requested_rel}/index.ts",
                    f"{requested_rel}/index.tsx",
                ]
                if actual_rel not in possible_requested and actual_rel.lower() in {item.lower() for item in possible_requested}:
                    findings.append(
                        Finding(
                            "FAIL",
                            "IMPORT_CASE",
                            importer_rel,
                            line_number,
                            f"import 路径大小写与真实文件不一致：{specifier} -> {actual_rel}",
                        )
                    )
                if not resolved.exists():
                    findings.append(
                        Finding("FAIL", "IMPORT_MISSING", importer_rel, line_number, f"相对 import 未找到目标文件：{specifier}")
                    )
    return findings


def check_required_paths(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for rel in REQUIRED_RELATIVE_PATHS:
        if not (project_root / rel).exists():
            findings.append(Finding("FAIL", "MISSING_REQUIRED_PATH", rel, 1, "关键目录或文件无法通过项目根目录相对路径定位"))
    return findings


def check_env_excluded(project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    gitignore = project_root / ".gitignore"
    if not gitignore.exists() or ".env.local" not in read_text(gitignore):
        findings.append(Finding("FAIL", "ENV_GITIGNORE", ".gitignore", 1, ".env.local 未在 .gitignore 中排除"))

    archive_path = project_root / "tools" / "archive_code.py"
    if not archive_path.exists():
        findings.append(Finding("FAIL", "ARCHIVE_SCRIPT_MISSING", "tools/archive_code.py", 1, "未找到代码存档脚本"))
        return findings

    spec = importlib.util.spec_from_file_location("archive_code_for_platform_check", archive_path)
    if spec is None or spec.loader is None:
        findings.append(Finding("FAIL", "ARCHIVE_IMPORT", "tools/archive_code.py", 1, "无法加载代码存档脚本"))
        return findings
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not getattr(module, "should_exclude")(".env.local"):
        findings.append(Finding("FAIL", "ENV_ARCHIVE", "tools/archive_code.py", 1, ".env.local 未被代码存档脚本排除"))
    return findings


def run_checks(project_root: Path) -> list[Finding]:
    return [
        *scan_windows_paths_and_calls(project_root),
        *scan_frontend_import_case(project_root),
        *check_required_paths(project_root),
        *check_env_excluded(project_root),
    ]


def print_report(findings: list[Finding]) -> None:
    fail_count = sum(1 for item in findings if item.level == "FAIL")
    warn_count = sum(1 for item in findings if item.level == "WARN")
    print("统信UOS兼容性轻量检查")
    print(f"FAIL={fail_count} WARN={warn_count}")
    if not findings:
        print("未发现阻断项。")
        return
    for item in findings:
        location = f"{item.path}:{item.line}" if item.line else item.path
        print(f"[{item.level}] {item.code} {location} - {item.message}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查造价智算后续迁移到 Linux/统信 UOS 的基础兼容性风险。")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="项目根目录，默认按脚本位置自动识别。")
    parser.add_argument("--strict-warnings", action="store_true", help="将已知 Windows 主线警告也视为失败。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    project_root = Path(args.project_root).resolve()
    findings = run_checks(project_root)
    print_report(findings)
    has_fail = any(item.level == "FAIL" for item in findings)
    has_warn = any(item.level == "WARN" for item in findings)
    return 1 if has_fail or (args.strict_warnings and has_warn) else 0


if __name__ == "__main__":
    raise SystemExit(main())
