"""AI 导师学习建议 API 测试：POST /api/tutor/suggest。

用 FastAPI TestClient + 临时 DB（通过 conftest 的 _isolated_env fixture 隔离）。
LLM 未配置时走模板化兜底路径，测试不依赖真实 LLM API。
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _tutor(
    client: TestClient, items: list[dict[str, Any]]
) -> Any:
    """调用 POST /api/tutor/suggest。"""
    return client.post("/api/tutor/suggest", json={"items": items})


# === 测试用例 ===


def test_missing_skills_returned() -> None:
    """missing 状态的技能应该被包含在建议中。"""
    from resume_agent.main import app

    items = [
        {"skill": "Kubernetes", "category": "tech_stack", "status": "missing"},
        {"skill": "Python", "category": "tech_stack", "status": "covered"},
    ]

    client = TestClient(app)
    resp = _tutor(client, items)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    suggestions = body["data"]["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["skill"] == "Kubernetes"
    assert suggestions[0]["status"] == "missing"
    # 模板化建议应包含 learning_path 和 resources
    assert "learning_path" in suggestions[0]
    assert "resources" in suggestions[0]
    assert len(suggestions[0]["resources"]) > 0


def test_partial_skills_returned() -> None:
    """partial 状态的技能应该被包含在建议中。"""
    from resume_agent.main import app

    items = [
        {"skill": "Go", "category": "tech_stack", "status": "partial"},
    ]

    client = TestClient(app)
    resp = _tutor(client, items)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    suggestions = body["data"]["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["skill"] == "Go"
    assert suggestions[0]["status"] == "partial"


def test_covered_skills_filtered_out() -> None:
    """covered 状态的技能应被过滤掉。"""
    from resume_agent.main import app

    items = [
        {"skill": "Docker", "category": "tech_stack", "status": "covered"},
        {"skill": "Rust", "category": "tech_stack", "status": "missing"},
    ]

    client = TestClient(app)
    resp = _tutor(client, items)

    assert resp.status_code == 200
    body = resp.json()
    suggestions = body["data"]["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["skill"] == "Rust"


def test_empty_items_returns_empty() -> None:
    """空 items 返回空建议列表。"""
    from resume_agent.main import app

    client = TestClient(app)
    resp = _tutor(client, [])

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["suggestions"] == []


def test_all_covered_returns_empty() -> None:
    """全部 covered 时返回空建议列表。"""
    from resume_agent.main import app

    items = [
        {"skill": "Java", "category": "tech_stack", "status": "covered"},
        {"skill": "Spring", "category": "tech_stack", "status": "covered"},
    ]

    client = TestClient(app)
    resp = _tutor(client, items)

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["suggestions"] == []


def test_llm_not_configured_fallback() -> None:
    """LLM 未配置时返回模板化建议（不报错）。"""
    from resume_agent.main import app

    items = [
        {"skill": "Kafka", "category": "tech_stack", "status": "missing"},
    ]

    client = TestClient(app)
    resp = _tutor(client, items)

    assert resp.status_code == 200
    body = resp.json()
    suggestions = body["data"]["suggestions"]
    assert len(suggestions) == 1
    # 模板化建议应包含完整的结构
    s = suggestions[0]
    assert s["skill"] == "Kafka"
    assert "learning_path" in s
    assert "concept" in s["learning_path"]
    assert "practice" in s["learning_path"]
    assert "validation" in s["learning_path"]
    assert "resources" in s
    assert len(s["resources"]) == 4
    # 每个资源应包含 type / title / url / description
    for r in s["resources"]:
        assert "type" in r
        assert "title" in r
        assert "url" in r
        assert "description" in r


def test_max_skills_limit() -> None:
    """超过 10 项技能时只处理前 10 项。"""
    from resume_agent.main import app

    items = [
        {"skill": f"Skill{i}", "category": "tech_stack", "status": "missing"}
        for i in range(15)
    ]

    client = TestClient(app)
    resp = _tutor(client, items)

    assert resp.status_code == 200
    body = resp.json()
    suggestions = body["data"]["suggestions"]
    assert len(suggestions) == 10


def test_response_structure() -> None:
    """验证响应结构完整性。"""
    from resume_agent.main import app

    items = [
        {"skill": "Redis", "category": "tech_stack", "status": "partial"},
    ]

    client = TestClient(app)
    resp = _tutor(client, items)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "data" in body
    assert "suggestions" in body["data"]

    s = body["data"]["suggestions"][0]
    assert "skill" in s
    assert "status" in s
    assert "learning_path" in s
    assert isinstance(s["learning_path"], dict)
    assert "concept" in s["learning_path"]
    assert "practice" in s["learning_path"]
    assert "validation" in s["learning_path"]
    assert "resources" in s
    assert isinstance(s["resources"], list)


def test_invalid_request_no_items() -> None:
    """空 items 列表返回空建议（非 error）。"""
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.post("/api/tutor/suggest", json={"items": []})

    # 空 items 返回空 suggestions，不是 error
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["suggestions"] == []


def test_missing_items_field() -> None:
    """缺少 items 字段返回 422 验证错误。"""
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.post("/api/tutor/suggest", json={})

    assert resp.status_code == 422


def test_mixed_statuses() -> None:
    """混合状态时只处理 missing 和 partial。"""
    from resume_agent.main import app

    items = [
        {"skill": "Linux", "category": "tech_stack", "status": "covered"},
        {"skill": "Nginx", "category": "tech_stack", "status": "partial"},
        {"skill": "Redis", "category": "tech_stack", "status": "missing"},
        {"skill": "MySQL", "category": "tech_stack", "status": "covered"},
        {"skill": "MongoDB", "category": "tech_stack", "status": "missing"},
    ]

    client = TestClient(app)
    resp = _tutor(client, items)

    assert resp.status_code == 200
    body = resp.json()
    suggestions = body["data"]["suggestions"]
    assert len(suggestions) == 3
    skills_in_suggestions = [s["skill"] for s in suggestions]
    assert "Nginx" in skills_in_suggestions
    assert "Redis" in skills_in_suggestions
    assert "MongoDB" in skills_in_suggestions
    assert "Linux" not in skills_in_suggestions
    assert "MySQL" not in skills_in_suggestions
