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

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from resume_agent.api.response import error, success
from resume_agent.db.connection import get_connection

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
    return {
        "id": row["id"],
        "node_id": row["node_id"],
        "parent_id": row["parent_id"],
        "node_type": row["node_type"],
        "title": row["title"],
        "company": row["company"],
        "direction": row["direction"],
        "content_json": content,
        "has_upstream_update": bool(row["has_upstream_update"]) if "has_upstream_update" in row.keys() else False,
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
                   content_json, has_upstream_update, created_at, updated_at
            FROM resume_versions
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
        # 1. 验证 parent 存在
        parent = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?",
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
                WHERE node_type = 'company' AND company = ? AND parent_id = ?
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
                    (id, node_id, parent_id, node_type, title, company, direction, content_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO resume_versions
                    (id, node_id, parent_id, node_type, title, company, direction)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_uuid,
                    node_id,
                    req.parent_id,
                    req.node_type,
                    req.title,
                    req.company,
                    req.direction,
                ),
            )

        row = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?",
            (node_id,),
        ).fetchone()

    return success(_row_to_node(row))


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
            "SELECT * FROM resume_versions WHERE node_id = ?",
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
    """更新节点的 title 和/或 content_json。

    content_json 存储时序列化为 JSON 字符串，返回时解析为 dict。

    Args:
        node_id: 业务节点 ID。
        req: 更新请求体（title / content_json 均可选）。

    Returns:
        统一响应 envelope，``data`` 为更新后的节点对象。
        节点不存在时返回 HTTP 404 + error envelope。
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return JSONResponse(
                status_code=404,
                content=error("NODE_NOT_FOUND", f"节点不存在: {node_id}"),
            )

        # 动态构建 SET 子句
        updates: list[str] = []
        params: list[Any] = []
        if req.title is not None:
            updates.append("title = ?")
            params.append(req.title)
        if req.content_json is not None:
            updates.append("content_json = ?")
            params.append(json.dumps(req.content_json, ensure_ascii=False))

        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(node_id)
            conn.execute(
                f"UPDATE resume_versions SET {', '.join(updates)} WHERE node_id = ?",
                params,
            )

        updated = conn.execute(
            "SELECT * FROM resume_versions WHERE node_id = ?",
            (node_id,),
        ).fetchone()

    return success(_row_to_node(updated))


@router.delete("/node/{node_id}")
def delete_node(node_id: str) -> dict[str, Any]:
    """删除节点及其所有子孙节点。

    递归查找并删除以 node_id 为根的子树（含自身）。
    master 节点不可删除。

    Args:
        node_id: 要删除的节点 ID。

    Returns:
        统一响应 envelope，data 含 deleted_count。
    """
    if node_id == "master":
        return error("CANNOT_DELETE_MASTER", "master 节点不可删除")

    with get_connection() as conn:
        # 检查节点是否存在
        row = conn.execute(
            "SELECT node_id FROM resume_versions WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return error("NODE_NOT_FOUND", f"节点不存在: {node_id}")

        # 递归收集所有子孙节点 ID
        to_delete: list[str] = [node_id]
        queue: list[str] = [node_id]
        while queue:
            current = queue.pop(0)
            children = conn.execute(
                "SELECT node_id FROM resume_versions WHERE parent_id = ?",
                (current,),
            ).fetchall()
            for child in children:
                to_delete.append(child["node_id"])
                queue.append(child["node_id"])

        # 批量删除
        placeholders = ",".join("?" * len(to_delete))
        conn.execute(
            f"DELETE FROM resume_versions WHERE node_id IN ({placeholders})",
            to_delete,
        )

    return success({"deleted_count": len(to_delete)})
