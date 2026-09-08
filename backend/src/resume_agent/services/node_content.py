"""版本树节点内容读写服务（US-27 agent-runtime 抽取自 api/generate.py）。

原 ``_get_node_content`` / ``_save_node_content`` 纯移动，行为不变。
乐观锁与节点内 commit 历史属 US-32，当前为直接覆盖语义。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from resume_agent.db.connection import get_connection

logger = logging.getLogger("resume_agent")


def get_node_content(node_id: str) -> dict[str, Any] | None:
    """获取节点 content_json。

    Args:
        node_id: 业务节点 ID。

    Returns:
        节点不存在返回 None；content_json 为空或非法时返回 ``{}``。
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT content_json FROM resume_versions WHERE node_id = ?",
            [node_id],
        ).fetchone()
    if not row:
        return None
    raw = row["content_json"]
    if not raw:
        return {}
    try:
        content: dict[str, Any] = json.loads(raw) if isinstance(raw, str) else raw
        return content
    except (json.JSONDecodeError, TypeError):
        return {}


def save_node_content(node_id: str, content: dict[str, Any]) -> bool:
    """保存节点 content_json（整段覆盖）。

    Args:
        node_id: 业务节点 ID。
        content: 完整内容字典。

    Returns:
        是否更新成功（节点不存在返回 False）。
    """
    with get_connection() as conn:
        content_str = json.dumps(content, ensure_ascii=False)
        cursor = conn.execute(
            "UPDATE resume_versions SET content_json = ? WHERE node_id = ?",
            [content_str, node_id],
        )
    return cursor.rowcount > 0


__all__ = ["get_node_content", "save_node_content"]
