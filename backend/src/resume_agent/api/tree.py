"""版本树端点。

实现版本树的读取、新建、详情、更新四个端点。
对齐 design.md（version-tree-mgmt）第 1 节。

- ``GET  /api/tree``              获取整棵树（nodes + edges）
- ``POST /api/tree/node``         新建节点，写入 resume_versions 表
- ``GET  /api/tree/{node_id}``     获取单个节点详情（content_json 解析）
- ``PUT  /api/tree/node/{node_id}`` 更新节点 title / content_json

edges 逻辑：每个有 ``parent_id`` 的节点生成一条 ``{source: parent_id, target: node_id}``。
"""

from __future__ import annotations

import contextlib
import json
import re
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from resume_agent.api.response import error, success
from resume_agent.db.connection import get_connection
from resume_agent.services.node_content import (
    get_node_content,
    get_node_history,
    move_node_history,
    save_node_content,
)

router = APIRouter(prefix="/tree", tags=["tree"])

# 中文方向 → 英文 slug 映射（branch 节点 node_id 使用）
_DIRECTION_SLUGS: dict[str, str] = {
    "安全": "security",
    "算法": "algorithm",
    "后端": "backend",
    "前端": "frontend",
    "数据": "data",
    "产品": "product",
    "其他": "other",
}


class CreateNodeRequest(BaseModel):
    """新建节点请求体。"""

    parent_id: str
    node_type: str  # branch / company（master 由 init_db seed，不可手动创建）
    title: str
    company: str | None = None
    direction: str | None = None
    role: str | None = None  # 岗位（company 节点用于生成 node_id）


class UpdateNodeRequest(BaseModel):
    """更新节点请求体。"""

    title: str | None = None
    content_json: dict[str, Any] | None = None
    expected_version: int | None = Field(default=None, strict=True, ge=0)


class HistoryRequest(BaseModel):
    expected_version: int | None = Field(default=None, strict=True, ge=0)


def _slugify(text: str) -> str:
    """将文本转为 URL 安全的 slug（小写、连字符分隔）。"""
    slug = text.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^\w\-]", "", slug)  # 移除非字母数字/连字符字符
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _direction_to_slug(direction: str) -> str:
    """将方向名转为 slug，中文方向优先查映射表。"""
    if direction in _DIRECTION_SLUGS:
        return _DIRECTION_SLUGS[direction]
    return _slugify(direction)


def _generate_node_id(req: CreateNodeRequest) -> str:
    """根据节点类型生成业务 node_id。

    - branch: direction 的 slugify（如 "安全" → "security"）
    - company: "{company}-{role}" 的 slugify（如 "Tencent-RS" → "tencent-rs"）
    """
    if req.node_type == "branch":
        return _direction_to_slug(req.direction or req.title)
    if req.node_type == "company":
        company = req.company or req.title
        if req.role:
            return _slugify(f"{company}-{req.role}")
        return _slugify(company)
    return _slugify(req.title)


def _row_to_node(row: dict[str, Any]) -> dict[str, Any]:
    """将 DB 行转为节点字典，并解析 content_json。

    content_json 为 JSON 字符串时解析为 dict；为 NULL 时返回 None；
    非 JSON 字符串时保留原值。
    """
    content = row["content_json"]
    if content is not None:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            content = json.loads(content)  # 非 JSON 字符串时保留原值
    if isinstance(content, dict):
        content["version"] = row["version"]
    return {
        "version": row["version"],
        "id": row["id"],
        "node_id": row["node_id"],
        "parent_id": row["parent_id"],
        "node_type": row["node_type"],
        "title": row["title"],
        "company": row["company"],
        "direction": row["direction"],
        "content_json": content,
        "has_upstream_update": bool(row["has_upstream_update"]) if "has_upstream_update" in row else False,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("")
def get_tree() -> dict[str, Any]:
    """获取版本树结构。

    从 ``resume_versions`` 表读取所有节点，构建 ``nodes`` 与 ``edges`` 数组。

    Returns:
        统一响应 envelope，``data`` 含 ``nodes`` 与 ``edges`` 数组。
        edges 由每个有 parent_id 的节点生成：``{source: parent_id, target: node_id}``。
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, node_id, parent_id, node_type, title, company, direction,
                   content_json, has_upstream_update, version, created_at, updated_at
            FROM resume_versions
            WHERE deleted_at IS NULL
            ORDER BY created_at, node_id
            """
        ).fetchall()

    nodes = [_row_to_node(row) for row in rows]
    edges = [
        {"source": node["parent_id"], "target": node["node_id"]}
        for node in nodes
        if node["parent_id"]
    ]
    return success({"nodes": nodes, "edges": edges})


@router.post("/node")
def create_node(req: CreateNodeRequest) -> dict[str, Any]:
    """新建版本树节点，写入 ``resume_versions`` 表。

    验证规则：
    - node_type 仅支持 branch / company（master 由系统 seed）
    - parent_id 对应的节点必须存在
    - branch 的 parent 必须是 master
    - company 的 parent 必须是 branch
    - 同一 branch 下不允许重复 company（company + parent_id 唯一）

    node_id 生成：
    - branch: direction 的 slugify（如 "安全" → "security"）
    - company: "{company}-{role}" 的 slugify

    Args:
        req: 节点创建请求。

    Returns:
        统一响应 envelope，``data`` 为新节点对象。
    """
    if req.node_type not in ("branch", "company"):
        return error(
            "INVALID_NODE_TYPE",
            f"仅支持创建 branch/company 节点: {req.node_type}",
        )
    if req.node_type == "company" and not req.company:
        return error("MISSING_COMPANY", "company 节点必须提供 company 字段")

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        # 1. 验证 parent 存在
        parent = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ? AND deleted_at IS NULL",
            (req.parent_id,),
        ).fetchone()
        if parent is None:
            return error("PARENT_NOT_FOUND", f"父节点不存在: {req.parent_id}")

        # 2. 验证 parent 类型匹配
        if req.node_type == "branch" and parent["node_type"] != "master":
            return error("PARENT_TYPE_MISMATCH", "branch 节点的父节点必须是 master")
        if req.node_type == "company" and parent["node_type"] != "branch":
            return error("PARENT_TYPE_MISMATCH", "company 节点的父节点必须是 branch")

        # 3. company 去重：同一 branch 下不允许重复 company
        if req.node_type == "company":
            dup = conn.execute(
                """
                SELECT * FROM resume_versions
                WHERE node_type = 'company' AND company = ? AND parent_id = ? AND deleted_at IS NULL
                """,
                (req.company, req.parent_id),
            ).fetchone()
            if dup is not None:
                return error(
                    "DUPLICATE_COMPANY",
                    f"该分支下已存在公司: {req.company}",
                )

        # 4. 生成 node_id 并检查唯一性
        node_id = _generate_node_id(req)
        existing = conn.execute(
            "SELECT node_id FROM resume_versions WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        if existing is not None:
            return error("NODE_ID_CONFLICT", f"节点 ID 已存在: {node_id}")

        # 5. 继承父节点 personal_info + section_order（US-12 + US-13）
        parent_content_raw = parent["content_json"]
        inherited_personal_info = None
        inherited_section_order = None
        if parent_content_raw:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                parent_content = (
                    json.loads(parent_content_raw)
                    if isinstance(parent_content_raw, str)
                    else parent_content_raw
                )
                if isinstance(parent_content, dict):
                    inherited_personal_info = parent_content.get("personal_info")
                    inherited_section_order = parent_content.get("section_order")

        # 6. INSERT 到 resume_versions
        node_uuid = str(uuid.uuid4())
        # 如果继承了字段，写入新节点的 content_json
        inherited_data: dict[str, Any] = {}
        if inherited_personal_info:
            inherited_data["personal_info"] = inherited_personal_info
        if inherited_section_order:
            inherited_data["section_order"] = inherited_section_order
        if inherited_data:
            content_json_str = json.dumps(inherited_data, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO resume_versions
                    (id, node_id, parent_id, node_type, title, company, direction, content_json,
                     upstream_baseline_json, upstream_source_id, upstream_source_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_uuid,
                    node_id,
                    req.parent_id,
                    req.node_type,
                    req.title,
                    req.company,
                    req.direction,
                    content_json_str,
                    parent_content_raw or "{}",
                    req.parent_id,
                    parent["version"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO resume_versions
                    (id, node_id, parent_id, node_type, title, company, direction,
                     upstream_baseline_json, upstream_source_id, upstream_source_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_uuid,
                    node_id,
                    req.parent_id,
                    req.node_type,
                    req.title,
                    req.company,
                    req.direction,
                    parent_content_raw or "{}",
                    req.parent_id,
                    parent["version"],
                ),
            )

        row = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?",
            (node_id,),
        ).fetchone()

    return success(_row_to_node(row))


@router.get("/trash")
def get_trash() -> dict[str, Any]:
    """List restorable batch roots (children restore with their batch)."""
    with get_connection() as conn:
        items = conn.execute(
            "SELECT n.node_id,n.title,n.deleted_at,n.delete_batch,"
            "datetime(n.deleted_at,'+30 days') AS expires_at FROM resume_versions n "
            "WHERE n.deleted_at > datetime('now','-30 days') AND NOT EXISTS "
            "(SELECT 1 FROM resume_versions p WHERE p.node_id=n.parent_id "
            "AND p.delete_batch=n.delete_batch) ORDER BY n.deleted_at DESC"
        ).fetchall()
    return success({"items": items})


@router.get("/node/{node_id}/history")
def node_history(node_id: str) -> dict[str, Any]:
    return success(get_node_history(node_id))


@router.post("/node/{node_id}/undo")
def undo_node(node_id: str, req: HistoryRequest) -> dict[str, Any]:
    if move_node_history(node_id, req.expected_version):
        from resume_agent.api.upstream import propagate_upstream_changes

        propagate_upstream_changes(node_id)
    return get_node(node_id)


@router.post("/node/{node_id}/redo")
def redo_node(node_id: str, req: HistoryRequest) -> dict[str, Any]:
    if move_node_history(node_id, req.expected_version, redo=True):
        from resume_agent.api.upstream import propagate_upstream_changes

        propagate_upstream_changes(node_id)
    return get_node(node_id)


@router.post("/node/{node_id}/restore")
def restore_node(node_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM resume_versions WHERE node_id=?", (node_id,)).fetchone()
        if row is None or row["deleted_at"] is None:
            raise HTTPException(404, "回收站节点不存在")
        alive = conn.execute(
            "SELECT 1 FROM resume_versions WHERE node_id=? AND deleted_at>datetime('now','-30 days')",
            (node_id,),
        ).fetchone()
        if alive is None:
            raise HTTPException(410, "已超过30天恢复期限")
        batch = conn.execute(
            "SELECT node_id,parent_id FROM resume_versions WHERE delete_batch=?", (row["delete_batch"],),
        ).fetchall()
        ids = {item["node_id"] for item in batch}
        for item in batch:
            parent_id = item["parent_id"]
            if parent_id and parent_id not in ids:
                parent = conn.execute(
                    "SELECT 1 FROM resume_versions WHERE node_id=? AND deleted_at IS NULL", (parent_id,),
                ).fetchone()
                if parent is None:
                    raise HTTPException(409, "请先恢复父节点")
        conn.execute(
            "UPDATE resume_versions SET deleted_at=NULL,delete_batch=NULL,version=version+1,"
            "updated_at=datetime('now') WHERE delete_batch=?", (row["delete_batch"],),
        )
    return success({"restored_count": len(batch)})


@router.get("/{node_id}")
def get_node(node_id: str) -> dict[str, Any]:
    """获取单个节点详情。

    content_json 为 JSON 字符串时解析为 dict 返回；为 NULL 时返回 null。

    Args:
        node_id: 业务节点 ID。

    Returns:
        统一响应 envelope，``data`` 为节点对象。
        节点不存在时返回 HTTP 404 + error envelope。
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ? AND deleted_at IS NULL",
            (node_id,),
        ).fetchone()

    if row is None:
        return JSONResponse(
            status_code=404,
            content=error("NODE_NOT_FOUND", f"节点不存在: {node_id}"),
        )
    return success(_row_to_node(row))


@router.put("/node/{node_id}")
def update_node(node_id: str, req: UpdateNodeRequest) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        content = get_node_content(node_id, conn=conn)
        if content is None:
            return JSONResponse(status_code=404, content=error("NODE_NOT_FOUND", f"节点不存在: {node_id}"))
        if req.expected_version is None:
            raise HTTPException(428, "保存需要节点版本，请重新加载后重试")
        previous_content = {key: value for key, value in content.items() if key != "version"}
        save_node_content(
            node_id, content if req.content_json is None else req.content_json,
            req.expected_version, conn=conn, title=req.title,
        )
        row = conn.execute("SELECT * FROM resume_versions WHERE node_id=?", (node_id,)).fetchone()
    if req.content_json is not None and any(
        previous_content.get(section) != req.content_json.get(section)
        for section in ("personal_info", "experience", "projects", "skills")
    ):
        from resume_agent.api.upstream import propagate_upstream_changes

        propagate_upstream_changes(node_id)
    return success(_row_to_node(row))


@router.delete("/node/{node_id}")
def delete_node(node_id: str) -> dict[str, Any]:
    """Soft-delete the currently live subtree under a distinct recovery batch."""
    if node_id == "master":
        return error("CANNOT_DELETE_MASTER", "master 节点不可删除")
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT node_id FROM resume_versions WHERE node_id=? AND deleted_at IS NULL", (node_id,),
        ).fetchone()
        if row is None:
            return error("NODE_NOT_FOUND", f"节点不存在: {node_id}")
        nodes = conn.execute(
            "WITH RECURSIVE subtree(node_id) AS (SELECT node_id FROM resume_versions WHERE node_id=? "
            "UNION ALL SELECT n.node_id FROM resume_versions n JOIN subtree s ON n.parent_id=s.node_id "
            "WHERE n.deleted_at IS NULL) SELECT node_id FROM subtree", (node_id,),
        ).fetchall()
        batch = str(uuid.uuid4())
        conn.executemany(
            "UPDATE resume_versions SET deleted_at=datetime('now'),delete_batch=?,version=version+1,"
            "updated_at=datetime('now') WHERE node_id=?", [(batch, n["node_id"]) for n in nodes],
        )
    return success({"deleted_count": len(nodes)})
