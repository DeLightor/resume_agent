"""US-33 API contract: direct-parent baselines, decisions, and stale protection."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _node(client: TestClient, node_id: str) -> dict:
    return client.get(f"/api/tree/{node_id}").json()["data"]


def _write(client: TestClient, node_id: str, content: dict) -> dict:
    current = _node(client, node_id)
    response = client.put(f"/api/tree/node/{node_id}", json={"content_json": content, "expected_version": current["version"]})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _child(client: TestClient) -> str:
    response = client.post("/api/tree/node", json={"parent_id": "master", "node_type": "branch", "title": "后端", "direction": "后端"})
    assert response.json()["ok"]
    return response.json()["data"]["node_id"]


def test_project_bullet_change_requires_explicit_decision_and_preserves_local_edit() -> None:
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database
    from resume_agent.main import app

    init_database(settings.sqlite_path)
    client = TestClient(app)
    parent = {"experience": [{"company": "A", "role": "工程师", "bullets": ["搭建服务", "降低延迟"]}], "projects": [], "skills": []}
    _write(client, "master", parent)
    child_id = _child(client)
    _write(client, child_id, parent)
    child = _node(client, child_id)
    child["content_json"]["experience"][0]["bullets"].insert(1, "本地补充")
    _write(client, child_id, child["content_json"])
    parent["experience"][0]["bullets"][0] = "主导搭建服务"
    source = _write(client, "master", parent)

    snapshot = client.get(f"/api/tree/node/{child_id}/upstream-changes").json()["data"]
    assert snapshot["source_node_id"] == "master"
    assert snapshot["upstream_version"] == source["version"]
    assert snapshot["count"] == 1
    field, change = next(iter(snapshot["changes"].items()))
    assert change["section"] == "experience"
    assert change["conflict"] is False

    current = _node(client, child_id)
    accepted = client.post(f"/api/tree/node/{child_id}/merge", headers={"If-Match": str(current["version"])}, json={"field": field, "upstream_version": source["version"]})
    assert accepted.status_code == 200, accepted.text
    assert _node(client, child_id)["content_json"]["experience"][0]["bullets"] == ["主导搭建服务", "本地补充", "降低延迟"]


def test_conflicting_project_change_can_be_retained_and_is_not_shown_again() -> None:
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database
    from resume_agent.main import app

    init_database(settings.sqlite_path)
    client = TestClient(app)
    original = {"projects": [{"name": "P", "description": "初版"}], "experience": [], "skills": []}
    _write(client, "master", original)
    child_id = _child(client)
    _write(client, child_id, original)
    local = {"projects": [{"name": "P", "description": "本地改写"}], "experience": [], "skills": []}
    _write(client, child_id, local)
    upstream = {"projects": [{"name": "P", "description": "上游改写"}], "experience": [], "skills": []}
    source = _write(client, "master", upstream)
    snapshot = client.get(f"/api/tree/node/{child_id}/upstream-changes").json()["data"]
    field, change = next(iter(snapshot["changes"].items()))
    assert change["conflict"] is True
    current = _node(client, child_id)
    rejected = client.post(f"/api/tree/node/{child_id}/reject", headers={"If-Match": str(current["version"])}, json={"field": field, "upstream_version": source["version"]})
    assert rejected.status_code == 200, rejected.text
    assert _node(client, child_id)["content_json"]["projects"] == local["projects"]
    assert client.get(f"/api/tree/node/{child_id}/upstream-changes").json()["data"]["count"] == 0


def test_stale_parent_version_rejects_a_displayed_decision() -> None:
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database
    from resume_agent.main import app

    init_database(settings.sqlite_path)
    client = TestClient(app)
    _write(client, "master", {"skills": ["Python"], "experience": [], "projects": []})
    child_id = _child(client)
    _write(client, child_id, {"skills": ["Python"], "experience": [], "projects": []})
    source = _write(client, "master", {"skills": ["Python", "SQL"], "experience": [], "projects": []})
    snapshot = client.get(f"/api/tree/node/{child_id}/upstream-changes").json()["data"]
    field = next(iter(snapshot["changes"]))
    _write(client, "master", {"skills": ["Python", "SQL", "Go"], "experience": [], "projects": []})
    current = _node(client, child_id)
    response = client.post(f"/api/tree/node/{child_id}/merge", headers={"If-Match": str(current["version"])}, json={"field": field, "upstream_version": source["version"]})
    assert response.status_code == 409


def test_manual_child_convergence_clears_an_obsolete_prompt() -> None:
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database
    from resume_agent.main import app

    init_database(settings.sqlite_path)
    client = TestClient(app)
    content = {"skills": ["Python"], "experience": [], "projects": []}
    _write(client, "master", content)
    child_id = _child(client)
    content = {"skills": ["Python", "SQL"], "experience": [], "projects": []}
    _write(client, "master", content)
    assert client.get(f"/api/tree/node/{child_id}/upstream-changes").json()["data"]["count"] == 1
    _write(client, child_id, content)
    snapshot = client.get(f"/api/tree/node/{child_id}/upstream-changes").json()["data"]
    assert snapshot["has_upstream_update"] is False
    assert snapshot["count"] == 0
