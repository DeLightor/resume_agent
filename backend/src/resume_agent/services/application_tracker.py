"""US-37 投递记录的事务性存储服务。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from resume_agent.db.connection import get_connection

APPLICATION_STATUSES = frozenset(
    {"draft", "applied", "hr_screen", "interview", "offer", "rejected", "withdrawn"}
)
FINISHED_STATUSES = frozenset({"offer", "rejected", "withdrawn"})
OPTIONAL_FIELDS = frozenset({"job_url", "jd_snapshot", "next_action", "follow_up_at", "notes"})
MUTABLE_FIELDS = frozenset({"company", "role", "status", *OPTIONAL_FIELDS})


class ApplicationError(Exception):
    """An API-safe domain error for application tracking."""

    def __init__(self, status_code: int, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _utc_string(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ApplicationError(400, "INVALID_ARGUMENT", f"{field_name} 必须是带时区的 RFC 3339 时间")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApplicationError(400, "INVALID_ARGUMENT", f"{field_name} 格式无效") from exc
    if parsed.tzinfo is None:
        raise ApplicationError(400, "INVALID_ARGUMENT", f"{field_name} 必须包含时区")
    return _utc_string(parsed)


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApplicationError(400, "INVALID_ARGUMENT", f"{field_name} 不能为空")
    return value.strip()


def _require_version(value: Any) -> int:
    if value is None:
        raise ApplicationError(428, "VERSION_REQUIRED", "保存需要记录版本，请刷新后重试")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ApplicationError(400, "INVALID_ARGUMENT", "expected_version 必须是非负整数")
    return value


def _validate_status(value: Any) -> str:
    if not isinstance(value, str) or value not in APPLICATION_STATUSES:
        raise ApplicationError(400, "INVALID_ARGUMENT", "status 不是支持的投递状态")
    return value


def _json_object(value: Any, field_name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ApplicationError(400, "INVALID_ARGUMENT", f"{field_name} 必须是对象")
    return value


def _decode_json(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "event_type": row["event_type"],
        "from_status": row["from_status"],
        "to_status": row["to_status"],
        "note": row["note"],
        "changed_fields": _decode_json(row["changed_fields_json"], []),
        "created_at": row["created_at"],
    }


def _record(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    follow_up = _parse_utc(row["follow_up_at"], field_name="follow_up_at") if row["follow_up_at"] else None
    source_deleted = bool(row.get("source_deleted"))
    return {
        "id": row["id"],
        "resume_node_id": row["resume_node_id"],
        "resume_node_title": row["resume_node_title"],
        "source_node_deleted": source_deleted,
        "resume_version": row["resume_version"],
        "resume_snapshot": _decode_json(row["resume_snapshot_json"], {}),
        "company": row["company"],
        "role": row["role"],
        "job_url": row["job_url"],
        "jd_snapshot": _decode_json(row["jd_snapshot_json"], None),
        "status": row["status"],
        "next_action": row["next_action"],
        "follow_up_at": follow_up,
        "notes": row["notes"],
        "version": row["version"],
        "deleted_at": row["deleted_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "is_overdue": bool(
            follow_up
            and datetime.fromisoformat(follow_up.replace("Z", "+00:00")) < now
            and row["deleted_at"] is None
            and row["status"] not in FINISHED_STATUSES
        ),
    }


def _get_record(conn: sqlite3.Connection, application_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT a.*, CASE WHEN n.node_id IS NULL OR n.deleted_at IS NOT NULL THEN 1 ELSE 0 END AS source_deleted
        FROM application_records a
        LEFT JOIN resume_versions n ON n.node_id=a.resume_node_id
        WHERE a.id=?
        """,
        (application_id,),
    ).fetchone()
    if row is None:
        raise ApplicationError(404, "APPLICATION_NOT_FOUND", "投递记录不存在")
    return row


def _append_event(
    conn: sqlite3.Connection,
    application_id: str,
    event_type: str,
    timestamp: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
    changed_fields: list[str] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO application_events
        (application_id, event_type, from_status, to_status, note, changed_fields_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (application_id, event_type, from_status, to_status, note, json.dumps(changed_fields or []), timestamp),
    )


def create_application(payload: dict[str, Any], now_fn: Callable[[], datetime] = utc_now) -> dict[str, Any]:
    node_id = _require_text(payload.get("resume_node_id"), "resume_node_id")
    company = _require_text(payload.get("company"), "company")
    role = _require_text(payload.get("role"), "role")
    status = _validate_status(payload.get("status", "draft"))
    jd_snapshot = _json_object(payload.get("jd_snapshot"), "jd_snapshot")
    optional = _validated_optional_fields(payload, creating=True)
    timestamp = _utc_string(now_fn())

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        node = conn.execute(
            "SELECT node_id, title, version, content_json FROM resume_versions WHERE node_id=? AND deleted_at IS NULL",
            (node_id,),
        ).fetchone()
        if node is None:
            raise ApplicationError(404, "NODE_NOT_FOUND", "来源简历节点不存在或已在回收站")
        snapshot = _decode_json(node["content_json"], {})
        if not isinstance(snapshot, dict):
            snapshot = {}
        application_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO application_records (
                id, resume_node_id, resume_node_title, resume_version, resume_snapshot_json,
                company, role, job_url, jd_snapshot_json, status, next_action, follow_up_at,
                notes, version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                application_id, node_id, node["title"], node["version"], json.dumps(snapshot, ensure_ascii=False),
                company, role, optional["job_url"], json.dumps(jd_snapshot, ensure_ascii=False) if jd_snapshot is not None else None,
                status, optional["next_action"], optional["follow_up_at"], optional["notes"], timestamp, timestamp,
            ),
        )
        _append_event(conn, application_id, "created", timestamp, to_status=status)
        row = _get_record(conn, application_id)
    return _record(row, now_fn())


def _validated_optional_fields(payload: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    values: dict[str, Any] = dict.fromkeys(OPTIONAL_FIELDS)
    for field in OPTIONAL_FIELDS:
        if not creating and field not in payload:
            continue
        value = payload.get(field)
        if field == "follow_up_at":
            values[field] = _parse_utc(value, field_name=field)
        elif field == "jd_snapshot":
            values[field] = _json_object(value, field)
        elif value is not None and not isinstance(value, str):
            raise ApplicationError(400, "INVALID_ARGUMENT", f"{field} 必须是字符串或 null")
        else:
            values[field] = value.strip() if isinstance(value, str) else None
    return values


def list_applications(status: str | None, deleted: str, now_fn: Callable[[], datetime] = utc_now) -> list[dict[str, Any]]:
    if status is not None:
        _validate_status(status)
    if deleted not in {"exclude", "only", "include"}:
        raise ApplicationError(400, "INVALID_ARGUMENT", "deleted 必须是 exclude、only 或 include")
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None:
        clauses.append("a.status=?")
        params.append(status)
    if deleted == "exclude":
        clauses.append("a.deleted_at IS NULL")
    elif deleted == "only":
        clauses.append("a.deleted_at IS NOT NULL")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT a.*, CASE WHEN n.node_id IS NULL OR n.deleted_at IS NOT NULL THEN 1 ELSE 0 END AS source_deleted
            FROM application_records a LEFT JOIN resume_versions n ON n.node_id=a.resume_node_id
            {where} ORDER BY a.updated_at DESC, a.id DESC
            """,
            params,
        ).fetchall()
    now = now_fn()
    return [_record(row, now) for row in rows]


def get_application(application_id: str, now_fn: Callable[[], datetime] = utc_now) -> dict[str, Any]:
    with get_connection() as conn:
        row = _get_record(conn, application_id)
        events = conn.execute(
            "SELECT * FROM application_events WHERE application_id=? ORDER BY id ASC", (application_id,)
        ).fetchall()
    result = _record(row, now_fn())
    result["events"] = [_event(event) for event in events]
    return result


def update_application(
    application_id: str, payload: dict[str, Any], now_fn: Callable[[], datetime] = utc_now
) -> dict[str, Any]:
    expected_version = _require_version(payload.get("expected_version"))
    unsupported = set(payload) - (MUTABLE_FIELDS | {"expected_version", "status_change_note"})
    if unsupported:
        raise ApplicationError(400, "INVALID_ARGUMENT", f"不支持更新字段: {', '.join(sorted(unsupported))}")
    timestamp = _utc_string(now_fn())
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _get_record(conn, application_id)
        if row["deleted_at"] is not None:
            raise ApplicationError(409, "APPLICATION_DELETED", "已删除记录不能编辑")
        if row["version"] != expected_version:
            raise ApplicationError(409, "VERSION_CONFLICT", "记录已更新，请刷新后重试", version=row["version"])
        updates: dict[str, Any] = {}
        changed_fields: list[str] = []
        if "company" in payload:
            company = _require_text(payload["company"], "company")
            if company != row["company"]:
                updates["company"] = company
                changed_fields.append("company")
        if "role" in payload:
            role = _require_text(payload["role"], "role")
            if role != row["role"]:
                updates["role"] = role
                changed_fields.append("role")
        for field, value in _validated_optional_fields(payload, creating=False).items():
            if field not in payload:
                continue
            column = "jd_snapshot_json" if field == "jd_snapshot" else field
            checked = value
            database_value = json.dumps(checked, ensure_ascii=False) if field == "jd_snapshot" and checked is not None else checked
            if database_value != row[column]:
                updates[column] = database_value
                changed_fields.append(field)
        next_status = row["status"]
        status_changed = False
        if "status" in payload:
            next_status = _validate_status(payload["status"])
            status_changed = next_status != row["status"]
            if status_changed:
                updates["status"] = next_status
        if not updates:
            return _record(row, now_fn())
        assignments = ", ".join(f"{column}=?" for column in updates)
        values = list(updates.values()) + [timestamp, application_id, expected_version]
        cursor = conn.execute(
            f"UPDATE application_records SET {assignments}, version=version+1, updated_at=? WHERE id=? AND version=? AND deleted_at IS NULL",
            values,
        )
        if cursor.rowcount != 1:
            raise ApplicationError(409, "VERSION_CONFLICT", "记录已更新，请刷新后重试")
        if status_changed:
            note = payload.get("status_change_note")
            if note is not None and not isinstance(note, str):
                raise ApplicationError(400, "INVALID_ARGUMENT", "status_change_note 必须是字符串")
            _append_event(conn, application_id, "status_changed", timestamp, from_status=row["status"], to_status=next_status, note=note.strip() if isinstance(note, str) else None)
        if changed_fields:
            _append_event(conn, application_id, "updated", timestamp, changed_fields=changed_fields)
        updated = _get_record(conn, application_id)
    return _record(updated, now_fn())


def _change_deleted_state(
    application_id: str, expected_version: Any, *, restore: bool, now_fn: Callable[[], datetime] = utc_now
) -> dict[str, Any]:
    version = _require_version(expected_version)
    now = now_fn()
    timestamp = _utc_string(now)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _get_record(conn, application_id)
        if row["version"] != version:
            raise ApplicationError(409, "VERSION_CONFLICT", "记录已更新，请刷新后重试", version=row["version"])
        if restore:
            if row["deleted_at"] is None:
                raise ApplicationError(409, "APPLICATION_ACTIVE", "记录尚未删除")
            deleted_at = datetime.fromisoformat(row["deleted_at"].replace("Z", "+00:00"))
            if now - deleted_at > timedelta(days=30):
                raise ApplicationError(410, "RESTORE_EXPIRED", "已超过 30 天恢复期限")
            cursor = conn.execute(
                "UPDATE application_records SET deleted_at=NULL, version=version+1, updated_at=? WHERE id=? AND version=?",
                (timestamp, application_id, version),
            )
            event_type = "restored"
        else:
            if row["deleted_at"] is not None:
                raise ApplicationError(409, "APPLICATION_DELETED", "记录已删除")
            cursor = conn.execute(
                "UPDATE application_records SET deleted_at=?, version=version+1, updated_at=? WHERE id=? AND version=? AND deleted_at IS NULL",
                (timestamp, timestamp, application_id, version),
            )
            event_type = "deleted"
        if cursor.rowcount != 1:
            raise ApplicationError(409, "VERSION_CONFLICT", "记录已更新，请刷新后重试")
        _append_event(conn, application_id, event_type, timestamp)
        updated = _get_record(conn, application_id)
    return _record(updated, now_fn())


def delete_application(application_id: str, expected_version: Any) -> dict[str, Any]:
    return _change_deleted_state(application_id, expected_version, restore=False)


def restore_application(application_id: str, expected_version: Any) -> dict[str, Any]:
    return _change_deleted_state(application_id, expected_version, restore=True)
