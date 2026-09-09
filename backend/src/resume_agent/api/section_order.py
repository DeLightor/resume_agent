"""简历段落排序端点（US-13）。

提供段落顺序的获取和更新功能。
段落顺序存储在版本树节点的 content_json.section_order 字段中。

对齐 PRD US-13 / openspec/changes/section-order/proposal.md。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from resume_agent.api.response import error, success

logger = logging.getLogger("resume_agent")

router = APIRouter(tags=["section-order"])

# 默认 8 段顺序
DEFAULT_SECTION_ORDER: list[dict[str, Any]] = [
    {"key": "summary", "title": "自我评价", "visible": True},
    {"key": "experience", "title": "工作经历", "visible": True},
    {"key": "projects", "title": "项目经历", "visible": True},
    {"key": "skills", "title": "技能总结", "visible": True},
    {"key": "education", "title": "教育背景", "visible": True},
    {"key": "awards", "title": "获奖经历", "visible": False},
    {"key": "publications", "title": "论文/专利", "visible": False},
    {"key": "certificates", "title": "证书", "visible": False},
]


class SectionItem(BaseModel):
    """段落排序单项。"""

    key: str
    title: str
    visible: bool = True


class SectionOrder(BaseModel):
    """段落排序列表。"""

    sections: list[SectionItem]


def _get_node_content(node_id: str) -> dict[str, Any] | None:
    """获取节点 content_json。"""
    import json

    from resume_agent.db.connection import get_connection

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
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}


def _save_node_content(node_id: str, content: dict[str, Any]) -> bool:
    """保存节点 content_json。"""
    import json

    from resume_agent.db.connection import get_connection

    with get_connection() as conn:
        content_str = json.dumps(content, ensure_ascii=False)
        cursor = conn.execute(
            "UPDATE resume_versions SET content_json = ? WHERE node_id = ?",
            [content_str, node_id],
        )
    return cursor.rowcount > 0


@router.get("/tree/node/{node_id}/section-order")
async def get_section_order(node_id: str) -> dict[str, Any]:
    """获取节点的段落顺序。

    不存在时返回默认 8 段顺序。
    """
    content = _get_node_content(node_id)
    if content is None:
        return error("NODE_NOT_FOUND", f"节点 {node_id} 不存在")

    sections = content.get("section_order")
    if not sections or not isinstance(sections, list):
        return success({"sections": DEFAULT_SECTION_ORDER})

    # 校验并补全
    valid_keys = {s["key"] for s in DEFAULT_SECTION_ORDER}
    result: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for s in sections:
        if isinstance(s, dict) and s.get("key") in valid_keys and s["key"] not in seen_keys:
            result.append({
                "key": s["key"],
                "title": s.get("title", ""),
                "visible": s.get("visible", True),
            })
            seen_keys.add(s["key"])

    # 补全缺失的段落
    for default_s in DEFAULT_SECTION_ORDER:
        if default_s["key"] not in seen_keys:
            result.append(default_s)

    return success({"sections": result})


@router.put("/tree/node/{node_id}/section-order")
async def update_section_order(
    node_id: str, order: SectionOrder
) -> dict[str, Any]:
    """更新节点的段落顺序。"""
    content = _get_node_content(node_id)
    if content is None:
        return error("NODE_NOT_FOUND", f"节点 {node_id} 不存在")

    content["section_order"] = [s.model_dump() for s in order.sections]
    if not _save_node_content(node_id, content):
        return error("UPDATE_FAILED", "保存段落顺序失败")

    return success({"sections": content["section_order"]})
