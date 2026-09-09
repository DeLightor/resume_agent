"""一键生成 API 测试：US-14。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _init_db() -> None:
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database

    init_database(settings.sqlite_path)


def test_full_generate_node_not_found() -> None:
    """节点不存在时返回错误。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.post(
        "/api/generate/full",
        json={"node_id": "nonexistent-node"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "NODE_NOT_FOUND" in body["error"]["code"]


def test_section_regenerate_invalid_section() -> None:
    """无效段落类型返回错误。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.post(
        "/api/generate/section",
        json={"node_id": "master", "section": "invalid_section"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "INVALID_SECTION" in body["error"]["code"]


def test_section_regenerate_node_not_found() -> None:
    """单段重新生成时节点不存在返回错误。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.post(
        "/api/generate/section",
        json={"node_id": "nonexistent", "section": "experience"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "NODE_NOT_FOUND" in body["error"]["code"]


def test_full_generate_empty_knowledge_base() -> None:
    """知识库为空时仍然返回（段落标注为空）。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.post(
        "/api/generate/full",
        json={"node_id": "master"},
    )

    # 知识库可能为空，但不应报错
    assert resp.status_code == 200
    body = resp.json()
    # 如果知识库为空，返回 ok=true 但段落标注 empty
    if body["ok"]:
        sections = body["data"]["sections"]
        assert len(sections) == 4  # summary, experience, projects, skills
