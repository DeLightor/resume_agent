"""Agent 会话与 trace 的 SQLite 持久化（US-27 agent-runtime Task 1.2）。

会话存储设计：
- ``agent_sessions.messages_json`` 存完整 OpenAI 协议消息数组
  （含 assistant 的 tool_calls 与 role=tool 的结果），恢复 = 直接续跑。
- ``agent_traces`` 记录每次工具调用的轮次 / 入参 / 输出（输出截断 4KB）。
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from resume_agent.db.connection import get_connection

logger = logging.getLogger("resume_agent")

# trace 输出截断上限（字节），防止大结果撑爆库与后续 prompt
_TRACE_OUTPUT_LIMIT = 4096

# 合法会话状态
SESSION_STATUSES = ("running", "awaiting_user", "done", "failed")


@dataclass
class AgentSession:
    """Agent 会话内存表示，字段与 ``agent_sessions`` 表一一对应。"""

    id: str
    status: str = "running"
    context: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    pending_question: str | None = None
    # agent-write-guard: awaiting_user 时待确认的写入
    # {tool_call_id, node_id, content}；resume 仲裁后清空。
    pending_write: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


def create_session(
    db_path: Path | str | None = None,
    context: dict[str, Any] | None = None,
) -> AgentSession:
    """创建一个 running 状态的新会话并落库。

    Args:
        db_path: 数据库路径，None 时使用全局 settings.sqlite_path。
        context: 会话上下文（如当前节点、JD 摘要）。

    Returns:
        落库后的 ``AgentSession``。
    """
    session = AgentSession(
        id=str(uuid.uuid4()),
        status="running",
        context=context or {},
        messages=[],
    )
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO agent_sessions (id, status, context_json, messages_json)"
            " VALUES (?, ?, ?, ?)",
            [
                session.id,
                session.status,
                json.dumps(session.context, ensure_ascii=False),
                "[]",
            ],
        )
    return session


def get_session(
    session_id: str,
    db_path: Path | str | None = None,
) -> AgentSession | None:
    """按 id 读取会话，不存在返回 None。"""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM agent_sessions WHERE id = ?",
            [session_id],
        ).fetchone()
    if not row:
        return None
    return _row_to_session(row)


def save_session(session: AgentSession, db_path: Path | str | None = None) -> None:
    """全量保存会话（状态/上下文/消息/待答问题）。"""
    if session.status not in SESSION_STATUSES:
        raise ValueError(f"非法会话状态: {session.status}")
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE agent_sessions SET status = ?, context_json = ?,"
            " messages_json = ?, pending_question = ?, pending_write_json = ?,"
            " updated_at = datetime('now') WHERE id = ?",
            [
                session.status,
                json.dumps(session.context, ensure_ascii=False),
                json.dumps(session.messages, ensure_ascii=False),
                session.pending_question,
                json.dumps(session.pending_write, ensure_ascii=False)
                if session.pending_write is not None
                else None,
                session.id,
            ],
        )


def list_sessions(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """列出所有会话摘要（新→旧），不含消息体。"""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, status, context_json, pending_question,"
            " created_at, updated_at FROM agent_sessions"
            " ORDER BY datetime(updated_at) DESC"
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append({
            "id": row["id"],
            "status": row["status"],
            "context": _loads_or(row["context_json"], {}),
            "pending_question": row["pending_question"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
    return items


def append_trace(
    session_id: str,
    round: int,
    tool_name: str,
    input_data: dict[str, Any] | None,
    output_data: Any,
    db_path: Path | str | None = None,
) -> None:
    """追加一条工具调用轨迹，输出超过上限时截断。"""
    output_str = json.dumps(output_data, ensure_ascii=False, default=str)
    if len(output_str) > _TRACE_OUTPUT_LIMIT:
        output_str = output_str[: _TRACE_OUTPUT_LIMIT - 20] + ' …[truncated]"'
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO agent_traces (id, session_id, round, tool_name,"
            " input_json, output_json) VALUES (?, ?, ?, ?, ?, ?)",
            [
                str(uuid.uuid4()),
                session_id,
                round,
                tool_name,
                json.dumps(input_data or {}, ensure_ascii=False),
                output_str,
            ],
        )


def list_traces(
    session_id: str,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """按会话查询全部轨迹（时间顺序），output 为原始 JSON 字符串。"""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, round, tool_name, input_json, output_json, created_at"
            " FROM agent_traces WHERE session_id = ?"
            " ORDER BY datetime(created_at) ASC, rowid ASC",
            [session_id],
        ).fetchall()
    return [
        {
            "id": row["id"],
            "round": row["round"],
            "tool_name": row["tool_name"],
            "input": _loads_or(row["input_json"], {}),
            "output": row["output_json"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _row_to_session(row: dict[str, Any]) -> AgentSession:
    """SQLite 行 → AgentSession。"""
    return AgentSession(
        id=row["id"],
        status=row["status"],
        context=_loads_or(row["context_json"], {}),
        messages=_loads_or(row["messages_json"], []),
        pending_question=row["pending_question"],
        pending_write=_loads_or(row.get("pending_write_json"), None),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _loads_or(raw: str | None, default: Any) -> Any:
    """容错 JSON 解析：空/非法返回默认值。"""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


__all__ = [
    "AgentSession",
    "SESSION_STATUSES",
    "create_session",
    "get_session",
    "save_session",
    "list_sessions",
    "append_trace",
    "list_traces",
]
