from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4

import httpx

from . import feishu_robot_settings
from .paths import PROJECT_DEFAULT_SETTINGS_PATH, PROJECT_ROOT


RUNTIME_ROOT = PROJECT_ROOT / "Codex-Temp" / "runtime" / "feishu-bot"
SETTINGS_PATH = feishu_robot_settings.SETTINGS_PATH
DB_PATH = RUNTIME_ROOT / "tasks.sqlite3"
TASKS_ROOT = RUNTIME_ROOT / "tasks"
CONTROL_PATH = RUNTIME_ROOT / "control.json"
PID_PATH = RUNTIME_ROOT / "runner.pid"
CONSOLE_EVENTS_PATH = RUNTIME_ROOT / "console-events.jsonl"
RUNNER_OUT_LOG_PATH = RUNTIME_ROOT / "logs" / "runner.out.log"
RUNNER_ERR_LOG_PATH = RUNTIME_ROOT / "logs" / "runner.err.log"
CONSOLE_EVENT_MAX_BYTES = 2 * 1024 * 1024
CONSOLE_MESSAGE_MAX_CHARS = 20000
CONSOLE_EVENT_LEVELS = {"info", "success", "warning", "error"}
CONSOLE_EVENT_CATEGORIES = {"process", "config", "connection", "message", "knowledge", "task"}
_CONSOLE_EVENT_LOCK = threading.Lock()
REQUIRED_MAPPING_FIELDS = ("要素1", "单位", "输出-价格列")
TERMINAL_STATES = {"completed", "needs_manual", "failed"}
ACTIVE_STATES = {"downloading", "inspecting", "matching", "risk", "report", "uploading"}
DEFAULT_PROFILE_ID = "default"
DEFAULT_FEISHU_DOMAIN = "https://open.feishu.cn"
ALLOWED_FEISHU_DOMAINS = {"open.feishu.cn", "open.weact.pipechina.com.cn"}
ACK_REACTION_EMOJI = "Get"
MESSAGE_MAX_AGE_SECONDS = 5 * 60
UPLOAD_WINDOW_MINUTES = 1
UPLOAD_COMMANDS = {"@上传", "@上传文件"}
GREETING_COMMANDS = {"你好"}
GROUP_MEMBER_COMMANDS = {"群里有几个人", "群成员", "都有谁"}
HELP_COMMANDS = {"帮助", "指令"}
TASK_LIST_COMMANDS = {"任务", "最近任务"}
HIGH_RISK_COMMANDS = {"高风险"}
TASK_DETAIL_COMMAND_PATTERN = re.compile(
    r"^(进度|风险|结果)\s+(FS-\d{8}-\d{6}-[A-Z0-9]{6})$",
    re.IGNORECASE,
)
TASK_STATUS_LABELS = {
    "queued": "排队中",
    "downloading": "正在下载文件",
    "inspecting": "正在识别表格与字段",
    "matching": "正在批量匹配",
    "risk": "正在进行风险识别",
    "report": "正在生成成果",
    "uploading": "正在回传成果",
    "completed": "已完成",
    "needs_manual": "需要人工处理",
    "retryable_failed": "等待自动重试",
    "failed": "处理失败",
}
TASK_COMMAND_HELP = (
    "可用指令：\n"
    "• 任务 / 最近任务：查看当前会话最近 5 个任务；\n"
    "• 进度 FS-任务编号：查看任务当前阶段；\n"
    "• 风险 FS-任务编号：查看任务风险统计；\n"
    "• 高风险：查看当前会话最近的高风险任务；\n"
    "• 结果 FS-任务编号：重新发送已完成任务的 Excel、Word 和完成卡片；\n"
    "• @上传 / @上传文件：开启 1 分钟文件接收窗口；\n"
    "• @知识库：问题：查询本地规则、知识库和依据来源；\n"
    "• 群成员：在群聊中查询真实人数和名单。\n\n"
    "群聊请先 @当前机器人；单聊可直接发送。任务信息只在原任务所在会话内可查询。"
)
BOT_INTRODUCTION = (
    "你好，我是造价智算机器人，是造价智算在飞书和 WeAct 中的协同助手。\n\n"
    "我可以提供五类功能：\n"
    "1. Excel 自动处理：接收标准 .xlsx，按顺序完成匹配、风险识别，并返回 Excel 和 Word 成果；\n"
    "2. 知识库问答：检索本地规则、知识库和依据来源后回答专业问题；\n"
    "3. 群成员查询：在群聊中询问“群里有几个人”“群成员”或“都有谁”，返回真实人数和名单；\n"
    "4. 任务查询与成果重发：查询当前会话的任务进度、风险和历史成果；\n"
    "5. 普通智能问答：其他文字问题由大模型提供辅助回答。\n\n"
    "使用方法：\n"
    "• 群聊：先 @机器人，再发送“@上传”“@知识库：问题”“任务”“帮助”或其他问题；\n"
    "• 单聊：直接发送上传、知识库、问候、任务或普通问题；群成员请到目标群中查询；\n"
    "• 上传时请在收到提示后的 1 分钟内发送一个 .xlsx 文件。\n\n"
    "说明：价格和系数仍由造价智算规则与知识库处理，大模型不会直接裁决最终结果。"
)


def normalize_feishu_domain(value: object) -> str:
    domain = str(value or DEFAULT_FEISHU_DOMAIN).strip().rstrip("/")
    try:
        parsed = urlparse(domain)
    except ValueError:
        return DEFAULT_FEISHU_DOMAIN
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_FEISHU_DOMAINS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return DEFAULT_FEISHU_DOMAIN
    return domain


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sanitize_console_text(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(
        r"(?i)(app[_ -]?secret|tenant[_ -]?access[_ -]?token|access[_ -]?token|authorization|ticket|access[_ -]?key|file[_ -]?key)\s*[:=]\s*[^\s&]+",
        r"\1=***",
        text,
    )
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+", "Bearer ***", text)
    text = re.sub(r"(wss://[A-Za-z0-9.-]+)(?:/[^\s]*)?", r"\1", text)
    text = re.sub(
        r"(?i)([?&](?:ticket|access_key|access_token|tenant_access_token)=)[^&\s]+",
        r"\1***",
        text,
    )
    return text[:CONSOLE_MESSAGE_MAX_CHARS]


def append_runtime_event(
    category: str,
    message: str,
    *,
    level: str = "info",
    task_id: str = "",
    profile_id: str = "",
    path: Path | None = None,
) -> None:
    target = Path(path or CONSOLE_EVENTS_PATH)
    normalized_level = level if level in CONSOLE_EVENT_LEVELS else "info"
    normalized_category = category if category in CONSOLE_EVENT_CATEGORIES else "process"
    payload = {
        "timestamp": utc_now(),
        "level": normalized_level,
        "category": normalized_category,
        "message": _sanitize_console_text(message),
        "task_id": _sanitize_console_text(task_id),
        "profile_id": _sanitize_console_text(profile_id),
        "source": "runtime",
    }
    if not payload["message"]:
        return
    try:
        with _CONSOLE_EVENT_LOCK:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.stat().st_size >= CONSOLE_EVENT_MAX_BYTES:
                rotated = target.with_suffix(f"{target.suffix}.1")
                rotated.unlink(missing_ok=True)
                target.replace(rotated)
            with target.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return


def _runner_timestamp(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        local_timezone = datetime.now().astimezone().tzinfo
        return parsed.replace(tzinfo=local_timezone).astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return utc_now()


def _read_runner_connection_events(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - 512 * 1024))
            text = stream.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        timestamp_match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d+)?\]", line)
        timestamp = _runner_timestamp(timestamp_match.group(1)) if timestamp_match else utc_now()
        host_match = re.search(r"wss://([^\s/?]+)", line)
        host = _sanitize_console_text(host_match.group(1) if host_match else "")
        level = "info"
        message = ""
        if "connected to wss://" in line and "disconnected" not in line:
            level = "success"
            message = f"长连接已建立：{host or '飞书消息节点'}"
        elif "disconnected to wss://" in line:
            level = "warning"
            message = f"长连接已断开：{host or '飞书消息节点'}"
        elif "trying to reconnect" in line:
            level = "warning"
            retry_match = re.search(r"trying to reconnect for the ([^\s]+) time", line)
            message = f"正在自动重连{f'（{retry_match.group(1)}）' if retry_match else ''}"
        elif "receive message loop exit" in line:
            level = "warning"
            message = "消息接收循环中断，等待自动重连"
        elif "connect failed" in line:
            level = "error"
            code_match = re.search(r"err:\s*([0-9-]+)", line)
            message = f"长连接建立失败{f'（错误码 {code_match.group(1)}）' if code_match else ''}"
        if message:
            events.append({
                "timestamp": timestamp,
                "level": level,
                "category": "connection",
                "message": message,
                "task_id": "",
                "profile_id": "",
                "source": "sdk",
            })
    return events


def _read_runtime_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for target in (path.with_suffix(f"{path.suffix}.1"), path):
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines[-1000:]:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            message = _sanitize_console_text(raw.get("message"))
            if not message:
                continue
            events.append({
                "timestamp": str(raw.get("timestamp") or utc_now()),
                "level": str(raw.get("level") or "info") if str(raw.get("level") or "info") in CONSOLE_EVENT_LEVELS else "info",
                "category": str(raw.get("category") or "process") if str(raw.get("category") or "process") in CONSOLE_EVENT_CATEGORIES else "process",
                "message": message,
                "task_id": _sanitize_console_text(raw.get("task_id")),
                "profile_id": _sanitize_console_text(raw.get("profile_id")),
                "source": "runtime",
            })
    return events


def load_bot_defaults() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "enabled": False,
        "concurrency": 1,
        "retentionDays": 30,
        "allowedExtensions": [".xlsx"],
        "maxFileSizeMb": 50,
        "apiBaseUrl": "http://127.0.0.1:8000",
        "expectedProfiles": {},
        "enableLlmRiskNarrative": True,
        "retryCount": 2,
        "retryDelaySeconds": 2,
    }
    api_base_url_override = str(os.getenv("FEISHU_APP_BOT_API_BASE_URL") or "").strip()
    try:
        raw = json.loads(PROJECT_DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        if api_base_url_override:
            defaults["apiBaseUrl"] = api_base_url_override
        return defaults
    section = raw.get("feishuAppBot", {}) if isinstance(raw, dict) else {}
    if isinstance(section, dict):
        for key in defaults:
            if key in section:
                defaults[key] = section[key]
    if api_base_url_override:
        defaults["apiBaseUrl"] = api_base_url_override
    defaults["concurrency"] = 1
    return defaults


def load_completion_card_app_url() -> str:
    value = str(feishu_robot_settings.load_section("webhook").get("app_url") or "").strip()
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _read_credential_store() -> dict[str, Any]:
    if SETTINGS_PATH == feishu_robot_settings.SETTINGS_PATH:
        raw = feishu_robot_settings.load_section("app_bot")
    else:
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"active_profile": "", "profiles": {}}
    if not isinstance(raw, dict):
        return {"active_profile": "", "profiles": {}}

    profiles: dict[str, dict[str, str]] = {}
    raw_profiles = raw.get("profiles")
    if isinstance(raw_profiles, dict):
        for profile_id, value in raw_profiles.items():
            if not isinstance(value, dict):
                continue
            profile_key = str(profile_id or "").strip()
            app_id = str(value.get("app_id") or "").strip()
            app_secret = str(value.get("app_secret") or "").strip()
            if profile_key and app_id and app_secret:
                profiles[profile_key] = {
                    "label": str(value.get("label") or profile_key).strip() or profile_key,
                    "app_id": app_id,
                    "app_secret": app_secret,
                    "domain": normalize_feishu_domain(value.get("domain")),
                }

    # Backward compatibility for the original single-profile format.
    if not profiles:
        app_id = str(raw.get("app_id") or "").strip()
        app_secret = str(raw.get("app_secret") or "").strip()
        if app_id and app_secret:
            profiles[DEFAULT_PROFILE_ID] = {
                "label": "默认机器人（普通飞书）",
                "app_id": app_id,
                "app_secret": app_secret,
                "domain": normalize_feishu_domain(raw.get("domain")),
            }

    active_profile = str(raw.get("active_profile") or "").strip()
    if active_profile not in profiles:
        active_profile = next(iter(profiles), "")
    return {"active_profile": active_profile, "profiles": profiles}


def load_credentials(profile_id: str | None = None) -> dict[str, str]:
    store = _read_credential_store()
    selected_profile = str(profile_id or store.get("active_profile") or "").strip()
    profiles = store.get("profiles") if isinstance(store.get("profiles"), dict) else {}
    selected = profiles.get(selected_profile) if isinstance(profiles, dict) else None
    if not isinstance(selected, dict):
        return {}
    return {
        "profile_id": selected_profile,
        "app_id": str(selected.get("app_id") or "").strip(),
        "app_secret": str(selected.get("app_secret") or "").strip(),
        "domain": normalize_feishu_domain(selected.get("domain")),
    }


def credential_configuration_issue(
    profile_id: str | None = None,
    credentials: dict[str, str] | None = None,
) -> str:
    selected_profile = str(profile_id or active_profile_id() or "").strip()
    expected_profiles = load_bot_defaults().get("expectedProfiles")
    if not selected_profile or not isinstance(expected_profiles, dict) or not expected_profiles:
        return ""
    expected = expected_profiles.get(selected_profile)
    if not isinstance(expected, dict):
        return f"当前机器人配置未在项目默认设置中登记：{selected_profile}"
    selected = credentials if credentials is not None else load_credentials(selected_profile)
    actual_app_id = str(selected.get("app_id") or "").strip()
    expected_app_id = str(expected.get("appId") or "").strip()
    if expected_app_id and actual_app_id and actual_app_id != expected_app_id:
        return f"当前机器人 App ID 与项目登记不一致，{selected_profile} 应使用 {expected_app_id}"
    actual_domain = normalize_feishu_domain(selected.get("domain"))
    expected_domain_raw = str(expected.get("domain") or "").strip()
    expected_domain = normalize_feishu_domain(expected_domain_raw)
    if expected_domain_raw and actual_domain != expected_domain:
        return f"当前机器人域名与项目登记不一致，{selected_profile} 应使用 {expected_domain}"
    return ""


def credential_profiles() -> list[dict[str, Any]]:
    store = _read_credential_store()
    profiles = store.get("profiles") if isinstance(store.get("profiles"), dict) else {}
    return [
        {
            "profile_id": profile_id,
            "label": str(value.get("label") or profile_id),
            "app_id_suffix": str(value.get("app_id") or "")[-4:],
            "domain_host": urlparse(normalize_feishu_domain(value.get("domain"))).hostname or "",
            "configuration_ok": not bool(credential_configuration_issue(profile_id, value)),
        }
        for profile_id, value in profiles.items()
        if isinstance(value, dict)
    ]


def active_profile_id() -> str:
    return str(_read_credential_store().get("active_profile") or "").strip()


def save_active_profile(profile_id: str) -> None:
    profile_id = str(profile_id or "").strip()
    store = _read_credential_store()
    profiles = store.get("profiles") if isinstance(store.get("profiles"), dict) else {}
    if profile_id not in profiles:
        raise ValueError("未找到指定的飞书机器人配置")
    payload = {
        "active_profile": profile_id,
        "profiles": profiles,
    }
    if SETTINGS_PATH == feishu_robot_settings.SETTINGS_PATH:
        feishu_robot_settings.save_section("app_bot", payload)
    else:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_PATH.with_suffix(f"{SETTINGS_PATH.suffix}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(SETTINGS_PATH)
    selected = profiles.get(profile_id) if isinstance(profiles, dict) else {}
    label = str(selected.get("label") or profile_id) if isinstance(selected, dict) else profile_id
    append_runtime_event("config", f"已切换第二层机器人：{label}", profile_id=profile_id)


def is_bot_enabled() -> bool:
    try:
        raw = json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return bool(load_bot_defaults().get("enabled"))
    return bool(raw.get("enabled")) if isinstance(raw, dict) else bool(load_bot_defaults().get("enabled"))


def save_bot_enabled(enabled: bool) -> None:
    CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTROL_PATH.write_text(json.dumps({"enabled": bool(enabled)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    append_runtime_event("config", "已启用第二层机器人接收" if enabled else "已关闭第二层机器人接收")


def bot_process_running() -> bool:
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        if os.name == "nt":
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def start_bot_process() -> bool:
    if not is_bot_enabled() or bot_process_running():
        return bot_process_running()
    credentials = load_credentials()
    if not credentials.get("app_id") or not credentials.get("app_secret"):
        return False
    configuration_issue = credential_configuration_issue(credentials=credentials)
    if configuration_issue:
        append_runtime_event(
            "config",
            configuration_issue,
            level="error",
            profile_id=str(credentials.get("profile_id") or ""),
        )
        return False
    runner = PROJECT_ROOT / "backend" / "feishu_bot_runner.py"
    log_dir = RUNTIME_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (log_dir / "runner.out.log").open("a", encoding="utf-8") as stdout, (log_dir / "runner.err.log").open("a", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            [sys.executable, str(runner)], cwd=PROJECT_ROOT,
            stdout=stdout, stderr=stderr, creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(process.pid), encoding="utf-8")
    append_runtime_event(
        "process",
        "第二层机器人子进程已启动，正在建立长连接",
        profile_id=str(credentials.get("profile_id") or ""),
    )
    return True


def wait_for_bot_process_exit(timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while bot_process_running() and time.monotonic() < deadline:
        time.sleep(0.1)
    return not bot_process_running()


def bot_status(db_path: Path | None = None) -> dict[str, Any]:
    defaults = load_bot_defaults()
    credentials = load_credentials()
    store = TaskStore(db_path or DB_PATH)
    counts = store.counts()
    current = store.current_task()
    configuration_issue = credential_configuration_issue(credentials=credentials)
    return {
        "enabled": is_bot_enabled(),
        "configured": bool(credentials.get("app_id") and credentials.get("app_secret") and not configuration_issue),
        "profile_consistent": not bool(configuration_issue),
        "configuration_error": configuration_issue,
        "active_profile": active_profile_id(),
        "profiles": credential_profiles(),
        "running": bot_process_running(),
        "connection_mode": "local_long_connection",
        "concurrency": 1,
        "retention_days": int(defaults.get("retentionDays") or 30),
        "counts": counts,
        "current_task": public_task(current) if current else None,
        "recent_tasks": [public_task(task) for task in store.list_tasks(limit=30)],
    }


def public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: task.get(key)
        for key in (
            "task_id", "file_name", "status", "stage", "error", "created_at",
            "updated_at", "completed_at", "retry_count", "risk_total", "risk_high",
        )
    }


class TaskStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    message_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    file_key TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    backend_job_id TEXT NOT NULL DEFAULT '',
                    output_excel TEXT NOT NULL DEFAULT '',
                    output_report TEXT NOT NULL DEFAULT '',
                    risk_total INTEGER NOT NULL DEFAULT 0,
                    risk_high INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(message_id, file_key)
                );
                CREATE TABLE IF NOT EXISTS task_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending_uploads (
                    chat_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY(chat_id, sender_id)
                );
                CREATE TABLE IF NOT EXISTS knowledge_events (
                    event_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_events (
                    event_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS inbound_message_events (
                    event_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL UNIQUE,
                    message_created_at TEXT NOT NULL DEFAULT '',
                    received_at TEXT NOT NULL
                );
                """
            )

            # Additive migration for databases created before message-id deduplication.
            for table_name in ("knowledge_events", "conversation_events"):
                columns = {
                    str(row["name"])
                    for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
                }
                if "message_id" not in columns:
                    connection.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN message_id TEXT NOT NULL DEFAULT ''"
                    )
                connection.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table_name}_message_id "
                    f"ON {table_name}(message_id) WHERE message_id <> ''"
                )

    def record_inbound_message(
        self,
        *,
        event_id: str,
        message_id: str,
        message_created_at: str,
        received_at: str,
    ) -> tuple[bool, str]:
        """Persist both platform identifiers before any side effect is scheduled."""
        if not event_id or not message_id:
            return False, "missing_id"
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO inbound_message_events
                (event_id,message_id,message_created_at,received_at) VALUES (?,?,?,?)""",
                (event_id, message_id, message_created_at, received_at),
            )
            if cursor.rowcount == 1:
                return True, ""
            if connection.execute(
                "SELECT 1 FROM inbound_message_events WHERE event_id=?", (event_id,),
            ).fetchone():
                return False, "event_id"
            if connection.execute(
                "SELECT 1 FROM inbound_message_events WHERE message_id=?", (message_id,),
            ).fetchone():
                return False, "message_id"
        return False, "unknown"

    def record_knowledge_event(self, event_id: str, message_id: str = "") -> bool:
        if not event_id:
            return False
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO knowledge_events(event_id, message_id, created_at) VALUES (?, ?, ?)",
                (event_id, message_id, utc_now()),
            )
            return cursor.rowcount == 1

    def record_conversation_event(self, event_id: str, message_id: str = "") -> bool:
        if not event_id:
            return False
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO conversation_events(event_id, message_id, created_at) VALUES (?, ?, ?)",
                (event_id, message_id, utc_now()),
            )
            return cursor.rowcount == 1

    def open_upload_window(self, chat_id: str, sender_id: str, minutes: int = UPLOAD_WINDOW_MINUTES) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO pending_uploads(chat_id,sender_id,created_at,expires_at) VALUES (?,?,?,?)
                ON CONFLICT(chat_id,sender_id) DO UPDATE SET created_at=excluded.created_at,expires_at=excluded.expires_at""",
                (chat_id, sender_id, now.isoformat(timespec="seconds"), (now + timedelta(minutes=minutes)).isoformat(timespec="seconds")),
            )

    def consume_upload_window(self, chat_id: str, sender_id: str) -> bool:
        now = utc_now()
        with self._connect() as connection:
            row = None
            if sender_id:
                row = connection.execute(
                    "SELECT sender_id,expires_at FROM pending_uploads WHERE chat_id=? AND sender_id=?",
                    (chat_id, sender_id),
                ).fetchone()
            if not row and not sender_id:
                candidates = connection.execute(
                    "SELECT sender_id,expires_at FROM pending_uploads WHERE chat_id=? AND expires_at>=? ORDER BY created_at DESC LIMIT 2",
                    (chat_id, now),
                ).fetchall()
                if len(candidates) == 1:
                    row = candidates[0]
            if row:
                connection.execute("DELETE FROM pending_uploads WHERE chat_id=? AND sender_id=?", (chat_id, row["sender_id"]))
        return bool(row and str(row["expires_at"]) >= now)

    def find_task(self, *, event_id: str, message_id: str, file_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE event_id=? OR (message_id=? AND file_key=?) ORDER BY created_at LIMIT 1",
                (event_id, message_id, file_key),
            ).fetchone()
        return dict(row) if row else None

    def enqueue(self, *, event_id: str, message_id: str, chat_id: str, file_key: str, file_name: str) -> tuple[dict[str, Any], bool]:
        now = utc_now()
        task_id = f"FS-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6].upper()}"
        with self._connect() as connection:
            try:
                connection.execute(
                    """INSERT INTO tasks
                    (task_id,event_id,message_id,chat_id,file_key,file_name,status,stage,created_at,updated_at)
                    VALUES (?,?,?,?,?,?, 'queued','queued',?,?)""",
                    (task_id, event_id, message_id, chat_id, file_key, file_name, now, now),
                )
                connection.execute(
                    "INSERT INTO task_logs(task_id,status,detail,created_at) VALUES (?, 'queued', '任务已入队', ?)",
                    (task_id, now),
                )
                created = True
            except sqlite3.IntegrityError:
                created = False
            row = connection.execute(
                "SELECT * FROM tasks WHERE event_id=? OR (message_id=? AND file_key=?) ORDER BY created_at LIMIT 1",
                (event_id, message_id, file_key),
            ).fetchone()
        return dict(row), created

    def recover_interrupted(self) -> int:
        now = utc_now()
        placeholders = ",".join("?" for _ in ACTIVE_STATES)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE tasks SET status='retryable_failed',stage='recovered',error='进程中断，等待恢复',updated_at=? WHERE status IN ({placeholders})",
                (now, *sorted(ACTIVE_STATES)),
            )
            return cursor.rowcount

    def claim_next(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM tasks WHERE status IN ('queued','retryable_failed') ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            now = utc_now()
            connection.execute(
                "UPDATE tasks SET status='downloading',stage='downloading',error='',updated_at=? WHERE task_id=?",
                (now, row["task_id"]),
            )
            updated = connection.execute("SELECT * FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()
            return dict(updated)

    def update(self, task_id: str, status: str, detail: str = "", **fields: Any) -> None:
        allowed = {"stage", "error", "backend_job_id", "output_excel", "output_report", "risk_total", "risk_high", "retry_count"}
        values = {key: value for key, value in fields.items() if key in allowed}
        values["status"] = status
        values["updated_at"] = utc_now()
        if status in TERMINAL_STATES:
            values["completed_at"] = utc_now()
        columns = ",".join(f"{key}=?" for key in values)
        with self._connect() as connection:
            connection.execute(f"UPDATE tasks SET {columns} WHERE task_id=?", (*values.values(), task_id))
            connection.execute(
                "INSERT INTO task_logs(task_id,status,detail,created_at) VALUES (?,?,?,?)",
                (task_id, status, sanitize_error(detail), utc_now()),
            )

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_for_chat(self, task_id: str, chat_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id=? AND chat_id=?",
                (task_id, chat_id),
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [dict(row) for row in rows]

    def list_tasks_for_chat(self, chat_id: str, limit: int = 5) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE chat_id=? ORDER BY created_at DESC LIMIT ?",
                (chat_id, max(1, min(limit, 30))),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_high_risk_tasks_for_chat(self, chat_id: str, limit: int = 5) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE chat_id=? AND risk_high>0 ORDER BY created_at DESC LIMIT ?",
                (chat_id, max(1, min(limit, 30))),
            ).fetchall()
        return [dict(row) for row in rows]

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute("SELECT status,COUNT(*) AS count FROM tasks GROUP BY status").fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def current_task(self) -> dict[str, Any] | None:
        placeholders = ",".join("?" for _ in ACTIVE_STATES)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY updated_at LIMIT 1",
                tuple(sorted(ACTIVE_STATES)),
            ).fetchone()
        return dict(row) if row else None

    def list_logs(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,task_id,status,detail,created_at FROM task_logs ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def queue_position(self, task_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT created_at FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if not row:
                return 0
            count = connection.execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('queued','retryable_failed') AND created_at<=?",
                (row["created_at"],),
            ).fetchone()[0]
        return int(count)


def read_console_events(
    limit: int = 200,
    *,
    db_path: Path | None = None,
    console_path: Path | None = None,
    runner_out_path: Path | None = None,
    runner_err_path: Path | None = None,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    events = _read_runtime_events(Path(console_path or CONSOLE_EVENTS_PATH))
    events.extend(_read_runner_connection_events(Path(runner_out_path or RUNNER_OUT_LOG_PATH)))
    events.extend(_read_runner_connection_events(Path(runner_err_path or RUNNER_ERR_LOG_PATH)))
    try:
        task_logs = TaskStore(db_path or DB_PATH).list_logs(limit=max(safe_limit, 200))
    except sqlite3.Error:
        task_logs = []
    warning_statuses = {"needs_manual", "retryable_failed", "recovered"}
    error_statuses = {"failed"}
    success_statuses = {"completed"}
    for item in task_logs:
        status = str(item.get("status") or "")
        level = "error" if status in error_statuses else "warning" if status in warning_statuses else "success" if status in success_statuses else "info"
        events.append({
            "timestamp": str(item.get("created_at") or utc_now()),
            "level": level,
            "category": "task",
            "message": _sanitize_console_text(item.get("detail") or status or "任务状态更新"),
            "task_id": _sanitize_console_text(item.get("task_id")),
            "profile_id": "",
            "source": "task",
        })
    events.sort(key=lambda item: str(item.get("timestamp") or ""))
    return events[-safe_limit:]

@dataclass(frozen=True)
class IncomingFileTask:
    event_id: str
    message_id: str
    chat_id: str
    file_key: str
    file_name: str


@dataclass(frozen=True)
class MessageEnvelope:
    event_id: str
    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str
    mentioned: bool
    text: str
    files: list[tuple[str, str]]
    message_created_at: str = ""
    mention_open_ids: tuple[str, ...] = ()
    mention_names: tuple[str, ...] = ()


def parse_message_event(payload: Any) -> IncomingFileTask:
    envelope = parse_message_envelope(payload)
    if not envelope.mentioned:
        raise ValueError("请在群聊中 @机器人 后上传文件")
    return _incoming_task(envelope)


def parse_message_envelope(payload: Any) -> MessageEnvelope:
    raw = _to_dict(payload)
    header = raw.get("header", {}) if isinstance(raw.get("header"), dict) else {}
    event = raw.get("event", raw)
    message = event.get("message", {}) if isinstance(event, dict) else {}
    chat_type = str(message.get("chat_type") or "").lower()
    if chat_type not in {"group", "group_chat", "p2p", "private", "single"}:
        raise ValueError("仅支持飞书群聊或机器人单聊任务")
    sender = event.get("sender", {}) if isinstance(event, dict) else {}
    sender_id_data = sender.get("sender_id", {}) if isinstance(sender, dict) else {}
    sender_id = str(sender_id_data.get("open_id") or sender_id_data.get("user_id") or sender_id_data.get("union_id") or "").strip()
    mentions = message.get("mentions") or []
    content_text = str(message.get("content") or "")
    mentioned = bool(mentions or "@_user_" in content_text or "@机器人" in content_text)
    mention_open_ids: list[str] = []
    mention_names: list[str] = []
    for mention in mentions if isinstance(mentions, list) else []:
        if not isinstance(mention, dict):
            continue
        mention_id = mention.get("id") if isinstance(mention.get("id"), dict) else {}
        open_id = str(mention_id.get("open_id") or mention.get("open_id") or "").strip()
        name = str(mention.get("name") or "").strip()
        if open_id:
            mention_open_ids.append(open_id)
        if name:
            mention_names.append(name)
    try:
        content = json.loads(content_text) if isinstance(message.get("content"), str) else message.get("content")
    except json.JSONDecodeError:
        content = {"text": content_text}
    text = _message_text(content)
    files = _find_files(content)
    event_id = str(header.get("event_id") or raw.get("event_id") or "").strip()
    message_id = str(message.get("message_id") or "").strip()
    chat_id = str(message.get("chat_id") or "").strip()
    message_created_at = normalize_platform_message_time(message.get("create_time"))
    if not event_id or not message_id or not chat_id:
        raise ValueError("飞书消息缺少任务所需标识")
    return MessageEnvelope(
        event_id, message_id, chat_id, chat_type, sender_id, mentioned, text, files,
        message_created_at,
        tuple(dict.fromkeys(mention_open_ids)), tuple(dict.fromkeys(mention_names)),
    )


def normalize_platform_message_time(value: Any) -> str:
    """Normalize Feishu/WeAct millisecond timestamps without rejecting legacy payloads."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            timestamp = float(text)
            if timestamp >= 100_000_000_000:
                timestamp /= 1000
            parsed = datetime.fromtimestamp(timestamp, timezone.utc)
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed = parsed.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError):
        return ""
    return parsed.isoformat(timespec="milliseconds")


def message_is_stale(
    envelope: MessageEnvelope,
    *,
    received_at: str | None = None,
    max_age_seconds: int = MESSAGE_MAX_AGE_SECONDS,
) -> bool:
    """Ignore only positively identified stale events; missing timestamps stay compatible."""
    if not envelope.message_created_at:
        return False
    try:
        created_at = datetime.fromisoformat(envelope.message_created_at)
        received = datetime.fromisoformat(received_at) if received_at else datetime.now(timezone.utc)
        if received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (received.astimezone(timezone.utc) - created_at.astimezone(timezone.utc)).total_seconds() > max_age_seconds


def _mentions_current_bot(
    envelope: MessageEnvelope,
    bot_open_id: str | None = None,
    bot_name: str | None = None,
) -> bool:
    if bot_open_id is None and bot_name is None:
        return envelope.mentioned
    normalized_id = str(bot_open_id or "").strip()
    normalized_name = str(bot_name or "").strip()
    if normalized_id:
        return normalized_id in envelope.mention_open_ids
    return bool(normalized_name and normalized_name in envelope.mention_names)


def describe_message_event(payload: Any, feishu: "FeishuApi", *, received_at: str = "") -> str:
    """Build a readable audit line for a handled event without exposing runtime credentials."""
    try:
        envelope = parse_message_envelope(payload)
    except ValueError:
        return "发送人、会话与消息内容无法解析｜来源 IP：飞书长连接事件未提供"

    sender_name = feishu.resolve_user_name(envelope.sender_id) if envelope.sender_id else ""
    sender_name = sender_name or envelope.sender_id or "未知发送人"
    sender_identity = envelope.sender_id or "无发送人 ID"
    is_private = envelope.chat_type in {"p2p", "private", "single"}
    if is_private:
        chat_name = f"与 {sender_name} 的单聊"
        chat_kind = "单聊"
    else:
        chat_name = feishu.resolve_chat_name(envelope.chat_id) or envelope.chat_id or "未知群聊"
        chat_kind = "群聊"

    message_parts: list[str] = []
    if envelope.text:
        message_parts.append(envelope.text)
    if envelope.files:
        message_parts.append("附件：" + "、".join(name for _key, name in envelope.files))
    message = "；".join(message_parts) or "（空消息）"
    return (
        f"发送人：{sender_name}（{sender_identity}）｜"
        f"会话：{chat_name}（{chat_kind}；{envelope.chat_id}）｜"
        f"消息 ID：{envelope.message_id}｜"
        f"平台创建时间：{envelope.message_created_at or '未提供'}｜"
        f"本机接收时间：{received_at or utc_now()}｜"
        f"来源 IP：飞书长连接事件未提供｜消息：{message}"
    )


def _message_text(value: Any) -> str:
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        for child in value.values():
            found = _message_text(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _message_text(child)
            if found:
                return found
    elif isinstance(value, str):
        return value.strip()
    return ""


def _strip_bot_mentions(text: str) -> str:
    clean = re.sub(r"<at[^>]*>.*?</at>", " ", str(text or ""), flags=re.IGNORECASE)
    clean = re.sub(r"@_user_(?:\d+)?", " ", clean, flags=re.IGNORECASE)
    return clean.replace("@机器人", " ").strip()


def extract_knowledge_question(text: str) -> str:
    """Extract an explicit @知识库 question while tolerating the bot mention before it."""
    clean = _strip_bot_mentions(text)
    for prefix in ("@知识库", "#知识库", "查库：", "查库:"):
        index = clean.find(prefix)
        if index < 0:
            continue
        question = clean[index + len(prefix):].lstrip(" \t\r\n:：,，.。;；")
        return question.strip()
    return ""


def clean_bot_command_text(text: str) -> str:
    return _strip_bot_mentions(text).rstrip(" \t\r\n。.!！?？")


def is_upload_command(text: str) -> bool:
    return clean_bot_command_text(text) in UPLOAD_COMMANDS


def is_greeting_command(text: str) -> bool:
    return clean_bot_command_text(text) in GREETING_COMMANDS


def is_group_member_command(text: str) -> bool:
    return clean_bot_command_text(text) in GROUP_MEMBER_COMMANDS


def parse_task_command(text: str) -> tuple[str, str]:
    command = clean_bot_command_text(text)
    if command in HELP_COMMANDS:
        return "help", ""
    if command in TASK_LIST_COMMANDS:
        return "task_list", ""
    if command in HIGH_RISK_COMMANDS:
        return "high_risk", ""
    match = TASK_DETAIL_COMMAND_PATTERN.fullmatch(command)
    if match:
        action = {"进度": "progress", "风险": "risk", "结果": "result"}[match.group(1)]
        return action, match.group(2).upper()
    if command in {"进度", "风险", "结果"}:
        return "task_usage", command
    return "", ""


def task_command_kind(text: str) -> str:
    action, _ = parse_task_command(text)
    return action or "chat"


def parse_knowledge_request(
    payload: Any,
    *,
    bot_open_id: str | None = None,
    bot_name: str | None = None,
) -> tuple[MessageEnvelope, str] | None:
    envelope = parse_message_envelope(payload)
    question = extract_knowledge_question(envelope.text)
    if not question:
        return None
    is_private = envelope.chat_type in {"p2p", "private", "single"}
    if not is_private and not _mentions_current_bot(envelope, bot_open_id, bot_name):
        raise IgnoreEvent("非机器人知识库消息")
    if envelope.files:
        raise ValueError("知识库问答请先发送文字问题，不要同时上传文件")
    return envelope, question


def _incoming_task(envelope: MessageEnvelope) -> IncomingFileTask:
    if len(envelope.files) != 1:
        raise ValueError("请发送且只发送一个 .xlsx 文件")
    file_key, file_name = envelope.files[0]
    if Path(file_name).suffix.lower() != ".xlsx":
        raise ValueError("当前只支持 .xlsx 文件")
    return IncomingFileTask(envelope.event_id, envelope.message_id, envelope.chat_id, file_key, safe_filename(file_name))


def _to_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "to_dict"):
        value = payload.to_dict()
        return value if isinstance(value, dict) else {}
    if hasattr(payload, "__dict__"):
        return json.loads(json.dumps(payload, default=lambda obj: getattr(obj, "__dict__", str(obj))))
    return {}


def _find_files(value: Any) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        key = str(value.get("file_key") or "").strip()
        name = str(value.get("file_name") or value.get("name") or "").strip()
        if key and name:
            found.append((key, name))
        for child in value.values():
            found.extend(_find_files(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_files(child))
    return list(dict.fromkeys(found))


def safe_filename(name: str) -> str:
    clean = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", Path(name).name).strip(" .")
    return clean[:180] or "input.xlsx"


def sanitize_error(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"(?i)(app[_ -]?secret|tenant[_ -]?access[_ -]?token)\s*[:=]\s*\S+", r"\1=***", text)
    return text[:500]


class FeishuApi:
    def __init__(self, app_id: str, app_secret: str, *, domain: str = DEFAULT_FEISHU_DOMAIN, client: httpx.Client | None = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = normalize_feishu_domain(domain)
        self.base_url = f"{self.domain}/open-apis"
        self.client = client or httpx.Client(timeout=60)
        self._token = ""
        self._token_expires_at = 0.0
        self._user_name_cache: dict[str, str] = {}
        self._chat_name_cache: dict[str, str] = {}
        self._bot_identity_cache: tuple[str, str] | None = None

    def token(self) -> str:
        if self._token and time.time() < self._token_expires_at:
            return self._token
        response = self.client.post(
            f"{self.base_url}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 0:
            raise RuntimeError(payload.get("msg") or "获取飞书访问令牌失败")
        self._token = str(payload.get("tenant_access_token") or "")
        self._token_expires_at = time.time() + max(60, int(payload.get("expire") or 7200) - 300)
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}"}

    def resolve_user_name(self, user_id: str) -> str:
        normalized = str(user_id or "").strip()
        if not normalized:
            return ""
        if normalized in self._user_name_cache:
            return self._user_name_cache[normalized]
        name = ""
        try:
            response = self.client.get(
                f"{self.base_url}/contact/v3/users/{quote(normalized, safe='')}",
                params={"user_id_type": "open_id"},
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
            if int(payload.get("code") or 0) == 0:
                data = payload.get("data") or {}
                user = data.get("user") or {}
                name = str(user.get("name") or user.get("nickname") or "").strip()
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, RuntimeError):
            name = ""
        resolved = name or normalized
        self._user_name_cache[normalized] = resolved
        return resolved

    def resolve_chat_name(self, chat_id: str) -> str:
        normalized = str(chat_id or "").strip()
        if not normalized:
            return ""
        if normalized in self._chat_name_cache:
            return self._chat_name_cache[normalized]
        name = ""
        try:
            response = self.client.get(
                f"{self.base_url}/im/v1/chats/{quote(normalized, safe='')}",
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
            if int(payload.get("code") or 0) == 0:
                data = payload.get("data") or {}
                chat = data.get("chat") if isinstance(data.get("chat"), dict) else data
                name = str(chat.get("name") or "").strip()
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, RuntimeError):
            name = ""
        resolved = name or normalized
        self._chat_name_cache[normalized] = resolved
        return resolved

    def resolve_bot_identity(self) -> tuple[str, str]:
        if self._bot_identity_cache is not None:
            return self._bot_identity_cache
        response = self.client.get(f"{self.base_url}/bot/v3/info", headers=self._headers())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or int(payload.get("code") or 0) != 0:
            raise RuntimeError(str(payload.get("msg") if isinstance(payload, dict) else "") or "获取当前机器人身份失败")
        bot = payload.get("bot") if isinstance(payload.get("bot"), dict) else {}
        if not bot and isinstance(payload.get("data"), dict):
            data = payload["data"]
            bot = data.get("bot") if isinstance(data.get("bot"), dict) else data
        identity = (str(bot.get("open_id") or "").strip(), str(bot.get("app_name") or bot.get("name") or "").strip())
        if not identity[0] and not identity[1]:
            raise RuntimeError("飞书未返回当前机器人身份")
        self._bot_identity_cache = identity
        return identity

    def list_chat_members(self, chat_id: str) -> dict[str, Any]:
        normalized = str(chat_id or "").strip()
        if not normalized:
            raise ValueError("缺少群聊标识")
        members: list[dict[str, str]] = []
        page_token = ""
        member_total = 0
        for _ in range(100):
            params: dict[str, Any] = {"member_id_type": "open_id", "page_size": 100}
            if page_token:
                params["page_token"] = page_token
            response = self.client.get(
                f"{self.base_url}/im/v1/chats/{quote(normalized, safe='')}/members",
                params=params,
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or int(payload.get("code") or 0) != 0:
                raise RuntimeError(str(payload.get("msg") if isinstance(payload, dict) else "") or "获取群成员失败")
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            member_total = max(member_total, int(data.get("member_total") or 0))
            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                member_id = str(item.get("member_id") or "").strip()
                name = str(item.get("name") or "").strip()
                if member_id or name:
                    members.append({"member_id": member_id, "name": name or "未命名成员"})
            if not data.get("has_more"):
                break
            next_token = str(data.get("page_token") or "").strip()
            if not next_token or next_token == page_token:
                raise RuntimeError("群成员分页信息异常")
            page_token = next_token
        unique_members = list({(item["member_id"], item["name"]): item for item in members}.values())
        return {"member_total": member_total or len(unique_members), "members": unique_members}

    def download_file(self, message_id: str, file_key: str, target: Path) -> Path:
        response = self.client.get(
            f"{self.base_url}/im/v1/messages/{message_id}/resources/{file_key}",
            params={"type": "file"}, headers=self._headers(),
        )
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target

    def send_text(self, chat_id: str, text: str) -> None:
        self._send_message(chat_id, "text", {"text": text})

    def send_card(self, chat_id: str, card: dict[str, Any]) -> None:
        self._send_message(chat_id, "interactive", card)

    def add_reaction(self, message_id: str, emoji_type: str = ACK_REACTION_EMOJI) -> None:
        normalized_message_id = str(message_id or "").strip()
        normalized_emoji_type = str(emoji_type or "").strip()
        if not normalized_message_id or not normalized_emoji_type:
            raise ValueError("消息 ID 和表情类型不能为空")
        response = self.client.post(
            f"{self.base_url}/im/v1/messages/{quote(normalized_message_id, safe='')}/reactions",
            headers=self._headers(),
            json={"reaction_type": {"emoji_type": normalized_emoji_type}},
        )
        try:
            payload = response.json()
        except ValueError:
            response.raise_for_status()
            raise RuntimeError("飞书消息表情回复返回了无法解析的响应")
        if int(payload.get("code") or 0) != 0:
            code = int(payload.get("code") or 0)
            message = str(payload.get("msg") or "飞书消息表情回复失败")
            raise RuntimeError(f"{message}（错误码 {code}）")
        response.raise_for_status()

    def upload_file(self, path: Path) -> str:
        with path.open("rb") as stream:
            response = self.client.post(
                f"{self.base_url}/im/v1/files",
                headers=self._headers(),
                data={"file_type": "stream", "file_name": path.name},
                files={"file": (path.name, stream, "application/octet-stream")},
            )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 0:
            raise RuntimeError(payload.get("msg") or "飞书文件上传失败")
        return str((payload.get("data") or {}).get("file_key") or "")

    def send_file(self, chat_id: str, path: Path) -> None:
        self._send_message(chat_id, "file", {"file_key": self.upload_file(path)})

    def _send_message(self, chat_id: str, msg_type: str, content: dict[str, Any]) -> None:
        response = self.client.post(
            f"{self.base_url}/im/v1/messages",
            params={"receive_id_type": "chat_id"}, headers=self._headers(),
            json={"receive_id": chat_id, "msg_type": msg_type, "content": json.dumps(content, ensure_ascii=False)},
        )
        try:
            payload = response.json()
        except ValueError:
            response.raise_for_status()
            raise RuntimeError("飞书消息接口返回了无法解析的响应")
        if int(payload.get("code") or 0) != 0:
            code = int(payload.get("code") or 0)
            raise RuntimeError(f"{payload.get('msg') or '飞书消息发送失败'}（错误码 {code}）")
        response.raise_for_status()


class ProfessionalApi:
    def __init__(self, base_url: str, *, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=600)

    def health_check(self) -> None:
        response = self.client.get(f"{self.base_url}/api/health", timeout=10)
        payload = self._response_json(response)
        if str(payload.get("status") or "").strip().lower() != "ok":
            raise RuntimeError("专业服务健康检查未返回 ok")

    def run(self, input_path: Path, task_dir: Path, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
        notify = progress or (lambda _stage: None)
        defaults = load_bot_defaults()
        project = self._get_json("GET", "/api/project-default-settings")
        mapping_defaults = project.get("inputMapping", {})
        field_preferences = mapping_defaults.get("fieldPreferences", {})
        inspect = self._post_file(
            "/api/inspect", input_path,
            data={"header_row": str(mapping_defaults.get("headerRow") or 4), "field_preferences": json.dumps(field_preferences, ensure_ascii=False)},
        )
        sheets = list(inspect.get("sheets") or [])
        configs = []
        candidates = sheets or [{**inspect, "sheet_name": "", "enabled": True}]
        for sheet in candidates:
            if not sheet.get("enabled", True):
                continue
            mapping = dict(sheet.get("suggested_mapping") or {})
            missing = [field for field in REQUIRED_MAPPING_FIELDS if not mapping.get(field)]
            if missing:
                name = str(sheet.get("sheet_name") or "当前工作表")
                raise NeedsManual(f"{name} 无法可靠识别字段：{'、'.join(missing)}")
            configs.append({
                "sheet_name": sheet.get("sheet_name"), "enabled": True,
                "header_row": int(sheet.get("header_row") or inspect.get("header_row") or 4),
                "column_mapping": mapping,
                "output_match_report": bool(mapping_defaults.get("outputMatchReport", True)),
                "merge_vertical_cells": bool(mapping_defaults.get("mergeVerticalCells", True)),
                "merge_horizontal_cells": bool(mapping_defaults.get("mergeHorizontalCells", True)),
                "only_match_rows_with_value": bool(mapping_defaults.get("onlyMatchRowsWithValue", True)),
                "match_value_filter_field": str(mapping_defaults.get("matchValueFilterField") or "数量"),
            })
        process_data = {
            "header_row": str(mapping_defaults.get("headerRow") or 4),
            "output_match_report": str(bool(mapping_defaults.get("outputMatchReport", True))).lower(),
            "merge_vertical_cells": str(bool(mapping_defaults.get("mergeVerticalCells", True))).lower(),
            "merge_horizontal_cells": str(bool(mapping_defaults.get("mergeHorizontalCells", True))).lower(),
            "only_match_rows_with_value": str(bool(mapping_defaults.get("onlyMatchRowsWithValue", True))).lower(),
            "match_value_filter_field": str(mapping_defaults.get("matchValueFilterField") or "数量"),
            "defer_matching": "true",
        }
        if sheets:
            process_data["sheet_configs"] = json.dumps(configs, ensure_ascii=False)
        else:
            process_data["column_mapping"] = json.dumps(configs[0]["column_mapping"], ensure_ascii=False)
        prepared = self._post_file("/api/process", input_path, data=process_data)
        job_id = str(prepared.get("job_id") or "")
        notify("matching")
        self._get_json("POST", "/api/process/batch-match", json_body={"job_id": job_id})
        notify("risk")
        warning = self._get_json("POST", "/api/experience-warnings/run", data={"job_id": job_id})
        risks = self._get_json("GET", "/api/risk/summary", params={"job_id": job_id})
        notify("report")
        llm_error = ""
        if defaults.get("enableLlmRiskNarrative", True):
            try:
                self._get_json("POST", "/api/risk-report", data={"job_id": job_id})
            except Exception as exc:  # optional enhancement
                llm_error = sanitize_error(exc)
        output_dir = task_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        excel_path = self._download(f"/api/download/{job_id}/excel", output_dir)
        report_path = self._download(f"/api/download/{job_id}/report", output_dir)
        return {"job_id": job_id, "excel": excel_path, "report": report_path, "risks": risks, "summary": warning.get("summary", {}), "llm_error": llm_error}

    def ask_knowledge(self, question: str) -> str:
        payload = self._get_json(
            "POST",
            "/api/knowledge/ask",
            json_body={"question": question, "force_knowledge": True},
        )
        answer = str(payload.get("answer") or "当前知识库未找到明确依据，需要人工复核。").strip()
        sources = payload.get("sources") or []
        source_lines = []
        for index, source in enumerate(sources[:5], start=1):
            if not isinstance(source, dict):
                continue
            source_file = str(source.get("source_file") or "").strip()
            title_path = str(source.get("title_path") or "").strip()
            if source_file:
                source_lines.append(f"{index}. {source_file}{f' / {title_path}' if title_path else ''}")
        if source_lines and "依据来源" not in answer:
            answer = f"{answer}\n\n依据来源：\n{chr(10).join(source_lines)}"
        if "不改变程序填价结果" not in answer and "不改变填价结果" not in answer:
            answer += "\n\n提示：本回答只解释依据，不改变程序填价结果。"
        return answer[:7000]

    def ask_chat(self, question: str) -> str:
        payload = self._get_json(
            "POST",
            "/api/llm-chat",
            data={"message": question},
        )
        answer = str(payload.get("answer") or "大模型暂未返回有效回答，请稍后重试。").strip()
        return answer[:7000]

    def _post_file(self, path: str, file_path: Path, *, data: dict[str, str]) -> dict[str, Any]:
        with file_path.open("rb") as stream:
            response = self.client.post(f"{self.base_url}{path}", data=data, files={"file": (file_path.name, stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        return self._response_json(response)

    def _get_json(self, method: str, path: str, *, data: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.client.request(method, f"{self.base_url}{path}", data=data, json=json_body, params=params)
        return self._response_json(response)

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        if response.is_error:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = response.text
            raise RuntimeError(detail or f"专业服务返回 {response.status_code}")
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _download(self, path: str, output_dir: Path) -> Path:
        response = self.client.get(f"{self.base_url}{path}")
        response.raise_for_status()
        disposition = response.headers.get("content-disposition", "")
        match = re.search(r"filename\*=utf-8''([^;]+)|filename=\"?([^\";]+)", disposition, re.I)
        encoded_name = match.group(1) if match and match.group(1) else match.group(2) if match else Path(path).name
        name = safe_filename(unquote(encoded_name))
        target = output_dir / name
        target.write_bytes(response.content)
        return target


class NeedsManual(ValueError):
    pass


class IgnoreEvent(ValueError):
    pass


def build_task_completion_card(
    *,
    task_id: str,
    file_name: str,
    risk_total: int,
    risk_high: int,
    llm_degraded: bool = False,
    app_url: str = "",
) -> dict[str, Any]:
    risk_line = f"结构化风险 **{risk_total} 项**，其中高风险 **{risk_high} 项**。"
    if risk_total == 0:
        risk_line = "本次未识别到结构化风险。"
    content = (
        f"**任务编号：** {task_id}\n"
        f"**输入文件：** {safe_filename(file_name)}\n"
        f"**处理状态：** 已完成\n\n"
        f"⚠️ {risk_line}\n"
        f"📎 Excel 和 Word 成果文件已发送，可在本卡片上方下载。"
    )
    if llm_degraded:
        content += "\n\n> 大模型风险说明本次已降级，结构化结果和成果文件不受影响。"
    elements: list[dict[str, Any]] = [{
        "tag": "div",
        "text": {"tag": "lark_md", "content": content},
    }]
    if app_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "进入造价智算"},
                "type": "primary",
                "url": app_url,
            }],
        })
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "造价智算 · 任务处理完成"},
            "template": "green",
        },
        "elements": elements,
    }


class TaskWorker:
    def __init__(self, store: TaskStore, feishu: FeishuApi, professional: ProfessionalApi):
        self.store = store
        self.feishu = feishu
        self.professional = professional

    def run_once(self) -> bool:
        task = self.store.claim_next()
        if not task:
            return False
        task_id = task["task_id"]
        task_dir = TASKS_ROOT / task_id
        input_path = task_dir / "input" / safe_filename(task["file_name"])
        try:
            self.store.update(task_id, "downloading", "下载飞书文件", stage="downloading")
            self.feishu.download_file(task["message_id"], task["file_key"], input_path)
            max_bytes = int(load_bot_defaults().get("maxFileSizeMb") or 50) * 1024 * 1024
            if input_path.stat().st_size > max_bytes:
                raise NeedsManual(f"文件超过 {max_bytes // 1024 // 1024} MB 上限")
            self.store.update(task_id, "inspecting", "检查工作表与默认映射", stage="inspecting")
            def report_progress(stage: str) -> None:
                self.store.update(task_id, stage, f"进入 {stage} 阶段", stage=stage)
                progress_messages = {
                    "matching": f"任务 {task_id}：表格与字段识别完成，正在执行批量匹配。",
                    "risk": f"任务 {task_id}：批量匹配完成，正在进行经验池预警和风险识别。",
                    "report": f"任务 {task_id}：风险识别完成，正在生成 Excel 和 Word 成果。",
                }
                message = progress_messages.get(stage)
                if message:
                    try:
                        self.feishu.send_text(task["chat_id"], message)
                    except Exception:
                        pass

            result = self.professional.run(
                input_path,
                task_dir,
                progress=report_progress,
            )
            risk_summary = dict((result.get("risks") or {}).get("summary") or {})
            high = int((risk_summary.get("severity_counts") or {}).get("high") or 0)
            total = int(risk_summary.get("total") or 0)
            self.store.update(task_id, "uploading", "回传成果", stage="uploading", backend_job_id=result["job_id"], risk_total=total, risk_high=high)
            degraded = "；大模型风险说明已降级" if result.get("llm_error") else ""
            self.feishu.send_file(task["chat_id"], result["excel"])
            self.feishu.send_file(task["chat_id"], result["report"])
            try:
                self.feishu.send_card(
                    task["chat_id"],
                    build_task_completion_card(
                        task_id=task_id,
                        file_name=task["file_name"],
                        risk_total=total,
                        risk_high=high,
                        llm_degraded=bool(result.get("llm_error")),
                        app_url=load_completion_card_app_url(),
                    ),
                )
            except Exception as exc:
                append_runtime_event(
                    "task",
                    f"完成卡片发送失败，已降级为文字通知：{sanitize_error(exc)}",
                    level="warning",
                    task_id=task_id,
                    profile_id=active_profile_id(),
                )
                try:
                    self.feishu.send_text(task["chat_id"], f"任务 {task_id} 已完成。结构化风险 {total} 项，其中高风险 {high} 项{degraded}。Excel 和 Word 成果文件已发送。")
                except Exception as fallback_exc:
                    append_runtime_event(
                        "task",
                        f"完成文字通知也发送失败，但成果文件已成功回传：{sanitize_error(fallback_exc)}",
                        level="warning",
                        task_id=task_id,
                        profile_id=active_profile_id(),
                    )
            self.store.update(task_id, "completed", "成果已回传", stage="completed", output_excel=str(result["excel"]), output_report=str(result["report"]), risk_total=total, risk_high=high)
        except NeedsManual as exc:
            self.store.update(task_id, "needs_manual", exc, stage="needs_manual", error=sanitize_error(exc))
            self.feishu.send_text(task["chat_id"], f"任务 {task_id} 需要人工处理：{sanitize_error(exc)}。系统未猜测字段，也未写入价格。")
        except Exception as exc:
            self._handle_failure(task, exc)
        return True

    def _handle_failure(self, task: dict[str, Any], exc: Exception) -> None:
        defaults = load_bot_defaults()
        retries = int(task.get("retry_count") or 0) + 1
        limit = int(defaults.get("retryCount") or 2)
        error = sanitize_error(exc)
        if retries <= limit:
            self.store.update(task["task_id"], "retryable_failed", error, stage="retryable_failed", error=error, retry_count=retries)
        else:
            self.store.update(task["task_id"], "failed", error, stage="failed", error=error, retry_count=retries)
            try:
                self.feishu.send_text(task["chat_id"], f"任务 {task['task_id']} 处理失败：{error}。请在本地专业工作台检查。")
            except Exception:
                pass


def accept_event(
    payload: Any,
    store: TaskStore,
    feishu: FeishuApi,
    *,
    bot_open_id: str | None = None,
    bot_name: str | None = None,
) -> dict[str, Any] | None:
    envelope = parse_message_envelope(payload)
    is_private = envelope.chat_type in {"p2p", "private", "single"}
    if not envelope.files:
        if not is_upload_command(envelope.text):
            return None
        if not is_private and not _mentions_current_bot(envelope, bot_open_id, bot_name):
            raise IgnoreEvent("非机器人上传指令")
        if not envelope.sender_id:
            raise ValueError("无法识别发起人，请重新发送 @上传")
        store.open_upload_window(envelope.chat_id, envelope.sender_id)
        feishu.send_text(envelope.chat_id, "已进入收件状态，请在 1 分钟内直接拖入并发送一个 .xlsx 文件。")
        return {"pending": True}

    incoming = _incoming_task(envelope)
    existing = store.find_task(
        event_id=incoming.event_id,
        message_id=incoming.message_id,
        file_key=incoming.file_key,
    )
    if existing:
        return {"task_id": existing["task_id"], "created": False}
    if not store.consume_upload_window(envelope.chat_id, envelope.sender_id):
        if not is_private and not _mentions_current_bot(envelope, bot_open_id, bot_name):
            raise IgnoreEvent("非机器人任务消息")
        raise ValueError("请先发送“@上传”或“@上传文件”，再在 1 分钟内发送一个 .xlsx 文件")
    task, created = store.enqueue(
        event_id=incoming.event_id, message_id=incoming.message_id, chat_id=incoming.chat_id,
        file_key=incoming.file_key, file_name=incoming.file_name,
    )
    if created:
        position = store.queue_position(task["task_id"])
        feishu.send_text(incoming.chat_id, f"已收件。任务编号：{task['task_id']}，当前排队位置：{position}。系统将按顺序完成匹配、风险识别、Excel 和 Word 输出。")
    return {"task_id": task["task_id"], "created": created}


def acknowledge_message_event(payload: Any, feishu: FeishuApi) -> str:
    """Add the lightweight “了解” reaction to one received user message."""
    envelope = parse_message_envelope(payload)
    feishu.add_reaction(envelope.message_id, ACK_REACTION_EMOJI)
    return envelope.message_id


def should_acknowledge_message(
    payload: Any,
    *,
    bot_open_id: str | None = None,
    bot_name: str | None = None,
    received_at: str | None = None,
) -> bool:
    """Only acknowledge direct messages and group messages that explicitly mention the bot."""
    envelope = parse_message_envelope(payload)
    if message_is_stale(envelope, received_at=received_at):
        return False
    is_private = envelope.chat_type in {"p2p", "private", "single"}
    return is_private or _mentions_current_bot(envelope, bot_open_id, bot_name)


def accept_knowledge_event(
    payload: Any,
    store: TaskStore,
    feishu: FeishuApi,
    *,
    bot_open_id: str | None = None,
    bot_name: str | None = None,
) -> dict[str, Any] | None:
    request = parse_knowledge_request(payload, bot_open_id=bot_open_id, bot_name=bot_name)
    if request is None:
        return None
    envelope, question = request
    if not store.record_knowledge_event(envelope.event_id, envelope.message_id):
        return {"handled": True, "duplicate": True}
    feishu.send_text(envelope.chat_id, "已收到知识库问题，正在检索本地规则、知识库和依据来源，请稍候。")
    return {"handled": True, "duplicate": False, "chat_id": envelope.chat_id, "question": question}


def answer_knowledge_event(chat_id: str, question: str, feishu: FeishuApi, professional: ProfessionalApi) -> None:
    try:
        answer = professional.ask_knowledge(question)
        feishu.send_text(chat_id, f"知识库查询完成：\n\n{answer}")
        append_runtime_event("knowledge", "知识库问题查询完成并已回复", level="success", profile_id=active_profile_id())
    except Exception as exc:
        append_runtime_event("knowledge", f"知识库问题查询失败：{sanitize_error(exc)}", level="error", profile_id=active_profile_id())
        feishu.send_text(chat_id, f"知识库查询暂时失败：{sanitize_error(exc)}。请稍后重试，或在造价智算“知识库问答”中查询。")


def task_status_label(task: dict[str, Any]) -> str:
    status = str(task.get("status") or "")
    return TASK_STATUS_LABELS.get(status, status or "未知状态")


def format_task_list(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "当前会话还没有任务。发送“@上传”或“@上传文件”后，可在 1 分钟内上传一个 .xlsx 文件。"
    lines = [f"当前会话最近 {len(tasks)} 个任务："]
    for index, task in enumerate(tasks, start=1):
        risk = ""
        if int(task.get("risk_total") or 0) or task.get("status") == "completed":
            risk = f"；风险 {int(task.get('risk_total') or 0)} 项 / 高风险 {int(task.get('risk_high') or 0)} 项"
        lines.append(
            f"{index}. {task['task_id']}｜{task_status_label(task)}｜{safe_filename(task.get('file_name') or '')}{risk}"
        )
    lines.append("发送“进度 FS-任务编号”“风险 FS-任务编号”或“结果 FS-任务编号”可查看详情。")
    return "\n".join(lines)


def format_task_progress(task: dict[str, Any], store: TaskStore) -> str:
    lines = [
        f"任务编号：{task['task_id']}",
        f"文件：{safe_filename(task.get('file_name') or '')}",
        f"当前状态：{task_status_label(task)}",
    ]
    if task.get("status") in {"queued", "retryable_failed"}:
        lines.append(f"当前全局排队位置：{store.queue_position(task['task_id'])}")
    if task.get("error"):
        lines.append(f"说明：{sanitize_error(task['error'])}")
    lines.append(f"最近更新时间：{task.get('updated_at') or '未记录'}")
    return "\n".join(lines)


def format_task_risk(task: dict[str, Any]) -> str:
    if task.get("status") not in {"completed", "uploading"}:
        return f"任务 {task['task_id']} 当前为“{task_status_label(task)}”，风险识别尚未形成最终结果。"
    return (
        f"任务 {task['task_id']} 风险统计：\n"
        f"• 结构化风险：{int(task.get('risk_total') or 0)} 项\n"
        f"• 高风险：{int(task.get('risk_high') or 0)} 项\n"
        "详细风险说明请查看该任务的 Word 报告。"
    )


def format_high_risk_tasks(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "当前会话的历史任务中，暂未发现已记录的高风险任务。"
    lines = [f"当前会话最近 {len(tasks)} 个高风险任务："]
    for index, task in enumerate(tasks, start=1):
        lines.append(
            f"{index}. {task['task_id']}｜高风险 {int(task.get('risk_high') or 0)} 项｜"
            f"总风险 {int(task.get('risk_total') or 0)} 项｜{safe_filename(task.get('file_name') or '')}"
        )
    lines.append("发送“风险 FS-任务编号”可查看单个任务风险统计。")
    return "\n".join(lines)


def answer_task_result_event(chat_id: str, task_id: str, store: TaskStore, feishu: FeishuApi) -> None:
    task = store.get_for_chat(task_id, chat_id)
    if not task:
        feishu.send_text(chat_id, "当前会话未找到该任务。请发送“任务”查看本会话可查询的任务编号。")
        return
    if task.get("status") != "completed":
        feishu.send_text(chat_id, f"任务 {task_id} 当前为“{task_status_label(task)}”，尚无可重新发送的完整成果。")
        return
    outputs = [Path(str(task.get("output_excel") or "")), Path(str(task.get("output_report") or ""))]
    if any(not str(path) or not path.is_file() for path in outputs):
        feishu.send_text(chat_id, f"任务 {task_id} 的历史成果文件已不存在，请在造价智算工作台重新处理原文件。")
        append_runtime_event(
            "task", "历史成果重发失败：成果文件不存在", level="warning",
            task_id=task_id, profile_id=active_profile_id(),
        )
        return
    try:
        for path in outputs:
            feishu.send_file(chat_id, path)
        try:
            feishu.send_card(
                chat_id,
                build_task_completion_card(
                    task_id=task_id,
                    file_name=str(task.get("file_name") or ""),
                    risk_total=int(task.get("risk_total") or 0),
                    risk_high=int(task.get("risk_high") or 0),
                    app_url=load_completion_card_app_url(),
                ),
            )
        except Exception as exc:
            append_runtime_event(
                "task", f"历史成果完成卡片发送失败，已降级为文字通知：{sanitize_error(exc)}",
                level="warning", task_id=task_id, profile_id=active_profile_id(),
            )
            feishu.send_text(
                chat_id,
                f"任务 {task_id} 的 Excel 和 Word 成果已重新发送。结构化风险 "
                f"{int(task.get('risk_total') or 0)} 项，其中高风险 {int(task.get('risk_high') or 0)} 项。",
            )
        append_runtime_event(
            "task", "历史 Excel、Word 和完成通知已重新发送", level="success",
            task_id=task_id, profile_id=active_profile_id(),
        )
    except Exception as exc:
        error = sanitize_error(exc)
        append_runtime_event(
            "task", f"历史成果重发失败：{error}", level="error",
            task_id=task_id, profile_id=active_profile_id(),
        )
        feishu.send_text(chat_id, f"任务 {task_id} 的成果重新发送失败：{error}。原任务状态和成果记录未被修改。")


def accept_conversation_event(
    payload: Any,
    store: TaskStore,
    feishu: FeishuApi,
    *,
    bot_open_id: str | None = None,
    bot_name: str | None = None,
) -> dict[str, Any]:
    envelope = parse_message_envelope(payload)
    is_private = envelope.chat_type in {"p2p", "private", "single"}
    if not is_private and not _mentions_current_bot(envelope, bot_open_id, bot_name):
        raise IgnoreEvent("非机器人对话消息")
    if envelope.files:
        raise IgnoreEvent("文件消息不进入文字问答")
    question = clean_bot_command_text(envelope.text)
    if not store.record_conversation_event(envelope.event_id, envelope.message_id):
        duplicate_kind = (
            "greeting" if not question or is_greeting_command(question)
            else "members" if is_group_member_command(question)
            else task_command_kind(question)
        )
        return {"handled": True, "duplicate": True, "kind": duplicate_kind}
    if not question:
        feishu.send_text(envelope.chat_id, BOT_INTRODUCTION)
        return {"handled": True, "duplicate": False, "kind": "greeting"}
    if is_greeting_command(question):
        feishu.send_text(envelope.chat_id, BOT_INTRODUCTION)
        return {"handled": True, "duplicate": False, "kind": "greeting"}
    if is_group_member_command(question):
        if is_private:
            feishu.send_text(envelope.chat_id, "群成员查询仅适用于群聊。请在目标群中 @机器人 后发送“群里有几个人”“群成员”或“都有谁”。")
            return {"handled": True, "duplicate": False, "kind": "members_private"}
        feishu.send_text(envelope.chat_id, "正在读取当前群的真实成员信息，请稍候。")
        return {
            "handled": True,
            "duplicate": False,
            "kind": "members",
            "chat_id": envelope.chat_id,
        }
    task_action, task_value = parse_task_command(question)
    if task_action == "help":
        feishu.send_text(envelope.chat_id, TASK_COMMAND_HELP)
        return {"handled": True, "duplicate": False, "kind": "help"}
    if task_action == "task_list":
        feishu.send_text(envelope.chat_id, format_task_list(store.list_tasks_for_chat(envelope.chat_id)))
        return {"handled": True, "duplicate": False, "kind": "task_list"}
    if task_action == "high_risk":
        feishu.send_text(
            envelope.chat_id,
            format_high_risk_tasks(store.list_high_risk_tasks_for_chat(envelope.chat_id)),
        )
        return {"handled": True, "duplicate": False, "kind": "high_risk"}
    if task_action == "task_usage":
        feishu.send_text(envelope.chat_id, f"请发送“{task_value} FS-任务编号”。发送“任务”可查看当前会话的任务编号。")
        return {"handled": True, "duplicate": False, "kind": "task_usage"}
    if task_action in {"progress", "risk", "result"}:
        task = store.get_for_chat(task_value, envelope.chat_id)
        if not task:
            feishu.send_text(envelope.chat_id, "当前会话未找到该任务。请发送“任务”查看本会话可查询的任务编号。")
            return {"handled": True, "duplicate": False, "kind": "task_missing"}
        if task_action == "progress":
            feishu.send_text(envelope.chat_id, format_task_progress(task, store))
            return {"handled": True, "duplicate": False, "kind": "progress"}
        if task_action == "risk":
            feishu.send_text(envelope.chat_id, format_task_risk(task))
            return {"handled": True, "duplicate": False, "kind": "risk"}
        if task.get("status") != "completed":
            feishu.send_text(
                envelope.chat_id,
                f"任务 {task_value} 当前为“{task_status_label(task)}”，尚无可重新发送的完整成果。",
            )
            return {"handled": True, "duplicate": False, "kind": "result_unavailable"}
        feishu.send_text(envelope.chat_id, f"已找到任务 {task_value}，正在重新发送历史成果，请稍候。")
        return {
            "handled": True,
            "duplicate": False,
            "kind": "result",
            "chat_id": envelope.chat_id,
            "task_id": task_value,
        }
    feishu.send_text(envelope.chat_id, "已收到问题，正在由大模型组织回答，请稍候。")
    return {
        "handled": True,
        "duplicate": False,
        "kind": "chat",
        "chat_id": envelope.chat_id,
        "question": question,
    }


def answer_chat_event(chat_id: str, question: str, feishu: FeishuApi, professional: ProfessionalApi) -> None:
    try:
        answer = professional.ask_chat(question)
        feishu.send_text(chat_id, answer)
        append_runtime_event("message", "大模型托底问答完成并已回复", level="success", profile_id=active_profile_id())
    except Exception as exc:
        append_runtime_event("message", f"大模型托底问答失败：{sanitize_error(exc)}", level="error", profile_id=active_profile_id())
        feishu.send_text(chat_id, f"大模型问答暂时失败：{sanitize_error(exc)}。请稍后重试。")


def format_chat_members(payload: dict[str, Any]) -> str:
    members = [item for item in payload.get("members") or [] if isinstance(item, dict)]
    total = int(payload.get("member_total") or len(members))
    lines = [f"当前群共有 {total} 人。", "", "群成员："]
    for index, member in enumerate(members, start=1):
        name = str(member.get("name") or "未命名成员").strip() or "未命名成员"
        candidate = f"{index}. {name}"
        if len("\n".join([*lines, candidate])) > 6500:
            lines.append(f"……名单较长，当前消息已显示前 {index - 1} 人。")
            break
        lines.append(candidate)
    if not members:
        lines.append("暂未读取到可展示的成员姓名。")
    return "\n".join(lines)


def answer_group_members_event(chat_id: str, feishu: FeishuApi) -> None:
    try:
        result = feishu.list_chat_members(chat_id)
        feishu.send_text(chat_id, format_chat_members(result))
        append_runtime_event("message", "群成员确定性查询完成并已回复", level="success", profile_id=active_profile_id())
    except Exception as exc:
        error = sanitize_error(exc)
        append_runtime_event("message", f"群成员查询失败：{error}", level="error", profile_id=active_profile_id())
        feishu.send_text(chat_id, f"群成员查询暂时失败：{error}。请检查机器人是否具有读取群信息与群成员的权限。")


def cleanup_expired(store: TaskStore, tasks_root: Path = TASKS_ROOT, retention_days: int | None = None) -> int:
    days = retention_days or int(load_bot_defaults().get("retentionDays") or 30)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for task in store.list_tasks(limit=100):
        if task.get("status") not in TERMINAL_STATES:
            continue
        completed = task.get("completed_at")
        if not completed:
            continue
        try:
            completed_at = datetime.fromisoformat(str(completed))
        except ValueError:
            continue
        if completed_at < cutoff:
            target = tasks_root / task["task_id"]
            if target.exists():
                shutil.rmtree(target)
                removed += 1
    with store._connect() as connection:
        connection.execute("DELETE FROM knowledge_events WHERE created_at < ?", (cutoff.isoformat(timespec="seconds"),))
        connection.execute("DELETE FROM conversation_events WHERE created_at < ?", (cutoff.isoformat(timespec="seconds"),))
        connection.execute("DELETE FROM inbound_message_events WHERE received_at < ?", (cutoff.isoformat(timespec="seconds"),))
    return removed
