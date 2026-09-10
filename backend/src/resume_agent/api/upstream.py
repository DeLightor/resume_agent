"""上游变更检测与提示（US-17）。

当 master 节点修改 personal_info 后，递归标记所有子节点
`has_upstream_update=1`，并记录字段级差异到 `upstream_changes`。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from resume_agent.api.personal_info import _write_version
from resume_agent.api.response import error, success
from resume_agent.services.node_content import get_node_content as _get_node_content
from resume_agent.services.node_content import save_node_content

logger = logging.getLogger("resume_agent")

router = APIRouter(tags=["upstream"])

# 递归遍历上限
MAX_NODES = 50




def _get_children(node_id: str) -> list[dict[str, Any]]:
    """获取直接子节点。"""
    from resume_agent.db.connection import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT node_id, content_json, parent_id FROM resume_versions WHERE parent_id = ? AND deleted_at IS NULL",
            [node_id],
        ).fetchall()
    return [dict(row) for row in rows]


def _diff_personal_info(
    parent_pi: dict[str, Any],
    child_pi: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """字段级差异对比。

    对比 personal_info 的三个子字段：contact / education / summary。
    返回 {field: {old, new}} 格式。
    """
    changes: dict[str, dict[str, Any]] = {}

    for field in ("contact", "education", "summary"):
        parent_val = parent_pi.get(field)
        child_val = child_pi.get(field)

        # 标准化为可比较的 JSON 字符串
        parent_norm = json.dumps(parent_val, ensure_ascii=False, sort_keys=True)
        child_norm = json.dumps(child_val, ensure_ascii=False, sort_keys=True)

        if parent_norm != child_norm:
            changes[field] = {
                "old": child_val,
                "new": parent_val,
            }

    return changes


def _mark_upstream_update(
    node_id: str,
    changes: dict[str, dict[str, Any]],
) -> None:
    """标记节点有上游变更。"""
    from resume_agent.db.connection import get_connection

    changes_json = json.dumps(changes, ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            "UPDATE resume_versions SET has_upstream_update = 1, upstream_changes = ?, version=version+1 WHERE node_id = ? AND deleted_at IS NULL AND COALESCE(upstream_changes, '') != ?",
            [changes_json, node_id, changes_json],
        )


def _clear_upstream_update(node_id: str) -> None:
    """清除上游变更标记。"""
    from resume_agent.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE resume_versions SET has_upstream_update = 0, upstream_changes = NULL, version=version+1 WHERE node_id = ? AND deleted_at IS NULL AND has_upstream_update != 0",
            [node_id],
        )


def propagate_upstream_changes(node_id: str) -> int:
    """递归标记所有子节点的上游变更。

    Args:
        node_id: 被修改的节点 ID（通常是 master）

    Returns:
        标记的节点数量
    """
    parent_content = _get_node_content(node_id)
    if parent_content is None:
        return 0

    parent_pi = parent_content.get("personal_info", {})
    if not isinstance(parent_pi, dict):
        parent_pi = {}

    count = 0
    visited = {node_id}

    def _recurse(pid: str, p_pi: dict[str, Any]) -> None:
        nonlocal count
        if count >= MAX_NODES:
            return

        children = _get_children(pid)
        for child in children:
            child_id = child["node_id"]
            if child_id in visited:
                continue
            visited.add(child_id)

            child_content_str = child.get("content_json", "")
            if child_content_str:
                try:
                    child_content = json.loads(child_content_str) if isinstance(child_content_str, str) else child_content_str
                except (json.JSONDecodeError, TypeError):
                    child_content = {}
            else:
                child_content = {}

            child_pi = child_content.get("personal_info", {})
            if not isinstance(child_pi, dict):
                child_pi = {}

            changes = _diff_personal_info(p_pi, child_pi)
            if changes:
                _mark_upstream_update(child_id, changes)
                count += 1
            else:
                # 无差异，清除旧标记
                _clear_upstream_update(child_id)

            # 递归处理子节点的子节点
            _recurse(child_id, p_pi)

    _recurse(node_id, parent_pi)
    logger.info("propagate_upstream_changes: marked %d nodes from %s", count, node_id)
    return count


# === API 端点 ===


class MergeRequest(BaseModel):
    """单字段合并请求。"""

    field: str


class RejectRequest(BaseModel):
    """单字段拒绝请求。"""

    field: str


@router.get("/tree/node/{node_id}/upstream-changes")
async def get_upstream_changes(node_id: str) -> dict[str, Any]:
    """获取节点的上游变更列表。"""
    from resume_agent.db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT has_upstream_update, upstream_changes, version FROM resume_versions WHERE node_id = ? AND deleted_at IS NULL",
            [node_id],
        ).fetchone()

    if not row:
        return error("NODE_NOT_FOUND", f"节点 {node_id} 不存在")

    has_update = bool(row["has_upstream_update"])
    changes_raw = row["upstream_changes"]

    changes: dict[str, Any] = {}
    if changes_raw:
        try:
            changes = json.loads(changes_raw) if isinstance(changes_raw, str) else changes_raw
        except (json.JSONDecodeError, TypeError):
            changes = {}

    return success({
        "has_upstream_update": has_update,
        "changes": changes,
        "count": len(changes),
        "version": row["version"],
    })


def _apply_upstream(node_id: str, field: str | None, reject: bool, if_match: str | None) -> dict[str, Any]:
    """Apply a versioned decision and its remaining-change metadata atomically."""
    from resume_agent.db.connection import get_connection

    expected = _write_version(if_match)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id=? AND deleted_at IS NULL", (node_id,),
        ).fetchone()
        if row is None:
            return error("NODE_NOT_FOUND", f"节点 {node_id} 不存在")
        if row["version"] != expected:
            raise HTTPException(409, {"message": "节点已更新，请重新加载后重试", "version": row["version"]})
        try:
            changes = json.loads(row["upstream_changes"] or "{}")
        except (TypeError, ValueError):
            return error("PARSE_ERROR", "变更数据解析失败")
        if not changes:
            return error("NO_CHANGES", "没有待处理的上游变更")
        if field is not None and field not in changes:
            return error("FIELD_NOT_FOUND", f"字段 {field} 没有待处理的变更")
        fields = [field] if field is not None else list(changes)
        content = _get_node_content(node_id, conn=conn)
        if not reject:
            pi = content.get("personal_info", {})
            if not isinstance(pi, dict):
                pi = {}
            for key in fields:
                pi[key] = changes[key].get("new")
            content["personal_info"] = pi
            save_node_content(node_id, content, expected, conn=conn)
        for key in fields:
            del changes[key]
        # Metadata-only decisions also advance the version to protect stale requests.
        version = conn.execute("SELECT version FROM resume_versions WHERE node_id=?", (node_id,)).fetchone()["version"]
        if version == expected:
            conn.execute("UPDATE resume_versions SET version=version+1 WHERE node_id=?", (node_id,))
            version += 1
        conn.execute(
            "UPDATE resume_versions SET upstream_changes=?,has_upstream_update=? WHERE node_id=?",
            (json.dumps(changes, ensure_ascii=False) if changes else None, int(bool(changes)), node_id),
        )
    if field is None:
        return success({"merged_count": len(fields), "all_merged": True, "version": version})
    return success({"field": field, "rejected" if reject else "merged": True,
                    "remaining_changes": len(changes), "version": version})


@router.post("/tree/node/{node_id}/merge")
async def merge_field(node_id: str, req: MergeRequest, if_match: str | None = Header(default=None)) -> dict[str, Any]:
    return _apply_upstream(node_id, req.field, False, if_match)


@router.post("/tree/node/{node_id}/merge/all")
async def merge_all(node_id: str, if_match: str | None = Header(default=None)) -> dict[str, Any]:
    return _apply_upstream(node_id, None, False, if_match)


@router.post("/tree/node/{node_id}/reject")
async def reject_field(node_id: str, req: RejectRequest, if_match: str | None = Header(default=None)) -> dict[str, Any]:
    return _apply_upstream(node_id, req.field, True, if_match)
