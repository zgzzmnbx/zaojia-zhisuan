from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import feishu_app_bot
from backend.app.main import app


class FakeFeishu:
    def __init__(self):
        self.texts: list[tuple[str, str]] = []
        self.files: list[tuple[str, Path]] = []

    def send_text(self, chat_id: str, text: str) -> None:
        self.texts.append((chat_id, text))

    def send_file(self, chat_id: str, path: Path) -> None:
        self.files.append((chat_id, path))

    def download_file(self, message_id: str, file_key: str, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"xlsx")
        return target


def event_payload(*, event_id: str = "evt-1", message_id: str = "msg-1", files=None, mentions=None):
    return {
        "header": {"event_id": event_id},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": "chat-1",
                "chat_type": "group",
                "mentions": [{"name": "机器人"}] if mentions is None else mentions,
                "content": json.dumps({"files": files if files is not None else [{"file_key": "file-1", "file_name": "控制价.xlsx"}]}, ensure_ascii=False),
            }
        },
    }


def test_parse_valid_group_message():
    task = feishu_app_bot.parse_message_event(event_payload())
    assert task.file_name == "控制价.xlsx"
    assert task.chat_id == "chat-1"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (event_payload(mentions=[]), "@机器人"),
        (event_payload(files=[]), "必须且只能"),
        (event_payload(files=[{"file_key": "f", "file_name": "a.xls"}]), ".xlsx"),
        (event_payload(files=[{"file_key": "a", "file_name": "a.xlsx"}, {"file_key": "b", "file_name": "b.xlsx"}]), "必须且只能"),
    ],
)
def test_parse_rejects_invalid_messages(payload, message):
    with pytest.raises(ValueError, match=message):
        feishu_app_bot.parse_message_event(payload)


def test_enqueue_is_idempotent_and_fifo(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    first, created = store.enqueue(event_id="e1", message_id="m1", chat_id="c", file_key="f1", file_name="a.xlsx")
    duplicate, created_again = store.enqueue(event_id="e1", message_id="m1", chat_id="c", file_key="f1", file_name="a.xlsx")
    second, _ = store.enqueue(event_id="e2", message_id="m2", chat_id="c", file_key="f2", file_name="b.xlsx")
    assert created is True
    assert created_again is False
    assert duplicate["task_id"] == first["task_id"]
    assert store.claim_next()["task_id"] == first["task_id"]
    store.update(first["task_id"], "completed", stage="completed")
    assert store.claim_next()["task_id"] == second["task_id"]


def test_accept_event_replies_once_for_duplicate(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    feishu = FakeFeishu()
    first = feishu_app_bot.accept_event(event_payload(), store, feishu)
    second = feishu_app_bot.accept_event(event_payload(), store, feishu)
    assert first["created"] is True
    assert second["created"] is False
    assert len(feishu.texts) == 1
    assert first["task_id"] in feishu.texts[0][1]


def test_worker_completes_and_returns_two_files(tmp_path, monkeypatch):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    task, _ = store.enqueue(event_id="e1", message_id="m1", chat_id="c", file_key="f", file_name="a.xlsx")
    feishu = FakeFeishu()

    class Professional:
        def run(self, input_path, task_dir, *, progress=None):
            progress("matching")
            progress("risk")
            progress("report")
            output = task_dir / "output"
            output.mkdir(parents=True, exist_ok=True)
            excel = output / "result.xlsx"
            report = output / "report.docx"
            excel.write_bytes(b"excel")
            report.write_bytes(b"word")
            return {
                "job_id": "job-1", "excel": excel, "report": report, "llm_error": "",
                "risks": {"summary": {"total": 3, "severity_counts": {"high": 1}}},
            }

    monkeypatch.setattr(feishu_app_bot, "TASKS_ROOT", tmp_path / "task-files")
    worker = feishu_app_bot.TaskWorker(store, feishu, Professional())
    assert worker.run_once() is True
    saved = store.get(task["task_id"])
    assert saved["status"] == "completed"
    assert saved["risk_total"] == 3
    assert len(feishu.files) == 2


def test_worker_marks_mapping_problem_needs_manual(tmp_path, monkeypatch):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    task, _ = store.enqueue(event_id="e1", message_id="m1", chat_id="c", file_key="f", file_name="a.xlsx")
    feishu = FakeFeishu()

    class Professional:
        def run(self, input_path, task_dir, *, progress=None):
            raise feishu_app_bot.NeedsManual("缺少单位")

    monkeypatch.setattr(feishu_app_bot, "TASKS_ROOT", tmp_path / "task-files")
    feishu_app_bot.TaskWorker(store, feishu, Professional()).run_once()
    assert store.get(task["task_id"])["status"] == "needs_manual"
    assert "未猜测字段" in feishu.texts[-1][1]


def test_worker_retries_then_fails(tmp_path, monkeypatch):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    task, _ = store.enqueue(event_id="e1", message_id="m1", chat_id="c", file_key="f", file_name="a.xlsx")
    feishu = FakeFeishu()

    class Professional:
        def run(self, input_path, task_dir, *, progress=None):
            raise RuntimeError("network down")

    monkeypatch.setattr(feishu_app_bot, "TASKS_ROOT", tmp_path / "task-files")
    monkeypatch.setattr(feishu_app_bot, "load_bot_defaults", lambda: {"retryCount": 1})
    worker = feishu_app_bot.TaskWorker(store, feishu, Professional())
    worker.run_once()
    assert store.get(task["task_id"])["status"] == "retryable_failed"
    worker.run_once()
    assert store.get(task["task_id"])["status"] == "failed"


def test_recover_interrupted_tasks(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    task, _ = store.enqueue(event_id="e1", message_id="m1", chat_id="c", file_key="f", file_name="a.xlsx")
    store.claim_next()
    assert store.recover_interrupted() == 1
    assert store.get(task["task_id"])["status"] == "retryable_failed"


def test_cleanup_only_removes_expired_terminal_task_files(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    task, _ = store.enqueue(event_id="e1", message_id="m1", chat_id="c", file_key="f", file_name="a.xlsx")
    store.update(task["task_id"], "completed", stage="completed")
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(timespec="seconds")
    with store._connect() as connection:
        connection.execute("UPDATE tasks SET completed_at=? WHERE task_id=?", (old, task["task_id"]))
    task_dir = tmp_path / "tasks" / task["task_id"]
    task_dir.mkdir(parents=True)
    assert feishu_app_bot.cleanup_expired(store, tmp_path / "tasks", retention_days=30) == 1
    assert not task_dir.exists()


def test_status_api_does_not_expose_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(feishu_app_bot, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(feishu_app_bot, "load_credentials", lambda: {"app_id": "app", "app_secret": "secret"})
    response = TestClient(app).get("/api/collaboration/feishu-app-bot/status")
    assert response.status_code == 200
    text = response.text
    assert "secret" not in text
    assert response.json()["configured"] is True
