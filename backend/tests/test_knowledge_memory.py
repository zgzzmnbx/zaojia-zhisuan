from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.knowledge_memory import KnowledgeMemoryStore
from app.knowledge_qa import KnowledgeSearchResult
from app.main import app


def candidate_payload(**overrides):
    payload = {
        "project_name": "东部管道勘察项目",
        "scope_type": "project",
        "title": "隧道洞身复杂程度复核口径",
        "question": "山岭隧道洞身如何复核复杂程度？",
        "conclusion": "当前项目按复杂条件复核，并保留设计说明作为来源。",
        "conditions": "仅适用于东部管道勘察项目的山岭隧道洞身。",
        "exceptions": "设计文件明确采用其他复杂程度时重新复核。",
        "source_type": "knowledge_answer",
        "source_reference": "表4-通用工程勘察费用 / 第90行",
        "evidence_summary": "知识库回答和行级复核结论。",
        "submitter": "编制人甲",
    }
    payload.update(overrides)
    return payload


def confirm_item(store: KnowledgeMemoryStore, item: dict) -> dict:
    store.transition(
        item["id"],
        item["project_key"],
        "submit",
        actor="编制人甲",
    )
    return store.transition(
        item["id"],
        item["project_key"],
        "confirm",
        actor="复核人乙",
        actor_role="reviewer",
        reason="已核对项目设计说明",
    )


def test_create_candidate_pending_does_not_search_and_confirmed_same_project_does(tmp_path):
    store = KnowledgeMemoryStore(tmp_path / "knowledge-memory.sqlite3")
    item = store.create_candidate(candidate_payload())

    assert item["status"] == "candidate"
    assert item["project_key"] == "东部管道勘察项目"
    assert store.search_confirmed("隧道洞身复杂程度", item["project_key"]) == []

    store.transition(item["id"], item["project_key"], "submit", actor="编制人甲")
    assert store.search_confirmed("隧道洞身复杂程度", item["project_key"]) == []

    confirmed = store.transition(
        item["id"],
        item["project_key"],
        "confirm",
        actor="复核人乙",
        actor_role="reviewer",
        reason="已核对项目资料",
    )
    results = store.search_confirmed("隧道洞身复杂程度", item["project_key"])

    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmer"] == "复核人乙"
    assert [result["id"] for result in results] == [item["id"]]
    assert store.search_confirmed("隧道洞身复杂程度", "另一个项目") == []


def test_edit_increments_version_and_audit_is_complete(tmp_path):
    db_path = tmp_path / "knowledge-memory.sqlite3"
    store = KnowledgeMemoryStore(db_path)
    item = store.create_candidate(candidate_payload())

    edited = store.update_item(
        item["id"],
        item["project_key"],
        {
            "actor": "编制人甲",
            "reason": "补充适用条件",
            "conditions": "仅适用于东部管道项目 A 标段。",
        },
    )
    store.transition(item["id"], item["project_key"], "submit", actor="编制人甲")
    store.transition(
        item["id"],
        item["project_key"],
        "confirm",
        actor="复核人乙",
        actor_role="reviewer",
        reason="确认",
    )
    audit = store.audit(item["id"], item["project_key"])

    assert edited["version"] == 2
    assert [record["action"] for record in audit] == ["create", "edit", "submit", "confirm"]
    with sqlite3.connect(db_path) as connection:
        version_count = connection.execute(
            "SELECT COUNT(*) FROM knowledge_versions WHERE item_id=?",
            (item["id"],),
        ).fetchone()[0]
    assert version_count == 2


def test_rejected_revoked_and_suspected_stale_items_stop_searching(tmp_path):
    store = KnowledgeMemoryStore(tmp_path / "knowledge-memory.sqlite3")
    rejected = store.create_candidate(candidate_payload(title="候选一"))
    store.transition(
        rejected["id"],
        rejected["project_key"],
        "reject",
        actor="复核人乙",
        reason="依据不足",
    )
    assert store.search_confirmed("隧道洞身", rejected["project_key"]) == []

    revoked = confirm_item(store, store.create_candidate(candidate_payload(title="候选二")))
    store.transition(
        revoked["id"],
        revoked["project_key"],
        "revoke",
        actor="复核人乙",
        reason="项目口径已更新",
    )
    assert store.search_confirmed("隧道洞身", revoked["project_key"]) == []

    stale = confirm_item(store, store.create_candidate(candidate_payload(title="候选三")))
    store.transition(
        stale["id"],
        stale["project_key"],
        "mark_stale",
        actor="复核人乙",
        reason="发现新版本设计说明",
    )
    assert store.search_confirmed("隧道洞身", stale["project_key"]) == []


def test_expired_confirmed_item_is_automatically_marked_stale(tmp_path):
    store = KnowledgeMemoryStore(tmp_path / "knowledge-memory.sqlite3")
    item = store.create_candidate(
        candidate_payload(expires_at="2020-01-01T00:00:00+00:00")
    )
    confirm_item(store, item)

    assert store.search_confirmed("隧道洞身", item["project_key"]) == []
    refreshed = store.get_item(item["id"], item["project_key"])
    assert refreshed["status"] == "suspected_stale"
    assert store.audit(item["id"], item["project_key"])[-1]["actor"] == "system"


def test_api_rejects_missing_scope_illegal_transition_cross_project_and_unapproved_role(
    tmp_path,
    monkeypatch,
):
    import app.main as main_module

    monkeypatch.setattr(
        main_module,
        "DEFAULT_KNOWLEDGE_MEMORY_DB_PATH",
        tmp_path / "knowledge-memory.sqlite3",
    )
    client = TestClient(app)
    missing_scope = candidate_payload(project_name="", project_key="")
    response = client.post("/api/knowledge-memory/candidates", json=missing_scope)
    assert response.status_code == 400

    created = client.post(
        "/api/knowledge-memory/candidates",
        json=candidate_payload(),
    ).json()["item"]
    cross_project = client.get(
        f"/api/knowledge-memory/items/{created['id']}",
        params={"project_key": "其他项目"},
    )
    assert cross_project.status_code == 404

    illegal = client.post(
        f"/api/knowledge-memory/items/{created['id']}/confirm",
        json={
            "project_key": created["project_key"],
            "actor": "复核人乙",
            "actor_role": "reviewer",
        },
    )
    assert illegal.status_code == 409

    client.post(
        f"/api/knowledge-memory/items/{created['id']}/submit",
        json={"project_key": created["project_key"], "actor": "编制人甲"},
    )
    unauthorized = client.post(
        f"/api/knowledge-memory/items/{created['id']}/confirm",
        json={
            "project_key": created["project_key"],
            "actor": "普通本地用户",
            "actor_role": "viewer",
        },
    )
    assert unauthorized.status_code == 403


def test_api_candidate_edit_submit_confirm_list_and_audit(tmp_path, monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(
        main_module,
        "DEFAULT_KNOWLEDGE_MEMORY_DB_PATH",
        tmp_path / "knowledge-memory.sqlite3",
    )
    client = TestClient(app)
    created_response = client.post(
        "/api/knowledge-memory/candidates",
        json=candidate_payload(),
    )
    assert created_response.status_code == 200
    created = created_response.json()["item"]
    assert created_response.json()["identity_mode"] == "local_trial"

    edited_response = client.patch(
        f"/api/knowledge-memory/items/{created['id']}",
        json={
            "project_key": created["project_key"],
            "actor": "编制人甲",
            "reason": "补充例外",
            "exceptions": "不适用于水域测量。",
        },
    )
    assert edited_response.status_code == 200
    assert edited_response.json()["item"]["version"] == 2

    assert client.post(
        f"/api/knowledge-memory/items/{created['id']}/submit",
        json={"project_key": created["project_key"], "actor": "编制人甲"},
    ).status_code == 200
    confirmed_response = client.post(
        f"/api/knowledge-memory/items/{created['id']}/confirm",
        json={
            "project_key": created["project_key"],
            "actor": "复核人乙",
            "actor_role": "project_owner",
            "reason": "已确认",
        },
    )
    assert confirmed_response.status_code == 200
    assert confirmed_response.json()["item"]["status"] == "confirmed"

    listed = client.get(
        "/api/knowledge-memory/items",
        params={"project_key": created["project_key"], "status": "confirmed"},
    ).json()["items"]
    audit = client.get(
        f"/api/knowledge-memory/items/{created['id']}/audit",
        params={"project_key": created["project_key"]},
    ).json()["audit"]
    assert len(listed) == 1
    assert [record["action"] for record in audit] == ["create", "edit", "submit", "confirm"]


def test_knowledge_ask_uses_only_confirmed_same_project_memory_and_displays_metadata(
    tmp_path,
    monkeypatch,
):
    import app.main as main_module

    db_path = tmp_path / "knowledge-memory.sqlite3"
    monkeypatch.setattr(main_module, "DEFAULT_KNOWLEDGE_MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "search_knowledge", lambda *args, **kwargs: [])
    captured = {}

    def fake_call_chat_completion(config, messages):
        captured["messages"] = messages
        return "智算解释：按当前项目记忆复核。\n\n项目记忆：东部管道勘察项目。"

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(main_module, "call_chat_completion", fake_call_chat_completion)
    client = TestClient(app)
    created = client.post(
        "/api/knowledge-memory/candidates",
        json=candidate_payload(),
    ).json()["item"]

    pending_response = client.post(
        "/api/knowledge/ask",
        json={
            "question": "山岭隧道洞身如何复核复杂程度？",
            "project_key": created["project_key"],
        },
    )
    assert pending_response.json()["evidence_found"] is False

    client.post(
        f"/api/knowledge-memory/items/{created['id']}/submit",
        json={"project_key": created["project_key"], "actor": "编制人甲"},
    )
    client.post(
        f"/api/knowledge-memory/items/{created['id']}/confirm",
        json={
            "project_key": created["project_key"],
            "actor": "复核人乙",
            "actor_role": "reviewer",
            "reason": "确认",
        },
    )
    response = client.post(
        "/api/knowledge/ask",
        json={
            "question": "山岭隧道洞身如何复核复杂程度？",
            "project_key": created["project_key"],
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["sources"] == []
    assert payload["project_memories"][0]["confirmer"] == "复核人乙"
    assert payload["project_memories"][0]["project_key"] == created["project_key"]
    assert "【正式知识与规则依据】" in captured["messages"][1]["content"]
    assert "【当前项目已确认知识记忆】" in captured["messages"][1]["content"]
    assert client.post(
        "/api/knowledge/ask",
        json={
            "question": "山岭隧道洞身如何复核复杂程度？",
            "project_key": "其他项目",
        },
    ).json()["evidence_found"] is False


def test_formal_knowledge_is_presented_before_project_memory(monkeypatch):
    import app.main as main_module

    formal = KnowledgeSearchResult(
        id="formal-1",
        source_file="标准资料.md",
        source_type="standard",
        title_path="正式标准",
        snippet="正式标准结论",
        score=10,
        module="通用概念",
    )
    memory = {
        "id": "KM-1",
        "project_key": "项目一",
        "project_name": "项目一",
        "title": "项目口径",
        "conclusion": "项目记忆结论",
        "conditions": "当前项目",
        "exceptions": "",
        "source_reference": "复核记录",
        "confirmer": "复核人",
        "confirmed_at": "2026-07-17T00:00:00+00:00",
    }
    captured = {}
    monkeypatch.setattr(main_module, "search_knowledge", lambda *args, **kwargs: [formal])
    monkeypatch.setattr(
        main_module,
        "search_confirmed_project_memory",
        lambda *args, **kwargs: [memory],
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    def fake_call_chat_completion(config, messages):
        captured["prompt"] = messages[1]["content"]
        return "正式依据优先，项目记忆补充。"

    monkeypatch.setattr(main_module, "call_chat_completion", fake_call_chat_completion)
    response = TestClient(app).post(
        "/api/knowledge/ask",
        json={"question": "项目口径是什么？", "project_key": "项目一"},
    )

    assert response.status_code == 200
    assert captured["prompt"].index("【正式知识与规则依据】") < captured["prompt"].index(
        "【当前项目已确认知识记忆】"
    )
    assert response.json()["sources"][0]["source_type"] == "standard"


def test_memory_database_failure_does_not_break_existing_no_evidence_behavior(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "search_knowledge", lambda *args, **kwargs: [])

    def broken_memory(*args, **kwargs):
        raise sqlite3.DatabaseError("broken")

    def fail_model(*args, **kwargs):
        raise AssertionError("无正式依据且记忆库故障时不应调用大模型")

    monkeypatch.setattr(main_module, "search_confirmed_project_memory", broken_memory)
    monkeypatch.setattr(main_module, "call_chat_completion", fail_model)
    response = TestClient(app).post(
        "/api/knowledge/ask",
        json={"question": "完全未知的问题", "project_key": "项目一"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "当前知识库未找到明确依据，需要人工复核。"
    assert response.json()["memory_available"] is False


def test_frontend_only_knowledge_messages_expose_candidate_action():
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "保存为知识候选" in source
    assert "knowledgeCandidate" in source
    assert "askZhisuanFreeform" in source
    assert "project_memories" in source
