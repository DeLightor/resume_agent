"""Direct-parent, three-way upstream decisions for resume content (US-33)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from resume_agent.api.personal_info import _write_version
from resume_agent.api.response import error, success
from resume_agent.api.tree_events import record_tree_update
from resume_agent.db.connection import get_connection
from resume_agent.services.content_merge import apply_change, build_changes
from resume_agent.services.node_content import get_node_content, save_node_content

logger = logging.getLogger("resume_agent")
router = APIRouter(tags=["upstream"])
MAX_NODES = 50


def _decode(value: Any) -> dict[str, Any]:
    try:
        result = json.loads(value) if value else {}
    except (TypeError, ValueError):
        result = {}
    return result if isinstance(result, dict) else {}


def _children(conn: Any, node_id: str) -> list[dict[str, Any]]:
    return conn.execute("SELECT * FROM resume_versions WHERE parent_id=? AND deleted_at IS NULL", (node_id,)).fetchall()


def _update_child_snapshot(conn: Any, child: dict[str, Any], parent: dict[str, Any]) -> bool:
    """Recompute one direct child's pending decisions in the caller transaction."""
    baseline_raw = child.get("upstream_baseline_json")
    if not baseline_raw:
        # Existing nodes do not have a reliable common ancestor.  Start tracking
        # from their current direct parent without inventing old conflicts.
        conn.execute(
            "UPDATE resume_versions SET upstream_baseline_json=?,upstream_source_id=?,upstream_source_version=? WHERE node_id=?",
            (parent["content_json"] or "{}", parent["node_id"], parent["version"], child["node_id"]),
        )
        return False
    changes = build_changes(_decode(baseline_raw), _decode(parent["content_json"]), _decode(child["content_json"]))
    encoded = json.dumps(changes, ensure_ascii=False) if changes else None
    pending_changed = (child.get("upstream_changes") or None) != encoded or bool(child.get("has_upstream_update")) != bool(changes)
    source_changed = child.get("upstream_source_version") != parent["version"] or child.get("upstream_source_id") != parent["node_id"]
    if pending_changed:
        conn.execute(
            "UPDATE resume_versions SET has_upstream_update=?,upstream_changes=?,upstream_source_id=?,upstream_source_version=?,version=version+1,updated_at=datetime('now') WHERE node_id=?",
            (int(bool(changes)), encoded, parent["node_id"], parent["version"], child["node_id"]),
        )
    elif source_changed:
        conn.execute(
            "UPDATE resume_versions SET upstream_source_id=?,upstream_source_version=? WHERE node_id=?",
            (parent["node_id"], parent["version"], child["node_id"]),
        )
    return pending_changed


def propagate_upstream_changes(node_id: str, db_path: Path | str | None = None) -> int:
    """Reconcile a changed node, then refresh its direct descendants."""
    touched: list[str] = []
    with get_connection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        parent = conn.execute("SELECT * FROM resume_versions WHERE node_id=? AND deleted_at IS NULL", (node_id,)).fetchone()
        if parent is None:
            return 0
        # A child can manually converge with its current parent.  Its old
        # pending prompt must disappear before that child becomes source for
        # descendants.
        if parent.get("parent_id"):
            direct_parent = conn.execute(
                "SELECT * FROM resume_versions WHERE node_id=? AND deleted_at IS NULL", (parent["parent_id"],),
            ).fetchone()
            if direct_parent is not None and _update_child_snapshot(conn, parent, direct_parent):
                touched.append(node_id)
        for child in _children(conn, node_id)[:MAX_NODES]:
            if _update_child_snapshot(conn, child, parent):
                touched.append(child["node_id"])
        if touched:
            record_tree_update(conn, touched)
    logger.info("propagate_upstream_changes: refreshed %d children from %s", len(touched), node_id)
    return len(touched)


class MergeRequest(BaseModel):
    field: str
    upstream_version: int | None = Field(default=None, ge=0)


class RejectRequest(MergeRequest):
    pass


class MergeAllRequest(BaseModel):
    upstream_version: int | None = Field(default=None, ge=0)


def _snapshot_for(row: dict[str, Any]) -> dict[str, Any]:
    changes = _decode(row.get("upstream_changes"))
    public = {key: {name: value for name, value in item.items() if not name.startswith("_")}
              for key, item in changes.items() if isinstance(item, dict)}
    return {
        "has_upstream_update": bool(row.get("has_upstream_update")), "changes": public,
        "count": len(public), "version": row["version"], "upstream_version": row.get("upstream_source_version"),
        "source_node_id": row.get("upstream_source_id"),
    }


@router.get("/tree/node/{node_id}/upstream-changes")
async def get_upstream_changes(node_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM resume_versions WHERE node_id=? AND deleted_at IS NULL", (node_id,)).fetchone()
    if row is None:
        return error("NODE_NOT_FOUND", f"节点 {node_id} 不存在")
    return success(_snapshot_for(row))


def _apply_upstream(node_id: str, fields: list[str] | None, reject: bool, if_match: str | None, upstream_version: int | None) -> dict[str, Any]:
    expected = _write_version(if_match)
    changed_content = False
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM resume_versions WHERE node_id=? AND deleted_at IS NULL", (node_id,)).fetchone()
        if row is None:
            return error("NODE_NOT_FOUND", f"节点 {node_id} 不存在")
        if row["version"] != expected:
            raise HTTPException(409, {"message": "节点已更新，请刷新后重试", "version": row["version"]})
        source_id = row.get("upstream_source_id")
        source = conn.execute("SELECT * FROM resume_versions WHERE node_id=? AND deleted_at IS NULL", (source_id,)).fetchone() if source_id else None
        displayed_version = row.get("upstream_source_version") if upstream_version is None else upstream_version
        legacy = not source_id
        if not legacy and (source is None or source["version"] != displayed_version or row.get("upstream_source_version") != displayed_version):
            raise HTTPException(409, "上游内容已更新，请刷新后重新选择")
        changes = _decode(row.get("upstream_changes"))
        if not changes:
            return error("NO_CHANGES", "没有待处理的上游变更")
        selected = list(changes) if fields is None else fields
        if any(field not in changes for field in selected):
            return error("FIELD_NOT_FOUND", "指定变更已不存在，请刷新后重试")
        if fields is None and any(bool(changes[field].get("conflict")) for field in selected):
            raise HTTPException(409, "存在冲突，请逐项选择采用上游或保留当前")
        content = get_node_content(node_id, conn=conn) or {}
        baseline = _decode(row.get("upstream_baseline_json"))
        for field in selected:
            decision = changes[field]
            if "_locator" not in decision:
                # US-17 rows created before common baselines.  Keep their
                # original API usable while new snapshots always use locators.
                decision = {**decision, "_locator": {"kind": "path", "path": ["personal_info", field]},
                            "_new_missing": False, "_old_missing": False, "_base_missing": False}
            if not reject:
                content = apply_change(content, decision)
                changed_content = True
            baseline = apply_change(baseline, decision)
            del changes[field]
        if changed_content:
            save_node_content(node_id, content, expected, conn=conn)
        current = conn.execute("SELECT version FROM resume_versions WHERE node_id=?", (node_id,)).fetchone()["version"]
        if current == expected:
            conn.execute("UPDATE resume_versions SET version=version+1,updated_at=datetime('now') WHERE node_id=?", (node_id,))
            current += 1
        conn.execute(
            "UPDATE resume_versions SET upstream_baseline_json=?,upstream_changes=?,has_upstream_update=? WHERE node_id=?",
            (json.dumps(baseline, ensure_ascii=False), json.dumps(changes, ensure_ascii=False) if changes else None, int(bool(changes)), node_id),
        )
        notify = [node_id]
        if changed_content:
            for descendant in _children(conn, node_id)[:MAX_NODES]:
                parent_after = {**row, "node_id": node_id, "content_json": json.dumps(content, ensure_ascii=False), "version": current}
                if _update_child_snapshot(conn, descendant, parent_after):
                    notify.append(descendant["node_id"])
        record_tree_update(conn, notify)
    if fields is None:
        return success({"merged_count": len(selected), "all_merged": True, "version": current})
    return success({"field": selected[0], "rejected" if reject else "merged": True, "remaining_changes": len(changes), "version": current})


@router.post("/tree/node/{node_id}/merge")
async def merge_field(node_id: str, req: MergeRequest, if_match: str | None = Header(default=None)) -> dict[str, Any]:
    return _apply_upstream(node_id, [req.field], False, if_match, req.upstream_version)


@router.post("/tree/node/{node_id}/merge/all")
async def merge_all(node_id: str, req: MergeAllRequest | None = None, if_match: str | None = Header(default=None)) -> dict[str, Any]:
    return _apply_upstream(node_id, None, False, if_match, req.upstream_version if req else None)


@router.post("/tree/node/{node_id}/reject")
async def reject_field(node_id: str, req: RejectRequest, if_match: str | None = Header(default=None)) -> dict[str, Any]:
    return _apply_upstream(node_id, [req.field], True, if_match, req.upstream_version)
