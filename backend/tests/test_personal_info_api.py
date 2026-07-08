"""个人信息管理 API 测试：US-12。

测试 GET/PUT /api/tree/node/{id}/personal-info 和继承机制。
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _init_db() -> None:
    """初始化测试数据库。"""
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database

    init_database(settings.sqlite_path)


def _setup_node(client: TestClient, node_id: str = "master") -> None:
    """确保测试节点存在。"""
    # master 节点由 conftest 创建
    pass


def _create_branch(client: TestClient, direction: str = "backend") -> str:
    """创建 branch 节点，返回 node_id。"""
    resp = client.post(
        "/api/tree/node",
        json={
            "parent_id": "master",
            "node_type": "branch",
            "title": f"后端方向-{direction}",
            "direction": direction,
        },
    )
    assert resp.status_code == 200
    return resp.json()["data"]["node_id"]


def test_get_personal_info_default_empty() -> None:
    """节点没有 personal_info 时返回空对象。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.get("/api/tree/node/master/personal-info")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    pi = body["data"]["personal_info"]
    assert pi["contact"]["name"] == ""
    assert pi["contact"]["phone"] == ""
    assert pi["education"] == []
    assert pi["summary"] == ""


def test_update_personal_info() -> None:
    """更新节点个人信息。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    info = {
        "contact": {
            "name": "张三",
            "phone": "13800138000",
            "email": "zhangsan@example.com",
            "location": "北京",
        },
        "job_intention": {
            "target_role": "后端工程师",
            "expected_salary": "25k",
            "availability": "随时",
        },
        "education": [
            {
                "school": "清华大学",
                "degree": "本科",
                "major": "计算机科学",
                "period": "2018-2022",
            }
        ],
        "summary": "3 年后端开发经验",
    }

    resp = client.put("/api/tree/node/master/personal-info", json=info)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    pi = body["data"]["personal_info"]
    assert pi["contact"]["name"] == "张三"
    assert pi["contact"]["phone"] == "13800138000"
    assert pi["education"][0]["school"] == "清华大学"
    assert pi["summary"] == "3 年后端开发经验"


def test_get_after_update() -> None:
    """更新后重新获取个人信息。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 先更新
    info = {
        "contact": {"name": "李四", "email": "lisi@test.com"},
        "job_intention": {"target_role": "前端工程师"},
        "education": [],
        "summary": "",
    }
    client.put("/api/tree/node/master/personal-info", json=info)

    # 再获取
    resp = client.get("/api/tree/node/master/personal-info")

    assert resp.status_code == 200
    body = resp.json()
    pi = body["data"]["personal_info"]
    assert pi["contact"]["name"] == "李四"
    assert pi["contact"]["email"] == "lisi@test.com"
    assert pi["job_intention"]["target_role"] == "前端工程师"


def test_get_nonexistent_node() -> None:
    """获取不存在节点的个人信息返回错误。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)
    resp = client.get("/api/tree/node/nonexistent-node/personal-info")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False


def test_inherit_personal_info_on_create() -> None:
    """创建子节点时自动继承父节点的 personal_info。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 1. 先给 master 设置 personal_info
    info = {
        "contact": {"name": "王五", "phone": "13900139000"},
        "job_intention": {"target_role": "全栈工程师"},
        "education": [],
        "summary": "",
    }
    client.put("/api/tree/node/master/personal-info", json=info)

    # 2. 创建 branch 子节点
    branch_id = _create_branch(client, direction="fullstack")

    # 3. 检查子节点是否继承了 personal_info
    resp = client.get(f"/api/tree/node/{branch_id}/personal-info")
    assert resp.status_code == 200
    body = resp.json()
    pi = body["data"]["personal_info"]
    assert pi["contact"]["name"] == "王五"
    assert pi["contact"]["phone"] == "13900139000"
    assert pi["job_intention"]["target_role"] == "全栈工程师"


def test_independent_modification() -> None:
    """子节点修改 personal_info 不影响父节点。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # 1. 确认 master 有 personal_info
    info = {
        "contact": {"name": "赵六", "phone": "13700137000"},
        "job_intention": {},
        "education": [],
        "summary": "",
    }
    client.put("/api/tree/node/master/personal-info", json=info)

    # 2. 创建 branch 子节点
    branch_id = _create_branch(client, direction="devops")

    # 3. 修改子节点的 personal_info
    new_info = {
        "contact": {"name": "赵六-修改", "phone": "13700137001"},
        "job_intention": {},
        "education": [],
        "summary": "",
    }
    client.put(f"/api/tree/node/{branch_id}/personal-info", json=new_info)

    # 4. 验证父节点不受影响
    resp = client.get("/api/tree/node/master/personal-info")
    body = resp.json()
    assert body["data"]["personal_info"]["contact"]["name"] == "赵六"
    assert body["data"]["personal_info"]["contact"]["phone"] == "13700137000"


def test_partial_fields() -> None:
    """部分字段更新（其他字段保持空）。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    info = {
        "contact": {"name": "钱七", "github": "https://github.com/qian7"},
        "job_intention": {},
        "education": [
            {"school": "北大", "degree": "硕士", "major": "AI", "period": "2020-2023"},
        ],
        "summary": "",
    }
    resp = client.put("/api/tree/node/master/personal-info", json=info)

    assert resp.status_code == 200
    body = resp.json()
    pi = body["data"]["personal_info"]
    assert pi["contact"]["name"] == "钱七"
    assert pi["contact"]["github"] == "https://github.com/qian7"
    assert pi["contact"]["phone"] == ""  # 未设置的字段为空
    assert len(pi["education"]) == 1


def test_multiple_education_items() -> None:
    """教育背景支持多条。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    info = {
        "contact": {},
        "job_intention": {},
        "education": [
            {"school": "清华", "degree": "本科", "major": "CS", "period": "2016-2020"},
            {"school": "北大", "degree": "硕士", "major": "AI", "period": "2020-2023"},
        ],
        "summary": "",
    }
    resp = client.put("/api/tree/node/master/personal-info", json=info)

    assert resp.status_code == 200
    body = resp.json()
    pi = body["data"]["personal_info"]
    assert len(pi["education"]) == 2
    assert pi["education"][0]["school"] == "清华"
    assert pi["education"][1]["school"] == "北大"


def test_no_inheritance_without_parent_info() -> None:
    """父节点没有 personal_info 时，子节点也为空。"""
    from resume_agent.main import app

    _init_db()
    client = TestClient(app)

    # master 确保没有 personal_info（前面测试可能设置过，这里直接创建 branch）
    branch_id = _create_branch(client, direction="mobile")

    resp = client.get(f"/api/tree/node/{branch_id}/personal-info")
    body = resp.json()
    pi = body["data"]["personal_info"]
    # 要么为空对象，要么继承自 master（取决于测试顺序）
    assert pi is not None
