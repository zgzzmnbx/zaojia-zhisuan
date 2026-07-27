from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKENS_JSON = (
    ROOT
    / "frontend"
    / "src"
    / "design-system"
    / "dabawei-shadcn-ui.tokens.json"
)
TOKENS_CSS = (
    ROOT / "frontend" / "src" / "design-system" / "dabawei-shadcn-ui.css"
)
RUNTIME_CSS = ROOT / "frontend" / "src" / "styles.css"
DASHBOARD_CSS = (
    ROOT
    / "frontend"
    / "src"
    / "components"
    / "project-dashboard"
    / "projectDashboard.css"
)
COMPONENT_SAMPLE = (
    ROOT
    / "01-assets"
    / "01-UI参考图"
    / "code"
    / "大尾巴-Shadcn-UI-组件样张-v1.0.0.html"
)
UI_SPEC = ROOT / "00-PRD" / "03-UI设计规范.md"
UI_PRD = ROOT / "00-PRD" / "03-整体UI设计PRD.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"[FAIL] {message}")


def main() -> None:
    tokens = json.loads(TOKENS_JSON.read_text(encoding="utf-8"))
    tokens_css = TOKENS_CSS.read_text(encoding="utf-8")
    runtime_css = RUNTIME_CSS.read_text(encoding="utf-8")
    dashboard_css = DASHBOARD_CSS.read_text(encoding="utf-8")
    component_sample = COMPONENT_SAMPLE.read_text(encoding="utf-8")
    ui_spec = UI_SPEC.read_text(encoding="utf-8")
    ui_prd = UI_PRD.read_text(encoding="utf-8")

    require(tokens["name"] == "大尾巴 Shadcn UI", "设计系统名称不一致")
    require(tokens["version"] == "1.0.0", "设计系统版本不是 1.0.0")
    require(
        tokens["sourcePreset"]["code"] == "b1au7YYAi",
        "shadcn preset 不是 b1au7YYAi",
    )
    require(
        tokens["sourcePreset"]["runtimeFont"] == "Zaojia PingFang SC",
        "运行时字体未锁定为自托管苹方",
    )

    required_css_tokens = {
        "--dws-color-primary",
        "--dws-color-border",
        "--dws-color-success",
        "--dws-color-warning",
        "--dws-color-danger",
        "--dws-button-height",
        "--dws-panel-radius",
        "--dws-segmented-height",
        "--dws-table-row-height",
        "--dws-dialog-width",
        "--dws-chart-blue-strong",
    }
    missing_css_tokens = sorted(
        token for token in required_css_tokens if token not in tokens_css
    )
    require(
        not missing_css_tokens,
        f"CSS 令牌缺失：{', '.join(missing_css_tokens)}",
    )
    require(
        '@import "./design-system/dabawei-shadcn-ui.css";' in runtime_css,
        "frontend/src/styles.css 未引入设计系统令牌",
    )
    require(
        "--db-primary: var(--dws-color-primary);" in runtime_css,
        "运行时主色尚未映射到大尾巴 Shadcn UI",
    )
    require(
        ".shell.layout-daweiba" in tokens_css,
        "大尾巴主题尚未接入设计系统基础与焦点状态",
    )
    require(
        "--pd-primary: var(--dws-color-primary);" in dashboard_css,
        "Dashboard 主色尚未映射到大尾巴 Shadcn UI",
    )
    require(
        "../../../frontend/src/design-system/dabawei-shadcn-ui.css"
        in component_sample,
        "组件样张未引用正式设计令牌",
    )
    require(
        "pingfang-sc-regular.woff2" in component_sample,
        "组件样张未接入项目自托管苹方",
    )
    for document_name, document in (
        ("UI 设计规范", ui_spec),
        ("整体 UI 设计 PRD", ui_prd),
    ):
        require(
            "大尾巴 Shadcn UI" in document,
            f"{document_name} 未声明新版设计系统",
        )
        require(
            "b1au7YYAi" in document,
            f"{document_name} 未登记当前 preset",
        )

    print(
        "[PASS] 大尾巴 Shadcn UI v1.0.0："
        f"{len(required_css_tokens)} 项核心 CSS 令牌、"
        "大尾巴主题 / Dashboard 映射、组件样张和双文档登记均通过。"
    )


if __name__ == "__main__":
    main()
