"""US-8 模板列表 API 测试。"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_templates_returns_list() -> None:
    """GET /api/templates 返回模板列表，字段齐全。"""
    from resume_agent.main import app

    client = TestClient(app)
    response = client.get("/api/templates")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    templates = body["data"]
    assert isinstance(templates, list)
    assert len(templates) == 3

    # 验证每个模板字段齐全
    for tpl in templates:
        assert "id" in tpl
        assert "name" in tpl
        assert "description" in tpl
        assert "theme_color" in tpl
        assert tpl["theme_color"].startswith("#")
        assert tpl["id"]


def test_get_templates_has_modern() -> None:
    """模板列表包含 modern 模板。"""
    from resume_agent.main import app

    client = TestClient(app)
    response = client.get("/api/templates")
    templates = response.json()["data"]

    ids = [t["id"] for t in templates]
    assert "modern" in ids

    modern = next(t for t in templates if t["id"] == "modern")
    assert modern["theme_color"] == "#2563eb"


def test_get_templates_has_classic() -> None:
    """模板列表包含 classic 模板（天宫蓝）。"""
    from resume_agent.main import app

    client = TestClient(app)
    response = client.get("/api/templates")
    templates = response.json()["data"]

    ids = [t["id"] for t in templates]
    assert "classic" in ids

    classic = next(t for t in templates if t["id"] == "classic")
    assert classic["theme_color"] == "#1C487C"


def test_get_templates_has_tech() -> None:
    """模板列表包含 tech 模板（薄荷绿）。"""
    from resume_agent.main import app

    client = TestClient(app)
    response = client.get("/api/templates")
    templates = response.json()["data"]

    ids = [t["id"] for t in templates]
    assert "tech" in ids

    tech = next(t for t in templates if t["id"] == "tech")
    assert tech["theme_color"] == "#0F766E"
