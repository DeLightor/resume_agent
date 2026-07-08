"""完整性检测 API 测试：US-15。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _init_db() -> None:
    from resume_agent.db.init_db import init_database
    from resume_agent.config import settings

    init_database(settings.sqlite_path)


def test_check_completeness_empty_node() -> None:
    """空节点的完整性评分应该很低。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.post("/api/completeness/check", json={"node_id": "master"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["score"] < 50
    checks = body["data"]["checks"]
    assert len(checks) == 8


def test_check_completeness_node_not_found() -> None:
    """节点不存在返回错误。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.post("/api/completeness/check", json={"node_id": "nonexistent"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False


def test_update_section_summary() -> None:
    """编辑 summary 段落。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.put(
        "/api/tree/node/master/section",
        json={"section": "summary", "data": "这是一个测试自我评价，内容足够长，超过二十个字"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True

    # 验证保存
    resp2 = client.post("/api/completeness/check", json={"node_id": "master"})
    body2 = resp2.json()
    summary_check = next(
        c for c in body2["data"]["checks"] if c["field"] == "summary"
    )
    assert summary_check["status"] == "ok"


def test_update_section_invalid() -> None:
    """无效段落返回错误。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.put(
        "/api/tree/node/master/section",
        json={"section": "invalid", "data": {}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False


def test_update_section_experience() -> None:
    """编辑 experience 段落。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    experience_data = [
        {
            "role": "后端工程师",
            "company": "测试公司",
            "period": "2023-2024",
            "highlights": ["负责API开发", "优化数据库"],
        }
    ]
    resp = client.put(
        "/api/tree/node/master/section",
        json={"section": "experience", "data": experience_data},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True

    # 验证完整性检测
    resp2 = client.post("/api/completeness/check", json={"node_id": "master"})
    body2 = resp2.json()
    exp_check = next(
        c for c in body2["data"]["checks"] if c["field"] == "experience"
    )
    assert exp_check["status"] == "ok"
    assert exp_check.get("count") == 1
