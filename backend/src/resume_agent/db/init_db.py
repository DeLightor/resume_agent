"""数据库初始化。

启动时自动建表（幂等），并在版本树表为空时写入初始 ``master`` 节点。
"""

from __future__ import annotations

import sqlite3
import uuid
from importlib import resources
from pathlib import Path
from typing import Any

from resume_agent.config import settings
from resume_agent.db.connection import get_connection

# 表名集合，供健康检查与测试使用
TABLES: tuple[str, ...] = ("resume_versions", "knowledge_chunks", "upload_records")


def _load_schema_sql() -> str:
    """从包资源中读取建表 DDL。"""
    schema_text = (
        resources.files("resume_agent.db").joinpath("schema.sql").read_text(encoding="utf-8")
    )
    return schema_text


def init_database(db_path: Path | str | None = None) -> None:
    """初始化数据库：建表 + 写入初始 master 节点。

    幂等操作，可重复调用。

    Args:
        db_path: 数据库路径，默认使用 ``settings.sqlite_path``。

    Raises:
        sqlite3.Error: 建表失败时抛出。
    """
    path = Path(db_path) if db_path is not None else settings.sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = _load_schema_sql()
    with get_connection(path) as conn:
        conn.executescript(schema_sql)
        _migrate_upstream_columns(conn)
        _seed_master_node(conn)


def _migrate_upstream_columns(conn: sqlite3.Connection) -> None:
    """US-17: 幂等添加 has_upstream_update 和 upstream_changes 列。

    ALTER TABLE ADD COLUMN 在列已存在时会报错，需捕获并忽略。
    """
    for col_def in [
        "has_upstream_update INTEGER DEFAULT 0",
        "upstream_changes TEXT",
    ]:
        col_name = col_def.split()[0]
        try:
            conn.execute(f"ALTER TABLE resume_versions ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass  # 列已存在


def _seed_master_node(conn: sqlite3.Connection) -> None:
    """若 ``resume_versions`` 表为空，写入初始 master 节点。"""
    count_row: dict[str, Any] = conn.execute(
        "SELECT COUNT(*) AS cnt FROM resume_versions"
    ).fetchone()
    if count_row["cnt"] > 0:
        return

    master_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO resume_versions (id, node_id, parent_id, node_type, title)
        VALUES (?, ?, NULL, ?, ?)
        """,
        (master_id, "master", "master", "Master 主干"),
    )


def count_nodes(db_path: Path | str | None = None) -> int:
    """统计 ``resume_versions`` 表中的节点数，供健康检查使用。"""
    try:
        with get_connection(db_path) as conn:
            row: dict[str, Any] = conn.execute(
                "SELECT COUNT(*) AS cnt FROM resume_versions"
            ).fetchone()
            return int(row["cnt"])
    except sqlite3.Error:
        return 0


def list_tables(db_path: Path | str | None = None) -> list[str]:
    """列出当前数据库中的所有用户表名。"""
    with get_connection(db_path) as conn:
        rows: list[dict[str, Any]] = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return [str(row["name"]) for row in rows]
