"""版本 Diff 对比 API 测试：POST /api/diff。

对比方向：以 B 为基准，查看 A 相对 B 的变化。
- A 有 B 没有 → added（A 新增了）
- B 有 A 没有 → removed（A 移除了）
- 两者都有但不同 → modified，old_value=B 的值，new_value=A 的值

用 FastAPI TestClient + 临时 DB（通过 conftest 的 _isolated_env fixture 隔离）。
测试中直接操作数据库写入带 content_json 的测试节点。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient

from resume_agent.db.connection import get_connection

# === 辅助函数 ===


def _init_db() -> None:
    """初始化隔离环境下的数据库（建表 + seed master）。"""
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database

    init_database(settings.sqlite_path)


def _insert_node(
    node_id: str,
    title: str = "测试节点",
    content_json: dict[str, Any] | None = None,
    parent_id: str = "master",
    node_type: str = "company",
) -> None:
    """直接向 resume_versions 表插入测试节点。"""
    raw = (
        json.dumps(content_json, ensure_ascii=False)
        if content_json is not None
        else None
    )
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO resume_versions
                (id, node_id, parent_id, node_type, title, content_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), node_id, parent_id, node_type, title, raw),
        )


def _diff(
    client: TestClient, node_a_id: str, node_b_id: str
) -> Any:
    """调用 POST /api/diff。"""
    return client.post(
        "/api/diff",
        json={"node_a_id": node_a_id, "node_b_id": node_b_id},
    )


# === 测试用例 ===


def test_diff_same_node_returns_empty() -> None:
    """两节点相同返回空 diff。"""
    _init_db()
    from resume_agent.main import app

    content = {
        "experience": [
            {"company": "Tencent", "role": "SDE", "highlights": ["做了 A"]}
        ],
        "projects": [{"name": "P1", "description": "desc"}],
        "skills": {
            "tech_stack": [{"name": "Python", "context": "熟练"}],
        },
    }
    _insert_node("node-a", "节点 A", content)

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-a")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    diffs = body["data"]["diffs"]
    assert diffs["experience"] == []
    assert diffs["projects"] == []
    assert diffs["skills"] == []
    summary = body["data"]["summary"]
    assert summary == {"added": 0, "removed": 0, "modified": 0}


def test_diff_added_experience() -> None:
    """A 有 B 没有的经历 → added（A 新增了）。"""
    _init_db()
    from resume_agent.main import app

    _insert_node(
        "node-a",
        "节点 A",
        {
            "experience": [
                {
                    "company": "ByteDance",
                    "role": "Algo",
                    "highlights": ["推荐系统"],
                }
            ]
        },
    )
    _insert_node("node-b", "节点 B", {"experience": []})

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-b")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    exp_diffs = body["data"]["diffs"]["experience"]
    assert len(exp_diffs) == 1
    assert exp_diffs[0]["type"] == "added"
    assert exp_diffs[0]["field"] == "experience[0]"
    assert exp_diffs[0]["value"]["company"] == "ByteDance"
    assert exp_diffs[0]["value"]["role"] == "Algo"
    # summary
    assert body["data"]["summary"]["added"] == 1


def test_diff_removed_project() -> None:
    """B 有 A 没有的项目 → removed（A 移除了）。"""
    _init_db()
    from resume_agent.main import app

    _insert_node("node-a", "节点 A", {"projects": []})
    _insert_node(
        "node-b",
        "节点 B",
        {"projects": [{"name": "ProjB", "description": "desc"}]},
    )

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-b")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    proj_diffs = body["data"]["diffs"]["projects"]
    assert len(proj_diffs) == 1
    assert proj_diffs[0]["type"] == "removed"
    assert proj_diffs[0]["field"] == "projects[0]"
    assert proj_diffs[0]["value"]["name"] == "ProjB"
    assert body["data"]["summary"]["removed"] == 1


def test_diff_modified_skill_context() -> None:
    """技能 context 修改 → modified，old_value=B 的值，new_value=A 的值。"""
    _init_db()
    from resume_agent.main import app

    _insert_node(
        "node-a",
        "节点 A",
        {
            "skills": {
                "tech_stack": [{"name": "Python", "context": "精通，5 年经验"}],
            }
        },
    )
    _insert_node(
        "node-b",
        "节点 B",
        {
            "skills": {
                "tech_stack": [{"name": "Python", "context": "熟练使用"}],
            }
        },
    )

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-b")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    skill_diffs = body["data"]["diffs"]["skills"]
    assert len(skill_diffs) == 1
    diff = skill_diffs[0]
    assert diff["type"] == "modified"
    assert diff["field"] == "skills.tech_stack[0]"
    # old_value = B 的值（基准），new_value = A 的值（目标）
    assert diff["old_value"]["context"] == "熟练使用"
    assert diff["new_value"]["context"] == "精通，5 年经验"
    # details 应包含 context 字段差异
    assert len(diff["details"]) == 1
    assert diff["details"][0]["field"] == "context"
    assert diff["details"][0]["old_value"] == "熟练使用"
    assert diff["details"][0]["new_value"] == "精通，5 年经验"
    assert body["data"]["summary"]["modified"] == 1


def test_diff_null_content_json() -> None:
    """content_json 为 null 不报错。"""
    _init_db()
    from resume_agent.main import app

    _insert_node("node-a", "节点 A", content_json=None)
    _insert_node("node-b", "节点 B", content_json=None)

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-b")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    diffs = body["data"]["diffs"]
    assert diffs["experience"] == []
    assert diffs["projects"] == []
    assert diffs["skills"] == []
    assert body["data"]["summary"] == {"added": 0, "removed": 0, "modified": 0}
    assert body["data"]["node_a"]["node_id"] == "node-a"
    assert body["data"]["node_b"]["node_id"] == "node-b"


def test_diff_node_not_found() -> None:
    """节点不存在返回 404 error。"""
    _init_db()
    from resume_agent.main import app

    _insert_node("node-a", "节点 A", {"experience": []})

    client = TestClient(app)
    resp = _diff(client, "node-a", "nonexistent")

    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NODE_NOT_FOUND"


def test_diff_node_a_not_found() -> None:
    """node_a 不存在返回 404 error。"""
    _init_db()
    from resume_agent.main import app

    _insert_node("node-b", "节点 B", {"experience": []})

    client = TestClient(app)
    resp = _diff(client, "nonexistent", "node-b")

    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NODE_NOT_FOUND"


def test_diff_full_three_sections() -> None:
    """完整三段对比。

    对比方向：以 B 为基准，查看 A 相对 B 的变化。
    - A 有 B 没有 → added
    - B 有 A 没有 → removed
    - 两者都有但不同 → modified（old=B, new=A）
    """
    _init_db()
    from resume_agent.main import app

    content_a = {
        "experience": [
            {
                "company": "Tencent",
                "role": "SDE",
                "highlights": ["新亮点 A", "共有亮点"],
            },
            {
                "company": "ByteDance",
                "role": "Algo",
                "highlights": ["推荐系统"],
            },
        ],
        "projects": [
            {"name": "ProjA", "description": "new", "tech_stack": ["Go", "Rust"]},
        ],
        "skills": {
            "tech_stack": [{"name": "Python", "context": "精通"}],
            "soft_skills": [{"name": "沟通", "context": "良好"}],
        },
    }
    content_b = {
        "experience": [
            {
                "company": "Tencent",
                "role": "SDE",
                "highlights": ["共有亮点", "旧亮点 B"],
            },
        ],
        "projects": [
            {"name": "ProjA", "description": "old", "tech_stack": ["Go"]},
            {"name": "ProjRemoved", "description": "to be removed"},
        ],
        "skills": {
            "tech_stack": [{"name": "Python", "context": "熟练"}],
            "hard_skills": [{"name": "算法", "context": "基础"}],
        },
    }
    _insert_node("node-a", "节点 A", content_a)
    _insert_node("node-b", "节点 B", content_b)

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-b")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    diffs = body["data"]["diffs"]

    # experience：Tencent 匹配但 highlights 不同 → modified；ByteDance → added（A 有 B 没有）
    exp_types = sorted(d["type"] for d in diffs["experience"])
    assert "modified" in exp_types
    assert "added" in exp_types
    modified_exp = next(
        d for d in diffs["experience"] if d["type"] == "modified"
    )
    # old_value = B 的值，new_value = A 的值
    assert modified_exp["old_value"]["company"] == "Tencent"
    assert modified_exp["new_value"]["company"] == "Tencent"
    added_exp = next(d for d in diffs["experience"] if d["type"] == "added")
    assert added_exp["value"]["company"] == "ByteDance"

    # projects：ProjA modified；ProjRemoved → removed（B 有 A 没有）
    proj_types = sorted(d["type"] for d in diffs["projects"])
    assert "modified" in proj_types
    assert "removed" in proj_types
    modified_proj = next(
        d for d in diffs["projects"] if d["type"] == "modified"
    )
    assert modified_proj["old_value"]["name"] == "ProjA"
    removed_proj = next(
        d for d in diffs["projects"] if d["type"] == "removed"
    )
    assert removed_proj["value"]["name"] == "ProjRemoved"

    # skills：Python context modified；算法 → removed（B 有 A 没有）；沟通 → added（A 有 B 没有）
    skill_types = sorted(d["type"] for d in diffs["skills"])
    assert "modified" in skill_types
    assert "removed" in skill_types
    assert "added" in skill_types


def test_diff_summary_counts() -> None:
    """summary 计数正确。

    A（目标）有: 公司A(modified highlights) + 公司New(added)
    B（基准）有: 公司A + 公司Remove(removed, B 有 A 没有)
    项目: Keep(相同) + NewProj(added, A 有 B 没有)
    技能: Python(modified) + 沟通(added, A 有 B 没有)
    """
    _init_db()
    from resume_agent.main import app

    content_a = {
        "experience": [
            # A 公司同 role 但 highlights 改了 → modified
            {"company": "A", "role": "R", "highlights": ["x", "z"]},
            # New 公司只有 A 有 → added
            {"company": "New", "role": "R", "highlights": ["y"]},
        ],
        "projects": [
            {"name": "Keep", "description": "same"},
            {"name": "NewProj", "description": "new"},  # → added
        ],
        "skills": {
            "tech_stack": [
                {"name": "Python", "context": "new"},  # → modified
            ],
            "soft_skills": [
                {"name": "沟通", "context": "好"},  # → added
            ],
        },
    }
    content_b = {
        "experience": [
            {"company": "A", "role": "R", "highlights": ["x"]},
            # Remove 公司只有 B 有 → removed
            {"company": "Remove", "role": "R", "highlights": ["y"]},
        ],
        "projects": [
            {"name": "Keep", "description": "same"},
        ],
        "skills": {
            "tech_stack": [{"name": "Python", "context": "old"}],
        },
    }
    _insert_node("node-a", "节点 A", content_a)
    _insert_node("node-b", "节点 B", content_b)

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-b")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    summary = body["data"]["summary"]
    # added: New 公司 + NewProj + 沟通 = 3
    # removed: Remove 公司 = 1
    # modified: A 公司 highlights + Python context = 2
    assert summary["added"] == 3
    assert summary["removed"] == 1
    assert summary["modified"] == 2


def test_diff_node_meta_returned() -> None:
    """响应包含 node_a / node_b 元信息。"""
    _init_db()
    from resume_agent.main import app

    _insert_node("node-a", "腾讯推荐", {"experience": []})
    _insert_node("node-b", "字节推荐", {"experience": []})

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-b")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["node_a"] == {"node_id": "node-a", "title": "腾讯推荐"}
    assert body["data"]["node_b"] == {"node_id": "node-b", "title": "字节推荐"}


def test_diff_missing_sections_treated_as_empty() -> None:
    """content_json 缺少某段时视为空集合，不报错。"""
    _init_db()
    from resume_agent.main import app

    # A 只有 experience，B 只有 projects
    _insert_node(
        "node-a",
        "节点 A",
        {"experience": [{"company": "C", "role": "R", "highlights": []}]},
    )
    _insert_node(
        "node-b",
        "节点 B",
        {"projects": [{"name": "P", "description": "d"}]},
    )

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-b")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    diffs = body["data"]["diffs"]
    # A 的 experience 在 B 中不存在 → added（A 新增了）
    assert len(diffs["experience"]) == 1
    assert diffs["experience"][0]["type"] == "added"
    # B 的 project 在 A 中不存在 → removed（A 移除了）
    assert len(diffs["projects"]) == 1
    assert diffs["projects"][0]["type"] == "removed"
    # skills 两边都缺失 → 空
    assert diffs["skills"] == []


def test_diff_experience_highlights_subdiff() -> None:
    """experience modified 时 details 包含 highlights 的新增/删除。

    对比方向：以 B 为基准，查看 A 相对 B 的变化。
    A 有 ["新亮点", "共有"]，B 有 ["共有", "旧亮点"]
    → added: "新亮点"（A 有 B 没有）
    → removed: "旧亮点"（B 有 A 没有）
    """
    _init_db()
    from resume_agent.main import app

    _insert_node(
        "node-a",
        "节点 A",
        {
            "experience": [
                {
                    "company": "Tencent",
                    "role": "SDE",
                    "highlights": ["新亮点", "共有"],
                }
            ]
        },
    )
    _insert_node(
        "node-b",
        "节点 B",
        {
            "experience": [
                {
                    "company": "Tencent",
                    "role": "SDE",
                    "highlights": ["共有", "旧亮点"],
                }
            ]
        },
    )

    client = TestClient(app)
    resp = _diff(client, "node-a", "node-b")

    assert resp.status_code == 200
    body = resp.json()
    exp_diffs = body["data"]["diffs"]["experience"]
    assert len(exp_diffs) == 1
    diff = exp_diffs[0]
    assert diff["type"] == "modified"
    details = diff["details"]
    detail_types = sorted(d["type"] for d in details)
    assert "added" in detail_types
    assert "removed" in detail_types
    # added = A 有 B 没有 = "新亮点"
    added_detail = next(d for d in details if d["type"] == "added")
    assert added_detail["value"] == "新亮点"
    # removed = B 有 A 没有 = "旧亮点"
    removed_detail = next(d for d in details if d["type"] == "removed")
    assert removed_detail["value"] == "旧亮点"
