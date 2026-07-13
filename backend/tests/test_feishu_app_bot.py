from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import feishu_app_bot
from backend.app.main import app


@pytest.fixture(autouse=True)
def isolate_runtime_console_log(tmp_path, monkeypatch):
    monkeypatch.setattr(feishu_app_bot, "CONSOLE_EVENTS_PATH", tmp_path / "console-events.jsonl")


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


def event_payload(*, event_id: str = "evt-1", message_id: str = "msg-1", files=None, mentions=None, text: str = "", sender_id: str = "user-1", chat_type: str = "group"):
    return {
        "header": {"event_id": event_id},
        "event": {
            "sender": {"sender_id": {"open_id": sender_id}},
            "message": {
                "message_id": message_id,
                "chat_id": "chat-1",
                "chat_type": chat_type,
                "mentions": [{"name": "机器人"}] if mentions is None else mentions,
                "content": json.dumps({"text": text, "files": files if files is not None else [{"file_key": "file-1", "file_name": "控制价.xlsx"}]}, ensure_ascii=False),
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
        (event_payload(files=[]), "只发送一个"),
        (event_payload(files=[{"file_key": "f", "file_name": "a.xls"}]), ".xlsx"),
        (event_payload(files=[{"file_key": "a", "file_name": "a.xlsx"}, {"file_key": "b", "file_name": "b.xlsx"}]), "只发送一个"),
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


def test_at_then_separate_file_message_creates_task(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    feishu = FakeFeishu()
    pending = feishu_app_bot.accept_event(event_payload(files=[], message_id="mention"), store, feishu)
    file_message = event_payload(event_id="evt-file", message_id="file-message", mentions=[])
    created = feishu_app_bot.accept_event(file_message, store, feishu)
    assert pending["pending"] is True
    assert created["created"] is True
    assert "5 分钟" in feishu.texts[0][1]


def test_unrelated_file_message_is_ignored(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    with pytest.raises(feishu_app_bot.IgnoreEvent):
        feishu_app_bot.accept_event(event_payload(mentions=[]), store, FakeFeishu())


def test_pending_upload_is_bound_to_sender(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    feishu_app_bot.accept_event(event_payload(files=[], sender_id="user-a"), store, FakeFeishu())
    with pytest.raises(feishu_app_bot.IgnoreEvent):
        feishu_app_bot.accept_event(event_payload(mentions=[], sender_id="user-b"), store, FakeFeishu())


def test_group_file_uses_only_pending_window_when_sender_id_is_missing(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    feishu = FakeFeishu()
    feishu_app_bot.accept_event(event_payload(files=[], sender_id="user-a"), store, feishu)
    result = feishu_app_bot.accept_event(
        event_payload(event_id="file-event", message_id="file-message", mentions=[], sender_id=""),
        store,
        feishu,
    )
    assert result["created"] is True


def test_private_chat_accepts_file_without_at(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    result = feishu_app_bot.accept_event(event_payload(chat_type="p2p", mentions=[]), store, FakeFeishu())
    assert result["created"] is True


def test_private_text_prompts_for_xlsx(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    feishu = FakeFeishu()
    result = feishu_app_bot.accept_event(event_payload(chat_type="p2p", files=[], mentions=[]), store, feishu)
    assert result["pending"] is True
    assert ".xlsx" in feishu.texts[0][1]


def test_group_knowledge_question_requires_bot_mention(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    feishu = FakeFeishu()
    result = feishu_app_bot.accept_knowledge_event(
        event_payload(files=[], text="@知识库：第二层经验提示是什么意思？"), store, feishu,
    )
    assert result["handled"] is True
    assert result["question"] == "第二层经验提示是什么意思？"
    assert "正在检索" in feishu.texts[0][1]


def test_group_knowledge_question_without_bot_mention_is_ignored(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    with pytest.raises(feishu_app_bot.IgnoreEvent):
        feishu_app_bot.accept_knowledge_event(
            event_payload(files=[], mentions=[], text="@知识库：第二层经验提示是什么意思？"), store, FakeFeishu(),
        )


def test_private_knowledge_question_does_not_require_bot_mention(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    result = feishu_app_bot.accept_knowledge_event(
        event_payload(chat_type="p2p", files=[], mentions=[], text="@知识库：技术工作费依据是什么？"), store, FakeFeishu(),
    )
    assert result["question"] == "技术工作费依据是什么？"


def test_knowledge_question_is_idempotent(tmp_path):
    store = feishu_app_bot.TaskStore(tmp_path / "tasks.sqlite3")
    feishu = FakeFeishu()
    first = feishu_app_bot.accept_knowledge_event(
        event_payload(files=[], text="@知识库：预警阈值怎么来的？"), store, feishu,
    )
    second = feishu_app_bot.accept_knowledge_event(
        event_payload(files=[], text="@知识库：预警阈值怎么来的？"), store, feishu,
    )
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert len(feishu.texts) == 1


def test_answer_knowledge_event_returns_answer_and_handles_failure():
    feishu = FakeFeishu()

    class Professional:
        def ask_knowledge(self, question):
            assert question == "技术工作费依据是什么？"
            return "依据来源：规则说明"

    feishu_app_bot.answer_knowledge_event("chat-1", "技术工作费依据是什么？", feishu, Professional())
    assert "知识库查询完成" in feishu.texts[-1][1]


def test_professional_api_knowledge_query_uses_existing_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/knowledge/ask"
        body = json.loads(request.content.decode("utf-8"))
        assert body == {"question": "技术工作费依据是什么？", "force_knowledge": True}
        return httpx.Response(
            200,
            json={
                "answer": "技术工作费按规则表解释。",
                "sources": [{"source_file": "规则说明.md", "title_path": "第一层规则"}],
            },
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    professional = feishu_app_bot.ProfessionalApi("http://127.0.0.1:8000", client=client)
    answer = professional.ask_knowledge("技术工作费依据是什么？")
    assert "技术工作费按规则表解释" in answer
    assert "规则说明.md / 第一层规则" in answer
    assert "不改变程序填价结果" in answer


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
    assert any("批量匹配完成" in text for _, text in feishu.texts)
    assert any("正在生成 Excel 和 Word" in text for _, text in feishu.texts)


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


def test_console_events_merge_runtime_connection_and_task_logs_without_secrets(tmp_path):
    console_path = tmp_path / "console-events.jsonl"
    runner_out = tmp_path / "runner.out.log"
    runner_err = tmp_path / "runner.err.log"
    db_path = tmp_path / "tasks.sqlite3"
    feishu_app_bot.append_runtime_event(
        "message",
        "收到消息 ticket=private-ticket chat_id=private-chat https://open.feishu.cn/open-apis/private/path",
        path=console_path,
    )
    runner_out.write_text(
        "[Lark] [2026-07-13 19:31:38,123] [INFO] connected to "
        "wss://lark-frontier.weact.pipechina.com.cn/ws/v2?ticket=private-ticket&access_key=private-key\n",
        encoding="utf-8",
    )
    store = feishu_app_bot.TaskStore(db_path)
    task, _ = store.enqueue(event_id="e-console", message_id="m-console", chat_id="c", file_key="f", file_name="a.xlsx")
    store.update(task["task_id"], "completed", "成果已回传", stage="completed")

    items = feishu_app_bot.read_console_events(
        limit=50,
        db_path=db_path,
        console_path=console_path,
        runner_out_path=runner_out,
        runner_err_path=runner_err,
    )

    serialized = json.dumps(items, ensure_ascii=False)
    assert "private-ticket" not in serialized
    assert "private-key" not in serialized
    assert "private-chat" not in serialized
    assert "/ws/v2" not in serialized
    assert any(item["category"] == "connection" and "lark-frontier.weact.pipechina.com.cn" in item["message"] for item in items)
    assert any(item["category"] == "message" for item in items)
    assert any(item["category"] == "task" and item["task_id"] == task["task_id"] for item in items)


def test_console_log_api_is_bounded_and_does_not_expose_raw_runner_url(tmp_path, monkeypatch):
    console_path = tmp_path / "console-events.jsonl"
    runner_out = tmp_path / "runner.out.log"
    runner_out.write_text(
        "[Lark] [2026-07-13 19:31:38,123] [INFO] connected to "
        "wss://msg-frontier.feishu.cn/ws/v2?ticket=secret-ticket\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(feishu_app_bot, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(feishu_app_bot, "CONSOLE_EVENTS_PATH", console_path)
    monkeypatch.setattr(feishu_app_bot, "RUNNER_OUT_LOG_PATH", runner_out)
    monkeypatch.setattr(feishu_app_bot, "RUNNER_ERR_LOG_PATH", tmp_path / "runner.err.log")

    response = TestClient(app).get("/api/collaboration/feishu-app-bot/logs?limit=1")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert "secret-ticket" not in response.text
    assert "/ws/v2" not in response.text


def test_start_bot_process_records_child_pid_immediately(tmp_path, monkeypatch):
    pid_path = tmp_path / "runner.pid"
    monkeypatch.setattr(feishu_app_bot, "PID_PATH", pid_path)
    monkeypatch.setattr(feishu_app_bot, "RUNTIME_ROOT", tmp_path / "runtime")
    monkeypatch.setattr(feishu_app_bot, "is_bot_enabled", lambda: True)
    monkeypatch.setattr(feishu_app_bot, "bot_process_running", lambda: False)
    monkeypatch.setattr(
        feishu_app_bot,
        "load_credentials",
        lambda: {"app_id": "app", "app_secret": "secret", "domain": "https://open.weact.pipechina.com.cn"},
    )
    monkeypatch.setattr(feishu_app_bot.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=4321))

    assert feishu_app_bot.start_bot_process() is True
    assert pid_path.read_text(encoding="utf-8") == "4321"


def test_credential_profiles_support_multiple_bots_without_exposing_secrets(tmp_path, monkeypatch):
    settings_path = tmp_path / "feishu-app-settings.json"
    settings_path.write_text(json.dumps({
        "active_profile": "default",
        "profiles": {
            "default": {"label": "默认机器人（普通飞书）", "app_id": "cli_default", "app_secret": "secret-default"},
            "weact_cost": {"label": "Weact机器人（管网内网）", "app_id": "cli_weact", "app_secret": "secret-weact", "domain": "https://open.weact.pipechina.com.cn"},
        },
    }), encoding="utf-8")
    monkeypatch.setattr(feishu_app_bot, "SETTINGS_PATH", settings_path)

    assert feishu_app_bot.active_profile_id() == "default"
    assert [item["profile_id"] for item in feishu_app_bot.credential_profiles()] == ["default", "weact_cost"]
    assert feishu_app_bot.load_credentials()["app_id"] == "cli_default"
    feishu_app_bot.save_active_profile("weact_cost")
    assert feishu_app_bot.active_profile_id() == "weact_cost"
    assert feishu_app_bot.load_credentials()["app_secret"] == "secret-weact"
    assert feishu_app_bot.load_credentials()["domain"] == "https://open.weact.pipechina.com.cn"
    assert feishu_app_bot.credential_profiles()[1]["domain_host"] == "open.weact.pipechina.com.cn"
    assert "secret-weact" not in json.dumps(feishu_app_bot.credential_profiles(), ensure_ascii=False)


def test_feishu_api_uses_selected_enterprise_domain():
    api = feishu_app_bot.FeishuApi(
        "cli_weact",
        "secret-weact",
        domain="https://open.weact.pipechina.com.cn",
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(500))),
    )

    assert api.domain == "https://open.weact.pipechina.com.cn"
    assert api.base_url == "https://open.weact.pipechina.com.cn/open-apis"


@pytest.mark.parametrize(
    "domain",
    [
        "http://open.weact.pipechina.com.cn",
        "https://example.com",
        "https://open.weact.pipechina.com.cn/path",
    ],
)
def test_invalid_feishu_domain_falls_back_to_public_feishu(domain):
    assert feishu_app_bot.normalize_feishu_domain(domain) == "https://open.feishu.cn"


def test_app_bot_switch_persists_and_starts_when_enabled(tmp_path, monkeypatch):
    control_path = tmp_path / "control.json"
    monkeypatch.setattr(feishu_app_bot, "CONTROL_PATH", control_path)
    monkeypatch.setattr(feishu_app_bot, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(feishu_app_bot, "bot_process_running", lambda: False)
    started: list[bool] = []
    monkeypatch.setattr(feishu_app_bot, "start_bot_process", lambda: started.append(True) or True)
    response = TestClient(app).post("/api/collaboration/feishu-app-bot/settings", json={"enabled": True})
    assert response.status_code == 200
    assert json.loads(control_path.read_text(encoding="utf-8"))["enabled"] is True
    assert started == [True]


def test_app_bot_profile_switch_persists_and_starts_selected_profile(tmp_path, monkeypatch):
    settings_path = tmp_path / "feishu-app-settings.json"
    settings_path.write_text(json.dumps({
        "active_profile": "default",
        "profiles": {
            "default": {"label": "默认机器人（普通飞书）", "app_id": "cli_default", "app_secret": "secret-default"},
            "weact_cost": {"label": "Weact机器人（管网内网）", "app_id": "cli_weact", "app_secret": "secret-weact", "domain": "https://open.weact.pipechina.com.cn"},
        },
    }), encoding="utf-8")
    control_path = tmp_path / "control.json"
    monkeypatch.setattr(feishu_app_bot, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(feishu_app_bot, "CONTROL_PATH", control_path)
    monkeypatch.setattr(feishu_app_bot, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(feishu_app_bot, "bot_process_running", lambda: False)
    started: list[bool] = []
    monkeypatch.setattr(feishu_app_bot, "start_bot_process", lambda: started.append(True) or True)

    response = TestClient(app).post(
        "/api/collaboration/feishu-app-bot/settings",
        json={"enabled": True, "profile_id": "weact_cost"},
    )

    assert response.status_code == 200
    assert response.json()["active_profile"] == "weact_cost"
    assert response.json()["configured"] is True
    assert json.loads(control_path.read_text(encoding="utf-8"))["enabled"] is True
    assert started == [True]


def test_app_bot_switch_can_disable_without_starting(tmp_path, monkeypatch):
    control_path = tmp_path / "control.json"
    monkeypatch.setattr(feishu_app_bot, "CONTROL_PATH", control_path)
    monkeypatch.setattr(feishu_app_bot, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(feishu_app_bot, "bot_process_running", lambda: True)
    monkeypatch.setattr(feishu_app_bot, "start_bot_process", lambda: pytest.fail("关闭时不应启动进程"))
    response = TestClient(app).post("/api/collaboration/feishu-app-bot/settings", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert json.loads(control_path.read_text(encoding="utf-8"))["enabled"] is False


def test_bot_process_running_detects_a_live_windows_process(tmp_path, monkeypatch):
    pid_path = tmp_path / "runner.pid"
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    monkeypatch.setattr(feishu_app_bot, "PID_PATH", pid_path)
    assert feishu_app_bot.bot_process_running() is True
