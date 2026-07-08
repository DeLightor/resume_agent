"""个人信息管理端点（US-12）。

提供个人信息的获取、更新和从知识库提取功能。
个人信息存储在版本树节点的 content_json.personal_info 字段中。

对齐 PRD US-12 / openspec/changes/personal-info/proposal.md。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from resume_agent.api.response import error, success

logger = logging.getLogger("resume_agent")

router = APIRouter(tags=["personal-info"])


# === Pydantic 模型 ===


class ContactInfo(BaseModel):
    """联系信息。"""

    name: str = ""
    gender: str = ""
    birth_date: str = ""
    phone: str = ""
    email: str = ""
    location: str = ""
    website: str = ""
    github: str = ""
    linkedin: str = ""


class JobIntention(BaseModel):
    """求职意向。"""

    target_role: str = ""
    expected_salary: str = ""
    availability: str = ""


class EducationItem(BaseModel):
    """教育背景单项。"""

    school: str = ""
    degree: str = ""
    major: str = ""
    period: str = ""


class PersonalInfo(BaseModel):
    """完整个人信息。"""

    contact: ContactInfo = ContactInfo()
    job_intention: JobIntention = JobIntention()
    education: list[EducationItem] = []
    summary: str = ""


# === 辅助函数 ===


def _get_node_content(node_id: str) -> dict[str, Any] | None:
    """获取节点 content_json，不存在返回 None。"""
    from resume_agent.db.connection import get_connection

    import json

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
    """保存节点 content_json，成功返回 True。"""
    from resume_agent.db.connection import get_connection

    import json

    with get_connection() as conn:
        content_str = json.dumps(content, ensure_ascii=False)
        cursor = conn.execute(
            "UPDATE resume_versions SET content_json = ? WHERE node_id = ?",
            [content_str, node_id],
        )
    return cursor.rowcount > 0


def _extract_personal_info(content: dict[str, Any]) -> PersonalInfo:
    """从 content_json 中提取 personal_info，不存在返回空对象。"""
    pi_data = content.get("personal_info", {})
    if not isinstance(pi_data, dict):
        return PersonalInfo()
    try:
        return PersonalInfo(**pi_data)
    except Exception:  # noqa: BLE001
        return PersonalInfo()


# === API 端点 ===


@router.get("/tree/node/{node_id}/personal-info")
async def get_personal_info(node_id: str) -> dict[str, Any]:
    """获取节点的个人信息。

    Args:
        node_id: 节点 ID。

    Returns:
        统一响应 envelope，data 含 personal_info 对象。
    """
    content = _get_node_content(node_id)
    if content is None:
        return error("NODE_NOT_FOUND", f"节点 {node_id} 不存在")

    pi = _extract_personal_info(content)
    return success({"personal_info": pi.model_dump()})


@router.put("/tree/node/{node_id}/personal-info")
async def update_personal_info(
    node_id: str, info: PersonalInfo
) -> dict[str, Any]:
    """更新节点的个人信息。

    Args:
        node_id: 节点 ID。
        info: 完整的个人信息对象。

    Returns:
        统一响应 envelope，data 含更新后的 personal_info。
    """
    content = _get_node_content(node_id)
    if content is None:
        return error("NODE_NOT_FOUND", f"节点 {node_id} 不存在")

    content["personal_info"] = info.model_dump()
    if not _save_node_content(node_id, content):
        return error("UPDATE_FAILED", "保存个人信息失败")

    # US-17: 触发上游变更传播到子节点
    try:
        from resume_agent.api.upstream import propagate_upstream_changes
        marked = propagate_upstream_changes(node_id)
        logger.info("upstream propagation: marked %d children from %s", marked, node_id)
    except Exception as exc:
        logger.warning("upstream propagation failed: %s", exc)

    return success({"personal_info": info.model_dump()})


@router.post("/personal-info/extract")
async def extract_personal_info() -> dict[str, Any]:
    """从知识库文档中提取个人信息。

    流程：
    1. 从知识库搜索包含个人信息的文本片段（搜索"姓名 电话 邮箱 教育"等关键词）。
    2. 将搜索结果传给 LLM，提取结构化的个人信息。
    3. LLM 未配置时返回错误提示。

    Returns:
        统一响应 envelope，data 含提取的 personal_info。
    """
    from resume_agent.rag.chroma_client import get_knowledge_collection

    # 1. 从知识库搜索个人信息相关文本
    collection = get_knowledge_collection()
    search_queries = ["姓名 电话 邮箱 地址", "教育背景 学校 学历", "个人简介 自我介绍"]
    all_chunks: list[str] = []
    seen_ids: set[str] = set()

    for query in search_queries:
        try:
            result = collection.query(query_texts=[query], n_results=3)
            ids = result.get("ids", [[]])[0]
            documents = result.get("documents", [[]])[0]
            for idx, doc in enumerate(documents):
                chunk_id = ids[idx] if idx < len(ids) else ""
                if chunk_id and chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    all_chunks.append(doc)
        except Exception:  # noqa: BLE001
            continue

    if not all_chunks:
        return error("NO_CONTENT", "知识库为空，请先上传知识素材")

    # 2. 检查 LLM 配置
    from resume_agent.llm.client import LLMClient

    llm = LLMClient()
    if not llm.configured:
        return error("LLM_NOT_CONFIGURED", "LLM 未配置，无法提取个人信息")

    # 3. 调用 LLM 提取个人信息
    context = "\n---\n".join(all_chunks[:5])  # 最多取 5 个片段
    system_prompt = """你是信息提取助手。从给定的文本片段中提取个人信息，输出 JSON 对象。
提取以下字段（找不到的留空）：
{
  "contact": { "name": "", "gender": "", "birth_date": "", "phone": "", "email": "", "location": "", "website": "", "github": "", "linkedin": "" },
  "education": [ { "school": "", "degree": "", "major": "", "period": "" } ],
  "summary": ""
}
只输出 JSON，不要输出其他内容。"""

    user_prompt = f"请从以下文本中提取个人信息：\n\n{context}"

    try:
        response = await llm.chat(
            system_prompt=system_prompt,
            user_content=user_prompt,
            response_format_json=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 提取个人信息失败: %s", exc)
        return error("LLM_ERROR", f"LLM 提取失败: {exc}")

    # 4. 解析 LLM 返回
    import json

    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                data = json.loads(cleaned[first : last + 1])
            except json.JSONDecodeError:
                return error("PARSE_ERROR", "LLM 返回内容无法解析")
        else:
            return error("PARSE_ERROR", "LLM 返回内容无法解析")

    # 5. 组装 PersonalInfo
    contact_data = data.get("contact", {})
    education_data = data.get("education", [])

    contact = ContactInfo(
        name=contact_data.get("name", ""),
        gender=contact_data.get("gender", ""),
        birth_date=contact_data.get("birth_date", ""),
        phone=contact_data.get("phone", ""),
        email=contact_data.get("email", ""),
        location=contact_data.get("location", ""),
        website=contact_data.get("website", ""),
        github=contact_data.get("github", ""),
        linkedin=contact_data.get("linkedin", ""),
    )

    education = [
        EducationItem(
            school=e.get("school", ""),
            degree=e.get("degree", ""),
            major=e.get("major", ""),
            period=e.get("period", ""),
        )
        for e in education_data
        if isinstance(e, dict)
    ]

    pi = PersonalInfo(
        contact=contact,
        education=education,
        summary=data.get("summary", ""),
    )

    return success({"personal_info": pi.model_dump()})
