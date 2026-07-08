"""信息完整性检测 + 段落编辑端点（US-15）。

提供简历信息完整度检测和段落级编辑功能。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from resume_agent.api.response import error, success

logger = logging.getLogger("resume_agent")

router = APIRouter(tags=["completeness"])


def _get_node_content(node_id: str) -> dict[str, Any] | None:
    """获取节点 content_json。"""
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
    from resume_agent.db.connection import get_connection

    with get_connection() as conn:
        content_str = json.dumps(content, ensure_ascii=False)
        cursor = conn.execute(
            "UPDATE resume_versions SET content_json = ? WHERE node_id = ?",
            [content_str, node_id],
        )
    return cursor.rowcount > 0


class CompletenessRequest(BaseModel):
    """完整性检测请求。"""

    node_id: str


class SectionEditRequest(BaseModel):
    """段落编辑请求。"""

    section: str
    data: Any


# 检测规则权重
_FIELD_WEIGHTS = {
    "name": 15,
    "phone": 10,
    "email": 10,
    "summary": 15,
    "experience": 20,
    "projects": 15,
    "skills": 10,
    "education": 5,
}


def _check_personal_info(content: dict[str, Any]) -> list[dict[str, Any]]:
    """检测个人信息完整度。"""
    checks: list[dict[str, Any]] = []
    pi = content.get("personal_info", {})
    if not isinstance(pi, dict):
        pi = {}
    contact = pi.get("contact", {})
    if not isinstance(contact, dict):
        contact = {}

    for field, weight in [("name", 15), ("phone", 10), ("email", 10)]:
        value = contact.get(field, "")
        if value and str(value).strip():
            checks.append({"field": field, "status": "ok", "weight": weight})
        else:
            checks.append({"field": field, "status": "missing", "weight": 0, "message": f"{field} 缺失"})

    return checks


def _check_summary(content: dict[str, Any]) -> dict[str, Any]:
    """检测自我评价。"""
    pi = content.get("personal_info", {})
    summary = ""
    if isinstance(pi, dict):
        summary = str(pi.get("summary", "") or "")
    if not summary:
        summary = str(content.get("summary", "") or "")

    if not summary.strip():
        return {"field": "summary", "status": "missing", "weight": 0, "message": "自我评价缺失"}
    if len(summary) < 20:
        return {"field": "summary", "status": "weak", "weight": 7, "message": f"内容不足（{len(summary)}字）"}
    return {"field": "summary", "status": "ok", "weight": 15}


def _check_section_list(
    content: dict[str, Any], section: str, weight: int, label: str
) -> dict[str, Any]:
    """检测列表型段落。"""
    items = content.get(section, [])
    if not isinstance(items, list):
        items = []
    count = len(items)
    if count == 0:
        return {"field": section, "status": "missing", "weight": 0, "message": f"无{label}"}
    if count < 1:
        return {"field": section, "status": "weak", "weight": weight // 2, "message": f"{label}不足"}
    return {"field": section, "status": "ok", "weight": weight, "count": count}


def _check_skills(content: dict[str, Any]) -> dict[str, Any]:
    """检测技能。"""
    skills = content.get("skills")
    if not skills:
        return {"field": "skills", "status": "missing", "weight": 0, "message": "无技能总结"}
    if isinstance(skills, list) and len(skills) > 0:
        return {"field": "skills", "status": "ok", "weight": 10, "count": len(skills)}
    if isinstance(skills, dict) and len(skills) > 0:
        total = sum(
            len(v) for v in skills.values() if isinstance(v, list)
        )
        if total > 0:
            return {"field": "skills", "status": "ok", "weight": 10, "count": total}
    return {"field": "skills", "status": "missing", "weight": 0, "message": "无技能总结"}


def _check_education(content: dict[str, Any]) -> dict[str, Any]:
    """检测教育背景。"""
    pi = content.get("personal_info", {})
    edu = []
    if isinstance(pi, dict):
        edu = pi.get("education", [])
    if not isinstance(edu, list):
        edu = []
    if len(edu) == 0:
        # fallback: 顶层 education
        edu = content.get("education", [])
        if not isinstance(edu, list):
            edu = []
    if len(edu) == 0:
        return {"field": "education", "status": "missing", "weight": 0, "message": "无教育背景"}
    return {"field": "education", "status": "ok", "weight": 5, "count": len(edu)}


@router.post("/completeness/check")
async def check_completeness(req: CompletenessRequest) -> dict[str, Any]:
    """检测简历信息完整度。"""
    content = _get_node_content(req.node_id)
    if content is None:
        return error("NODE_NOT_FOUND", f"节点 {req.node_id} 不存在")

    checks: list[dict[str, Any]] = []

    # 个人信息
    checks.extend(_check_personal_info(content))

    # 自我评价
    checks.append(_check_summary(content))

    # 工作经历
    checks.append(_check_section_list(content, "experience", 20, "工作经历"))

    # 项目经历
    checks.append(_check_section_list(content, "projects", 15, "项目经历"))

    # 技能
    checks.append(_check_skills(content))

    # 教育背景
    checks.append(_check_education(content))

    # 计算总分
    total_weight = sum(c.get("weight", 0) for c in checks)
    max_weight = sum(_FIELD_WEIGHTS.values())
    score = round(total_weight / max_weight * 100) if max_weight > 0 else 0

    return success({
        "score": score,
        "checks": checks,
    })


@router.put("/tree/node/{node_id}/section")
async def update_section(node_id: str, req: SectionEditRequest) -> dict[str, Any]:
    """编辑节点的某个段落。"""
    content = _get_node_content(node_id)
    if content is None:
        return error("NODE_NOT_FOUND", f"节点 {node_id} 不存在")

    valid_sections = {"summary", "experience", "projects", "skills", "education"}
    if req.section not in valid_sections:
        return error("INVALID_SECTION", f"不支持的段落: {req.section}")

    if req.section == "summary":
        content["summary"] = req.data
        pi = content.get("personal_info", {})
        if isinstance(pi, dict):
            pi["summary"] = req.data
            content["personal_info"] = pi
    elif req.section == "education":
        pi = content.get("personal_info", {})
        if isinstance(pi, dict):
            pi["education"] = req.data
            content["personal_info"] = pi
        content["education"] = req.data
    else:
        content[req.section] = req.data

    if not _save_node_content(node_id, content):
        return error("UPDATE_FAILED", "保存段落失败")

    return success({"section": req.section, "data": req.data})
