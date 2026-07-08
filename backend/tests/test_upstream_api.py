"""上游变更检测 API 测试：US-17。"""

from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient


def _init_db() -> None:
    """每次测试前清理并重新初始化数据库。"""
    from resume_agent.db.init_db import init_database
    from resume_agent.config import settings

    db_path = settings.sqlite_path
    if os.path.exists(db_path):
        os.remove(db_path)
    init_database(db_path)


def _create_child_node(client: TestClient, parent_id: str, title: str) -> str:
    """创建子节点，返回实际生成的 node_id。"""
    resp = client.post(
        "/api/tree/node",
        json={
            "parent_id": parent_id,
            "node_type": "branch",
            "title": title,
        },
    )
    assert resp.json()["ok"] is True
    return resp.json()["data"]["node_id"]


def _update_personal_info(client: TestClient, node_id: str, pi: dict) -> dict:
    """更新个人信息。"""
    resp = client.put(f"/api/tree/node/{node_id}/personal-info", json=pi)
    return resp.json()


def test_upstream_changes_propagation() -> None:
    """master 修改 personal_info 后，子节点应标记 has_upstream_update。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 1. 创建子节点（继承 master 的 personal_info）
    child_id = _create_child_node(client, "master", "子分支一")

    # 2. 修改 master 的 personal_info
    new_pi = {
        "contact": {
            "name": "新名字",
            "phone": "13800000000",
            "email": "new@test.com",
            "location": "北京",
        },
        "education": [],
        "summary": "新的自我评价",
    }
    result = _update_personal_info(client, "master", new_pi)
    assert result["ok"] is True

    # 3. 检查子节点是否被标记
    resp = client.get(f"/api/tree/node/{child_id}/upstream-changes")
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["has_upstream_update"] is True
    assert body["data"]["count"] > 0


def test_upstream_changes_no_diff() -> None:
    """子节点与 master 相同时不应标记。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 先设置 master 的 personal_info
    pi = {
        "contact": {"name": "测试", "phone": "13900000000", "email": "test@test.com"},
        "education": [],
        "summary": "测试评价",
    }
    _update_personal_info(client, "master", pi)

    # 创建子节点（继承 master 的 personal_info）
    child_id = _create_child_node(client, "master", "子分支二")

    # 再次更新 master（相同内容）→ 子节点已有相同值，不应标记
    _update_personal_info(client, "master", pi)

    resp = client.get(f"/api/tree/node/{child_id}/upstream-changes")
    body = resp.json()
    assert body["data"]["count"] == 0


def test_upstream_changes_get_not_found() -> None:
    """不存在的节点返回错误。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.get("/api/tree/node/nonexistent/upstream-changes")
    body = resp.json()
    assert body["ok"] is False


def test_tree_returns_has_upstream_update() -> None:
    """getTree 返回 has_upstream_update 字段。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 创建子节点
    child_id = _create_child_node(client, "master", "子分支三")

    # 修改 master personal_info
    _update_personal_info(client, "master", {
        "contact": {"name": "传播测试", "phone": "13700000000", "email": "prop@test.com"},
        "education": [],
        "summary": "",
    })

    # 获取树
    resp = client.get("/api/tree")
    body = resp.json()
    nodes = body["data"]["nodes"]
    child = next(n for n in nodes if n["node_id"] == child_id)
    assert child["has_upstream_update"] is True


def test_merge_field() -> None:
    """合并单个字段。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 创建子节点
    child_id = _create_child_node(client, "master", "子分支四")

    # 修改 master personal_info
    _update_personal_info(client, "master", {
        "contact": {"name": "合并测试", "phone": "13600000000", "email": "merge@test.com"},
        "education": [],
        "summary": "合并评价",
    })

    # 合并 contact 字段
    resp = client.post(f"/api/tree/node/{child_id}/merge", json={"field": "contact"})
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["merged"] is True


def test_merge_all() -> None:
    """批量全部接受。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 创建子节点
    child_id = _create_child_node(client, "master", "子分支五")

    # 修改 master personal_info
    _update_personal_info(client, "master", {
        "contact": {"name": "全部合并", "phone": "13500000000", "email": "all@test.com"},
        "education": [],
        "summary": "全部合并评价",
    })

    # 全部接受
    resp = client.post(f"/api/tree/node/{child_id}/merge/all")
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["all_merged"] is True
    assert body["data"]["merged_count"] > 0


def test_reject_field() -> None:
    """拒绝单个字段。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 创建子节点
    child_id = _create_child_node(client, "master", "子分支六")

    # 修改 master personal_info
    _update_personal_info(client, "master", {
        "contact": {"name": "拒绝测试", "phone": "13400000000", "email": "reject@test.com"},
        "education": [],
        "summary": "拒绝评价",
    })

    # 拒绝 contact 字段
    resp = client.post(f"/api/tree/node/{child_id}/reject", json={"field": "contact"})
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["rejected"] is True
    # 还有 summary 字段未处理
    assert body["data"]["remaining_changes"] > 0


def test_reject_all_fields_clears_flag() -> None:
    """拒绝所有字段后清除 has_upstream_update。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 创建子节点
    child_id = _create_child_node(client, "master", "子分支七")

    # 修改 master personal_info（只有 contact 一个字段有变化）
    _update_personal_info(client, "master", {
        "contact": {"name": "清除标记", "phone": "13300000000", "email": "clear@test.com"},
        "education": [],
        "summary": "",
    })

    # 先查看有哪些变更
    resp = client.get(f"/api/tree/node/{child_id}/upstream-changes")
    changes = resp.json()["data"]["changes"]

    # 拒绝所有变更字段
    for field in changes:
        resp = client.post(f"/api/tree/node/{child_id}/reject", json={"field": field})
        body = resp.json()
        assert body["ok"] is True

    # 检查 has_upstream_update 已清除
    resp2 = client.get(f"/api/tree/node/{child_id}/upstream-changes")
    body2 = resp2.json()
    assert body2["data"]["has_upstream_update"] is False
