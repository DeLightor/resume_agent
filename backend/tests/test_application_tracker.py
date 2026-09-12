"""US-37 投递追踪 API 契约测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient


def _init_client() -> TestClient:
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database
    from resume_agent.main import app

    init_database(settings.sqlite_path)
    return TestClient(app)


def _create_source_node(client: TestClient, content: dict[str, Any] | None = None) -> str:
    node = client.post(
        "/api/tree/node",
        json={"parent_id": "master", "node_type": "branch", "title": "后端方向", "direction": "后端"},
    ).json()["data"]
    if content is not None:
        saved = client.put(
            f"/api/tree/node/{node['node_id']}",
            json={"content_json": content, "expected_version": node["version"]},
        )
        assert saved.status_code == 200
    return str(node["node_id"])


def _create_application(client: TestClient, node_id: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "resume_node_id": node_id,
        "company": "OpenAI",
        "role": "Backend Engineer",
        "status": "applied",
        "jd_snapshot": {"company": "OpenAI", "job_title": "Backend Engineer"},
    }
    payload.update(extra)
    response = client.post("/api/applications", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_init_database_creates_application_tables() -> None:
    _init_client()
    from resume_agent.db.init_db import list_tables

    tables = set(list_tables())
    assert {"application_records", "application_events"} <= tables


def test_create_freezes_server_side_node_snapshot() -> None:
    client = _init_client()
    source = _create_source_node(client, {"personal_info": {"name": "张三"}})

    created = _create_application(client, source)

    assert created["resume_node_id"] == source
    assert created["resume_version"] == 1
    assert created["resume_snapshot"] == {"personal_info": {"name": "张三"}}
    assert created["version"] == 0
    assert "resume_snapshot" not in created["jd_snapshot"]

    node = client.get(f"/api/tree/{source}").json()["data"]
    client.put(
        f"/api/tree/node/{source}",
        json={"content_json": {"personal_info": {"name": "李四"}}, "expected_version": node["version"]},
    )
    detail = client.get(f"/api/applications/{created['id']}").json()["data"]
    assert detail["resume_snapshot"] == {"personal_info": {"name": "张三"}}

    client.delete(f"/api/tree/node/{source}")
    retained = client.get(f"/api/applications/{created['id']}").json()["data"]
    assert retained["source_node_deleted"] is True
    assert retained["resume_snapshot"] == {"personal_info": {"name": "张三"}}


def test_create_rejects_missing_or_deleted_source_node_and_accepts_empty_content() -> None:
    client = _init_client()
    missing = client.post(
        "/api/applications", json={"resume_node_id": "missing", "company": "OpenAI", "role": "Engineer"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NODE_NOT_FOUND"

    source = _create_source_node(client)
    empty_snapshot = _create_application(client, source)
    assert empty_snapshot["resume_snapshot"] == {}

    client.delete(f"/api/tree/node/{source}")
    deleted = client.post(
        "/api/applications", json={"resume_node_id": source, "company": "OpenAI", "role": "Engineer"}
    )
    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "NODE_NOT_FOUND"


def test_update_requires_current_version_and_appends_ordered_events() -> None:
    client = _init_client()
    created = _create_application(client, _create_source_node(client))

    updated = client.put(
        f"/api/applications/{created['id']}",
        json={
            "expected_version": created["version"],
            "status": "interview",
            "status_change_note": "一面通过",
            "follow_up_at": "2030-01-03T09:00:00Z",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["version"] == 1

    detail = client.get(f"/api/applications/{created['id']}").json()["data"]
    events = detail["events"]
    assert [event["event_type"] for event in events] == ["created", "status_changed", "updated"]
    assert events[1]["from_status"] == "applied"
    assert events[1]["to_status"] == "interview"
    assert events[1]["note"] == "一面通过"
    assert events[2]["changed_fields"] == ["follow_up_at"]

    stale = client.put(
        f"/api/applications/{created['id']}",
        json={"expected_version": created["version"], "notes": "旧页面覆盖"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"

    no_op = client.put(
        f"/api/applications/{created['id']}",
        json={"expected_version": 1, "status": "interview"},
    )
    assert no_op.status_code == 200
    assert no_op.json()["data"]["version"] == 1
    assert len(client.get(f"/api/applications/{created['id']}").json()["data"]["events"]) == 3


def test_validation_and_list_filter_contract() -> None:
    client = _init_client()
    source = _create_source_node(client)
    bad = client.post(
        "/api/applications",
        json={"resume_node_id": source, "company": "", "role": "Engineer", "status": "unknown"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_ARGUMENT"

    created = _create_application(client, source)
    invalid_filter = client.get("/api/applications?status=invalid")
    assert invalid_filter.status_code == 400
    assert invalid_filter.json()["error"]["code"] == "INVALID_ARGUMENT"

    before_now = (datetime.now(UTC) - timedelta(minutes=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    updated = client.put(
        f"/api/applications/{created['id']}",
        json={"expected_version": created["version"], "follow_up_at": before_now},
    ).json()["data"]
    items = client.get("/api/applications?status=applied").json()["data"]
    assert items[0]["id"] == created["id"]
    assert items[0]["is_overdue"] is True
    assert updated["version"] == 1


def test_soft_delete_restore_uses_version_and_deleted_filter() -> None:
    client = _init_client()
    created = _create_application(client, _create_source_node(client))

    deleted = client.request(
        "DELETE", f"/api/applications/{created['id']}", json={"expected_version": created["version"]}
    )
    assert deleted.status_code == 200
    deleted_record = deleted.json()["data"]
    assert deleted_record["deleted_at"] is not None
    assert client.get("/api/applications").json()["data"] == []
    only_deleted = client.get("/api/applications?deleted=only").json()["data"]
    assert [item["id"] for item in only_deleted] == [created["id"]]

    stale_restore = client.post(
        f"/api/applications/{created['id']}/restore", json={"expected_version": created["version"]}
    )
    assert stale_restore.status_code == 409
    restored = client.post(
        f"/api/applications/{created['id']}/restore", json={"expected_version": deleted_record["version"]}
    )
    assert restored.status_code == 200
    assert restored.json()["data"]["deleted_at"] is None
    events = client.get(f"/api/applications/{created['id']}").json()["data"]["events"]
    assert [event["event_type"] for event in events][-2:] == ["deleted", "restored"]


def test_restore_rejects_record_deleted_more_than_30_days() -> None:
    client = _init_client()
    created = _create_application(client, _create_source_node(client))
    deleted = client.request(
        "DELETE", f"/api/applications/{created['id']}", json={"expected_version": created["version"]}
    ).json()["data"]

    from resume_agent.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE application_records SET deleted_at='2026-08-01T00:00:00Z' WHERE id=?",
            (created["id"],),
        )
    expired = client.post(
        f"/api/applications/{created['id']}/restore", json={"expected_version": deleted["version"]}
    )
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "RESTORE_EXPIRED"
