"""TreeBuilder 单元测试。

对齐 US-12：TreeBuilder 只创建方向（branch）节点，不创建公司节点
（简历中通常不含应聘公司信息）。

用临时数据库验证：
1. 空 DB → 调用 build → 创建 branch 节点（master + branch）
2. 再次调用同方向 → 命中去重，更新 content_json
3. 不同方向 → 创建独立 branch 节点
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from resume_agent.db.connection import get_connection
from resume_agent.db.init_db import init_database
from resume_agent.parsers.extractor import (
    BasicInfo,
    ExperienceItem,
    StructuredResume,
)
from resume_agent.services.tree_builder import TreeBuilder


def _make_resume(
    company: str = "Tencent",
    direction: str = "安全",
    name: str = "张三",
) -> StructuredResume:
    """构造一份测试用结构化简历。"""
    return StructuredResume(
        basic=BasicInfo(name=name, phone="138", email="a@b.com", location="北京"),
        experience=[
            ExperienceItem(
                company=company,
                role="研究员",
                period="2021-至今",
                highlights=["h1"],
            )
        ],
        skills=["Python"],
        primary_direction=direction,
    )


def _count_nodes(db_path: Path) -> int:
    """统计节点总数。"""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM resume_versions").fetchone()
        return int(row["cnt"])


def test_build_creates_branch(initialized_db: Path) -> None:
    """空 DB（仅 master）调用 build 应创建 branch 节点。"""
    builder = TreeBuilder(db_path=initialized_db)
    resume = _make_resume()

    result = builder.build_from_resume(resume)

    # master + branch = 2
    assert _count_nodes(initialized_db) == 2
    assert result["deduplicated"] is False
    node = result["node"]
    assert node["node_type"] == "branch"
    assert node["direction"] == "安全"
    assert node["parent_id"] == "master"
    assert node["node_id"] == "branch-安全"
    assert node["title"] == "安全岗方向"


def test_build_deduplicates_existing_branch(initialized_db: Path) -> None:
    """同方向再次 build 应命中去重，更新 content_json。"""
    builder = TreeBuilder(db_path=initialized_db)
    resume1 = _make_resume(company="Tencent", name="张三")
    result1 = builder.build_from_resume(resume1)
    assert result1["deduplicated"] is False

    # 再次构建同方向，但改名字
    resume2 = _make_resume(company="Alibaba", name="李四")
    result2 = builder.build_from_resume(resume2)

    # 应命中去重，不新增节点
    assert result2["deduplicated"] is True
    assert _count_nodes(initialized_db) == 2  # 仍是 master + 1 branch

    # content_json 应被更新为新简历
    node = result2["node"]
    content = json.loads(node["content_json"])
    assert content["basic"]["name"] == "李四"


def test_build_creates_separate_branch_for_different_direction(
    initialized_db: Path,
) -> None:
    """不同方向应创建独立 branch 节点。"""
    builder = TreeBuilder(db_path=initialized_db)
    builder.build_from_resume(_make_resume(company="Tencent", direction="安全"))
    builder.build_from_resume(_make_resume(company="Bytedance", direction="后端"))

    # master + 2 branches = 3
    assert _count_nodes(initialized_db) == 3
    with get_connection(initialized_db) as conn:
        branches = conn.execute(
            "SELECT * FROM resume_versions WHERE node_type = 'branch'"
        ).fetchall()
    assert len(branches) == 2
    directions = {b["direction"] for b in branches}
    assert directions == {"安全", "后端"}


def test_build_ensures_master_when_missing(tmp_db_path: Path) -> None:
    """即使 DB 未 seed master，build 也应自动创建。"""
    # 只建表，不 seed master
    init_database(tmp_db_path)
    with get_connection(tmp_db_path) as conn:
        conn.execute("DELETE FROM resume_versions WHERE node_id = 'master'")
    assert _count_nodes(tmp_db_path) == 0

    builder = TreeBuilder(db_path=tmp_db_path)
    builder.build_from_resume(_make_resume())

    # master + branch = 2
    assert _count_nodes(tmp_db_path) == 2
    with get_connection(tmp_db_path) as conn:
        master = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = 'master'"
        ).fetchone()
    assert master is not None
    assert master["node_type"] == "master"


def test_build_content_json_contains_full_resume(initialized_db: Path) -> None:
    """branch 节点的 content_json 应包含完整结构化简历。"""
    builder = TreeBuilder(db_path=initialized_db)
    resume = _make_resume()
    result = builder.build_from_resume(resume)

    content = json.loads(result["node"]["content_json"])
    assert content["basic"]["name"] == "张三"
    assert content["basic"]["phone"] == "138"
    assert content["experience"][0]["company"] == "Tencent"
    assert content["primary_direction"] == "安全"
    # US-12：basic + education 映射为 personal_info
    assert content["personal_info"]["contact"]["name"] == "张三"


def test_build_maps_personal_info(initialized_db: Path) -> None:
    """basic + education 应映射为 personal_info 写入 content_json。"""
    builder = TreeBuilder(db_path=initialized_db)
    resume = _make_resume()
    result = builder.build_from_resume(resume)

    content: dict[str, Any] = json.loads(result["node"]["content_json"])
    pi = content["personal_info"]
    assert pi["contact"]["phone"] == "138"
    assert pi["contact"]["email"] == "a@b.com"
    assert pi["job_intention"]["target_role"] == ""
