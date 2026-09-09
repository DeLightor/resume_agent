"""段落排序 API 测试：US-13。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _init_db() -> None:
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database

    init_database(settings.sqlite_path)


def test_get_default_section_order() -> None:
    """节点没有 section_order 时返回默认 8 段。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.get("/api/tree/node/master/section-order")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    sections = body["data"]["sections"]
    assert len(sections) == 8
    assert sections[0]["key"] == "summary"
    assert sections[1]["key"] == "experience"
    assert sections[5]["key"] == "awards"
    assert sections[5]["visible"] is False


def test_update_section_order() -> None:
    """更新段落顺序。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    sections = [
        {"key": "projects", "title": "项目经历", "visible": True},
        {"key": "summary", "title": "自我评价", "visible": True},
        {"key": "experience", "title": "工作经历", "visible": False},
        {"key": "skills", "title": "技能总结", "visible": True},
        {"key": "education", "title": "教育背景", "visible": True},
        {"key": "awards", "title": "获奖经历", "visible": False},
        {"key": "publications", "title": "论文/专利", "visible": False},
        {"key": "certificates", "title": "证书", "visible": False},
    ]
    resp = client.put("/api/tree/node/master/section-order", json={"sections": sections})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    result = body["data"]["sections"]
    assert result[0]["key"] == "projects"
    assert result[2]["visible"] is False


def test_reorder() -> None:
    """拖拽重新排序后获取确认。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 更新顺序：education 放到第一位
    sections = [
        {"key": "education", "title": "教育背景", "visible": True},
        {"key": "summary", "title": "自我评价", "visible": True},
        {"key": "experience", "title": "工作经历", "visible": True},
        {"key": "projects", "title": "项目经历", "visible": True},
        {"key": "skills", "title": "技能总结", "visible": True},
        {"key": "awards", "title": "获奖经历", "visible": False},
        {"key": "publications", "title": "论文/专利", "visible": False},
        {"key": "certificates", "title": "证书", "visible": False},
    ]
    client.put("/api/tree/node/master/section-order", json={"sections": sections})

    resp = client.get("/api/tree/node/master/section-order")
    body = resp.json()
    assert body["data"]["sections"][0]["key"] == "education"


def test_toggle_visible() -> None:
    """切换显示/隐藏。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    sections = [
        {"key": "summary", "title": "自我评价", "visible": False},
        {"key": "experience", "title": "工作经历", "visible": True},
        {"key": "projects", "title": "项目经历", "visible": True},
        {"key": "skills", "title": "技能总结", "visible": True},
        {"key": "education", "title": "教育背景", "visible": True},
        {"key": "awards", "title": "获奖经历", "visible": True},
        {"key": "publications", "title": "论文/专利", "visible": False},
        {"key": "certificates", "title": "证书", "visible": False},
    ]
    resp = client.put("/api/tree/node/master/section-order", json={"sections": sections})

    body = resp.json()
    result = body["data"]["sections"]
    assert result[0]["visible"] is False  # summary 隐藏
    assert result[5]["visible"] is True  # awards 显示


def test_get_nonexistent_node() -> None:
    """获取不存在节点的段落顺序返回错误。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.get("/api/tree/node/nonexistent-node/section-order")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False


def test_inherit_on_create() -> None:
    """创建子节点时继承父节点 section_order。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 1. 设置 master 的 section_order
    sections = [
        {"key": "education", "title": "教育背景", "visible": True},
        {"key": "summary", "title": "自我评价", "visible": True},
        {"key": "experience", "title": "工作经历", "visible": False},
        {"key": "projects", "title": "项目经历", "visible": True},
        {"key": "skills", "title": "技能总结", "visible": True},
        {"key": "awards", "title": "获奖经历", "visible": False},
        {"key": "publications", "title": "论文/专利", "visible": False},
        {"key": "certificates", "title": "证书", "visible": False},
    ]
    client.put("/api/tree/node/master/section-order", json={"sections": sections})

    # 2. 创建 branch 子节点
    resp = client.post(
        "/api/tree/node",
        json={
            "parent_id": "master",
            "node_type": "branch",
            "title": "测试方向",
            "direction": "test",
        },
    )
    branch_id = resp.json()["data"]["node_id"]

    # 3. 检查子节点是否继承了 section_order
    resp = client.get(f"/api/tree/node/{branch_id}/section-order")
    body = resp.json()
    result = body["data"]["sections"]
    assert result[0]["key"] == "education"
    assert result[2]["visible"] is False  # experience 隐藏


def test_missing_sections_autofill() -> None:
    """缺少的段落自动补全。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 只传 3 段
    sections = [
        {"key": "projects", "title": "项目经历", "visible": True},
        {"key": "summary", "title": "自我评价", "visible": True},
        {"key": "skills", "title": "技能总结", "visible": True},
    ]
    resp = client.put("/api/tree/node/master/section-order", json={"sections": sections})
    assert resp.status_code == 200

    # GET 时应该自动补全到 8 段
    resp = client.get("/api/tree/node/master/section-order")
    body = resp.json()
    result = body["data"]["sections"]
    assert len(result) == 8
