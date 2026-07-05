"""版本树节点 API 测试：POST /api/tree/node、GET /api/tree/{node_id}、PUT /api/tree/node/{node_id}。

用 FastAPI TestClient + 临时 DB（通过 conftest 的 _isolated_env fixture 隔离）。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from resume_agent.db.connection import get_connection

# === 辅助函数 ===


def _init_db() -> None:
    """初始化隔离环境下的数据库（建表 + seed master）。"""
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database

    init_database(settings.sqlite_path)


def _create_branch(
    client: TestClient,
    parent_id: str = "master",
    direction: str = "安全",
    title: str = "安全方向",
) -> Any:
    """通过 API 创建 branch 节点。"""
    return client.post(
        "/api/tree/node",
        json={
            "parent_id": parent_id,
            "node_type": "branch",
            "title": title,
            "direction": direction,
        },
    )


def _create_company(
    client: TestClient,
    parent_id: str,
    company: str = "Tencent",
    role: str = "RS",
    title: str = "Tencent RS",
) -> Any:
    """通过 API 创建 company 节点。"""
    return client.post(
        "/api/tree/node",
        json={
            "parent_id": parent_id,
            "node_type": "company",
            "title": title,
            "company": company,
            "role": role,
        },
    )


# === POST /api/tree/node 测试 ===


def test_create_branch_success() -> None:
    """创建 branch（parent=master）→ 成功。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    resp = _create_branch(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    node = body["data"]
    assert node["node_type"] == "branch"
    assert node["parent_id"] == "master"
    assert node["node_id"] == "security"  # 安全 → security
    assert node["direction"] == "安全"
    assert node["title"] == "安全方向"

    # 验证 DB 中确实写入
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?", ("security",)
        ).fetchone()
    assert row is not None
    assert row["node_type"] == "branch"


def test_create_company_success() -> None:
    """创建 company（parent=branch）→ 成功。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    branch_id = _create_branch(client).json()["data"]["node_id"]

    resp = _create_company(client, parent_id=branch_id)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    node = body["data"]
    assert node["node_type"] == "company"
    assert node["parent_id"] == branch_id
    assert node["node_id"] == "tencent-rs"  # Tencent-RS slugify
    assert node["company"] == "Tencent"

    # 验证 DB
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?", ("tencent-rs",)
        ).fetchone()
    assert row is not None
    assert row["company"] == "Tencent"


def test_create_company_duplicate_rejected() -> None:
    """同一 branch 下重复 company → 拒绝。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    branch_id = _create_branch(client).json()["data"]["node_id"]

    # 第一次创建 → 成功
    resp1 = _create_company(client, parent_id=branch_id, company="Tencent", role="RS")
    assert resp1.json()["ok"] is True

    # 第二次同公司（不同 role）→ 拒绝
    resp2 = _create_company(
        client, parent_id=branch_id, company="Tencent", role="Backend"
    )
    body = resp2.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "DUPLICATE_COMPANY"

    # 验证 DB 只有一个 Tencent company
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM resume_versions WHERE node_type = 'company' AND company = 'Tencent'"
        ).fetchall()
    assert len(rows) == 1


def test_create_node_parent_not_found() -> None:
    """parent 不存在 → 拒绝。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/tree/node",
        json={
            "parent_id": "nonexistent",
            "node_type": "branch",
            "title": "测试方向",
            "direction": "安全",
        },
    )

    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "PARENT_NOT_FOUND"


def test_create_branch_parent_type_mismatch() -> None:
    """branch 的 parent 不是 master → 拒绝。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    # 先创建一个 branch
    branch_id = _create_branch(client).json()["data"]["node_id"]

    # 尝试在该 branch 下再建 branch → parent 类型不匹配
    resp = _create_branch(client, parent_id=branch_id, direction="后端")
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "PARENT_TYPE_MISMATCH"


def test_create_company_parent_type_mismatch() -> None:
    """company 的 parent 不是 branch（是 master）→ 拒绝。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    # 直接在 master 下建 company → parent 类型不匹配
    resp = _create_company(client, parent_id="master")
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "PARENT_TYPE_MISMATCH"


# === GET /api/tree/{node_id} 测试 ===


def test_get_node_detail() -> None:
    """GET 节点详情。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    branch_id = _create_branch(client).json()["data"]["node_id"]

    resp = client.get(f"/api/tree/{branch_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    node = body["data"]
    assert node["node_id"] == branch_id
    assert node["node_type"] == "branch"
    assert node["content_json"] is None  # branch 无内容


def test_get_node_with_content_json() -> None:
    """GET 含 content_json 的节点 → 应解析为 dict。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    branch_id = _create_branch(client).json()["data"]["node_id"]

    # PUT 写入 content_json
    content = {"basic": {"name": "张三"}, "skills": ["Python"]}
    client.put(f"/api/tree/node/{branch_id}", json={"content_json": content})

    # GET 应返回解析后的 dict
    resp = client.get(f"/api/tree/{branch_id}")
    body = resp.json()
    assert body["data"]["content_json"] == content


def test_get_node_not_found() -> None:
    """GET 不存在的节点 → 404。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.get("/api/tree/nonexistent")
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NODE_NOT_FOUND"


# === PUT /api/tree/node/{node_id} 测试 ===


def test_update_node_title() -> None:
    """PUT 更新 title。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    branch_id = _create_branch(client).json()["data"]["node_id"]

    resp = client.put(f"/api/tree/node/{branch_id}", json={"title": "新标题"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["title"] == "新标题"
    # 其他字段不变
    assert body["data"]["node_id"] == branch_id
    assert body["data"]["node_type"] == "branch"

    # 验证 DB
    with get_connection() as conn:
        row = conn.execute(
            "SELECT title FROM resume_versions WHERE node_id = ?", (branch_id,)
        ).fetchone()
    assert row["title"] == "新标题"


def test_update_node_content_json() -> None:
    """PUT 更新 content_json → 存储为 JSON 字符串，返回解析为 dict。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    branch_id = _create_branch(client).json()["data"]["node_id"]

    content = {"basic": {"name": "张三"}, "experience": []}
    resp = client.put(
        f"/api/tree/node/{branch_id}", json={"content_json": content}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    # 返回时 content_json 应解析为 dict
    assert body["data"]["content_json"] == content

    # 验证 DB 中存储为 JSON 字符串
    with get_connection() as conn:
        row = conn.execute(
            "SELECT content_json FROM resume_versions WHERE node_id = ?",
            (branch_id,),
        ).fetchone()
    assert row["content_json"] is not None
    assert json.loads(row["content_json"]) == content


def test_update_node_not_found() -> None:
    """PUT 不存在的节点 → 404。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.put(
        "/api/tree/node/nonexistent", json={"title": "x"}
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NODE_NOT_FOUND"


def test_update_node_both_fields() -> None:
    """同时更新 title 和 content_json。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    branch_id = _create_branch(client).json()["data"]["node_id"]

    content = {"key": "value"}
    resp = client.put(
        f"/api/tree/node/{branch_id}",
        json={"title": "双更新", "content_json": content},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "双更新"
    assert data["content_json"] == content
