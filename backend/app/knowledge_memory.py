from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .paths import DEFAULT_KNOWLEDGE_MEMORY_DB_PATH


KNOWLEDGE_MEMORY_STATUSES = {
    "candidate",
    "pending",
    "confirmed",
    "rejected",
    "revoked",
    "suspected_stale",
}
KNOWLEDGE_MEMORY_SCOPE_TYPES = {"task", "project"}
CONFIRM_ROLES = {"project_owner", "reviewer", "rule_maintainer", "admin"}
EDITABLE_FIELDS = {
    "scope_type",
    "task_id",
    "job_id",
    "title",
    "question",
    "conclusion",
    "conditions",
    "exceptions",
    "expires_at",
    "source_type",
    "source_reference",
    "evidence_summary",
}
TRANSITIONS = {
    ("candidate", "submit"): "pending",
    ("candidate", "reject"): "rejected",
    ("pending", "confirm"): "confirmed",
    ("pending", "reject"): "rejected",
    ("confirmed", "revoke"): "revoked",
    ("confirmed", "mark_stale"): "suspected_stale",
    ("suspected_stale", "revoke"): "revoked",
}


class KnowledgeMemoryError(ValueError):
    pass


class KnowledgeMemoryNotFound(KnowledgeMemoryError):
    pass


class KnowledgeMemoryConflict(KnowledgeMemoryError):
    pass


class KnowledgeMemoryPermissionError(KnowledgeMemoryError):
    pass


def normalize_project_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized: list[str] = []
    pending_separator = False
    for character in text:
        if character.isalnum() or "\u4e00" <= character <= "\u9fff":
            if pending_separator and normalized:
                normalized.append("-")
            normalized.append(character)
            pending_separator = False
        else:
            pending_separator = True
    return "".join(normalized).strip("-")[:120]


def resolve_project_scope(payload: dict[str, Any]) -> tuple[str, str]:
    project_name = str(payload.get("project_name") or "").strip()
    project_key = normalize_project_key(payload.get("project_key") or project_name)
    if not project_key:
        raise KnowledgeMemoryError("请填写项目名称或 project_key")
    if not project_name:
        project_name = project_key
    return project_key, project_name


class KnowledgeMemoryStore:
    def __init__(self, db_path: Path = DEFAULT_KNOWLEDGE_MEMORY_DB_PATH):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema(connection)
        return connection

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge_items (
                id TEXT PRIMARY KEY,
                parent_id TEXT,
                project_key TEXT NOT NULL,
                project_name TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                task_id TEXT,
                job_id TEXT,
                title TEXT NOT NULL,
                question TEXT NOT NULL,
                conclusion TEXT NOT NULL,
                conditions TEXT NOT NULL DEFAULT '',
                exceptions TEXT NOT NULL DEFAULT '',
                expires_at TEXT,
                source_type TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                evidence_summary TEXT NOT NULL DEFAULT '',
                submitter TEXT NOT NULL,
                confirmer TEXT,
                status TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                confirmed_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY(parent_id) REFERENCES knowledge_items(id)
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_items_project_status
                ON knowledge_items(project_key, status, updated_at DESC);
            CREATE TABLE IF NOT EXISTS knowledge_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                change_reason TEXT NOT NULL DEFAULT '',
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(item_id, version),
                FOREIGN KEY(item_id) REFERENCES knowledge_items(id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL,
                project_key TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                from_status TEXT,
                to_status TEXT,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(item_id) REFERENCES knowledge_items(id)
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_audit_item
                ON knowledge_audit(item_id, id);
            """
        )

    def create_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_key, project_name = resolve_project_scope(payload)
        scope_type = str(payload.get("scope_type") or "project").strip()
        if scope_type not in KNOWLEDGE_MEMORY_SCOPE_TYPES:
            raise KnowledgeMemoryError("scope_type 仅支持 task 或 project")
        task_id = _optional_text(payload.get("task_id"))
        job_id = _optional_text(payload.get("job_id"))
        if scope_type == "task" and not (task_id or job_id):
            raise KnowledgeMemoryError("任务范围知识必须提供 task_id 或 job_id")
        required = {
            "title": "标题",
            "question": "原问题",
            "conclusion": "待确认结论",
            "source_type": "来源类型",
            "source_reference": "来源定位",
            "submitter": "提交人",
        }
        values: dict[str, str] = {}
        for key, label in required.items():
            values[key] = str(payload.get(key) or "").strip()
            if not values[key]:
                raise KnowledgeMemoryError(f"请填写{label}")
        expires_at = _normalize_optional_datetime(payload.get("expires_at"), "expires_at")
        now = _utc_now()
        item_id = f"KM-{uuid4().hex[:12].upper()}"
        item = {
            "id": item_id,
            "parent_id": _optional_text(payload.get("parent_id")),
            "project_key": project_key,
            "project_name": project_name,
            "scope_type": scope_type,
            "task_id": task_id,
            "job_id": job_id,
            "title": values["title"],
            "question": values["question"],
            "conclusion": values["conclusion"],
            "conditions": str(payload.get("conditions") or "").strip(),
            "exceptions": str(payload.get("exceptions") or "").strip(),
            "expires_at": expires_at,
            "source_type": values["source_type"],
            "source_reference": values["source_reference"],
            "evidence_summary": str(payload.get("evidence_summary") or "").strip(),
            "submitter": values["submitter"],
            "confirmer": None,
            "status": "candidate",
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "confirmed_at": None,
            "revoked_at": None,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_items (
                    id,parent_id,project_key,project_name,scope_type,task_id,job_id,
                    title,question,conclusion,conditions,exceptions,expires_at,
                    source_type,source_reference,evidence_summary,submitter,confirmer,
                    status,version,created_at,updated_at,confirmed_at,revoked_at
                ) VALUES (
                    :id,:parent_id,:project_key,:project_name,:scope_type,:task_id,:job_id,
                    :title,:question,:conclusion,:conditions,:exceptions,:expires_at,
                    :source_type,:source_reference,:evidence_summary,:submitter,:confirmer,
                    :status,:version,:created_at,:updated_at,:confirmed_at,:revoked_at
                )
                """,
                item,
            )
            self._record_version(connection, item, actor=values["submitter"], reason="创建知识候选")
            self._record_audit(
                connection,
                item,
                action="create",
                actor=values["submitter"],
                reason="创建知识候选",
                from_status=None,
                to_status="candidate",
            )
        return item

    def list_items(
        self,
        project_key: str,
        *,
        statuses: set[str] | None = None,
        query: str = "",
    ) -> list[dict[str, Any]]:
        normalized_key = _require_project_key(project_key)
        clauses = ["project_key=?"]
        parameters: list[Any] = [normalized_key]
        if statuses:
            invalid = statuses - KNOWLEDGE_MEMORY_STATUSES
            if invalid:
                raise KnowledgeMemoryError(f"未知知识状态：{', '.join(sorted(invalid))}")
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            parameters.extend(sorted(statuses))
        clean_query = query.strip()
        if clean_query:
            clauses.append("(title LIKE ? OR question LIKE ? OR conclusion LIKE ? OR evidence_summary LIKE ?)")
            marker = f"%{clean_query}%"
            parameters.extend([marker, marker, marker, marker])
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM knowledge_items WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC",
                parameters,
            ).fetchall()
        return [_row_dict(row) for row in rows]

    def get_item(self, item_id: str, project_key: str) -> dict[str, Any]:
        normalized_key = _require_project_key(project_key)
        with self._connect() as connection:
            row = self._get_row(connection, item_id, normalized_key)
        return _row_dict(row)

    def update_item(
        self,
        item_id: str,
        project_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        actor = str(payload.get("actor") or "").strip()
        if not actor:
            raise KnowledgeMemoryError("请填写操作人")
        normalized_key = _require_project_key(project_key)
        reason = str(payload.get("reason") or "编辑知识候选").strip()
        with self._connect() as connection:
            current_row = self._get_row(connection, item_id, normalized_key)
            current = _row_dict(current_row)
            if current["status"] not in {"candidate", "pending"}:
                raise KnowledgeMemoryConflict("已确认或已结束的知识不能直接覆盖，请创建新候选版本")
            updates: dict[str, Any] = {}
            for key in EDITABLE_FIELDS:
                if key not in payload:
                    continue
                if key == "scope_type":
                    value = str(payload.get(key) or "").strip()
                    if value not in KNOWLEDGE_MEMORY_SCOPE_TYPES:
                        raise KnowledgeMemoryError("scope_type 仅支持 task 或 project")
                elif key == "expires_at":
                    value = _normalize_optional_datetime(payload.get(key), "expires_at")
                else:
                    value = str(payload.get(key) or "").strip()
                updates[key] = (
                    value or None
                    if key in {"task_id", "job_id", "expires_at"}
                    else value
                )
            for required_key, label in (
                ("title", "标题"),
                ("question", "原问题"),
                ("conclusion", "结论"),
                ("source_type", "来源类型"),
                ("source_reference", "来源定位"),
            ):
                if required_key in updates and not updates[required_key]:
                    raise KnowledgeMemoryError(f"{label}不能为空")
            next_item = {**current, **updates}
            if next_item["scope_type"] == "task" and not (next_item.get("task_id") or next_item.get("job_id")):
                raise KnowledgeMemoryError("任务范围知识必须提供 task_id 或 job_id")
            next_item["version"] = int(current["version"]) + 1
            next_item["updated_at"] = _utc_now()
            assignments = ",".join(f"{key}=?" for key in [*updates, "version", "updated_at"])
            parameters = [next_item[key] for key in [*updates, "version", "updated_at"]]
            parameters.extend([item_id, normalized_key])
            connection.execute(
                f"UPDATE knowledge_items SET {assignments} WHERE id=? AND project_key=?",
                parameters,
            )
            self._record_version(connection, next_item, actor=actor, reason=reason)
            self._record_audit(
                connection,
                next_item,
                action="edit",
                actor=actor,
                reason=reason,
                from_status=current["status"],
                to_status=current["status"],
            )
        return self.get_item(item_id, normalized_key)

    def transition(
        self,
        item_id: str,
        project_key: str,
        action: str,
        *,
        actor: str,
        reason: str = "",
        actor_role: str = "",
    ) -> dict[str, Any]:
        clean_actor = actor.strip()
        if not clean_actor:
            raise KnowledgeMemoryError("请填写操作人")
        normalized_key = _require_project_key(project_key)
        clean_action = action.strip()
        with self._connect() as connection:
            current_row = self._get_row(connection, item_id, normalized_key)
            current = _row_dict(current_row)
            next_status = TRANSITIONS.get((current["status"], clean_action))
            if not next_status:
                raise KnowledgeMemoryConflict(
                    f"不允许从 {current['status']} 执行 {clean_action}"
                )
            if clean_action == "confirm" and actor_role not in CONFIRM_ROLES:
                raise KnowledgeMemoryPermissionError("当前本地试点身份没有确认角色")
            if clean_action in {"reject", "revoke", "mark_stale"} and not reason.strip():
                raise KnowledgeMemoryError("该状态变更必须填写原因")
            now = _utc_now()
            updates: dict[str, Any] = {
                "status": next_status,
                "updated_at": now,
            }
            if clean_action == "confirm":
                updates["confirmer"] = clean_actor
                updates["confirmed_at"] = now
            if clean_action == "revoke":
                updates["revoked_at"] = now
            assignments = ",".join(f"{key}=?" for key in updates)
            connection.execute(
                f"UPDATE knowledge_items SET {assignments} WHERE id=? AND project_key=?",
                [*updates.values(), item_id, normalized_key],
            )
            next_item = {**current, **updates}
            self._record_audit(
                connection,
                next_item,
                action=clean_action,
                actor=clean_actor,
                reason=reason.strip(),
                from_status=current["status"],
                to_status=next_status,
            )
        return self.get_item(item_id, normalized_key)

    def audit(self, item_id: str, project_key: str) -> list[dict[str, Any]]:
        normalized_key = _require_project_key(project_key)
        with self._connect() as connection:
            self._get_row(connection, item_id, normalized_key)
            rows = connection.execute(
                """
                SELECT id,item_id,project_key,action,actor,reason,from_status,to_status,version,created_at
                FROM knowledge_audit
                WHERE item_id=? AND project_key=?
                ORDER BY id
                """,
                (item_id, normalized_key),
            ).fetchall()
        return [_row_dict(row) for row in rows]

    def search_confirmed(
        self,
        question: str,
        project_key: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        normalized_key = _require_project_key(project_key)
        clean_question = question.strip()
        if not clean_question:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM knowledge_items
                WHERE project_key=? AND status='confirmed'
                ORDER BY updated_at DESC
                """,
                (normalized_key,),
            ).fetchall()
            active_rows: list[sqlite3.Row] = []
            now = datetime.now(timezone.utc)
            for row in rows:
                expires_at = _parse_datetime(row["expires_at"])
                if expires_at and expires_at <= now:
                    item = _row_dict(row)
                    connection.execute(
                        "UPDATE knowledge_items SET status='suspected_stale',updated_at=? WHERE id=?",
                        (_utc_now(), item["id"]),
                    )
                    item["status"] = "suspected_stale"
                    self._record_audit(
                        connection,
                        item,
                        action="mark_stale",
                        actor="system",
                        reason="知识已超过 expires_at，自动转为疑似失效",
                        from_status="confirmed",
                        to_status="suspected_stale",
                    )
                    continue
                active_rows.append(row)
        query_terms = _search_terms(clean_question)
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in active_rows:
            item = _row_dict(row)
            score = _memory_score(item, query_terms)
            if score > 0:
                item["score"] = round(score, 3)
                scored.append((score, item))
        scored.sort(key=lambda pair: (pair[0], pair[1]["updated_at"]), reverse=True)
        return [item for _, item in scored[: max(1, min(limit, 20))]]

    @staticmethod
    def _get_row(
        connection: sqlite3.Connection,
        item_id: str,
        project_key: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM knowledge_items WHERE id=? AND project_key=?",
            (item_id, project_key),
        ).fetchone()
        if not row:
            raise KnowledgeMemoryNotFound("未找到该项目范围内的知识")
        return row

    @staticmethod
    def _record_version(
        connection: sqlite3.Connection,
        item: dict[str, Any],
        *,
        actor: str,
        reason: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO knowledge_versions(item_id,version,snapshot_json,change_reason,actor,created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                item["id"],
                item["version"],
                json.dumps(item, ensure_ascii=False, sort_keys=True),
                reason,
                actor,
                _utc_now(),
            ),
        )

    @staticmethod
    def _record_audit(
        connection: sqlite3.Connection,
        item: dict[str, Any],
        *,
        action: str,
        actor: str,
        reason: str,
        from_status: str | None,
        to_status: str | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO knowledge_audit(
                item_id,project_key,action,actor,reason,from_status,to_status,version,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                item["id"],
                item["project_key"],
                action,
                actor,
                reason,
                from_status,
                to_status,
                item["version"],
                _utc_now(),
            ),
        )


def search_confirmed_project_memory(
    question: str,
    project_key: str,
    *,
    limit: int = 5,
    db_path: Path = DEFAULT_KNOWLEDGE_MEMORY_DB_PATH,
) -> list[dict[str, Any]]:
    if not normalize_project_key(project_key):
        return []
    return KnowledgeMemoryStore(db_path).search_confirmed(
        question,
        project_key,
        limit=limit,
    )


def _require_project_key(value: object) -> str:
    normalized = normalize_project_key(value)
    if not normalized:
        raise KnowledgeMemoryError("缺少有效 project_key")
    return normalized


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_optional_datetime(value: object, field_name: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = _parse_datetime(text)
    if not parsed:
        raise KnowledgeMemoryError(f"{field_name} 不是有效时间")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _search_terms(text: str) -> set[str]:
    clean = re.sub(r"\s+", "", text.lower())
    terms = {
        token
        for token in re.findall(r"[a-z0-9.%_-]{2,}|[\u4e00-\u9fff]{2,}", clean)
        if token
    }
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", clean))
    for width in (2, 3, 4):
        terms.update(
            chinese[index : index + width]
            for index in range(max(0, len(chinese) - width + 1))
        )
    return terms


def _memory_score(item: dict[str, Any], query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    weighted_fields = (
        ("title", 4.0),
        ("question", 3.0),
        ("conclusion", 3.0),
        ("conditions", 2.0),
        ("exceptions", 1.0),
        ("evidence_summary", 1.0),
    )
    score = 0.0
    for field, weight in weighted_fields:
        text = re.sub(r"\s+", "", str(item.get(field) or "").lower())
        score += sum(weight for term in query_terms if term in text)
    return score
