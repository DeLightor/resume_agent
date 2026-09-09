"""数据库建表测试。

验证 schema 初始化、表存在性、外键级联删除、CHECK 约束。
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from resume_agent.db.connection import get_connection
from resume_agent.db.init_db import TABLES, count_nodes, init_database, list_tables


def test_init_creates_all_tables(tmp_db_path: Path) -> None:
    """初始化后应包含 3 张表。"""
    init_database(tmp_db_path)
    tables = set(list_tables(tmp_db_path))
    for table in TABLES:
        assert table in tables, f"缺少表: {table}"


def test_init_is_idempotent(tmp_db_path: Path) -> None:
    """多次初始化应幂等，不报错。"""
    init_database(tmp_db_path)
    init_database(tmp_db_path)
    tables = set(list_tables(tmp_db_path))
    assert len(tables & set(TABLES)) == 4


def test_seed_master_node(tmp_db_path: Path) -> None:
    """初始化后应写入初始 master 节点。"""
    init_database(tmp_db_path)
    assert count_nodes(tmp_db_path) == 1
    with get_connection(tmp_db_path) as conn:
        row = conn.execute(
            "SELECT node_id, node_type, title FROM resume_versions WHERE node_id = ?",
            ("master",),
        ).fetchone()
    assert row is not None
    assert row["node_id"] == "master"
    assert row["node_type"] == "master"
    assert row["title"] == "Master 主干"


def test_insert_and_query_resume_version(tmp_db_path: Path) -> None:
    """插入 resume_versions 记录并查询。"""
    init_database(tmp_db_path)
    branch_id = str(uuid.uuid4())
    with get_connection(tmp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO resume_versions (id, node_id, parent_id, node_type, title, direction)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (branch_id, "security", "master", "branch", "安全岗方向", "安全"),
        )
    with get_connection(tmp_db_path) as conn:
        row = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?", ("security",)
        ).fetchone()
    assert row is not None
    assert row["node_type"] == "branch"
    assert row["direction"] == "安全"


def test_check_constraint_node_type(tmp_db_path: Path) -> None:
    """node_type CHECK 约束应拒绝非法值。"""
    init_database(tmp_db_path)
    bad_id = str(uuid.uuid4())
    with pytest.raises(sqlite3.IntegrityError), get_connection(tmp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO resume_versions (id, node_id, node_type, title)
            VALUES (?, ?, ?, ?)
            """,
            (bad_id, "bad-node", "invalid_type", "非法节点"),
        )


def test_check_constraint_parse_status(tmp_db_path: Path) -> None:
    """parse_status CHECK 约束应拒绝非法值。"""
    init_database(tmp_db_path)
    bad_id = str(uuid.uuid4())
    with pytest.raises(sqlite3.IntegrityError), get_connection(tmp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO upload_records (id, file_name, file_type, file_path, parse_status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bad_id, "f.pdf", "pdf", "files/f.pdf", "invalid_status"),
        )


def test_foreign_key_cascade_delete(tmp_db_path: Path) -> None:
    """删除父节点应级联删除子节点。"""
    init_database(tmp_db_path)
    branch_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    with get_connection(tmp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO resume_versions (id, node_id, parent_id, node_type, title, direction)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (branch_id, "security", "master", "branch", "安全岗方向", "安全"),
        )
        conn.execute(
            """
            INSERT INTO resume_versions (id, node_id, parent_id, node_type, title, company)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (company_id, "tencent-rs", "security", "company", "Tencent 安全研究员", "Tencent"),
        )
    # 删除 branch 节点，company 子节点应级联删除
    with get_connection(tmp_db_path) as conn:
        conn.execute("DELETE FROM resume_versions WHERE node_id = ?", ("security",))
    with get_connection(tmp_db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?", ("tencent-rs",)
        ).fetchall()
    assert len(rows) == 0


def test_count_nodes_returns_zero_for_empty(tmp_db_path: Path) -> None:
    """建表后但未 seed 时 count_nodes 应反映实际节点数。"""
    # 不调用 init_database，直接建空表
    with get_connection(tmp_db_path) as conn:
        conn.executescript("CREATE TABLE IF NOT EXISTS resume_versions (id TEXT PRIMARY KEY);")
    assert count_nodes(tmp_db_path) == 0
