from __future__ import annotations

import json
import os
from threading import Lock
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter

from .fill_engine import (
    EMPTY_ELEMENT_COLUMN,
    PHYSICAL_ADJUSTMENT_FIELD,
    PRICE_COLUMN_FIELDS,
    TECHNICAL_ADJUSTMENT_FIELD,
    FillEngine,
)
from . import feishu_webhook
from . import feishu_app_bot
from .knowledge_base import KnowledgeBase
from .knowledge_qa import (
    NO_EVIDENCE_ANSWER,
    build_knowledge_answer_prompt,
    is_knowledge_question,
    search_knowledge,
    strip_force_knowledge_prefix,
)
from .experience_warning import (
    DEFAULT_SELECTED_EXPERIENCE_FIELDS,
    DEFAULT_HIGH_RISK_WARNING_PERCENT,
    DEFAULT_LOW_RISK_WARNING_PERCENT,
    DEFAULT_WARNING_FILTER_FIELD,
    EXPERIENCE_MAPPING_FIELDS,
    PHYSICAL_METRIC,
    PRICE_METRIC,
    TECHNICAL_METRIC,
    WARNING_FILTER_FIELDS,
    WARNING_OUTPUT_FIELDS,
    _has_warning_filter_value,
    _warning_filter_column_index,
    analyze_workbook_warnings_with_progress,
    import_experience_pool,
    write_warnings_to_workbook,
)
from .experience_governance import build_experience_pool_governance_report, write_governance_markdown
from .fill_assist import build_fill_assist_candidates, build_fill_assist_context
from .risk_items import build_standard_trace, build_structured_risk_items, summarize_risk_items
from .workload_capture import (
    DEFAULT_SELECTED_WORKLOAD_FIELDS,
    DEFAULT_WORKLOAD_FILTER_FIELD,
    SOURCE_MAPPING_FIELDS,
    SOURCE_QUANTITY_FIELD,
    TARGET_MAPPING_FIELDS,
    WRITE_MODE_CONSERVATIVE,
    WRITE_MODE_OVERWRITE,
    WORKLOAD_FIELD_PREFERENCE_FIELDS,
    WORKLOAD_TARGET_FIELD_PREFERENCE_FIELDS,
    capture_workload,
    default_workload_field_preferences,
    default_workload_target_field_preferences,
    suggest_workload_column_mapping,
)
from .llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
    LlmConfig,
    build_risk_prompt,
    call_chat_completion,
)
from .schemas import FIELD_COLUMNS, FillSummary, ReviewRow
from .excel_recalc import recalculate_workbook
from .formula_resolver import WorkbookFormulaResolver
from .paths import (
    DEFAULT_EXPERIENCE_FIELD_PREFERENCES_PATH,
    DEFAULT_EXPERIENCE_POOL_PATH,
    DEFAULT_EXPERIENCE_POOL_TEMPLATE_PATH,
    DEFAULT_EXPERIENCE_WARNING_SETTINGS_PATH,
    DEFAULT_INPUT_FIELD_PREFERENCES_PATH,
    DEFAULT_KB_PATH,
    DEFAULT_PREVIEW_COLUMN_PREFERENCES_PATH,
    DEFAULT_UI_PREFERENCES_PATH,
    DEFAULT_WORKLOAD_FIELD_PREFERENCES_PATH,
    DEFAULT_WORKLOAD_TARGET_FIELD_PREFERENCES_PATH,
    LEGACY_EXPERIENCE_POOL_PATH,
    PROJECT_DEFAULT_SETTINGS_PATH,
    PROJECT_ROOT,
    RUNTIME_DIR,
)
from .report import append_risk_report, write_report


APP_VERSION = "v5.8.21"
OUTPUT_FILE_PREFIX = "【输出】"
TEMP_FILE_PREFIX = "【临时】"
PROCESS_STATE_FILENAME = "process-state.json"
MANUAL_EDIT_LOG_FILENAME = "preview-manual-edits.json"
MANUAL_EDIT_FILL = PatternFill(fill_type="solid", fgColor="DDEBFF")
MANUAL_EDIT_COMMENT_AUTHOR = "造价智算"
MANUAL_EDIT_NUMERIC_HEADER_TOKENS = (
    "金额",
    "费用",
    "数量",
    "工程量",
    "基价",
    "单价",
    "合价",
    "系数",
    "税",
    "小计",
    "合计",
)
MANUAL_EDIT_READONLY_HEADERS = {
    "匹配状态",
    "候选数量",
    "匹配说明",
    "预警参数",
    "预警细节",
    "输出-匹配状态",
    "输出-候选数量",
    "输出-匹配说明",
}
DEFAULT_PREVIEW_CELL_MAX_DISPLAY_CHARS = 8
MIN_PREVIEW_COLUMN_WIDTH_PX = 72
MAX_PREVIEW_COLUMN_WIDTH_PX = 420
DEFAULT_CORE_PREVIEW_LABELS = [
    "要素1",
    "要素2",
    "要素3",
    "要素4",
    "要素5",
    "单位",
    "单价",
    "实物工作费调整系数",
    "技术工作费调整系数",
    "预警参数",
    "预警细节",
]
RISK_REPORT_KNOWLEDGE_QUERIES = [
    "第二层经验提示是什么意思？",
    "待复核是什么原因？",
    "经验池预警偏离率和阈值怎么判断？",
    "基价 单价 字段完全匹配 非空要素顺序匹配",
    "实物工作费调整系数第一层标准规则第二层经验提示",
    "技术工作费调整系数0.22依据",
    "附加调整系数为什么不能连乘？",
]
DEMO_SAMPLE_TOKENS = ("输入100", "空单价100")
WARNING_PROGRESS_DEFAULT = {
    "status": "idle",
    "processed_rows": 0,
    "total_rows": 0,
    "matched_rows": 0,
    "warning_rows": 0,
}
WARNING_PROGRESS: dict[str, dict[str, object]] = {}
WARNING_PROGRESS_LOCK = Lock()
INPUT_FIELD_PREFERENCE_FIELDS = [
    *FIELD_COLUMNS,
    "输出-价格列",
    PHYSICAL_ADJUSTMENT_FIELD,
    TECHNICAL_ADJUSTMENT_FIELD,
]

app = FastAPI(title="造价智算 API", version=APP_VERSION)
FRONTEND_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "guankanzhisuan", "version": APP_VERSION}


@app.post("/api/inspect")
async def inspect_excel(
    file: UploadFile = File(...),
    header_row: int | None = Form(default=None),
    sheet_name: str | None = Form(default=None),
    field_preferences: str | None = Form(default=None),
) -> dict[str, object]:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 文件")

    job_id = uuid4().hex
    job_dir = RUNTIME_DIR / "inspect" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / file.filename
    input_path.write_bytes(await file.read())

    detected_row, headers = _read_headers(input_path, header_row=header_row, sheet_name=sheet_name)
    columns = _build_column_options(headers)
    input_preferences = _parse_input_field_preferences_form(field_preferences)
    sheets = _inspect_candidate_sheets(input_path, preferences=input_preferences)
    return {
        "header_row": detected_row,
        "headers": headers,
        "columns": columns,
        "suggested_mapping": _suggest_column_mapping(headers, input_preferences),
        "sheets": sheets,
    }


@app.get("/api/project-default-settings")
async def get_project_default_settings() -> dict[str, object]:
    return _project_default_settings_payload()


@app.get("/api/input/field-preferences")
async def get_input_field_preferences() -> dict[str, object]:
    return _input_field_preferences_payload()


@app.post("/api/input/field-preferences")
async def save_input_field_preferences(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    raw_preferences = payload.get("preferences")
    if raw_preferences is None:
        raw_preferences = payload
    if not isinstance(raw_preferences, dict):
        raise HTTPException(status_code=400, detail="输入字段偏好必须是对象")
    preferences = _sanitize_input_field_preferences(raw_preferences)
    return _input_field_preferences_payload(preferences)


@app.get("/api/ui-preferences")
async def get_ui_preferences() -> dict[str, object]:
    return _ui_preferences_payload()


@app.post("/api/ui-preferences")
async def save_ui_preferences(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    raw_preferences = payload.get("preferences")
    if raw_preferences is None:
        raw_preferences = payload
    if not isinstance(raw_preferences, dict):
        raise HTTPException(status_code=400, detail="页面用户设置必须是对象")
    preferences = _sanitize_ui_preferences(raw_preferences)
    _save_ui_preferences(preferences)
    return _ui_preferences_payload(preferences)


@app.get("/api/preview-column-preferences")
async def get_preview_column_preferences() -> dict[str, object]:
    return _preview_column_preferences_payload()


@app.post("/api/preview-column-preferences")
async def save_preview_column_preferences(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    raw_preferences = payload.get("preferences")
    if raw_preferences is None:
        raw_preferences = payload
    if not isinstance(raw_preferences, dict):
        raise HTTPException(status_code=400, detail="预览列设置必须是对象")
    preferences = _sanitize_preview_column_preferences(raw_preferences)
    return _preview_column_preferences_payload(preferences)


@app.get("/api/collaboration/feishu-webhook/status")
def get_feishu_webhook_status() -> dict[str, object]:
    return feishu_webhook.get_status()


@app.post("/api/collaboration/feishu-webhook/settings")
def update_feishu_webhook_settings(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    try:
        return feishu_webhook.save_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/collaboration/feishu-webhook/test")
def test_feishu_webhook() -> dict[str, object]:
    outcome = feishu_webhook.send_notification("test")
    if outcome.skipped:
        raise HTTPException(status_code=409, detail=outcome.error)
    if not outcome.success:
        raise HTTPException(status_code=502, detail=outcome.error or "飞书 Webhook 测试发送失败")
    return outcome.to_dict()


@app.get("/api/collaboration/feishu-webhook/history")
def get_feishu_webhook_history(limit: int = 50) -> dict[str, object]:
    return {"items": feishu_webhook.read_history(limit=limit)}


@app.get("/api/collaboration/feishu-app-bot/status")
def get_feishu_app_bot_status() -> dict[str, object]:
    return feishu_app_bot.bot_status()


@app.get("/api/collaboration/feishu-app-bot/tasks")
def get_feishu_app_bot_tasks(limit: int = 30) -> dict[str, object]:
    store = feishu_app_bot.TaskStore()
    return {"items": [feishu_app_bot.public_task(task) for task in store.list_tasks(limit=limit)]}


@app.get("/api/collaboration/feishu-app-bot/logs")
def get_feishu_app_bot_logs(limit: int = 200) -> dict[str, object]:
    return {"items": feishu_app_bot.read_console_events(limit=limit)}


@app.post("/api/collaboration/feishu-app-bot/settings")
def update_feishu_app_bot_settings(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    if "enabled" not in payload or not isinstance(payload.get("enabled"), bool):
        raise HTTPException(status_code=400, detail="enabled 必须是布尔值")
    enabled = bool(payload["enabled"])
    profile_id = payload.get("profile_id")
    if profile_id is not None:
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise HTTPException(status_code=400, detail="profile_id 必须是非空字符串")
        next_profile = profile_id.strip()
        if next_profile not in {item["profile_id"] for item in feishu_app_bot.credential_profiles()}:
            raise HTTPException(status_code=400, detail="未找到指定的飞书机器人配置")
        if next_profile != feishu_app_bot.active_profile_id():
            if feishu_app_bot.bot_process_running():
                feishu_app_bot.save_bot_enabled(False)
                if not feishu_app_bot.wait_for_bot_process_exit():
                    raise HTTPException(status_code=409, detail="当前机器人仍在退出，暂时不能切换配置")
            try:
                feishu_app_bot.save_active_profile(next_profile)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    feishu_app_bot.save_bot_enabled(enabled)
    if enabled:
        configuration_issue = feishu_app_bot.credential_configuration_issue()
        if configuration_issue:
            feishu_app_bot.save_bot_enabled(False)
            raise HTTPException(status_code=409, detail=configuration_issue)
        feishu_app_bot.start_bot_process()
    return feishu_app_bot.bot_status()


@app.post("/api/collaboration/feishu-webhook/notify")
def send_feishu_webhook_notification(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    notification_type = str(payload.get("notification_type") or "").strip()
    if notification_type not in feishu_webhook.ALLOWED_NOTIFICATION_TYPES - {"test"}:
        raise HTTPException(status_code=400, detail="不支持的通知类型")
    context = payload.get("context") or {}
    if not isinstance(context, dict):
        raise HTTPException(status_code=400, detail="通知上下文必须是对象")
    return feishu_webhook.send_notification(notification_type, context).to_dict()


@app.post("/api/process")
async def process_excel(
    file: UploadFile = File(...),
    column_mapping: str | None = Form(default=None),
    sheet_configs: str | None = Form(default=None),
    header_row: int = Form(default=1),
    output_match_report: bool = Form(default=True),
    merge_vertical_cells: bool = Form(default=True),
    merge_horizontal_cells: bool = Form(default=True),
    only_match_rows_with_value: bool = Form(default=True),
    match_value_filter_field: str = Form(default=DEFAULT_WARNING_FILTER_FIELD),
    defer_matching: bool = Form(default=False),
) -> dict[str, object]:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 文件")
    if not DEFAULT_KB_PATH.exists():
        raise HTTPException(status_code=500, detail=f"知识库不存在：{DEFAULT_KB_PATH}")

    job_id = uuid4().hex
    job_dir = RUNTIME_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / file.filename
    input_path.write_bytes(await file.read())

    output_timestamp = _output_timestamp()
    output_excel = job_dir / f"{OUTPUT_FILE_PREFIX}-控制价计算表-{output_timestamp}.xlsx"
    output_report = job_dir / f"{OUTPUT_FILE_PREFIX}-控制价报告-{output_timestamp}.docx"

    knowledge_base = KnowledgeBase.from_excel(DEFAULT_KB_PATH)
    mapping = _parse_column_mapping(column_mapping)
    parsed_sheet_configs = _parse_sheet_configs(sheet_configs)
    parsed_match_value_filter_field = _parse_warning_filter_field(match_value_filter_field)
    if defer_matching:
        output_excel.write_bytes(input_path.read_bytes())
        try:
            summary = _build_pending_match_summary(
                output_excel,
                column_mapping=mapping,
                header_row=header_row,
                sheet_configs=parsed_sheet_configs,
                only_match_rows_with_value=only_match_rows_with_value,
                match_value_filter_field=parsed_match_value_filter_field,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        summary.output_excel = output_excel.name
        summary.output_report = ""
        summary.warning_summary = _warning_not_run_summary()
        summary.warning_details = []
        _save_process_state(
            job_dir,
            file.filename,
            input_path,
            output_excel,
            None,
            summary,
            extra={
                "deferred_matching": True,
                "process_options": {
                    "column_mapping": mapping,
                    "sheet_configs": parsed_sheet_configs,
                    "header_row": header_row,
                    "output_match_report": output_match_report,
                    "merge_vertical_cells": merge_vertical_cells,
                    "merge_horizontal_cells": merge_horizontal_cells,
                    "only_match_rows_with_value": only_match_rows_with_value,
                    "match_value_filter_field": parsed_match_value_filter_field,
                },
            },
        )
        return {
            "job_id": job_id,
            "summary": summary.to_dict(),
            "downloads": {
                "excel": "",
                "report": "",
            },
        }
    try:
        summary = FillEngine(knowledge_base).fill_workbook(
            input_path,
            output_excel,
            column_mapping=mapping,
            header_row=header_row,
            output_match_report=output_match_report,
            merge_vertical_cells=merge_vertical_cells,
            merge_horizontal_cells=merge_horizontal_cells,
            only_match_rows_with_value=only_match_rows_with_value,
            match_value_filter_field=parsed_match_value_filter_field,
            sheet_configs=parsed_sheet_configs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    recalculate_workbook(output_excel)
    summary.warning_summary = _warning_not_run_summary()
    summary.warning_details = []
    summary.table_preview = _refresh_table_preview_from_output(summary.table_preview, output_excel)
    output_report = write_report(
        output_report,
        file.filename,
        summary,
        output_excel_path=output_excel,
        input_excel_path=input_path,
    )
    summary.output_report = output_report.name
    _save_process_state(job_dir, file.filename, input_path, output_excel, output_report, summary)

    return {
        "job_id": job_id,
        "summary": summary.to_dict(),
        "downloads": {
            "excel": f"/api/download/{job_id}/excel",
            "report": f"/api/download/{job_id}/report",
        },
    }


@app.post("/api/process/batch-match")
async def batch_match_process(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="缺少任务编号")
    job_dir = RUNTIME_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    if not DEFAULT_KB_PATH.exists():
        raise HTTPException(status_code=500, detail=f"知识库不存在：{DEFAULT_KB_PATH}")

    state = _load_process_state(job_dir)
    input_path = _state_path(job_dir, state, "input_excel", required=False)
    output_excel = _state_path(job_dir, state, "output_excel")
    if not output_excel or not output_excel.exists():
        raise HTTPException(status_code=404, detail="输出任务不存在，请重新上传")

    options = dict(state.get("process_options") or {})
    output_report = job_dir / f"{OUTPUT_FILE_PREFIX}-控制价报告-{_output_timestamp()}.docx"
    try:
        summary = FillEngine(KnowledgeBase.from_excel(DEFAULT_KB_PATH)).fill_workbook(
            output_excel,
            output_excel,
            column_mapping=options.get("column_mapping"),
            header_row=int(options.get("header_row") or 1),
            output_match_report=bool(options.get("output_match_report", True)),
            merge_vertical_cells=bool(options.get("merge_vertical_cells", True)),
            merge_horizontal_cells=bool(options.get("merge_horizontal_cells", True)),
            only_match_rows_with_value=bool(options.get("only_match_rows_with_value", False)),
            match_value_filter_field=str(options.get("match_value_filter_field") or DEFAULT_WARNING_FILTER_FIELD),
            sheet_configs=options.get("sheet_configs"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    recalculate_workbook(output_excel)
    summary.warning_summary = _warning_not_run_summary()
    summary.warning_details = []
    summary.matching_status = "completed"
    summary.table_preview = _refresh_table_preview_from_output(
        summary.table_preview,
        output_excel,
        header_rows=_parse_preview_header_rows(payload.get("header_rows")),
    )
    output_report = write_report(
        output_report,
        str(state.get("input_filename") or (input_path.name if input_path else output_excel.name)),
        summary,
        output_excel_path=output_excel,
        input_excel_path=input_path,
    )
    summary.output_excel = output_excel.name
    summary.output_report = output_report.name
    _save_process_state(
        job_dir,
        str(state.get("input_filename") or (input_path.name if input_path else output_excel.name)),
        input_path,
        output_excel,
        output_report,
        summary,
        extra={
            "deferred_matching": False,
            "process_options": options,
        },
    )
    return {
        "job_id": job_id,
        "summary": summary.to_dict(),
        "downloads": {
            "excel": f"/api/download/{job_id}/excel",
            "report": f"/api/download/{job_id}/report",
        },
    }


@app.post("/api/demo/load-sample")
async def load_demo_sample() -> dict[str, object]:
    sample_path = _find_demo_sample_path()
    if not sample_path:
        raise HTTPException(status_code=404, detail="未找到演示样例文件")
    return _process_existing_workbook(sample_path, demo_mode=True, sheet_configs=_demo_sample_sheet_configs(sample_path))


@app.get("/api/quality/experience-pool")
async def experience_pool_quality() -> dict[str, object]:
    report = build_experience_pool_governance_report(_resolve_experience_pool_path())
    report_path = RUNTIME_DIR / "experience-pool-governance-report.md"
    write_governance_markdown(report, report_path)
    return {**report, "report_path": str(report_path)}


@app.get("/api/risk/summary")
async def risk_summary(job_id: str) -> dict[str, object]:
    job_dir = RUNTIME_DIR / str(job_id).strip()
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    state = _load_process_state(job_dir)
    summary = _summary_from_dict(state.get("summary", {}))
    items = build_structured_risk_items(summary)
    return {
        "job_id": job_id,
        "summary": summarize_risk_items(items),
        "items": items,
    }


@app.get("/api/standard-trace")
async def standard_trace(job_id: str, sheet_name: str, row_number: int) -> dict[str, object]:
    job_dir = RUNTIME_DIR / str(job_id).strip()
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    state = _load_process_state(job_dir)
    summary = _summary_from_dict(state.get("summary", {}))
    return {
        "job_id": job_id,
        "sheet_name": sheet_name,
        "row_number": row_number,
        "trace": build_standard_trace(summary, sheet_name, row_number),
    }


@app.post("/api/fill-assist/candidates")
async def fill_assist_candidates(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    job_id = str(payload.get("job_id") or "").strip()
    sheet_name = str(payload.get("sheet_name") or "").strip()
    target_header = str(payload.get("target_header") or payload.get("field") or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="缺少任务编号")
    if not sheet_name:
        raise HTTPException(status_code=400, detail="缺少 sheet 名称")
    try:
        row_number = int(payload.get("row_number") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="行号必须是数字") from exc
    if row_number < 1:
        raise HTTPException(status_code=400, detail="行号必须大于等于 1")

    job_dir = RUNTIME_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    state = _load_process_state(job_dir)
    excel_path = _state_path(job_dir, state, "output_excel")
    if not excel_path or not excel_path.exists():
        raise HTTPException(status_code=404, detail="输出 Excel 不存在，请先完成转换")
    if not DEFAULT_KB_PATH.exists():
        raise HTTPException(status_code=500, detail=f"知识库不存在：{DEFAULT_KB_PATH}")
    try:
        context = build_fill_assist_context(excel_path, sheet_name, row_number, target_header)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    summary = _summary_from_dict(state.get("summary", {}))
    candidates = build_fill_assist_candidates(
        dict(context.get("row") or {}),
        knowledge_base=KnowledgeBase.from_excel(DEFAULT_KB_PATH),
        pool_path=_resolve_experience_pool_path(),
    )
    return {
        "job_id": job_id,
        "context": context,
        "candidates": candidates,
        "trace": build_standard_trace(summary, sheet_name, row_number),
    }


@app.post("/api/fill-assist/confirm")
async def confirm_fill_assist(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    candidate = payload.get("candidate")
    note = str(payload.get("note") or "").strip()
    if not isinstance(candidate, dict):
        raise HTTPException(status_code=400, detail="缺少候选信息")
    if candidate.get("source") == "custom" and not note:
        raise HTTPException(status_code=400, detail="自定义值必须填写依据备注")
    payload = dict(payload)
    payload["value"] = candidate.get("value")
    payload["edit_source"] = "fill-assist"
    payload["edit_note"] = note
    payload["candidate_meta"] = candidate
    return await update_preview_cell(payload)


@app.post("/api/experience-warnings/run")
async def run_experience_warnings(
    job_id: str = Form(...),
    preview_header_rows: str | None = Form(default=None),
) -> dict[str, object]:
    job_dir = RUNTIME_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    state = _load_process_state(job_dir)
    excel_path = _state_path(job_dir, state, "output_excel")
    input_path = _state_path(job_dir, state, "input_excel", required=False)
    if not excel_path or not excel_path.exists():
        excel_matches = list(job_dir.glob("*-填价结果-【codex】.xlsx"))
        if not excel_matches:
            raise HTTPException(status_code=404, detail="输出 Excel 不存在，请先完成转换")
        excel_path = excel_matches[0]

    summary = _summary_from_dict(state.get("summary", {}))
    warning_settings = _load_experience_warning_settings()
    _set_warning_progress(job_id, {"status": "running"})
    try:
        warning_result = analyze_workbook_warnings_with_progress(
            excel_path,
            _resolve_experience_pool_path(),
            progress_callback=lambda payload: _set_warning_progress(job_id, payload),
            low_risk_warning_ratio=float(warning_settings["low_risk_warning_ratio"]) / 100,
            high_risk_warning_ratio=float(warning_settings["high_risk_warning_ratio"]) / 100,
            only_check_rows_with_value=bool(warning_settings["only_check_rows_with_value"]),
            value_filter_field=str(warning_settings["value_filter_field"]),
        )
    except ValueError as exc:
        _set_warning_progress(job_id, {"status": "failed", "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _set_warning_progress(job_id, {"status": "failed", "error": str(exc)})
        raise
    summary.warning_summary = warning_result["summary"]
    summary.warning_summary["executed"] = True
    summary.warning_details = warning_result["warnings"]
    write_warnings_to_workbook(excel_path, list(warning_result.get("row_results") or summary.warning_details))
    summary.table_preview = _refresh_table_preview_from_output(
        summary.table_preview,
        excel_path,
        header_rows=_parse_preview_header_rows(preview_header_rows),
    )

    input_name = str(state.get("input_filename") or (input_path.name if input_path else "input.xlsx"))
    report_path = _state_path(job_dir, state, "output_report", required=False)
    if not report_path:
        report_matches = _find_report_files(job_dir, ".docx")
        report_path = report_matches[0] if report_matches else job_dir / f"{OUTPUT_FILE_PREFIX}-控制价报告-{_output_timestamp()}.docx"
    report_path = write_report(
        report_path,
        input_name,
        summary,
        output_excel_path=excel_path,
        input_excel_path=input_path,
    )
    summary.output_excel = excel_path.name
    summary.output_report = report_path.name
    _save_process_state(job_dir, input_name, input_path, excel_path, report_path, summary)
    _set_warning_progress(
        job_id,
        {
            "status": "completed",
            "processed_rows": int(summary.warning_summary.get("candidate_rows") or 0),
            "total_rows": int(summary.warning_summary.get("total_candidate_rows") or summary.warning_summary.get("candidate_rows") or 0),
            "matched_rows": int(summary.warning_summary.get("checked_rows") or 0),
            "warning_rows": int(summary.warning_summary.get("warning_rows") or 0),
        },
    )

    return {
        "job_id": job_id,
        "summary": summary.to_dict(),
        "downloads": {
            "excel": f"/api/download/{job_id}/excel",
            "report": f"/api/download/{job_id}/report",
        },
    }


@app.post("/api/preview/refresh")
async def refresh_table_preview(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="缺少任务编号")
    job_dir = RUNTIME_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    state = _load_process_state(job_dir)
    excel_path = _state_path(job_dir, state, "output_excel")
    if not excel_path or not excel_path.exists():
        raise HTTPException(status_code=404, detail="输出 Excel 不存在，请先完成转换")

    summary = _summary_from_dict(state.get("summary", {}))
    summary.table_preview = _refresh_table_preview_from_output(
        summary.table_preview,
        excel_path,
        header_rows=_parse_preview_header_rows(payload.get("header_rows")),
    )
    input_path = _state_path(job_dir, state, "input_excel", required=False)
    report_path = _state_path(job_dir, state, "output_report", required=False) or job_dir / str(state.get("output_report") or "")
    input_name = str(state.get("input_filename") or (input_path.name if input_path else "input.xlsx"))
    summary.output_excel = excel_path.name
    summary.output_report = report_path.name if report_path else str(state.get("output_report") or "")
    _save_process_state(job_dir, input_name, input_path, excel_path, report_path, summary)
    return {
        "job_id": job_id,
        "summary": summary.to_dict(),
        "downloads": {
            "excel": f"/api/download/{job_id}/excel",
            "report": f"/api/download/{job_id}/report",
        },
    }


@app.post("/api/preview/cell")
async def update_preview_cell(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    job_id = str(payload.get("job_id") or "").strip()
    sheet_name = str(payload.get("sheet_name") or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="缺少任务编号")
    if not sheet_name:
        raise HTTPException(status_code=400, detail="缺少 sheet 名称")
    try:
        row_number = int(payload.get("row_number") or 0)
        column_number = int(payload.get("column_number") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="行号和列号必须是数字") from exc
    if row_number < 1 or column_number < 1:
        raise HTTPException(status_code=400, detail="行号和列号必须大于等于 1")

    job_dir = RUNTIME_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    state = _load_process_state(job_dir)
    excel_path = _state_path(job_dir, state, "output_excel")
    if not excel_path or not excel_path.exists():
        raise HTTPException(status_code=404, detail="输出 Excel 不存在，请先完成转换")

    summary = _summary_from_dict(state.get("summary", {}))
    header_rows = _parse_preview_header_rows(payload.get("header_rows"))
    should_recalculate = bool(payload.get("recalculate"))
    edit_record = _write_preview_cell_edit(
        excel_path,
        job_id=job_id,
        sheet_name=sheet_name,
        row_number=row_number,
        column_number=column_number,
        new_value=payload.get("value"),
        header_rows=header_rows,
        edit_source=str(payload.get("edit_source") or "manual"),
        edit_note=str(payload.get("edit_note") or "").strip(),
        candidate_meta=payload.get("candidate_meta") if isinstance(payload.get("candidate_meta"), dict) else None,
    )
    _append_manual_edit_log(job_dir, edit_record)
    input_path = _state_path(job_dir, state, "input_excel", required=False)
    input_name = str(state.get("input_filename") or (input_path.name if input_path else "input.xlsx"))
    report_path = _state_path(job_dir, state, "output_report", required=False)
    recalculated = False
    if should_recalculate:
        recalculated = recalculate_workbook(excel_path)
        summary.table_preview = _refresh_table_preview_from_output(
            summary.table_preview,
            excel_path,
            header_rows=header_rows,
        )
        if not report_path:
            report_matches = _find_report_files(job_dir, ".docx")
            report_path = report_matches[0] if report_matches else job_dir / f"{OUTPUT_FILE_PREFIX}-控制价报告-{_output_timestamp()}.docx"
        report_path = write_report(
            report_path,
            input_name,
            summary,
            output_excel_path=excel_path,
            input_excel_path=input_path,
        )
    else:
        summary.table_preview = _apply_manual_edit_to_table_preview(summary.table_preview, edit_record, header_rows)
    summary.output_excel = excel_path.name
    summary.output_report = report_path.name if report_path else str(state.get("output_report") or "")
    _save_process_state(job_dir, input_name, input_path, excel_path, report_path, summary)

    return {
        "job_id": job_id,
        "summary": summary.to_dict(),
        "downloads": {
            "excel": f"/api/download/{job_id}/excel",
            "report": f"/api/download/{job_id}/report",
        },
        "manual_edit": edit_record,
        "manual_edits": _load_manual_edit_log(job_dir),
        "formula_recalculated": recalculated,
        "needs_recalculate": not should_recalculate,
    }


@app.post("/api/preview/recalculate")
async def recalculate_preview_workbook(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="缺少任务编号")
    job_dir = RUNTIME_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    state = _load_process_state(job_dir)
    excel_path = _state_path(job_dir, state, "output_excel")
    if not excel_path or not excel_path.exists():
        raise HTTPException(status_code=404, detail="输出 Excel 不存在，请先完成转换")

    summary = _summary_from_dict(state.get("summary", {}))
    header_rows = _parse_preview_header_rows(payload.get("header_rows"))
    recalculated = recalculate_workbook(excel_path)
    summary.table_preview = _refresh_table_preview_from_output(
        summary.table_preview,
        excel_path,
        header_rows=header_rows,
    )
    input_path = _state_path(job_dir, state, "input_excel", required=False)
    input_name = str(state.get("input_filename") or (input_path.name if input_path else "input.xlsx"))
    report_path = _state_path(job_dir, state, "output_report", required=False)
    if not report_path:
        report_matches = _find_report_files(job_dir, ".docx")
        report_path = report_matches[0] if report_matches else job_dir / f"{OUTPUT_FILE_PREFIX}-控制价报告-{_output_timestamp()}.docx"
    report_path = write_report(
        report_path,
        input_name,
        summary,
        output_excel_path=excel_path,
        input_excel_path=input_path,
    )
    summary.output_excel = excel_path.name
    summary.output_report = report_path.name
    _save_process_state(job_dir, input_name, input_path, excel_path, report_path, summary)
    return {
        "job_id": job_id,
        "summary": summary.to_dict(),
        "downloads": {
            "excel": f"/api/download/{job_id}/excel",
            "report": f"/api/download/{job_id}/report",
        },
        "manual_edits": _load_manual_edit_log(job_dir),
        "formula_recalculated": recalculated,
        "needs_recalculate": False,
    }


@app.get("/api/experience-warnings/progress/{job_id}")
async def get_experience_warning_progress(job_id: str) -> dict[str, object]:
    return _get_warning_progress(job_id)


@app.post("/api/experience-pool/inspect")
async def inspect_experience_pool_excel(
    file: UploadFile = File(...),
    header_row: int | None = Form(default=None),
    sheet_name: str | None = Form(default=None),
) -> dict[str, object]:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 文件")

    job_id = uuid4().hex
    job_dir = RUNTIME_DIR / "experience-pool-inspect" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / file.filename
    input_path.write_bytes(await file.read())

    sheets = _inspect_experience_sheets(input_path, header_row=header_row, sheet_name=sheet_name)
    first = sheets[0] if sheets else {"header_row": 1, "headers": [], "columns": [], "suggested_mapping": {}}
    return {
        "header_row": first["header_row"],
        "headers": first["headers"],
        "columns": first["columns"],
        "suggested_mapping": first["suggested_mapping"],
        "sheets": sheets,
    }


@app.get("/api/experience-pool/field-preferences")
async def get_experience_field_preferences() -> dict[str, object]:
    return _experience_field_preferences_payload()


@app.post("/api/experience-pool/field-preferences")
async def save_experience_field_preferences(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    raw_preferences = payload.get("preferences")
    if raw_preferences is None:
        raw_preferences = payload
    if not isinstance(raw_preferences, dict):
        raise HTTPException(status_code=400, detail="经验池字段偏好必须是对象")
    preferences = _sanitize_experience_field_preferences(raw_preferences)
    _save_experience_field_preferences(preferences)
    return _experience_field_preferences_payload(preferences)


@app.get("/api/experience-warnings/settings")
async def get_experience_warning_settings() -> dict[str, object]:
    return _experience_warning_settings_payload()


@app.post("/api/experience-warnings/settings")
async def save_experience_warning_settings(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    raw_settings = payload.get("settings")
    if raw_settings is None:
        raw_settings = payload
    if not isinstance(raw_settings, dict):
        raise HTTPException(status_code=400, detail="预警设置必须是对象")
    settings = _sanitize_experience_warning_settings(raw_settings)
    _save_experience_warning_settings(settings)
    return _experience_warning_settings_payload(settings)


@app.post("/api/experience-pool/import")
async def import_experience_pool_endpoint(
    file: UploadFile = File(...),
    selected_fields: str | None = Form(default=None),
    sheet_configs: str | None = Form(default=None),
    only_import_rows_with_value: bool = Form(default=True),
    value_filter_field: str = Form(default="工程量"),
) -> dict[str, object]:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 文件")

    selected = _parse_selected_experience_fields(selected_fields)
    job_id = uuid4().hex
    job_dir = RUNTIME_DIR / "experience-pool" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    source_path = job_dir / file.filename
    source_path.write_bytes(await file.read())
    parsed_sheet_configs = _parse_experience_sheet_configs(sheet_configs)
    filter_field = _parse_experience_filter_field(value_filter_field) if only_import_rows_with_value else None
    try:
        summary = import_experience_pool(
            source_path,
            DEFAULT_EXPERIENCE_POOL_PATH,
            selected_fields=selected,
            sheet_configs=parsed_sheet_configs,
            template_path=DEFAULT_EXPERIENCE_POOL_TEMPLATE_PATH,
            filter_non_empty_field=filter_field,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "job_id": job_id,
        "summary": summary,
        "pool_file": str(DEFAULT_EXPERIENCE_POOL_PATH),
    }


@app.post("/api/workload-capture/inspect")
async def inspect_workload_capture_excel(
    file: UploadFile = File(...),
    role: str = Form(default="source"),
    header_row: int | None = Form(default=None),
    sheet_name: str | None = Form(default=None),
    field_preferences: str | None = Form(default=None),
    adjacent_fallback_enabled: str | None = Form(default=None),
    element_sequence_enabled: str | None = Form(default=None),
) -> dict[str, object]:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 文件")
    clean_role = role if role in {"source", "target"} else "source"

    job_id = uuid4().hex
    job_dir = RUNTIME_DIR / "workload-capture-inspect" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / file.filename
    input_path.write_bytes(await file.read())

    sheets = _inspect_workload_sheets(
        input_path,
        clean_role,
        header_row=header_row,
        sheet_name=sheet_name,
        preferences=_parse_workload_field_preferences_form(field_preferences, clean_role),
        adjacent_fallback_enabled=_sanitize_optional_bool_setting(adjacent_fallback_enabled),
        element_sequence_enabled=_sanitize_optional_bool_setting(element_sequence_enabled),
    )
    first = sheets[0] if sheets else {"header_row": 1, "headers": [], "columns": [], "suggested_mapping": {}}
    return {
        "header_row": first["header_row"],
        "headers": first["headers"],
        "columns": first["columns"],
        "suggested_mapping": first["suggested_mapping"],
        "sheets": sheets,
    }


@app.post("/api/workload-capture/inspect-current-target")
async def inspect_current_workload_target(
    job_id: str = Form(...),
    header_row: int | None = Form(default=None),
    sheet_name: str | None = Form(default=None),
    field_preferences: str | None = Form(default=None),
    adjacent_fallback_enabled: str | None = Form(default=None),
    element_sequence_enabled: str | None = Form(default=None),
) -> dict[str, object]:
    clean_job_id = str(job_id or "").strip()
    if not clean_job_id:
        raise HTTPException(status_code=400, detail="缺少当前任务编号")
    job_dir = RUNTIME_DIR / clean_job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="当前任务不存在，请先完成转换")
    state = _load_process_state(job_dir)
    excel_path = _state_path(job_dir, state, "output_excel")
    if not excel_path or not excel_path.exists():
        raise HTTPException(status_code=404, detail="当前预览控制价表不存在，请先完成转换")

    sheets = _inspect_workload_sheets(
        excel_path,
        "target",
        header_row=header_row,
        sheet_name=sheet_name,
        preferences=_parse_workload_field_preferences_form(field_preferences, "target"),
        adjacent_fallback_enabled=_sanitize_optional_bool_setting(adjacent_fallback_enabled),
        element_sequence_enabled=_sanitize_optional_bool_setting(element_sequence_enabled),
    )
    first = sheets[0] if sheets else {"header_row": 1, "headers": [], "columns": [], "suggested_mapping": {}}
    return {
        "header_row": first["header_row"],
        "headers": first["headers"],
        "columns": first["columns"],
        "suggested_mapping": first["suggested_mapping"],
        "sheets": sheets,
    }


@app.get("/api/workload-capture/field-preferences")
async def get_workload_field_preferences() -> dict[str, object]:
    return _workload_field_preferences_payload()


@app.post("/api/workload-capture/field-preferences")
async def save_workload_field_preferences(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    raw_preferences = payload.get("preferences")
    if raw_preferences is None:
        raw_preferences = payload
    if not isinstance(raw_preferences, dict):
        raise HTTPException(status_code=400, detail="工作量字段偏好必须是对象")
    preferences = _sanitize_workload_field_preferences(raw_preferences)
    adjacent_fallback_enabled = _sanitize_bool_setting(payload.get("adjacent_fallback_enabled"), True)
    element_sequence_enabled = _sanitize_bool_setting(payload.get("element_sequence_enabled"), True)
    return _workload_field_preferences_payload(
        preferences,
        adjacent_fallback_enabled=adjacent_fallback_enabled,
        element_sequence_enabled=element_sequence_enabled,
    )


@app.get("/api/workload-capture/target-field-preferences")
async def get_workload_target_field_preferences() -> dict[str, object]:
    return _workload_target_field_preferences_payload()


@app.post("/api/workload-capture/target-field-preferences")
async def save_workload_target_field_preferences(payload: dict[str, object] = Body(...)) -> dict[str, object]:
    raw_preferences = payload.get("preferences")
    if raw_preferences is None:
        raw_preferences = payload
    if not isinstance(raw_preferences, dict):
        raise HTTPException(status_code=400, detail="控制价计算表字段偏好必须是对象")
    preferences = _sanitize_workload_target_field_preferences(raw_preferences)
    adjacent_fallback_enabled = _sanitize_bool_setting(payload.get("adjacent_fallback_enabled"), True)
    element_sequence_enabled = _sanitize_bool_setting(payload.get("element_sequence_enabled"), False)
    return _workload_target_field_preferences_payload(
        preferences,
        adjacent_fallback_enabled=adjacent_fallback_enabled,
        element_sequence_enabled=element_sequence_enabled,
    )


@app.post("/api/workload-capture/run")
async def run_workload_capture(
    workload_file: UploadFile = File(...),
    target_file: UploadFile = File(...),
    selected_fields: str | None = Form(default=None),
    source_sheet_configs: str | None = Form(default=None),
    target_sheet_configs: str | None = Form(default=None),
    only_capture_rows_with_value: bool = Form(default=True),
    value_filter_field: str = Form(default=SOURCE_QUANTITY_FIELD),
) -> dict[str, object]:
    if not workload_file.filename or not workload_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 格式的工作量表格")
    if not target_file.filename or not target_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 格式的控制价计算表")

    selected = _parse_workload_selected_fields(selected_fields)
    source_configs = _parse_workload_sheet_configs(source_sheet_configs, "source")
    target_configs = _parse_workload_sheet_configs(target_sheet_configs, "target")
    filter_field = _parse_workload_filter_field(value_filter_field) if only_capture_rows_with_value else None
    if not source_configs or not target_configs:
        raise HTTPException(status_code=400, detail="请先完成工作量表和控制价计算表的 sheet/列映射")

    job_id = uuid4().hex
    job_dir = RUNTIME_DIR / "workload-capture" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    workload_path = job_dir / workload_file.filename
    target_path = job_dir / target_file.filename
    workload_path.write_bytes(await workload_file.read())
    target_path.write_bytes(await target_file.read())
    output_timestamp = _output_timestamp()
    output_workload = job_dir / f"{TEMP_FILE_PREFIX}-原表-(工作量信息抓取后标注符合用)-{output_timestamp}.xlsx"
    output_target = job_dir / f"{TEMP_FILE_PREFIX}-控制价计算表（填好数量后）-{output_timestamp}.xlsx"

    try:
        summary = capture_workload(
            workload_path,
            target_path,
            output_workload,
            output_target,
            source_configs,
            target_configs,
            selected_fields=selected,
            filter_non_empty_field=filter_field,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "job_id": job_id,
        "summary": summary,
        "downloads": {
            "workload": f"/api/workload-capture/download/{job_id}/workload",
            "target": f"/api/workload-capture/download/{job_id}/target",
        },
    }


@app.post("/api/workload-capture/apply-to-current")
async def apply_workload_capture_to_current(
    workload_file: UploadFile = File(...),
    job_id: str = Form(...),
    selected_fields: str | None = Form(default=None),
    source_sheet_configs: str | None = Form(default=None),
    target_sheet_configs: str | None = Form(default=None),
    only_capture_rows_with_value: bool = Form(default=True),
    value_filter_field: str = Form(default=SOURCE_QUANTITY_FIELD),
    write_mode: str = Form(default="conservative"),
) -> dict[str, object]:
    if not workload_file.filename or not workload_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 格式的工作量表格")
    clean_job_id = str(job_id or "").strip()
    if not clean_job_id:
        raise HTTPException(status_code=400, detail="缺少当前任务编号")
    job_dir = RUNTIME_DIR / clean_job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="当前任务不存在，请先完成转换")

    selected = _parse_workload_selected_fields(selected_fields)
    source_configs = _parse_workload_sheet_configs(source_sheet_configs, "source")
    target_configs = _parse_workload_sheet_configs(target_sheet_configs, "target")
    filter_field = _parse_workload_filter_field(value_filter_field) if only_capture_rows_with_value else None
    mode = _parse_workload_write_mode(write_mode)
    if not source_configs or not target_configs:
        raise HTTPException(status_code=400, detail="请先完成工作量表和当前控制价表的 sheet/列映射")

    state = _load_process_state(job_dir)
    excel_path = _state_path(job_dir, state, "output_excel")
    if not excel_path or not excel_path.exists():
        raise HTTPException(status_code=404, detail="当前预览控制价表不存在，请先完成转换")
    input_path = _state_path(job_dir, state, "input_excel", required=False)
    input_name = str(state.get("input_filename") or (input_path.name if input_path else "input.xlsx"))

    workload_dir = job_dir / "workload-current"
    workload_dir.mkdir(parents=True, exist_ok=True)
    workload_path = workload_dir / workload_file.filename
    workload_path.write_bytes(await workload_file.read())
    marked_workload = workload_dir / f"{TEMP_FILE_PREFIX}-原表-(工作量信息抓取后标注符合用)-{_output_timestamp()}.xlsx"

    try:
        workload_summary = capture_workload(
            workload_path,
            excel_path,
            marked_workload,
            excel_path,
            source_configs,
            target_configs,
            selected_fields=selected,
            filter_non_empty_field=filter_field,
            write_mode=mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    recalculate_workbook(excel_path)
    summary = _summary_from_dict(state.get("summary", {}))
    summary.table_preview = _refresh_table_preview_from_output(summary.table_preview, excel_path)
    report_path = _state_path(job_dir, state, "output_report", required=False)
    if report_path:
        report_path = write_report(
            report_path,
            input_name,
            summary,
            output_excel_path=excel_path,
            input_excel_path=input_path,
        )
        summary.output_report = report_path.name
    else:
        summary.output_report = str(state.get("output_report") or "")
    summary.output_excel = excel_path.name
    _save_process_state(
        job_dir,
        input_name,
        input_path,
        excel_path,
        report_path,
        summary,
        extra={"workload_capture_summary": workload_summary},
    )
    return {
        "job_id": clean_job_id,
        "summary": summary.to_dict(),
        "downloads": {
            "excel": f"/api/download/{clean_job_id}/excel",
            "report": f"/api/download/{clean_job_id}/report",
        },
        "workload_summary": workload_summary,
        "workload_downloads": {
            "workload": f"/api/workload-capture/current-download/{clean_job_id}/workload",
        },
    }


@app.get("/api/workload-capture/current-download/{job_id}/{kind}")
def download_current_workload_capture(job_id: str, kind: str) -> FileResponse:
    if kind != "workload":
        raise HTTPException(status_code=400, detail="当前预览写入流程只提供标注工作量表下载")
    job_dir = RUNTIME_DIR / str(job_id).strip()
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    workload_dir = job_dir / "workload-current"
    if not workload_dir.exists():
        raise HTTPException(status_code=404, detail="标注工作量表不存在")
    matches = sorted(workload_dir.glob(f"{TEMP_FILE_PREFIX}-原表-*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise HTTPException(status_code=404, detail="标注工作量表不存在")
    path = matches[0]
    return FileResponse(path, filename=path.name)


@app.get("/api/workload-capture/download/{job_id}/{kind}")
def download_workload_capture(job_id: str, kind: str) -> FileResponse:
    job_dir = RUNTIME_DIR / "workload-capture" / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    if kind == "workload":
        matches = _find_workload_capture_files(job_dir, "workload")
    elif kind == "target":
        matches = _find_workload_capture_files(job_dir, "target")
    else:
        raise HTTPException(status_code=400, detail="下载类型只能是 workload 或 target")
    if not matches:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = matches[0]
    return FileResponse(path, filename=path.name)


@app.get("/api/download/{job_id}/{kind}")
def download(
    job_id: str,
    kind: str,
    hide_empty_rows: bool = False,
    value_filter_field: str | None = None,
) -> FileResponse:
    job_dir = RUNTIME_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    if kind == "excel":
        matches = _find_output_excel_files(job_dir)
    elif kind == "report":
        matches = _find_report_files(job_dir, ".docx")
    else:
        raise HTTPException(status_code=400, detail="下载类型只能是 excel 或 report")

    if not matches:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = matches[0]
    if kind == "excel" and hide_empty_rows:
        filter_field = _parse_warning_filter_field(value_filter_field)
        path = _excel_with_hidden_empty_rows(path, filter_field)
    return FileResponse(path, filename=path.name)


@app.post("/api/risk-report")
async def generate_risk_report(
    job_id: str = Form(...),
    provider: str = Form(default=DEFAULT_PROVIDER),
    model: str = Form(default=DEFAULT_MODEL),
    base_url: str = Form(default=DEFAULT_BASE_URL),
) -> dict[str, object]:
    job_dir = RUNTIME_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    excel_matches = _find_output_excel_files(job_dir)
    report_matches = _find_report_files(job_dir, ".docx")
    markdown_matches = _find_report_files(job_dir, ".md")
    if not excel_matches or not report_matches or not markdown_matches:
        raise HTTPException(status_code=404, detail="任务文件不完整，请先完成转换")

    markdown_text = markdown_matches[0].read_text(encoding="utf-8")
    knowledge_evidence, knowledge_sources = _build_risk_report_knowledge_evidence()
    config = LlmConfig(provider=provider, model=model, base_url=base_url)
    messages = build_risk_prompt(markdown_text, excel_matches[0], knowledge_evidence)
    prompt_path = _write_llm_prompt_markdown("风险报告", config, messages, job_dir)
    try:
        risk_text = call_chat_completion(config, messages)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    risk_md_path = job_dir / "大模型风险报告-【codex】.md"
    risk_md_path.write_text(risk_text + "\n", encoding="utf-8")
    append_risk_report(report_matches[0], risk_text)
    return {
        "job_id": job_id,
        "risk_report": risk_text,
        "knowledge_sources": knowledge_sources,
        "downloads": {"report": f"/api/download/{job_id}/report"},
        "debug": _build_llm_debug(config, messages, prompt_path),
    }


@app.post("/api/llm-chat")
async def llm_chat(
    message: str = Form(...),
    provider: str = Form(default=DEFAULT_PROVIDER),
    model: str = Form(default=DEFAULT_MODEL),
    base_url: str = Form(default=DEFAULT_BASE_URL),
) -> dict[str, object]:
    clean_message = message.strip()
    if not clean_message:
        raise HTTPException(status_code=400, detail="请输入要发送给大模型的问题")

    config = LlmConfig(provider=provider, model=model, base_url=base_url)
    knowledge_message, force_knowledge = strip_force_knowledge_prefix(clean_message)
    if force_knowledge:
        if not knowledge_message:
            raise HTTPException(status_code=400, detail="请输入查库问题")
        results = search_knowledge(knowledge_message, limit=8)
        if not results:
            return {
                "provider": provider,
                "model": model,
                "answer": NO_EVIDENCE_ANSWER,
                "forced_knowledge": True,
                "evidence_found": False,
                "sources": [],
                "debug": None,
            }
        messages = build_knowledge_answer_prompt(knowledge_message, results)
        prompt_path = _write_llm_prompt_markdown("强制知识库问答", config, messages)
        try:
            answer = call_chat_completion(config, messages)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "provider": provider,
            "model": model,
            "answer": answer or NO_EVIDENCE_ANSWER,
            "forced_knowledge": True,
            "evidence_found": True,
            "sources": [result.__dict__ for result in results],
            "debug": _build_llm_debug(config, messages, prompt_path),
        }

    messages = [
        {
            "role": "system",
            "content": "你是造价智算本地原型的大模型测试助手，回答应简洁、准确，避免编造未提供的事实。",
        },
        {"role": "user", "content": clean_message},
    ]
    prompt_path = _write_llm_prompt_markdown("问答测试", config, messages)
    try:
        answer = call_chat_completion(config, messages)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "provider": provider,
        "model": model,
        "answer": answer,
        "debug": _build_llm_debug(config, messages, prompt_path),
    }


@app.post("/api/knowledge/search")
async def knowledge_search(payload: dict[str, Any] = Body(...)) -> dict[str, object]:
    question = str(payload.get("question") or "").strip()
    question, prefix_forced = strip_force_knowledge_prefix(question)
    if not question:
        raise HTTPException(status_code=400, detail="请输入要检索的问题")
    force_knowledge = bool(payload.get("force_knowledge")) or prefix_forced
    limit = _parse_knowledge_limit(payload.get("limit"))
    row_context = _parse_row_context(payload.get("row_context"))
    results = search_knowledge(question, row_context=row_context, limit=limit)
    return {
        "query": question,
        "context_type": str(payload.get("context_type") or "general"),
        "knowledge_question": is_knowledge_question(question),
        "forced_knowledge": force_knowledge,
        "evidence_found": bool(results),
        "results": [result.__dict__ for result in results],
    }


@app.post("/api/knowledge/ask")
async def knowledge_ask(payload: dict[str, Any] = Body(...)) -> dict[str, object]:
    question = str(payload.get("question") or "").strip()
    question, prefix_forced = strip_force_knowledge_prefix(question)
    if not question:
        raise HTTPException(status_code=400, detail="请输入要询问的问题")
    force_knowledge = bool(payload.get("force_knowledge")) or prefix_forced

    limit = _parse_knowledge_limit(payload.get("limit"))
    row_context = _parse_row_context(payload.get("row_context"))
    results = search_knowledge(question, row_context=row_context, limit=limit)
    if not results:
        return {
            "answer": NO_EVIDENCE_ANSWER,
            "sources": [],
            "evidence_found": False,
            "forced_knowledge": force_knowledge,
            "debug": None,
        }

    provider = str(payload.get("provider") or DEFAULT_PROVIDER)
    model = str(payload.get("model") or DEFAULT_MODEL)
    base_url = str(payload.get("base_url") or DEFAULT_BASE_URL)
    config = LlmConfig(provider=provider, model=model, base_url=base_url)
    messages = build_knowledge_answer_prompt(question, results, row_context=row_context)
    prompt_path = _write_llm_prompt_markdown("知识库问答", config, messages)
    try:
        answer = call_chat_completion(config, messages)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "answer": answer or NO_EVIDENCE_ANSWER,
        "sources": [result.__dict__ for result in results],
        "evidence_found": True,
        "forced_knowledge": force_knowledge,
        "debug": _build_llm_debug(config, messages, prompt_path),
    }


def _parse_knowledge_limit(value: object) -> int:
    try:
        return max(1, min(int(value), 20))
    except (TypeError, ValueError):
        return 8


def _build_risk_report_knowledge_evidence() -> tuple[str, list[dict[str, object]]]:
    seen_ids: set[str] = set()
    collected: list[tuple[str, dict[str, object]]] = []
    for query in RISK_REPORT_KNOWLEDGE_QUERIES:
        for result in search_knowledge(query, limit=4):
            if result.id in seen_ids:
                continue
            seen_ids.add(result.id)
            collected.append((query, result.__dict__))
            if len(collected) >= 12:
                break
        if len(collected) >= 12:
            break

    if not collected:
        return "当前知识库未检索到明确风险报告依据，报告中应提示建议人工复核。", []

    blocks: list[str] = []
    sources: list[dict[str, object]] = []
    for index, (query, source) in enumerate(collected, start=1):
        source_with_query = {"query": query, **source}
        sources.append(source_with_query)
        title = source.get("title_path") or "未标注"
        blocks.append(
            "\n".join(
                [
                    f"资料{index}：",
                    f"检索问题：{query}",
                    f"来源文件：{source.get('source_file', '')}",
                    f"标题路径：{title}",
                    f"正文片段：{source.get('snippet', '')}",
                ]
            )
        )
    return "\n\n".join(blocks), sources


def _parse_row_context(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def _build_llm_debug(config: LlmConfig, messages: list[dict[str, str]], prompt_path: Path | None = None) -> dict[str, object]:
    return {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "messages": messages,
        "prompt_markdown": str(prompt_path) if prompt_path else "",
    }


def _write_llm_prompt_markdown(
    source: str,
    config: LlmConfig,
    messages: list[dict[str, str]],
    directory: Path | None = None,
) -> Path:
    output_dir = directory or (RUNTIME_DIR / "llm-prompts")
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_source = "".join(char for char in source if char.isalnum() or char in "-_一二三四五六七八九十风险报告问答测试行级AI复核")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"{timestamp}-{safe_source or '大模型'}-提示词-【codex】.md"
    lines = [
        "# 大模型提示词调试文件",
        "",
        f"- 来源：{source}",
        f"- Provider：{config.provider}",
        f"- Model：{config.model}",
        f"- Base URL：{config.base_url}",
        f"- Temperature：{DEFAULT_TEMPERATURE}",
        f"- Max tokens：{DEFAULT_MAX_TOKENS}",
        "",
        "> 本文件只记录发送给大模型的提示词，不包含 API Key。",
        "",
    ]
    for index, message in enumerate(messages, start=1):
        lines.extend([
            f"## Message {index} - {message.get('role', '')}",
            "",
            str(message.get("content", "")),
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _find_report_files(job_dir: Path, suffix: str) -> list[Path]:
    current_named = list(job_dir.glob(f"{OUTPUT_FILE_PREFIX}-控制价报告-*{suffix}"))
    if current_named:
        return current_named
    current = list(job_dir.glob(f"*-处理报告-*-【codex】{suffix}"))
    if current:
        return current
    return list(job_dir.glob(f"*-处理报告-【codex】{suffix}"))


def _find_output_excel_files(job_dir: Path) -> list[Path]:
    current = list(job_dir.glob(f"{OUTPUT_FILE_PREFIX}-控制价计算表-*.xlsx"))
    if current:
        return current
    return list(job_dir.glob("*-填价结果-【codex】.xlsx"))


def _excel_with_hidden_empty_rows(path: Path, value_filter_field: str) -> Path:
    output_path = path.with_name(f"{path.stem}-隐藏空行{path.suffix}")
    value_workbook = load_workbook(path, data_only=True)
    workbook = load_workbook(path)
    try:
        for sheet_name in workbook.sheetnames:
            if not _is_core_output_sheet(sheet_name):
                continue
            if sheet_name not in value_workbook.sheetnames:
                continue
            value_sheet = value_workbook[sheet_name]
            sheet = workbook[sheet_name]
            header_values = next(
                value_sheet.iter_rows(min_row=4, max_row=4, values_only=True),
                (),
            )
            filter_column = _warning_filter_column_index(list(header_values), value_filter_field)
            if filter_column is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"下载 Excel 隐藏空行失败：{sheet_name} 未找到指定列：{value_filter_field}",
                )
            for row_index in range(5, sheet.max_row + 1):
                sheet.row_dimensions[row_index].hidden = False
            merged_value_map = FillEngine._build_merged_value_map(value_sheet)
            for row_index in range(5, value_sheet.max_row + 1):
                first_column_value = FillEngine._read_mapped_value(value_sheet, row_index, 1, merged_value_map)
                filter_value = FillEngine._read_mapped_value(value_sheet, row_index, filter_column, merged_value_map)
                if _is_total_label(first_column_value):
                    continue
                if not _has_warning_filter_value(filter_value):
                    sheet.row_dimensions[row_index].hidden = True
        workbook.save(output_path)
    finally:
        value_workbook.close()
        workbook.close()
    return output_path


def _is_core_output_sheet(sheet_name: str) -> bool:
    normalized = str(sheet_name or "").replace(" ", "")
    return any(token in normalized for token in ("表2", "表3", "表4", "表二", "表三", "表四"))


def _is_total_label(value: object) -> bool:
    return str(value or "").strip().replace(" ", "").startswith("合计")


def _find_workload_capture_files(job_dir: Path, kind: str) -> list[Path]:
    if kind == "workload":
        current = list(job_dir.glob(f"{TEMP_FILE_PREFIX}-原表-(工作量信息抓取后标注符合用)-*.xlsx"))
        if current:
            return current
        return list(job_dir.glob("*-工作量抓取标注-【codex】.xlsx"))
    if kind == "target":
        current = list(job_dir.glob(f"{TEMP_FILE_PREFIX}-控制价计算表（填好数量后）-*.xlsx"))
        if current:
            return current
        return list(job_dir.glob("*-已抓取工作量-【codex】.xlsx"))
    return []


def _output_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M")


def _warning_not_run_summary() -> dict[str, object]:
    pool_path = _resolve_experience_pool_path()
    warning_settings = _load_experience_warning_settings()
    return {
        "pool_enabled": pool_path.exists(),
        "executed": False,
        "candidate_rows": 0,
        "checked_rows": 0,
        "no_comparable_rows": 0,
        "warning_rows": 0,
        "high_rows": 0,
        "low_rows": 0,
        "medium_rows": 0,
        "metric_counts": {},
        "match_mode_counts": {},
        "low_risk_threshold_percent": warning_settings["low_risk_warning_ratio"],
        "high_risk_threshold_percent": warning_settings["high_risk_warning_ratio"],
        "summary_text": "经验池预警尚未执行：点击“运行经验池预警分析”后，会与经验池比选并写入预警列。",
    }


def _set_warning_progress(job_id: str, payload: dict[str, Any]) -> None:
    with WARNING_PROGRESS_LOCK:
        current = dict(WARNING_PROGRESS.get(job_id, WARNING_PROGRESS_DEFAULT))
        current.update(payload)
        for key in ("processed_rows", "total_rows", "matched_rows", "warning_rows"):
            current[key] = int(current.get(key) or 0)
        WARNING_PROGRESS[job_id] = current


def _get_warning_progress(job_id: str) -> dict[str, object]:
    with WARNING_PROGRESS_LOCK:
        return dict(WARNING_PROGRESS.get(job_id, WARNING_PROGRESS_DEFAULT))


def _find_demo_sample_path() -> Path | None:
    data_dir = DEFAULT_KB_PATH.parent
    for path in data_dir.glob("*.xlsx"):
        if path.name.startswith("~$") or "答案" in path.name:
            continue
        if all(token in path.name for token in DEMO_SAMPLE_TOKENS):
            return path
    return None


def _process_existing_workbook(
    input_source: Path,
    *,
    demo_mode: bool = False,
    sheet_configs: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if not input_source.exists():
        raise HTTPException(status_code=404, detail=f"输入文件不存在：{input_source}")
    if not DEFAULT_KB_PATH.exists():
        raise HTTPException(status_code=500, detail=f"知识库不存在：{DEFAULT_KB_PATH}")

    job_id = uuid4().hex
    job_dir = RUNTIME_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / input_source.name
    input_path.write_bytes(input_source.read_bytes())
    output_timestamp = _output_timestamp()
    output_excel = job_dir / f"{OUTPUT_FILE_PREFIX}-控制价计算表-{output_timestamp}.xlsx"
    output_report = job_dir / f"{OUTPUT_FILE_PREFIX}-控制价报告-{output_timestamp}.docx"

    try:
        summary = FillEngine(KnowledgeBase.from_excel(DEFAULT_KB_PATH)).fill_workbook(
            input_path,
            output_excel,
            only_match_rows_with_value=True,
            match_value_filter_field=DEFAULT_WARNING_FILTER_FIELD,
            sheet_configs=sheet_configs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    recalculate_workbook(output_excel)
    summary.warning_summary = _warning_not_run_summary()
    summary.warning_details = []
    summary.table_preview = _refresh_table_preview_from_output(summary.table_preview, output_excel)
    output_report = write_report(
        output_report,
        input_source.name,
        summary,
        output_excel_path=output_excel,
        input_excel_path=input_path,
    )
    summary.output_report = output_report.name
    _save_process_state(job_dir, input_source.name, input_path, output_excel, output_report, summary)
    return {
        "job_id": job_id,
        "demo_mode": demo_mode,
        "sample_file": input_source.name,
        "summary": summary.to_dict(),
        "downloads": {
            "excel": f"/api/download/{job_id}/excel",
            "report": f"/api/download/{job_id}/report",
        },
    }


def _demo_sample_sheet_configs(sample_path: Path) -> list[dict[str, object]]:
    configs: list[dict[str, object]] = []
    for sheet in _inspect_candidate_sheets(sample_path):
        mapping = {
            str(key): str(value).strip()
            for key, value in dict(sheet.get("suggested_mapping") or {}).items()
            if value is not None
        }
        if not all(mapping.get(field) for field in ("要素1", "单位", "输出-价格列")):
            continue
        configs.append(
            {
                "sheet_name": str(sheet.get("sheet_name") or "").strip(),
                "enabled": True,
                "header_row": int(sheet.get("header_row") or 1),
                "column_mapping": mapping,
                "output_match_report": True,
                "merge_vertical_cells": True,
                "merge_horizontal_cells": True,
                "only_match_rows_with_value": True,
                "match_value_filter_field": DEFAULT_WARNING_FILTER_FIELD,
            }
        )
    if not configs:
        raise HTTPException(status_code=400, detail="演示样例未找到可转换的业务明细 sheet")
    return configs


def _build_pending_match_summary(
    workbook_path: Path,
    *,
    column_mapping: dict[str, str] | None,
    header_row: int,
    sheet_configs: list[dict[str, object]] | None,
    only_match_rows_with_value: bool,
    match_value_filter_field: str,
) -> FillSummary:
    workbook = load_workbook(workbook_path)
    value_workbook = load_workbook(workbook_path, data_only=True)
    try:
        configs = sheet_configs or [
            {
                "sheet_name": workbook.active.title,
                "enabled": True,
                "header_row": header_row,
                "column_mapping": column_mapping,
                "merge_vertical_cells": True,
                "merge_horizontal_cells": True,
                "only_match_rows_with_value": only_match_rows_with_value,
                "match_value_filter_field": match_value_filter_field,
            }
        ]
        preview_header_rows = {
            str(config.get("sheet_name") or workbook.active.title): int(config.get("header_row") or header_row)
            for config in configs
        }
        total_data_rows = 0
        price_column_name = ""
        for config in configs:
            if config.get("enabled") is False:
                continue
            sheet_name = str(config.get("sheet_name") or workbook.active.title)
            if sheet_name not in workbook.sheetnames:
                raise ValueError(f"输入表不存在候选 sheet：{sheet_name}")
            sheet = workbook[sheet_name]
            value_sheet = value_workbook[sheet_name]
            current_header_row = int(config.get("header_row") or header_row)
            headers = [cell.value for cell in value_sheet[current_header_row]]
            header_map = {str(name).strip(): idx for idx, name in enumerate(headers, start=1) if name}
            current_mapping = config.get("column_mapping") or column_mapping
            field_map = FillEngine._resolve_field_map(header_map, current_mapping)
            missing = [name for name in FIELD_COLUMNS if name not in field_map]
            if missing:
                raise ValueError(f"输入表缺少必要列：{', '.join(missing)}")
            current_price_column_name, _ = FillEngine._find_price_column(header_map, headers, current_mapping)
            if not price_column_name:
                price_column_name = current_price_column_name
            current_only_match_rows_with_value = bool(config.get("only_match_rows_with_value", only_match_rows_with_value))
            current_match_value_filter_field = str(config.get("match_value_filter_field") or match_value_filter_field)
            merged_value_map = FillEngine._build_merged_value_map(
                value_sheet,
                merge_vertical_cells=bool(config.get("merge_vertical_cells", True)),
                merge_horizontal_cells=bool(config.get("merge_horizontal_cells", True)),
            )
            filter_column_index = (
                FillEngine._find_value_filter_column(headers, current_match_value_filter_field)
                if current_only_match_rows_with_value
                else None
            )
            if current_only_match_rows_with_value and filter_column_index is None:
                raise ValueError(f"{sheet.title} 未找到指定列：{current_match_value_filter_field}")
            for excel_row in range(current_header_row + 1, sheet.max_row + 1):
                values = {
                    name: FillEngine._read_mapped_value(value_sheet, excel_row, field_map[name], merged_value_map)
                    for name in FIELD_COLUMNS
                }
                if FillEngine._is_ignored_row(values.get("要素1")):
                    continue
                if filter_column_index is not None:
                    filter_value = FillEngine._read_mapped_value(value_sheet, excel_row, filter_column_index, merged_value_map)
                    if not FillEngine._has_value_for_matching_filter(filter_value):
                        continue
                total_data_rows += 1
        table_preview = FillEngine._build_multi_sheet_table_preview(
            [
                (workbook[sheet_name], preview_header_rows.get(sheet_name, 1))
                for sheet_name in workbook.sheetnames
            ],
            max_rows=50,
        )
        return FillSummary(
            total_data_rows=total_data_rows,
            price_column=price_column_name,
            filled_rows=0,
            matched_rows=0,
            unchanged_rows=0,
            review_rows=0,
            conflict_rows=0,
            output_excel=workbook_path.name,
            output_report="",
            report_text=f"已读取{total_data_rows}行，等待批量匹配价格和两个系数。",
            table_preview=table_preview,
            matching_status="pending",
            warning_summary=_warning_not_run_summary(),
            warning_details=[],
        )
    finally:
        value_workbook.close()
        workbook.close()


def _save_process_state(
    job_dir: Path,
    input_filename: str,
    input_path: Path | None,
    output_excel: Path,
    output_report: Path | None,
    summary: FillSummary,
    extra: dict[str, object] | None = None,
) -> None:
    state_path = job_dir / PROCESS_STATE_FILENAME
    preserved: dict[str, object] = {}
    if state_path.exists():
        try:
            previous_state = json.loads(state_path.read_text(encoding="utf-8"))
            for key in ("deferred_matching", "process_options"):
                if key in previous_state:
                    preserved[key] = previous_state[key]
        except json.JSONDecodeError:
            preserved = {}
    state = {
        **preserved,
        "input_filename": input_filename,
        "input_excel": input_path.name if input_path else "",
        "output_excel": output_excel.name,
        "output_report": output_report.name if output_report else "",
        "summary": summary.to_dict(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if extra:
        state.update(extra)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_process_state(job_dir: Path) -> dict[str, object]:
    state_path = job_dir / PROCESS_STATE_FILENAME
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="任务状态文件损坏，请重新转换") from exc


def _manual_edit_log_path(job_dir: Path) -> Path:
    return job_dir / MANUAL_EDIT_LOG_FILENAME


def _load_manual_edit_log(job_dir: Path) -> list[dict[str, object]]:
    path = _manual_edit_log_path(job_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="人工修改记录文件损坏，请重新转换") from exc
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _append_manual_edit_log(job_dir: Path, record: dict[str, object]) -> None:
    records = _load_manual_edit_log(job_dir)
    records.append(record)
    _manual_edit_log_path(job_dir).write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _apply_manual_edit_to_table_preview(
    table_preview: dict[str, object],
    record: dict[str, object],
    header_rows: dict[str, int],
) -> dict[str, object]:
    target_sheet = str(record.get("sheet") or "").strip()
    row_number = int(record.get("row_number") or 0)
    column_number = int(record.get("column_number") or 0)
    next_value = record.get("new_value")

    def apply_to_sheet(preview: dict[str, object]) -> dict[str, object]:
        sheet_name = str(preview.get("sheet_name") or "").strip()
        if sheet_name != target_sheet:
            return preview
        header_row = header_rows.get(sheet_name)
        if header_row is None:
            try:
                header_row = int(preview.get("header_row") or 1)
            except (TypeError, ValueError):
                header_row = 1
        row_numbers = preview.get("row_numbers")
        if isinstance(row_numbers, list):
            row_index = next(
                (
                    index
                    for index, value in enumerate(row_numbers)
                    if _safe_int(value) == row_number
                ),
                -1,
            )
        else:
            row_index = row_number - header_row - 1
        column_index = column_number - 1
        rows = preview.get("rows")
        if not isinstance(rows, list) or row_index < 0 or row_index >= len(rows):
            return preview
        next_rows: list[object] = []
        for index, row in enumerate(rows):
            if index != row_index or not isinstance(row, list):
                next_rows.append(row)
                continue
            next_row = list(row)
            if column_index >= len(next_row):
                next_row.extend([""] * (column_index - len(next_row) + 1))
            next_row[column_index] = next_value
            next_rows.append(next_row)
        return {**dict(preview), "rows": next_rows}

    preview_sheets = table_preview.get("sheets")
    if isinstance(preview_sheets, list) and preview_sheets:
        sheets = [
            apply_to_sheet(sheet)
            for sheet in preview_sheets
            if isinstance(sheet, dict)
        ]
        if not sheets:
            return table_preview
        first = sheets[0]
        return {
            **dict(table_preview),
            "sheet_name": first.get("sheet_name", ""),
            "header_row": first.get("header_row"),
            "headers": first.get("headers", []),
            "rows": first.get("rows", []),
            "row_numbers": first.get("row_numbers", []),
            "sheets": sheets,
        }
    return apply_to_sheet(table_preview)


def _write_preview_cell_edit(
    output_excel: Path,
    *,
    job_id: str,
    sheet_name: str,
    row_number: int,
    column_number: int,
    new_value: object,
    header_rows: dict[str, int],
    edit_source: str = "manual",
    edit_note: str = "",
    candidate_meta: dict[str, object] | None = None,
) -> dict[str, object]:
    workbook = load_workbook(output_excel)
    try:
        if sheet_name not in workbook.sheetnames:
            raise HTTPException(status_code=400, detail=f"输出 Excel 不存在 sheet：{sheet_name}")
        sheet = workbook[sheet_name]
        if row_number > sheet.max_row or column_number > sheet.max_column:
            raise HTTPException(status_code=400, detail="编辑位置超出当前输出 Excel 范围")
        header_row = header_rows.get(sheet_name) or _find_preview_header_row(sheet, [])
        header_text = _preview_edit_header(sheet, header_row, column_number)
        cell = sheet.cell(row=row_number, column=column_number)
        _ensure_preview_cell_editable(sheet, cell, header_row, header_text)

        original_value = cell.value
        saved_value = _coerce_manual_edit_value(new_value, original_value, header_text)
        updated_at = datetime.now().isoformat(timespec="seconds")
        cell.value = saved_value
        cell.fill = MANUAL_EDIT_FILL
        column_letter = get_column_letter(column_number)
        source_text = "辅助填价人工确认" if edit_source == "fill-assist" else "人工修改"
        extra_comment_parts = []
        if candidate_meta:
            extra_comment_parts.append(f"候选来源：{candidate_meta.get('source_label') or candidate_meta.get('source') or ''}")
            extra_comment_parts.append(f"候选依据：{candidate_meta.get('basis') or ''}")
        if edit_note:
            extra_comment_parts.append(f"备注：{edit_note}")
        cell.comment = Comment(
            (
                f"{source_text}\n"
                f"原值：{_manual_edit_value_text(original_value)}\n"
                f"新值：{_manual_edit_value_text(saved_value)}\n"
                f"时间：{updated_at}"
                + ("\n" + "\n".join(part for part in extra_comment_parts if part.strip()) if extra_comment_parts else "")
            ),
            MANUAL_EDIT_COMMENT_AUTHOR,
        )
        workbook.save(output_excel)
        record = {
            "job_id": job_id,
            "sheet": sheet_name,
            "row_number": row_number,
            "column_number": column_number,
            "column_letter": column_letter,
            "header": header_text,
            "original_value": _jsonable_cell_value(original_value),
            "new_value": _jsonable_cell_value(saved_value),
            "updated_at": updated_at,
            "source": edit_source,
            "note": edit_note,
        }
        if candidate_meta:
            record["candidate"] = {
                "source": candidate_meta.get("source"),
                "source_label": candidate_meta.get("source_label"),
                "basis": candidate_meta.get("basis"),
                "reason": candidate_meta.get("reason"),
                "confidence": candidate_meta.get("confidence"),
                "confidence_label": candidate_meta.get("confidence_label"),
            }
        return record
    finally:
        workbook.close()


def _preview_edit_header(sheet: object, header_row: int, column_number: int) -> str:
    if 1 <= header_row <= sheet.max_row:
        value = sheet.cell(row=header_row, column=column_number).value
        return str(value or "").strip() or f"列{column_number}"
    return f"列{column_number}"


def _ensure_preview_cell_editable(sheet: object, cell: object, header_row: int, header_text: str) -> None:
    if cell.row <= header_row:
        raise HTTPException(status_code=400, detail="表头和标题行暂不支持人工修改")
    if sheet.row_dimensions[cell.row].hidden:
        raise HTTPException(status_code=400, detail="隐藏行暂不支持人工修改")
    if _is_readonly_preview_header(header_text):
        raise HTTPException(status_code=400, detail=f"{header_text} 属于系统生成列，暂不支持人工修改")
    if sheet.protection.sheet and cell.protection.locked:
        raise HTTPException(status_code=400, detail="受保护单元格暂不支持人工修改")
    if isinstance(cell.value, str) and cell.value.startswith("="):
        raise HTTPException(status_code=400, detail="公式单元格暂不支持人工修改")
    for merged_range in sheet.merged_cells.ranges:
        if cell.coordinate not in merged_range:
            continue
        if cell.coordinate != merged_range.start_cell.coordinate:
            raise HTTPException(status_code=400, detail="合并单元格非左上角暂不支持人工修改")
        return


def _is_readonly_preview_header(header_text: str) -> bool:
    compact = header_text.replace(" ", "")
    return compact in {item.replace(" ", "") for item in MANUAL_EDIT_READONLY_HEADERS}


def _coerce_manual_edit_value(value: object, original_value: object, header_text: str) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        if _should_coerce_manual_edit_to_number(original_value, header_text):
            numeric_text = text.replace(",", "")
            try:
                number = float(numeric_text)
            except ValueError:
                return value
            return int(number) if number.is_integer() else number
        return value
    return value


def _should_coerce_manual_edit_to_number(original_value: object, header_text: str) -> bool:
    if isinstance(original_value, (int, float)) and not isinstance(original_value, bool):
        return True
    compact = header_text.replace(" ", "")
    return any(token in compact for token in MANUAL_EDIT_NUMERIC_HEADER_TOKENS)


def _jsonable_cell_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _manual_edit_value_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _state_path(job_dir: Path, state: dict[str, object], key: str, required: bool = True) -> Path | None:
    name = str(state.get(key) or "").strip()
    if not name:
        if required:
            raise HTTPException(status_code=404, detail="任务状态不完整，请重新转换")
        return None
    return job_dir / name


def _summary_from_dict(raw: dict[str, object]) -> FillSummary:
    if not raw:
        raise HTTPException(status_code=404, detail="任务状态不完整，请重新转换")
    review_details = [
        ReviewRow(
            excel_row=int(row.get("excel_row") or 0),
            status=str(row.get("status") or ""),
            message=str(row.get("message") or ""),
            values=dict(row.get("values") or {}),
        )
        for row in raw.get("review_details", [])
        if isinstance(row, dict)
    ]
    return FillSummary(
        total_data_rows=int(raw.get("total_data_rows") or 0),
        price_column=str(raw.get("price_column") or ""),
        filled_rows=int(raw.get("filled_rows") or 0),
        matched_rows=int(raw.get("matched_rows") or 0),
        unchanged_rows=int(raw.get("unchanged_rows") or 0),
        review_rows=int(raw.get("review_rows") or 0),
        conflict_rows=int(raw.get("conflict_rows") or 0),
        output_excel=str(raw.get("output_excel") or ""),
        output_report=str(raw.get("output_report") or ""),
        report_text=str(raw.get("report_text") or ""),
        table_preview=dict(raw.get("table_preview") or {}),
        review_details=review_details,
        price_logs=list(raw.get("price_logs") or []),
        physical_matched_rows=int(raw.get("physical_matched_rows") or 0),
        physical_experience_rows=int(raw.get("physical_experience_rows") or 0),
        physical_review_rows=int(raw.get("physical_review_rows") or 0),
        technical_matched_rows=int(raw.get("technical_matched_rows") or 0),
        technical_experience_rows=int(raw.get("technical_experience_rows") or 0),
        technical_review_rows=int(raw.get("technical_review_rows") or 0),
        warning_summary=dict(raw.get("warning_summary") or {}),
        warning_details=list(raw.get("warning_details") or []),
        matching_status=str(raw.get("matching_status") or "completed"),
    )


def _refresh_table_preview_from_output(
    table_preview: dict[str, object],
    output_excel: Path,
    header_rows: dict[str, int] | None = None,
) -> dict[str, object]:
    if not output_excel.exists():
        return table_preview
    table_preview = _with_preview_header_rows(table_preview, header_rows or {})
    try:
        resolver = WorkbookFormulaResolver(output_excel)
    except Exception:
        resolver = None
    if resolver is not None:
        try:
            preview_sheets = table_preview.get("sheets")
            sheets = preview_sheets if isinstance(preview_sheets, list) and preview_sheets else [table_preview]
            refreshed = [
                _refresh_one_preview_sheet_with_resolver(resolver, sheet)
                for sheet in sheets
                if isinstance(sheet, dict)
            ]
            if not refreshed:
                return table_preview
            first = refreshed[0]
            return {
                "sheet_name": first["sheet_name"],
                "header_row": first.get("header_row"),
                "headers": first["headers"],
                "rows": first["rows"],
                "row_numbers": first.get("row_numbers", []),
                "sheets": refreshed,
            }
        finally:
            resolver.close()

    workbook = load_workbook(output_excel, read_only=True, data_only=True)
    try:
        preview_sheets = table_preview.get("sheets")
        sheets = preview_sheets if isinstance(preview_sheets, list) and preview_sheets else [table_preview]
        refreshed = [
            _refresh_one_preview_sheet(workbook, sheet)
            for sheet in sheets
            if isinstance(sheet, dict)
        ]
        if not refreshed:
            return table_preview
        first = refreshed[0]
        return {
            "sheet_name": first["sheet_name"],
            "header_row": first.get("header_row"),
            "headers": first["headers"],
            "rows": first["rows"],
            "row_numbers": first.get("row_numbers", []),
            "sheets": refreshed,
        }
    finally:
        workbook.close()


def _parse_preview_header_rows(raw: object) -> dict[str, int]:
    if raw is None:
        return {}
    payload = raw
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="预览表头行设置不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="预览表头行设置必须是对象")
    header_rows: dict[str, int] = {}
    for key, value in payload.items():
        sheet_name = str(key or "").strip()
        if not sheet_name:
            continue
        try:
            row_number = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{sheet_name} 的预览表头行不是有效数字") from exc
        if row_number < 1:
            raise HTTPException(status_code=400, detail=f"{sheet_name} 的预览表头行必须大于等于 1")
        header_rows[sheet_name] = row_number
    return header_rows


def _with_preview_header_rows(table_preview: dict[str, object], header_rows: dict[str, int]) -> dict[str, object]:
    if not header_rows:
        return table_preview

    def apply_header_row(preview: dict[str, object]) -> dict[str, object]:
        sheet_name = str(preview.get("sheet_name") or "").strip()
        header_row = header_rows.get(sheet_name)
        if header_row is None:
            return preview
        next_preview = dict(preview)
        next_preview["header_row"] = header_row
        return next_preview

    preview_sheets = table_preview.get("sheets")
    if isinstance(preview_sheets, list) and preview_sheets:
        sheets = [
            apply_header_row(sheet)
            for sheet in preview_sheets
            if isinstance(sheet, dict)
        ]
        if not sheets:
            return table_preview
        first = sheets[0]
        return {
            **dict(table_preview),
            "sheet_name": first.get("sheet_name", ""),
            "header_row": first.get("header_row"),
            "headers": first.get("headers", []),
            "rows": first.get("rows", []),
            "row_numbers": first.get("row_numbers", []),
            "sheets": sheets,
        }
    return apply_header_row(table_preview)


def _refresh_one_preview_sheet_with_resolver(
    resolver: WorkbookFormulaResolver,
    preview: dict[str, object],
) -> dict[str, object]:
    sheet_name = str(preview.get("sheet_name") or "")
    if sheet_name not in resolver.sheetnames:
        return preview
    sheet = resolver.value_workbook[sheet_name]
    merged_value_map = FillEngine._build_merged_value_map(sheet)
    header_row = _preview_header_row(preview, sheet, list(preview.get("headers") or []))
    preview_rows = preview.get("rows") or []
    max_rows = len(preview_rows) or 50
    column_count = _preview_column_count(
        list(preview.get("headers") or []),
        preview_rows,
        resolver.sheet_max_column(sheet_name),
    )
    column_count = _extend_preview_column_count_for_warning_columns(sheet, header_row, column_count)
    raw_headers = [
        value if value is not None else ""
        for value in _resolved_preview_row_values(resolver, sheet_name, header_row, column_count, merged_value_map)
    ]
    headers = FillEngine.preview_display_headers(sheet, header_row, raw_headers, column_count)
    rows = [
        [
            value if value is not None else ""
            for value in _resolved_preview_row_values(resolver, sheet_name, row_index, column_count, merged_value_map)
        ]
        for row_index in range(header_row + 1, min(resolver.sheet_max_row(sheet_name), header_row + max_rows) + 1)
    ]
    row_numbers = list(range(header_row + 1, header_row + 1 + len(rows)))
    return {"sheet_name": sheet.title, "header_row": header_row, "headers": headers, "rows": rows, "row_numbers": row_numbers}


def _resolved_preview_row_values(
    resolver: WorkbookFormulaResolver,
    sheet_name: str,
    row_index: int,
    column_count: int,
    merged_value_map: dict[tuple[int, int], Any],
) -> list[Any]:
    return [
        merged_value_map.get((row_index, column_index), resolver.cell_value(sheet_name, row_index, column_index))
        for column_index in range(1, column_count + 1)
    ]


def _refresh_one_preview_sheet(workbook: object, preview: dict[str, object]) -> dict[str, object]:
    sheet_name = str(preview.get("sheet_name") or "")
    if sheet_name not in workbook.sheetnames:
        return preview
    sheet = workbook[sheet_name]
    return _refresh_preview_from_sheet(sheet, preview)


def _refresh_preview_from_sheet(sheet: object, preview: dict[str, object]) -> dict[str, object]:
    headers = list(preview.get("headers") or [])
    header_row = _preview_header_row(preview, sheet, headers)
    preview_rows = preview.get("rows") or []
    max_rows = len(preview_rows) or 50
    column_count = _preview_column_count(headers, preview_rows, sheet.max_column)
    column_count = _extend_preview_column_count_for_warning_columns(sheet, header_row, column_count)
    raw_headers = [
        value if value is not None else ""
        for value in next(
            sheet.iter_rows(
                min_row=header_row,
                max_row=header_row,
                max_col=column_count,
                values_only=True,
            ),
            (),
        )
    ]
    headers = FillEngine.preview_display_headers(sheet, header_row, raw_headers, column_count)
    rows = [
        [value if value is not None else "" for value in row]
        for row in sheet.iter_rows(
            min_row=header_row + 1,
            max_row=min(sheet.max_row, header_row + max_rows),
            max_col=column_count,
            values_only=True,
        )
    ]
    row_numbers = list(range(header_row + 1, header_row + 1 + len(rows)))
    return {"sheet_name": sheet.title, "header_row": header_row, "headers": headers, "rows": rows, "row_numbers": row_numbers}


def _preview_header_row(preview: dict[str, object], sheet: object, headers: list[object]) -> int:
    try:
        header_row = int(preview.get("header_row") or 0)
    except (TypeError, ValueError):
        header_row = 0
    if 1 <= header_row <= sheet.max_row:
        return header_row
    return _find_preview_header_row(sheet, headers)


def _extend_preview_column_count_for_warning_columns(sheet: object, header_row: int, column_count: int) -> int:
    scan_limit = min(sheet.max_column, max(column_count + len(WARNING_OUTPUT_FIELDS) + 8, column_count))
    header_values = next(
        sheet.iter_rows(
            min_row=header_row,
            max_row=header_row,
            max_col=scan_limit,
            values_only=True,
        ),
        (),
    )
    for index, value in enumerate(header_values, start=1):
        if str(value or "").strip() in WARNING_OUTPUT_FIELDS:
            column_count = max(column_count, index)
    return column_count


def _preview_column_count(headers: list[object], rows: object, sheet_max_column: int) -> int:
    widths = [len(headers)]
    if isinstance(rows, list):
        widths.extend(len(row) for row in rows if isinstance(row, list))
    column_count = max(widths) if widths else 0
    if column_count <= 0:
        return min(sheet_max_column, 80)
    return min(column_count, sheet_max_column)


def _find_preview_header_row(sheet: object, headers: list[object]) -> int:
    compact_headers = [str(value or "").strip() for value in headers]
    non_empty_headers = [value for value in compact_headers if value]
    if not non_empty_headers:
        return 1
    for row_index in range(1, min(sheet.max_row, 8) + 1):
        values = [
            str(value or "").strip()
            for value in next(sheet.iter_rows(min_row=row_index, max_row=row_index, values_only=True), ())
        ]
        if values[: len(compact_headers)] == compact_headers:
            return row_index
        if len(non_empty_headers) >= 3 and sum(1 for value in non_empty_headers if value in values) >= 3:
            return row_index
    return 1


def _read_headers(path: Path, header_row: int | None = None, sheet_name: str | None = None) -> tuple[int, list[str]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    if sheet_name:
        if sheet_name not in workbook.sheetnames:
            workbook.close()
            raise HTTPException(status_code=400, detail=f"输入表不存在 sheet：{sheet_name}")
        sheet = workbook[sheet_name]
    else:
        sheet = workbook.active
    try:
        detected_row = header_row or _detect_header_row(sheet)
        row = next(sheet.iter_rows(min_row=detected_row, max_row=detected_row, values_only=True))
    except StopIteration as exc:
        raise HTTPException(status_code=400, detail="输入表没有表头行") from exc
    finally:
        workbook.close()
    return detected_row, [str(value).strip() if value is not None else "" for value in row]


def _inspect_candidate_sheets(
    path: Path,
    preferences: dict[str, list[str]] | None = None,
) -> list[dict[str, object]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet_names = [name for name in workbook.sheetnames if _is_candidate_sheet_name(name)]
        resolved_preferences = preferences if preferences is not None else _load_input_field_preferences()
        return [_inspect_sheet(workbook[name], resolved_preferences) for name in sheet_names]
    finally:
        workbook.close()


def _inspect_sheet(sheet: object, preferences: dict[str, list[str]] | None = None) -> dict[str, object]:
    detected_row = _detect_header_row(sheet)
    row = next(sheet.iter_rows(min_row=detected_row, max_row=detected_row, values_only=True), ())
    headers = [str(value).strip() if value is not None else "" for value in row]
    return {
        "sheet_name": sheet.title,
        "enabled": True,
        "header_row": detected_row,
        "headers": headers,
        "columns": _build_column_options(headers),
        "suggested_mapping": _suggest_column_mapping(headers, preferences),
    }


def _inspect_experience_sheets(path: Path, header_row: int | None = None, sheet_name: str | None = None) -> list[dict[str, object]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name:
            if sheet_name not in workbook.sheetnames:
                raise HTTPException(status_code=400, detail=f"输入表不存在 sheet：{sheet_name}")
            names = [sheet_name]
        else:
            names = list(workbook.sheetnames)
        candidate_names = [name for name in names if _is_candidate_sheet_name(name)]
        default_enabled = set(candidate_names) if candidate_names else {names[0]} if names else set()
        return [
            _inspect_experience_sheet(workbook[name], enabled=name in default_enabled, header_row=header_row)
            for name in names
        ]
    finally:
        workbook.close()


def _inspect_experience_sheet(sheet: object, enabled: bool, header_row: int | None = None) -> dict[str, object]:
    detected_row = header_row or _detect_header_row(sheet)
    row = next(sheet.iter_rows(min_row=detected_row, max_row=detected_row, values_only=True), ())
    headers = [str(value).strip() if value is not None else "" for value in row]
    return {
        "sheet_name": sheet.title,
        "enabled": enabled,
        "header_row": detected_row,
        "headers": headers,
        "columns": _build_column_options(headers),
        "suggested_mapping": _suggest_experience_column_mapping(headers),
    }


def _inspect_workload_sheets(
    path: Path,
    role: str,
    header_row: int | None = None,
    sheet_name: str | None = None,
    preferences: dict[str, list[str]] | None = None,
    adjacent_fallback_enabled: bool | None = None,
    element_sequence_enabled: bool | None = None,
) -> list[dict[str, object]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name:
            if sheet_name not in workbook.sheetnames:
                raise HTTPException(status_code=400, detail=f"输入表不存在 sheet：{sheet_name}")
            names = [sheet_name]
        else:
            names = list(workbook.sheetnames)
        if role == "source":
            default_enabled = {name for name in names if "工作量" in name and "范围" not in name}
            if not default_enabled and names:
                default_enabled = {names[0]}
        else:
            target_candidates = [name for name in names if _is_candidate_sheet_name(name)]
            default_enabled = set(target_candidates) if target_candidates else {names[0]} if names else set()
        return [
            _inspect_workload_sheet(
                workbook[name],
                role=role,
                enabled=name in default_enabled,
                header_row=header_row,
                preferences=preferences,
                adjacent_fallback_enabled=adjacent_fallback_enabled,
                element_sequence_enabled=element_sequence_enabled,
            )
            for name in names
        ]
    finally:
        workbook.close()


def _inspect_workload_sheet(
    sheet: object,
    role: str,
    enabled: bool,
    header_row: int | None = None,
    preferences: dict[str, list[str]] | None = None,
    adjacent_fallback_enabled: bool | None = None,
    element_sequence_enabled: bool | None = None,
) -> dict[str, object]:
    detected_row = header_row or _detect_workload_header_row(sheet, role)
    row = next(
        sheet.iter_rows(
            min_row=detected_row,
            max_row=detected_row,
            max_col=min(sheet.max_column, 300),
            values_only=True,
        ),
        (),
    )
    headers = [str(value).strip() if value is not None else "" for value in row]
    resolved_preferences = preferences if preferences is not None else (
        _load_workload_field_preferences() if role == "source" else _load_workload_target_field_preferences()
    )
    resolved_adjacent_fallback = adjacent_fallback_enabled if adjacent_fallback_enabled is not None else (
        _load_workload_adjacent_fallback_enabled() if role == "source" else _load_workload_target_adjacent_fallback_enabled()
    )
    resolved_element_sequence = element_sequence_enabled if element_sequence_enabled is not None else (
        _load_workload_element_sequence_enabled() if role == "source" else _load_workload_target_element_sequence_enabled()
    )
    return {
        "sheet_name": sheet.title,
        "enabled": enabled,
        "header_row": detected_row,
        "headers": headers,
        "columns": _build_column_options(headers),
        "suggested_mapping": suggest_workload_column_mapping(
            headers,
            role,
            resolved_preferences,
            resolved_adjacent_fallback,
            resolved_element_sequence,
        ),
    }


def _is_candidate_sheet_name(name: str) -> bool:
    return any(token in name for token in ["表2", "表3", "表4"])


def _detect_header_row(sheet: object) -> int:
    max_scan_row = min(sheet.max_row, 4)
    for row_index in range(1, max_scan_row + 1):
        values = next(sheet.iter_rows(min_row=row_index, max_row=row_index, values_only=True))
        if any(str(value).strip() == "要素1" for value in values if value is not None):
            return row_index
    return 1


def _detect_workload_header_row(sheet: object, role: str) -> int:
    if role == "target":
        return _detect_header_row(sheet)
    markers = ["项目", "工作任务", "内容", "类别", "单位", "数量", "工程量合计", "调整系数", "备注"]
    max_scan_row = min(sheet.max_row, 8)
    max_scan_col = min(sheet.max_column, 300)
    best_row = 1
    best_score = -1
    for row_index in range(1, max_scan_row + 1):
        values = [
            str(value or "").replace(" ", "")
            for value in next(
                sheet.iter_rows(
                    min_row=row_index,
                    max_row=row_index,
                    max_col=max_scan_col,
                    values_only=True,
                ),
                (),
            )
        ]
        score = sum(1 for marker in markers if any(marker in value for value in values))
        if score > best_score:
            best_score = score
            best_row = row_index
    return best_row


def _build_column_options(headers: list[str]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for index, header in enumerate(headers, start=1):
        letter = get_column_letter(index)
        columns.append(
            {
                "letter": letter,
                "header": header,
                "label": f"{letter}列 - {header}" if header else f"{letter}列",
            }
        )
    return columns


def _load_project_default_settings() -> dict[str, object]:
    if not PROJECT_DEFAULT_SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(PROJECT_DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _project_default_section(name: str) -> dict[str, object]:
    section = _load_project_default_settings().get(name, {})
    return section if isinstance(section, dict) else {}


def _project_default_bool(section: dict[str, object], key: str, default: bool) -> bool:
    return _sanitize_bool_setting(section.get(key), default)


def _project_default_int(section: dict[str, object], key: str, default: int, min_value: int = 1, max_value: int = 999) -> int:
    try:
        value = int(float(str(section.get(key, default)).strip()))
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def _project_input_mapping_defaults() -> dict[str, object]:
    section = _project_default_section("inputMapping")
    match_value_filter_field = _parse_warning_filter_field(
        str(section.get("matchValueFilterField", DEFAULT_WARNING_FILTER_FIELD) or DEFAULT_WARNING_FILTER_FIELD)
    )
    return {
        "headerRow": _project_default_int(section, "headerRow", 4),
        "outputMatchReport": _project_default_bool(section, "outputMatchReport", True),
        "onlyMatchRowsWithValue": _project_default_bool(section, "onlyMatchRowsWithValue", True),
        "matchValueFilterField": match_value_filter_field,
        "mergeVerticalCells": _project_default_bool(section, "mergeVerticalCells", True),
        "mergeHorizontalCells": _project_default_bool(section, "mergeHorizontalCells", True),
        "fieldPreferences": _default_input_field_preferences(),
    }


def _project_workload_capture_defaults() -> dict[str, object]:
    section = _project_default_section("workloadCapture")
    raw_selected_fields = section.get("selectedFields", DEFAULT_SELECTED_WORKLOAD_FIELDS)
    if isinstance(raw_selected_fields, list):
        selected_fields = [
            str(field).strip()
            for field in raw_selected_fields
            if str(field).strip() in DEFAULT_SELECTED_WORKLOAD_FIELDS
        ]
    else:
        selected_fields = []
    write_mode = str(section.get("writeMode", WRITE_MODE_CONSERVATIVE) or WRITE_MODE_CONSERVATIVE)
    if write_mode not in {WRITE_MODE_CONSERVATIVE, WRITE_MODE_OVERWRITE}:
        write_mode = WRITE_MODE_CONSERVATIVE
    value_filter_field = _parse_workload_filter_field(
        str(section.get("valueFilterField", DEFAULT_WORKLOAD_FILTER_FIELD) or DEFAULT_WORKLOAD_FILTER_FIELD)
    )
    return {
        "selectedFields": selected_fields or list(DEFAULT_SELECTED_WORKLOAD_FIELDS),
        "writeMode": write_mode,
        "onlyCaptureRowsWithValue": _project_default_bool(section, "onlyCaptureRowsWithValue", True),
        "valueFilterField": value_filter_field,
        "source": {
            "adjacentFallbackEnabled": _load_workload_adjacent_fallback_enabled(),
            "elementSequenceEnabled": _load_workload_element_sequence_enabled(),
            "fieldPreferences": _default_workload_field_preferences(),
        },
        "target": {
            "adjacentFallbackEnabled": _load_workload_target_adjacent_fallback_enabled(),
            "elementSequenceEnabled": _load_workload_target_element_sequence_enabled(),
            "fieldPreferences": _default_workload_target_field_preferences(),
        },
    }


def _project_zhisuan_window_defaults() -> dict[str, object]:
    section = _project_default_section("zhisuanWindow")
    quick_settings = section.get("quickSettings", {})
    dock_visibility = section.get("dockVisibility", {})
    return {
        "chatHeight": _project_default_int(section, "chatHeight", 430, 300, 720),
        "dockWidth": _project_default_int(section, "dockWidth", 400, 300, 560),
        "useViewportHeight": _project_default_bool(section, "useViewportHeight", False),
        "quickSettings": quick_settings if isinstance(quick_settings, dict) else {},
        "dockVisibility": dock_visibility if isinstance(dock_visibility, dict) else {},
        "welcomeMessage": str(section.get("welcomeMessage", "") or "").strip(),
        "dockStyle": str(section.get("dockStyle", "") or "").strip(),
    }


def _project_default_settings_payload() -> dict[str, object]:
    return {
        "version": int(_load_project_default_settings().get("version", 1) or 1),
        "file_path": str(PROJECT_DEFAULT_SETTINGS_PATH),
        "previewColumns": _default_preview_column_preferences(),
        "zhisuanWindow": _project_zhisuan_window_defaults(),
        "inputMapping": _project_input_mapping_defaults(),
        "workloadCapture": _project_workload_capture_defaults(),
        "feishuAppBot": feishu_app_bot.load_bot_defaults(),
    }


def _suggest_column_mapping(headers: list[str], preferences: dict[str, list[str]] | None = None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    defaults = _default_input_field_preferences()
    resolved_preferences = _sanitize_input_field_preferences(preferences or {})
    for name in FIELD_COLUMNS:
        mapping[name] = _find_preferred_input_column(headers, name, resolved_preferences, defaults)
        if not mapping[name] and name in {"要素2", "要素3", "要素4", "要素5"}:
            mapping[name] = EMPTY_ELEMENT_COLUMN

    price_column = _find_preferred_input_column(headers, "输出-价格列", resolved_preferences, defaults)
    mapping["输出-价格列"] = price_column
    mapping["价格列"] = price_column
    mapping[PHYSICAL_ADJUSTMENT_FIELD] = _find_preferred_input_column(
        headers,
        PHYSICAL_ADJUSTMENT_FIELD,
        resolved_preferences,
        defaults,
    )
    mapping[TECHNICAL_ADJUSTMENT_FIELD] = _find_preferred_input_column(
        headers,
        TECHNICAL_ADJUSTMENT_FIELD,
        resolved_preferences,
        defaults,
    )
    return mapping


def _builtin_input_field_preferences() -> dict[str, list[str]]:
    return {
        "要素1": ["要素1", "项目名称", "项目", "专业"],
        "要素2": ["要素2", "工作内容", "作业内容", "内容"],
        "要素3": ["要素3", "类别", "类别名称"],
        "要素4": ["要素4", "比例尺", "规格", "方法"],
        "要素5": ["要素5", "复杂程度", "等级"],
        "单位": ["单位", "计量单位"],
        "输出-价格列": ["单价匹配-测试", "基价测试列", "基价", "单价", "价格"],
        PHYSICAL_ADJUSTMENT_FIELD: ["实物工作费调整系数", "输出-实物工作费调整系数"],
        TECHNICAL_ADJUSTMENT_FIELD: ["技术工作费调整系数", "输出-技术工作费调整系数"],
    }


def _default_input_field_preferences() -> dict[str, list[str]]:
    defaults = _builtin_input_field_preferences()
    section = _project_default_section("inputMapping")
    raw_preferences = section.get("fieldPreferences", {})
    if not isinstance(raw_preferences, dict):
        return defaults
    return {**defaults, **_sanitize_input_field_preferences(raw_preferences)}


def _input_field_preferences_payload(preferences: dict[str, list[str]] | None = None) -> dict[str, object]:
    defaults = _default_input_field_preferences()
    return {
        "fields": INPUT_FIELD_PREFERENCE_FIELDS,
        "defaults": defaults,
        "preferences": preferences if preferences is not None else _load_input_field_preferences(),
        "mapping_defaults": _project_input_mapping_defaults(),
        "file_path": str(PROJECT_DEFAULT_SETTINGS_PATH),
    }


def _default_ui_preferences() -> dict[str, object]:
    return {
        "enabled": False,
        "styles": {},
        "text": {},
    }


def _ui_preferences_payload(preferences: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "defaults": _default_ui_preferences(),
        "preferences": preferences if preferences is not None else _load_ui_preferences(),
        "file_path": str(DEFAULT_UI_PREFERENCES_PATH),
    }


def _builtin_preview_column_preferences() -> dict[str, object]:
    return {
        "defaultLabels": DEFAULT_CORE_PREVIEW_LABELS,
        "sheetOverrides": {},
        "headerRows": {},
        "maxDisplayChars": DEFAULT_PREVIEW_CELL_MAX_DISPLAY_CHARS,
        "columnWidths": {},
    }


def _default_preview_column_preferences() -> dict[str, object]:
    defaults = _builtin_preview_column_preferences()
    section = _project_default_section("previewColumns")
    if not section:
        return defaults
    return _sanitize_preview_column_preferences(section, fallback=defaults)


def _preview_column_preferences_payload(preferences: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "defaults": _default_preview_column_preferences(),
        "preferences": preferences if preferences is not None else _load_preview_column_preferences(),
        "file_path": str(PROJECT_DEFAULT_SETTINGS_PATH),
    }


def _suggest_experience_column_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {field: "" for field in EXPERIENCE_MAPPING_FIELDS}
    defaults = _default_experience_field_preferences()
    preferences = _load_experience_field_preferences()
    direct_fields = [field for field in EXPERIENCE_MAPPING_FIELDS if field not in DEFAULT_SELECTED_EXPERIENCE_FIELDS]
    for field in direct_fields:
        mapping[field] = _find_experience_field_column(headers, field, preferences, defaults)
    for metric in DEFAULT_SELECTED_EXPERIENCE_FIELDS:
        mapping[metric] = _find_experience_metric_column(headers, metric, preferences.get(metric, []))
    remark_columns = [
        (index, header)
        for index, header in enumerate(headers, start=1)
        if any(token in header.replace(" ", "") for token in ["备注", "批注", "说明"])
    ]
    for offset, field in enumerate(["原表备注1", "原表备注2", "原表备注3"]):
        if offset < len(remark_columns):
            mapping[field] = get_column_letter(remark_columns[offset][0])
    return mapping


def _default_experience_field_preferences() -> dict[str, list[str]]:
    return {
        "要素1": ["要素1", "项目名称", "项目", "专业"],
        "要素2": ["要素2", "工作内容", "作业内容", "内容"],
        "要素3": ["要素3", "类别", "类别名称"],
        "要素4": ["要素4", "比例尺", "规格", "方法"],
        "要素5": ["要素5", "复杂程度", "等级"],
        "单位": ["单位", "计量单位"],
        PRICE_METRIC: ["【经验数】单价", "【经验数】基价", "经验单价", "经验基价", "基价", "单价", "价格"],
        "工程量": ["工程量", "数量"],
        PHYSICAL_METRIC: ["【经验数】实物工作费调整系数", "经验实物工作费调整系数", "实物工作费调整系数"],
        TECHNICAL_METRIC: ["【经验数】技术工作费调整系数", "经验技术工作费调整系数", "技术工作费调整系数"],
        "其他参数1": ["其他参数1"],
        "其他参数2": ["其他参数2"],
        "原表备注1": ["原表备注1", "备注1", "备注", "批注", "说明"],
        "原表备注2": ["原表备注2", "备注2"],
        "原表备注3": ["原表备注3", "备注3"],
    }


def _experience_field_preferences_payload(preferences: dict[str, list[str]] | None = None) -> dict[str, object]:
    defaults = _default_experience_field_preferences()
    return {
        "fields": EXPERIENCE_MAPPING_FIELDS,
        "defaults": defaults,
        "preferences": preferences if preferences is not None else _load_experience_field_preferences(),
        "file_path": str(DEFAULT_EXPERIENCE_FIELD_PREFERENCES_PATH),
    }


def _default_experience_warning_settings() -> dict[str, float | bool | str]:
    return {
        "low_risk_warning_ratio": DEFAULT_LOW_RISK_WARNING_PERCENT,
        "high_risk_warning_ratio": DEFAULT_HIGH_RISK_WARNING_PERCENT,
        "only_check_rows_with_value": True,
        "value_filter_field": DEFAULT_WARNING_FILTER_FIELD,
    }


def _experience_warning_settings_payload(settings: dict[str, float | bool | str] | None = None) -> dict[str, object]:
    defaults = _default_experience_warning_settings()
    return {
        "defaults": defaults,
        "settings": settings if settings is not None else _load_experience_warning_settings(),
        "filter_fields": list(WARNING_FILTER_FIELDS),
        "file_path": str(DEFAULT_EXPERIENCE_WARNING_SETTINGS_PATH),
    }


def _default_workload_field_preferences() -> dict[str, list[str]]:
    defaults = default_workload_field_preferences()
    source = _project_default_section("workloadCapture").get("source", {})
    raw_preferences = source.get("fieldPreferences", {}) if isinstance(source, dict) else {}
    if not isinstance(raw_preferences, dict):
        return defaults
    return {**defaults, **_sanitize_workload_field_preferences(raw_preferences)}


def _default_workload_target_field_preferences() -> dict[str, list[str]]:
    defaults = default_workload_target_field_preferences()
    target = _project_default_section("workloadCapture").get("target", {})
    raw_preferences = target.get("fieldPreferences", {}) if isinstance(target, dict) else {}
    if not isinstance(raw_preferences, dict):
        return defaults
    return {**defaults, **_sanitize_workload_target_field_preferences(raw_preferences)}


def _workload_field_preferences_payload(
    preferences: dict[str, list[str]] | None = None,
    adjacent_fallback_enabled: bool | None = None,
    element_sequence_enabled: bool | None = None,
) -> dict[str, object]:
    defaults = _default_workload_field_preferences()
    return {
        "fields": WORKLOAD_FIELD_PREFERENCE_FIELDS,
        "defaults": defaults,
        "preferences": preferences if preferences is not None else _load_workload_field_preferences(),
        "adjacent_fallback_enabled": (
            _load_workload_adjacent_fallback_enabled()
            if adjacent_fallback_enabled is None
            else adjacent_fallback_enabled
        ),
        "element_sequence_enabled": (
            _load_workload_element_sequence_enabled()
            if element_sequence_enabled is None
            else element_sequence_enabled
        ),
        "file_path": str(PROJECT_DEFAULT_SETTINGS_PATH),
    }


def _workload_target_field_preferences_payload(
    preferences: dict[str, list[str]] | None = None,
    adjacent_fallback_enabled: bool | None = None,
    element_sequence_enabled: bool | None = None,
) -> dict[str, object]:
    defaults = _default_workload_target_field_preferences()
    return {
        "fields": WORKLOAD_TARGET_FIELD_PREFERENCE_FIELDS,
        "defaults": defaults,
        "preferences": preferences if preferences is not None else _load_workload_target_field_preferences(),
        "adjacent_fallback_enabled": (
            _load_workload_target_adjacent_fallback_enabled()
            if adjacent_fallback_enabled is None
            else adjacent_fallback_enabled
        ),
        "element_sequence_enabled": (
            _load_workload_target_element_sequence_enabled()
            if element_sequence_enabled is None
            else element_sequence_enabled
        ),
        "file_path": str(PROJECT_DEFAULT_SETTINGS_PATH),
    }


def _load_input_field_preferences() -> dict[str, list[str]]:
    return {}


def _load_ui_preferences() -> dict[str, object]:
    defaults = _default_ui_preferences()
    if not DEFAULT_UI_PREFERENCES_PATH.exists():
        return defaults
    try:
        raw = json.loads(DEFAULT_UI_PREFERENCES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if isinstance(raw, dict) and isinstance(raw.get("preferences"), dict):
        raw = raw["preferences"]
    if not isinstance(raw, dict):
        return defaults
    return _sanitize_ui_preferences(raw)


def _load_preview_column_preferences() -> dict[str, object]:
    return _default_preview_column_preferences()


def _load_experience_field_preferences() -> dict[str, list[str]]:
    defaults = _default_experience_field_preferences()
    if not DEFAULT_EXPERIENCE_FIELD_PREFERENCES_PATH.exists():
        return {}
    try:
        raw = json.loads(DEFAULT_EXPERIENCE_FIELD_PREFERENCES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, dict) and isinstance(raw.get("preferences"), dict):
        raw = raw["preferences"]
    if not isinstance(raw, dict):
        return {}
    return {
        field: aliases
        for field, aliases in _sanitize_experience_field_preferences(raw).items()
        if aliases != defaults.get(field, [])
    }


def _load_workload_field_preferences() -> dict[str, list[str]]:
    return _default_workload_field_preferences()


def _load_workload_adjacent_fallback_enabled() -> bool:
    section = _project_default_section("workloadCapture").get("source", {})
    if isinstance(section, dict):
        return _sanitize_bool_setting(section.get("adjacentFallbackEnabled"), True)
    return True


def _load_workload_element_sequence_enabled() -> bool:
    section = _project_default_section("workloadCapture").get("source", {})
    if isinstance(section, dict):
        return _sanitize_bool_setting(section.get("elementSequenceEnabled"), True)
    return True


def _load_workload_target_field_preferences() -> dict[str, list[str]]:
    return _default_workload_target_field_preferences()


def _load_workload_target_adjacent_fallback_enabled() -> bool:
    section = _project_default_section("workloadCapture").get("target", {})
    if isinstance(section, dict):
        return _sanitize_bool_setting(section.get("adjacentFallbackEnabled"), True)
    return True


def _load_workload_target_element_sequence_enabled() -> bool:
    section = _project_default_section("workloadCapture").get("target", {})
    if isinstance(section, dict):
        return _sanitize_bool_setting(section.get("elementSequenceEnabled"), False)
    return False


def _load_adjacent_fallback_enabled(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(raw, dict):
        return True
    return _sanitize_bool_setting(raw.get("adjacent_fallback_enabled"), True)


def _load_element_sequence_enabled(path: Path, default: bool) -> bool:
    if not path.exists():
        return default
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(raw, dict):
        return default
    return _sanitize_bool_setting(raw.get("element_sequence_enabled"), default)


def _load_experience_warning_settings() -> dict[str, float | bool | str]:
    defaults = _default_experience_warning_settings()
    if not DEFAULT_EXPERIENCE_WARNING_SETTINGS_PATH.exists():
        return defaults
    try:
        raw = json.loads(DEFAULT_EXPERIENCE_WARNING_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if isinstance(raw, dict) and isinstance(raw.get("settings"), dict):
        raw = raw["settings"]
    if not isinstance(raw, dict):
        return defaults
    return _sanitize_experience_warning_settings(raw)


def _save_input_field_preferences(preferences: dict[str, list[str]]) -> None:
    DEFAULT_INPUT_FIELD_PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "preferences": preferences,
    }
    DEFAULT_INPUT_FIELD_PREFERENCES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_ui_preferences(preferences: dict[str, object]) -> None:
    DEFAULT_UI_PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "preferences": preferences,
    }
    DEFAULT_UI_PREFERENCES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_preview_column_preferences(preferences: dict[str, object]) -> None:
    DEFAULT_PREVIEW_COLUMN_PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "preferences": preferences,
    }
    DEFAULT_PREVIEW_COLUMN_PREFERENCES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_experience_field_preferences(preferences: dict[str, list[str]]) -> None:
    DEFAULT_EXPERIENCE_FIELD_PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "preferences": preferences,
    }
    DEFAULT_EXPERIENCE_FIELD_PREFERENCES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_workload_field_preferences(
    preferences: dict[str, list[str]],
    adjacent_fallback_enabled: bool = True,
    element_sequence_enabled: bool = True,
) -> None:
    DEFAULT_WORKLOAD_FIELD_PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "adjacent_fallback_enabled": adjacent_fallback_enabled,
        "element_sequence_enabled": element_sequence_enabled,
        "preferences": preferences,
    }
    DEFAULT_WORKLOAD_FIELD_PREFERENCES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_workload_target_field_preferences(
    preferences: dict[str, list[str]],
    adjacent_fallback_enabled: bool = True,
    element_sequence_enabled: bool = False,
) -> None:
    DEFAULT_WORKLOAD_TARGET_FIELD_PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "adjacent_fallback_enabled": adjacent_fallback_enabled,
        "element_sequence_enabled": element_sequence_enabled,
        "preferences": preferences,
    }
    DEFAULT_WORKLOAD_TARGET_FIELD_PREFERENCES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_experience_warning_settings(settings: dict[str, float | bool | str]) -> None:
    DEFAULT_EXPERIENCE_WARNING_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": settings,
    }
    DEFAULT_EXPERIENCE_WARNING_SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _sanitize_ui_preferences(raw_preferences: dict[object, object]) -> dict[str, object]:
    raw_styles = raw_preferences.get("styles", {})
    raw_text = raw_preferences.get("text", {})
    styles: dict[str, dict[str, float]] = {}
    text: dict[str, str] = {}

    if isinstance(raw_styles, dict):
        for raw_key, raw_values in raw_styles.items():
            key = _clean_ui_key(raw_key)
            if not key or not isinstance(raw_values, dict):
                continue
            values = _sanitize_ui_style_values(raw_values)
            if values:
                styles[key] = values

    if isinstance(raw_text, dict):
        for raw_key, raw_value in raw_text.items():
            key = _clean_ui_key(raw_key)
            if not key:
                continue
            value = str(raw_value).replace("\r", "").strip()
            if len(value) > 200:
                value = value[:200]
            text[key] = value

    return {
        "enabled": bool(raw_preferences.get("enabled", False)),
        "styles": styles,
        "text": text,
    }


def _sanitize_preview_column_preferences(
    raw_preferences: dict[object, object],
    fallback: dict[str, object] | None = None,
) -> dict[str, object]:
    defaults = fallback or _builtin_preview_column_preferences()
    raw_default_labels = raw_preferences.get("defaultLabels", defaults["defaultLabels"])
    raw_sheet_overrides = raw_preferences.get("sheetOverrides", {})
    raw_header_rows = raw_preferences.get("headerRows", {})
    raw_max_display_chars = raw_preferences.get("maxDisplayChars", defaults["maxDisplayChars"])
    raw_column_widths = raw_preferences.get("columnWidths", {})

    default_labels = _sanitize_text_list(raw_default_labels)
    if not default_labels:
        default_labels = list(defaults["defaultLabels"])

    sheet_overrides: dict[str, list[str]] = {}
    if isinstance(raw_sheet_overrides, dict):
        for raw_sheet_name, raw_labels in raw_sheet_overrides.items():
            sheet_name = str(raw_sheet_name or "").strip()
            labels = _sanitize_text_list(raw_labels)
            if sheet_name and labels:
                sheet_overrides[sheet_name] = labels

    header_rows: dict[str, int] = {}
    if isinstance(raw_header_rows, dict):
        for raw_sheet_name, raw_row in raw_header_rows.items():
            sheet_name = str(raw_sheet_name or "").strip()
            if not sheet_name:
                continue
            try:
                row_number = int(float(str(raw_row).strip()))
            except (TypeError, ValueError):
                continue
            if row_number >= 1:
                header_rows[sheet_name] = min(row_number, 999)

    try:
        max_display_chars = int(float(str(raw_max_display_chars).strip()))
    except (TypeError, ValueError):
        max_display_chars = DEFAULT_PREVIEW_CELL_MAX_DISPLAY_CHARS
    max_display_chars = max(4, min(40, max_display_chars))

    column_widths: dict[str, dict[str, int]] = {}
    if isinstance(raw_column_widths, dict):
        for raw_sheet_name, raw_widths in raw_column_widths.items():
            sheet_name = str(raw_sheet_name or "").strip()
            if not sheet_name or not isinstance(raw_widths, dict):
                continue
            widths: dict[str, int] = {}
            for raw_column_label, raw_width in raw_widths.items():
                column_label = str(raw_column_label or "").strip()
                if not column_label:
                    continue
                try:
                    width = int(round(float(str(raw_width).strip())))
                except (TypeError, ValueError):
                    continue
                widths[column_label] = max(MIN_PREVIEW_COLUMN_WIDTH_PX, min(MAX_PREVIEW_COLUMN_WIDTH_PX, width))
            if widths:
                column_widths[sheet_name] = widths

    return {
        "defaultLabels": default_labels,
        "sheetOverrides": sheet_overrides,
        "headerRows": header_rows,
        "maxDisplayChars": max_display_chars,
        "columnWidths": column_widths,
    }


def _sanitize_text_list(raw_values: object) -> list[str]:
    if not isinstance(raw_values, list):
        return []
    values: list[str] = []
    for raw_value in raw_values:
        value = str(raw_value or "").replace("\r", "").strip()
        if value and value not in values:
            values.append(value)
    return values


def _clean_ui_key(raw_key: object) -> str:
    key = str(raw_key).strip()
    if len(key) > 80:
        key = key[:80]
    return "".join(char for char in key if char.isalnum() or char in {"-", "_", "."})


def _sanitize_ui_style_values(raw_values: dict[object, object]) -> dict[str, float]:
    limits = {
        "paddingX": (0, 96),
        "paddingY": (0, 96),
        "fontSize": (10, 72),
        "radius": (0, 60),
        "gap": (0, 64),
        "marginTop": (-120, 120),
        "opacity": (20, 100),
    }
    sanitized: dict[str, float] = {}
    for key, raw_value in raw_values.items():
        name = str(key)
        if name not in limits:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        lower, upper = limits[name]
        value = max(lower, min(upper, value))
        sanitized[name] = round(value, 2)
    return sanitized


def _parse_json_form_object(raw_value: str | None, label: str) -> dict[object, object] | None:
    if raw_value is None or not str(raw_value).strip():
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{label}必须是 JSON 对象") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail=f"{label}必须是 JSON 对象")
    return parsed


def _parse_input_field_preferences_form(raw_value: str | None) -> dict[str, list[str]] | None:
    parsed = _parse_json_form_object(raw_value, "输入字段偏好")
    return None if parsed is None else _sanitize_input_field_preferences(parsed)


def _parse_workload_field_preferences_form(raw_value: str | None, role: str) -> dict[str, list[str]] | None:
    parsed = _parse_json_form_object(raw_value, "工作量字段偏好")
    if parsed is None:
        return None
    if role == "target":
        return _sanitize_workload_target_field_preferences(parsed)
    return _sanitize_workload_field_preferences(parsed)


def _sanitize_bool_setting(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "是", "开启"}:
            return True
        if normalized in {"false", "0", "no", "off", "否", "关闭"}:
            return False
    return bool(value)


def _sanitize_optional_bool_setting(value: object) -> bool | None:
    if value is None:
        return None
    return _sanitize_bool_setting(value, False)


def _sanitize_input_field_preferences(raw_preferences: dict[object, object]) -> dict[str, list[str]]:
    allowed = set(INPUT_FIELD_PREFERENCE_FIELDS)
    sanitized: dict[str, list[str]] = {}
    for key, raw_aliases in raw_preferences.items():
        field = str(key).strip()
        if field not in allowed:
            continue
        if isinstance(raw_aliases, str):
            aliases = raw_aliases.replace(",", "\n").replace("，", "\n").splitlines()
        elif isinstance(raw_aliases, list):
            aliases = [str(alias) for alias in raw_aliases]
        else:
            aliases = []
        cleaned: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            value = str(alias).strip()
            if not value or value in seen:
                continue
            cleaned.append(value)
            seen.add(value)
        if cleaned:
            sanitized[field] = cleaned
    return sanitized


def _sanitize_experience_warning_settings(raw_settings: dict[object, object]) -> dict[str, float | bool | str]:
    defaults = _default_experience_warning_settings()
    low_raw = raw_settings.get("low_risk_warning_ratio", defaults["low_risk_warning_ratio"])
    high_raw = raw_settings.get("high_risk_warning_ratio", defaults["high_risk_warning_ratio"])
    only_check_rows_with_value = bool(raw_settings.get("only_check_rows_with_value", defaults["only_check_rows_with_value"]))
    value_filter_field = _parse_warning_filter_field(
        str(raw_settings.get("value_filter_field", defaults["value_filter_field"]) or defaults["value_filter_field"])
    )
    try:
        low = float(low_raw)
        high = float(high_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="预警比率必须是数字") from exc
    if low < 0 or high < 0:
        raise HTTPException(status_code=400, detail="预警比率必须大于等于 0")
    if high < low:
        raise HTTPException(status_code=400, detail="高风险预警比率必须大于等于低风险预警比率")
    return {
        "low_risk_warning_ratio": round(low, 6),
        "high_risk_warning_ratio": round(high, 6),
        "only_check_rows_with_value": only_check_rows_with_value,
        "value_filter_field": value_filter_field,
    }


def _sanitize_experience_field_preferences(raw_preferences: dict[object, object]) -> dict[str, list[str]]:
    allowed = set(EXPERIENCE_MAPPING_FIELDS)
    sanitized: dict[str, list[str]] = {}
    for key, raw_aliases in raw_preferences.items():
        field = str(key).strip()
        if field not in allowed:
            continue
        if isinstance(raw_aliases, str):
            aliases = raw_aliases.replace(",", "\n").replace("，", "\n").splitlines()
        elif isinstance(raw_aliases, list):
            aliases = [str(alias) for alias in raw_aliases]
        else:
            aliases = []
        cleaned: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            value = str(alias).strip()
            if not value or value in seen:
                continue
            cleaned.append(value)
            seen.add(value)
        if cleaned:
            sanitized[field] = cleaned
    return sanitized


def _sanitize_workload_field_preferences(raw_preferences: dict[object, object]) -> dict[str, list[str]]:
    allowed = set(WORKLOAD_FIELD_PREFERENCE_FIELDS)
    sanitized: dict[str, list[str]] = {}
    for key, raw_aliases in raw_preferences.items():
        field = str(key).strip()
        if field not in allowed:
            continue
        if isinstance(raw_aliases, str):
            aliases = raw_aliases.replace(",", "\n").replace("，", "\n").splitlines()
        elif isinstance(raw_aliases, list):
            aliases = [str(alias) for alias in raw_aliases]
        else:
            aliases = []
        cleaned: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            value = str(alias).strip()
            if not value or value in seen:
                continue
            cleaned.append(value)
            seen.add(value)
        if cleaned:
            sanitized[field] = cleaned
    return sanitized


def _sanitize_workload_target_field_preferences(raw_preferences: dict[object, object]) -> dict[str, list[str]]:
    allowed = set(WORKLOAD_TARGET_FIELD_PREFERENCE_FIELDS)
    sanitized: dict[str, list[str]] = {}
    for key, raw_aliases in raw_preferences.items():
        field = str(key).strip()
        if field not in allowed:
            continue
        if isinstance(raw_aliases, str):
            aliases = raw_aliases.replace(",", "\n").replace("，", "\n").splitlines()
        elif isinstance(raw_aliases, list):
            aliases = [str(alias) for alias in raw_aliases]
        else:
            aliases = []
        cleaned: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            value = str(alias).strip()
            if not value or value in seen:
                continue
            cleaned.append(value)
            seen.add(value)
        if cleaned:
            sanitized[field] = cleaned
    return sanitized


def _find_experience_field_column(
    headers: list[str],
    field: str,
    preferences: dict[str, list[str]],
    defaults: dict[str, list[str]],
) -> str:
    preferred_aliases = preferences.get(field, [])
    default_aliases = defaults.get(field, [])
    for alias in preferred_aliases:
        found = _find_column_letter(headers, [alias])
        if found:
            return found
    for alias in preferred_aliases:
        if alias in default_aliases:
            continue
        found = _find_column_by_token(headers, alias)
        if found:
            return found
    found = _find_column_letter(headers, default_aliases)
    if found:
        return found
    return ""


def _find_preferred_input_column(
    headers: list[str],
    field: str,
    preferences: dict[str, list[str]],
    defaults: dict[str, list[str]],
) -> str:
    exact_field = _find_column_letter(headers, [field])
    if exact_field:
        return exact_field
    preferred_aliases = preferences.get(field, [])
    default_aliases = defaults.get(field, [])
    for alias in preferred_aliases:
        found = _find_column_letter(headers, [alias])
        if found:
            return found
    for alias in preferred_aliases:
        if alias in default_aliases:
            continue
        found = _find_column_by_token(headers, alias)
        if found:
            return found
    found = _find_column_letter(headers, default_aliases)
    if found:
        return found
    for alias in default_aliases:
        found = _find_column_by_token(headers, alias)
        if found:
            return found
    return ""


def _find_experience_metric_column(headers: list[str], metric: str, preferred_aliases: list[str] | None = None) -> str:
    compact_metric = metric.replace(" ", "")
    preferred_tokens = {
        PRICE_METRIC: ["【经验数】单价", "【经验数】基价", "经验单价", "经验基价", "基价", "单价", "价格"],
        PHYSICAL_METRIC: ["【经验数】实物工作费调整系数", "经验实物工作费调整系数", "实物工作费调整系数"],
        TECHNICAL_METRIC: ["【经验数】技术工作费调整系数", "经验技术工作费调整系数", "技术工作费调整系数"],
    }
    tokens = [*(preferred_aliases or []), *preferred_tokens.get(metric, [compact_metric])]
    for token in tokens:
        found = _find_column_by_token(headers, token)
        if found:
            return found
    return ""


def _find_column_letter(headers: list[str], names: list[str]) -> str:
    for index, header in enumerate(headers, start=1):
        if header in names:
            return get_column_letter(index)
    return ""


def _find_column_by_token(headers: list[str], token: str) -> str:
    compact_token = token.replace(" ", "")
    for index, header in enumerate(headers, start=1):
        if compact_token in header.replace(" ", ""):
            return get_column_letter(index)
    return ""


def _parse_column_mapping(raw_mapping: str | None) -> dict[str, str] | None:
    if not raw_mapping:
        return None
    try:
        payload = json.loads(raw_mapping)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="列映射不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="列映射必须是对象")
    return {str(key): str(value).strip() for key, value in payload.items() if value is not None}


def _parse_sheet_configs(raw_configs: str | None) -> list[dict[str, object]] | None:
    if not raw_configs:
        return None
    try:
        payload = json.loads(raw_configs)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="sheet 配置不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="sheet 配置必须是数组")
    configs: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="sheet 配置项必须是对象")
        column_mapping = item.get("column_mapping")
        if column_mapping is not None and not isinstance(column_mapping, dict):
            raise HTTPException(status_code=400, detail="sheet 列映射必须是对象")
        config = {
            "sheet_name": str(item.get("sheet_name", "")).strip(),
            "enabled": bool(item.get("enabled", True)),
            "header_row": int(item.get("header_row") or 1),
            "column_mapping": {
                str(key): str(value).strip()
                for key, value in (column_mapping or {}).items()
                if value is not None
            },
            "output_match_report": bool(item.get("output_match_report", True)),
            "merge_vertical_cells": bool(item.get("merge_vertical_cells", True)),
            "merge_horizontal_cells": bool(item.get("merge_horizontal_cells", True)),
        }
        if "only_match_rows_with_value" in item:
            config["only_match_rows_with_value"] = bool(item.get("only_match_rows_with_value"))
        if "match_value_filter_field" in item:
            config["match_value_filter_field"] = _parse_warning_filter_field(
                str(item.get("match_value_filter_field") or DEFAULT_WARNING_FILTER_FIELD)
            )
        configs.append(config)
    return configs


def _parse_experience_sheet_configs(raw_configs: str | None) -> list[dict[str, object]] | None:
    if not raw_configs:
        return None
    try:
        payload = json.loads(raw_configs)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="经验池 sheet 配置不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="经验池 sheet 配置必须是数组")
    allowed = set(EXPERIENCE_MAPPING_FIELDS)
    configs: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="经验池 sheet 配置项必须是对象")
        column_mapping = item.get("column_mapping")
        if column_mapping is not None and not isinstance(column_mapping, dict):
            raise HTTPException(status_code=400, detail="经验池列映射必须是对象")
        configs.append(
            {
                "sheet_name": str(item.get("sheet_name", "")).strip(),
                "enabled": bool(item.get("enabled", True)),
                "header_row": int(item.get("header_row") or 1),
                "column_mapping": {
                    str(key): str(value).strip()
                    for key, value in (column_mapping or {}).items()
                    if str(key) in allowed and value is not None
                },
            }
        )
    return configs


def _parse_selected_experience_fields(raw_fields: str | None) -> list[str]:
    if not raw_fields:
        return DEFAULT_SELECTED_EXPERIENCE_FIELDS
    try:
        payload = json.loads(raw_fields)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="经验字段不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="经验字段必须是数组")
    allowed = set(DEFAULT_SELECTED_EXPERIENCE_FIELDS)
    selected = [str(item) for item in payload if str(item) in allowed]
    if not selected:
        raise HTTPException(status_code=400, detail="至少选择一种经验字段")
    return selected


def _parse_experience_filter_field(raw_field: str | None) -> str:
    field = str(raw_field or "工程量").strip() or "工程量"
    if field not in EXPERIENCE_MAPPING_FIELDS:
        raise HTTPException(status_code=400, detail=f"经验池导入过滤字段不支持：{field}")
    return field


def _parse_warning_filter_field(raw_field: str | None) -> str:
    field = str(raw_field or DEFAULT_WARNING_FILTER_FIELD).strip() or DEFAULT_WARNING_FILTER_FIELD
    if field not in WARNING_FILTER_FIELDS:
        raise HTTPException(status_code=400, detail=f"预警过滤字段不支持：{field}")
    return field


def _parse_workload_selected_fields(raw_fields: str | None) -> list[str]:
    if not raw_fields:
        return DEFAULT_SELECTED_WORKLOAD_FIELDS
    try:
        payload = json.loads(raw_fields)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="工作量抓取字段不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="工作量抓取字段必须是数组")
    allowed = set(DEFAULT_SELECTED_WORKLOAD_FIELDS)
    selected = [str(item) for item in payload if str(item) in allowed]
    if not selected:
        raise HTTPException(status_code=400, detail="至少选择一个工作量抓取字段")
    return selected


def _parse_workload_filter_field(raw_field: str | None) -> str:
    field = str(raw_field or DEFAULT_WORKLOAD_FILTER_FIELD).strip() or DEFAULT_WORKLOAD_FILTER_FIELD
    if field not in SOURCE_MAPPING_FIELDS:
        raise HTTPException(status_code=400, detail=f"工作量抓取过滤字段不支持：{field}")
    return field


def _parse_workload_write_mode(raw_mode: str | None) -> str:
    mode = str(raw_mode or WRITE_MODE_CONSERVATIVE).strip().lower()
    if mode in {WRITE_MODE_CONSERVATIVE, "safe", "保守", "保守模式"}:
        return WRITE_MODE_CONSERVATIVE
    if mode in {WRITE_MODE_OVERWRITE, "cover", "覆盖", "覆盖模式"}:
        return WRITE_MODE_OVERWRITE
    raise HTTPException(status_code=400, detail="工作量抓取写入模式只能是保守模式或覆盖模式")


def _parse_workload_sheet_configs(raw_configs: str | None, role: str) -> list[dict[str, object]] | None:
    if not raw_configs:
        return None
    try:
        payload = json.loads(raw_configs)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="工作量抓取 sheet 配置不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="工作量抓取 sheet 配置必须是数组")
    allowed = set(SOURCE_MAPPING_FIELDS if role == "source" else TARGET_MAPPING_FIELDS)
    configs: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="工作量抓取 sheet 配置项必须是对象")
        column_mapping = item.get("column_mapping")
        if column_mapping is not None and not isinstance(column_mapping, dict):
            raise HTTPException(status_code=400, detail="工作量抓取列映射必须是对象")
        configs.append(
            {
                "sheet_name": str(item.get("sheet_name", "")).strip(),
                "enabled": bool(item.get("enabled", True)),
                "header_row": int(item.get("header_row") or 1),
                "column_mapping": {
                    str(key): str(value).strip()
                    for key, value in (column_mapping or {}).items()
                    if str(key) in allowed and value is not None
                },
            }
        )
    return configs


def _resolve_experience_pool_path() -> Path:
    if DEFAULT_EXPERIENCE_POOL_PATH.exists():
        return DEFAULT_EXPERIENCE_POOL_PATH
    if LEGACY_EXPERIENCE_POOL_PATH.exists():
        return LEGACY_EXPERIENCE_POOL_PATH
    return DEFAULT_EXPERIENCE_POOL_PATH


def _resolve_frontend_static_dir() -> Path | None:
    configured = os.getenv("GUANKAN_FRONTEND_DIR", "").strip()
    candidates = [
        Path(configured) if configured else None,
        PROJECT_ROOT / "web",
        PROJECT_ROOT / "frontend" / "dist",
    ]
    for candidate in candidates:
        if candidate and (candidate / "index.html").exists():
            return candidate
    return None


def _mount_frontend_static_files() -> None:
    static_dir = _resolve_frontend_static_dir()
    if static_dir is None:
        return
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")


_mount_frontend_static_files()



