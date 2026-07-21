from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from backend.app import external_task_dispatch
from backend.app.paths import BUSINESS_SKILLS_DIR, PROJECT_DEFAULT_SETTINGS_PATH, PROJECT_ROOT
from backend.app.professional_skills import ProfessionalSkillRegistry


class FakeFeishu:
    def __init__(self, *, chats: list[dict[str, str]] | None = None) -> None:
        self.chats = chats if chats is not None else [{"chat_id": "chat-test", "name": "智算测试"}]
        self.cards: list[tuple[str, str, dict]] = []
        self.files: list[tuple[str, str, Path]] = []
        self.fail_card = False
        self.fail_file = False
        self.card_error = ""

    def list_chats(self) -> list[dict[str, str]]:
        return self.chats

    def resolve_chat_name(self, chat_id: str) -> str:
        for chat in self.chats:
            if chat["chat_id"] == chat_id:
                return chat["name"]
        return ""

    def list_chat_members(self, chat_id: str) -> dict:
        assert chat_id == "chat-test"
        return {"member_total": 2, "members": [
            {"member_id": "ou-user-1", "name": "石萌"},
            {"member_id": "ou-user-2", "name": "测试人员"},
        ]}

    def send_card_to(self, receive_id: str, receive_id_type: str, card: dict) -> str:
        if self.fail_card:
            raise RuntimeError(self.card_error or "卡片发送失败 token=secret")
        self.cards.append((receive_id, receive_id_type, card))
        return f"card-{len(self.cards)}"

    def send_file_to(self, receive_id: str, receive_id_type: str, path: Path) -> str:
        if self.fail_file:
            raise RuntimeError("文件发送失败 token=secret")
        assert path.is_file()
        self.files.append((receive_id, receive_id_type, path))
        return f"file-{len(self.files)}"


def xlsx_bytes() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet["A1"] = "项目"
    worksheet["B1"] = "金额"
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


@pytest.fixture
def service(tmp_path: Path):
    feishu = FakeFeishu()
    store = external_task_dispatch.ExternalDispatchStore(tmp_path / "tasks.sqlite3")
    registry = ProfessionalSkillRegistry(PROJECT_ROOT, BUSINESS_SKILLS_DIR, PROJECT_DEFAULT_SETTINGS_PATH)
    dispatch = external_task_dispatch.ExternalTaskDispatchService(
        store=store,
        registry=registry,
        feishu=feishu,
        profile_id="weact",
        runtime_root=tmp_path / "runtime",
        app_url="http://127.0.0.1:5174/",
    )
    options = dispatch.options()
    return dispatch, store, feishu, options


def envelope(person_ref: str, **overrides: str) -> external_task_dispatch.TaskEnvelope:
    values = {
        "event_id": "evt-001",
        "event_type": external_task_dispatch.EVENT_TYPE,
        "source_system": external_task_dispatch.SOURCE_SYSTEM,
        "source_task_id": "EXT-001",
        "task_name": "勘察测量限价编制",
        "project_name": "测试项目",
        "skill_id": "survey-measurement-limit-price",
        "skill_version": "1.0.0",
        "delivery_mode": "group",
        "platform_profile_id": "weact",
        "assignee_ref": person_ref,
        "deadline": "2026-07-31T18:00:00+08:00",
        "instructions": "请按模板完成测试任务。",
        "input_artifact": external_task_dispatch.TaskArtifact("待填模板.xlsx", "v1.0"),
    }
    values.update(overrides)
    return external_task_dispatch.TaskEnvelope(**values)


def test_envelope_rejects_missing_and_wrong_event(person_ref: str = "PM-X"):
    with pytest.raises(external_task_dispatch.DispatchValidationError, match="缺少必填字段"):
        envelope(person_ref, task_name="").validate()
    with pytest.raises(external_task_dispatch.DispatchValidationError, match="不支持"):
        envelope(person_ref, event_type="task.changed").validate()


def test_options_returns_names_but_not_platform_ids(service):
    _, _, _, options = service
    encoded = json.dumps(options, ensure_ascii=False)
    assert options["target_group"]["name"] == "智算测试"
    assert [item["display_name"] for item in options["people"]] == ["测试人员", "石萌"]
    assert "ou-user" not in encoded
    assert "chat-test" not in encoded


def test_full_group_delivery_copies_template_and_uses_classic_card(service):
    dispatch, store, feishu, options = service
    source = xlsx_bytes()
    task, created = dispatch.create_and_deliver(
        envelope(options["people"][0]["person_ref"]), file_name="模板.xlsx", file_bytes=source,
    )
    assert created is True
    assert task["status"] == "pending_claim"
    assert task["card_status"] == task["file_status"] == "sent"
    assert len(feishu.cards) == len(feishu.files) == 1
    card = feishu.cards[0][2]
    assert set(card) == {"config", "header", "elements"}
    assert "schema" not in card and "update_multi" not in card
    assert "<at id=ou-user-2>" in json.dumps(card, ensure_ascii=False)
    row = store.get_task(task["task_id"])
    task_path = dispatch.runtime_root / row["task_excel_path"]
    source_path = dispatch.runtime_root / row["template_source_path"]
    assert task_path.read_bytes() == source == source_path.read_bytes()


def test_business_idempotency_does_not_send_twice(service):
    dispatch, _, feishu, options = service
    first, first_created = dispatch.create_and_deliver(
        envelope(options["people"][0]["person_ref"]), file_name="a.xlsx", file_bytes=xlsx_bytes(),
    )
    second, second_created = dispatch.create_and_deliver(
        envelope(options["people"][0]["person_ref"], event_id="evt-002"),
        file_name="b.xlsx",
        file_bytes=xlsx_bytes(),
    )
    assert first_created is True and second_created is False
    assert first["task_id"] == second["task_id"]
    assert len(feishu.cards) == len(feishu.files) == 1


def test_retry_only_resends_failed_file_step(service):
    dispatch, _, feishu, options = service
    feishu.fail_file = True
    task, _ = dispatch.create_and_deliver(
        envelope(options["people"][0]["person_ref"]), file_name="a.xlsx", file_bytes=xlsx_bytes(),
    )
    assert task["status"] == "dispatch_failed"
    assert task["card_status"] == "sent" and task["file_status"] == "pending"
    feishu.fail_file = False
    retried = dispatch.retry(task["task_id"])
    assert retried["status"] == "pending_claim"
    assert len(feishu.cards) == 1 and len(feishu.files) == 1
    assert retried["delivery_retry_count"] == 1


def test_direct_delivery_is_guarded_until_verified(service):
    dispatch, _, feishu, options = service
    direct = envelope(options["people"][0]["person_ref"], delivery_mode="direct")
    with pytest.raises(external_task_dispatch.DispatchValidationError, match="尚未完成验证"):
        dispatch.create_and_deliver(direct, file_name="a.xlsx", file_bytes=xlsx_bytes())
    dispatch.direct_delivery_verified = True
    task, _ = dispatch.create_and_deliver(
        envelope(options["people"][0]["person_ref"], delivery_mode="direct", source_task_id="EXT-002", event_id="evt-002"),
        file_name="a.xlsx",
        file_bytes=xlsx_bytes(),
    )
    assert task["status"] == "pending_claim"
    assert feishu.cards[-1][1] == feishu.files[-1][1] == "open_id"


def test_direct_delivery_rejects_missing_person_mapping(service):
    dispatch, _, _, _ = service
    dispatch.direct_delivery_verified = True
    with pytest.raises(external_task_dispatch.DispatchValidationError, match="人员映射"):
        dispatch.create_and_deliver(
            envelope("PM-NOT-FOUND", delivery_mode="direct"),
            file_name="a.xlsx",
            file_bytes=xlsx_bytes(),
        )


@pytest.mark.parametrize("platform_error", ["permission denied", "user unreachable"])
def test_direct_delivery_records_permission_or_unreachable_failure(service, platform_error):
    dispatch, _, feishu, options = service
    dispatch.direct_delivery_verified = True
    feishu.fail_card = True
    feishu.card_error = platform_error
    task, created = dispatch.create_and_deliver(
        envelope(
            options["people"][0]["person_ref"],
            delivery_mode="direct",
            source_task_id=f"EXT-{platform_error}",
            event_id=f"evt-{platform_error}",
        ),
        file_name="a.xlsx",
        file_bytes=xlsx_bytes(),
    )
    assert created is True
    assert task["status"] == "dispatch_failed"
    assert task["card_status"] == task["file_status"] == "pending"
    assert task["error"] == platform_error
    assert not feishu.files


def test_inactive_skill_and_profile_mismatch_are_rejected(service):
    dispatch, _, _, options = service
    person = options["people"][0]["person_ref"]
    with pytest.raises(external_task_dispatch.DispatchValidationError, match="投递平台"):
        dispatch.create_and_deliver(
            envelope(person, platform_profile_id="feishu"), file_name="a.xlsx", file_bytes=xlsx_bytes(),
        )
    with pytest.raises(external_task_dispatch.DispatchValidationError, match="不能创建真实任务"):
        dispatch.create_and_deliver(
            envelope(person, skill_id="general-service-cost-estimation", skill_version="0.1.0"),
            file_name="a.xlsx",
            file_bytes=xlsx_bytes(),
        )


def test_group_target_must_be_unique(tmp_path: Path):
    feishu = FakeFeishu(chats=[
        {"chat_id": "chat-a", "name": "智算测试"},
        {"chat_id": "chat-b", "name": "智算测试"},
    ])
    dispatch = external_task_dispatch.ExternalTaskDispatchService(
        store=external_task_dispatch.ExternalDispatchStore(tmp_path / "tasks.sqlite3"),
        registry=ProfessionalSkillRegistry(PROJECT_ROOT, BUSINESS_SKILLS_DIR, PROJECT_DEFAULT_SETTINGS_PATH),
        feishu=feishu,
        profile_id="weact",
        runtime_root=tmp_path / "runtime",
    )
    with pytest.raises(external_task_dispatch.DispatchValidationError, match="找到多个同名"):
        dispatch.options()


def test_public_task_never_exposes_platform_identifiers(service):
    dispatch, store, _, options = service
    task, _ = dispatch.create_and_deliver(
        envelope(options["people"][0]["person_ref"]), file_name="a.xlsx", file_bytes=xlsx_bytes(),
    )
    public = external_task_dispatch.public_dispatch_task(store.get_task(task["task_id"]))
    encoded = json.dumps(public, ensure_ascii=False)
    for secret in ("chat-test", "ou-user", "file_key", "token", "task_excel_path"):
        assert secret not in encoded


def test_card_failure_is_persisted_without_crashing_other_capabilities(service):
    dispatch, _, feishu, options = service
    feishu.fail_card = True
    task, created = dispatch.create_and_deliver(
        envelope(options["people"][0]["person_ref"]), file_name="a.xlsx", file_bytes=xlsx_bytes(),
    )
    assert created is True and task["status"] == "dispatch_failed"
    assert "secret" not in task["error"].lower()
    assert dispatch.registry.resolve_for_task("survey-measurement-limit-price", "1.0.0")["id"] == "survey-measurement-limit-price"
