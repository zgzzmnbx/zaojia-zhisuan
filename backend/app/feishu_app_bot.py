from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote
from uuid import uuid4

import httpx

from .paths import PROJECT_DEFAULT_SETTINGS_PATH, PROJECT_ROOT


RUNTIME_ROOT = PROJECT_ROOT / "Codex-Temp" / "runtime" / "feishu-bot"
SETTINGS_PATH = PROJECT_ROOT / "Codex-Temp" / "runtime" / "feishu-app-settings.json"
DB_PATH = RUNTIME_ROOT / "tasks.sqlite3"
TASKS_ROOT = RUNTIME_ROOT / "tasks"
CONTROL_PATH = RUNTIME_ROOT / "control.json"
PID_PATH = RUNTIME_ROOT / "runner.pid"
REQUIRED_MAPPING_FIELDS = ("要素1", "单位", "输出-价格列")
TERMINAL_STATES = {"completed", "needs_manual", "failed"}
ACTIVE_STATES = {"downloading", "inspecting", "matching", "risk", "report", "uploading"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_bot_defaults() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "enabled": False,
        "concurrency": 1,
        "retentionDays": 30,
        "allowedExtensions": [".xlsx"],
        "maxFileSizeMb": 50,
        "apiBaseUrl": "http://127.0.0.1:8000",
        "enableLlmRiskNarrative": True,
        "retryCount": 2,
        "retryDelaySeconds": 2,
    }
    try:
        raw = json.loads(PROJECT_DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    section = raw.get("feishuAppBot", {}) if isinstance(raw, dict) else {}
    if isinstance(section, dict):
        for key in defaults:
            if key in section:
                defaults[key] = section[key]
    defaults["concurrency"] = 1
    return defaults


def load_credentials() -> dict[str, str]:
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        "app_id": str(raw.get("app_id") or "").strip(),
        "app_secret": str(raw.get("app_secret") or "").strip(),
    }


def is_bot_enabled() -> bool:
    try:
        raw = json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return bool(load_bot_defaults().get("enabled"))
    return bool(raw.get("enabled")) if isinstance(raw, dict) else bool(load_bot_defaults().get("enabled"))


def save_bot_enabled(enabled: bool) -> None:
    CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTROL_PATH.write_text(json.dumps({"enabled": bool(enabled)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bot_process_running() -> bool:
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
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
    runner = PROJECT_ROOT / "backend" / "feishu_bot_runner.py"
    log_dir = RUNTIME_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (log_dir / "runner.out.log").open("a", encoding="utf-8") as stdout, (log_dir / "runner.err.log").open("a", encoding="utf-8") as stderr:
        subprocess.Popen(
            [sys.executable, str(runner)], cwd=PROJECT_ROOT,
            stdout=stdout, stderr=stderr, creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    return True


def bot_status(db_path: Path | None = None) -> dict[str, Any]:
    defaults = load_bot_defaults()
    credentials = load_credentials()
    store = TaskStore(db_path or DB_PATH)
    counts = store.counts()
    current = store.current_task()
    return {
        "enabled": is_bot_enabled(),
        "configured": bool(credentials.get("app_id") and credentials.get("app_secret")),
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
                """
            )

    def open_upload_window(self, chat_id: str, sender_id: str, minutes: int = 5) -> None:
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

    def list_tasks(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
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
    files: list[tuple[str, str]]


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
    try:
        content = json.loads(content_text) if isinstance(message.get("content"), str) else message.get("content")
    except json.JSONDecodeError:
        content = {"text": content_text}
    files = _find_files(content)
    event_id = str(header.get("event_id") or raw.get("event_id") or "").strip()
    message_id = str(message.get("message_id") or "").strip()
    chat_id = str(message.get("chat_id") or "").strip()
    if not event_id or not message_id or not chat_id:
        raise ValueError("飞书消息缺少任务所需标识")
    return MessageEnvelope(event_id, message_id, chat_id, chat_type, sender_id, mentioned, files)


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
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str, *, client: httpx.Client | None = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = client or httpx.Client(timeout=60)
        self._token = ""
        self._token_expires_at = 0.0

    def token(self) -> str:
        if self._token and time.time() < self._token_expires_at:
            return self._token
        response = self.client.post(
            f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
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

    def download_file(self, message_id: str, file_key: str, target: Path) -> Path:
        response = self.client.get(
            f"{self.BASE_URL}/im/v1/messages/{message_id}/resources/{file_key}",
            params={"type": "file"}, headers=self._headers(),
        )
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target

    def send_text(self, chat_id: str, text: str) -> None:
        self._send_message(chat_id, "text", {"text": text})

    def upload_file(self, path: Path) -> str:
        with path.open("rb") as stream:
            response = self.client.post(
                f"{self.BASE_URL}/im/v1/files",
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
            f"{self.BASE_URL}/im/v1/messages",
            params={"receive_id_type": "chat_id"}, headers=self._headers(),
            json={"receive_id": chat_id, "msg_type": msg_type, "content": json.dumps(content, ensure_ascii=False)},
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 0:
            raise RuntimeError(payload.get("msg") or "飞书消息发送失败")


class ProfessionalApi:
    def __init__(self, base_url: str, *, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=600)

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
            self.feishu.send_text(task["chat_id"], f"任务 {task_id} 已完成。结构化风险 {total} 项，其中高风险 {high} 项{degraded}。成果文件如下：")
            self.feishu.send_file(task["chat_id"], result["excel"])
            self.feishu.send_file(task["chat_id"], result["report"])
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


def accept_event(payload: Any, store: TaskStore, feishu: FeishuApi) -> dict[str, Any]:
    envelope = parse_message_envelope(payload)
    is_private = envelope.chat_type in {"p2p", "private", "single"}
    if is_private and not envelope.files:
        feishu.send_text(envelope.chat_id, "请直接拖入并发送一个 .xlsx 文件，我会自动完成匹配、风险识别、Excel 和 Word 输出。")
        return {"pending": True}
    if envelope.mentioned and not envelope.files:
        if not envelope.sender_id:
            raise ValueError("无法识别发起人，请重新 @机器人")
        store.open_upload_window(envelope.chat_id, envelope.sender_id)
        feishu.send_text(envelope.chat_id, "已进入收件状态，请在 5 分钟内直接拖入并发送一个 .xlsx 文件。")
        return {"pending": True}
    if not is_private and not envelope.mentioned:
        if not envelope.files or not store.consume_upload_window(envelope.chat_id, envelope.sender_id):
            raise IgnoreEvent("非机器人任务消息")
    incoming = _incoming_task(envelope)
    task, created = store.enqueue(
        event_id=incoming.event_id, message_id=incoming.message_id, chat_id=incoming.chat_id,
        file_key=incoming.file_key, file_name=incoming.file_name,
    )
    if created:
        position = store.queue_position(task["task_id"])
        feishu.send_text(incoming.chat_id, f"已收件。任务编号：{task['task_id']}，当前排队位置：{position}。系统将按顺序完成匹配、风险识别、Excel 和 Word 输出。")
    return {"task_id": task["task_id"], "created": created}


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
    return removed
