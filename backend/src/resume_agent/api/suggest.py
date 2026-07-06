"""AI 智能补全端点（US-9）。

在 AI 生成简历内容后，识别内容不足的字段，
结合 JD 需求和知识库语义检索，主动推荐可补充的素材。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from resume_agent.api.generate import (
    _collect_search_queries,
    _format_evidence_for_prompt,
    _parse_json_safely,
    _search_knowledge_base,
)
from resume_agent.api.response import error, success

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/suggest", tags=["suggest"])

# 建议数量上限
_MAX_SUGGESTIONS: int = 3
# 补全场景下取 top-3 检索素材
_MAX_EVIDENCE_FOR_SUGGEST: int = 3
# 描述最少字符数
_MIN_DESCRIPTION_LEN: int = 20
# 技能 context 最少字符数
_MIN_SKILL_CONTEXT_LEN: int = 5
# highlights 最少条数
_MIN_HIGHLIGHTS_COUNT: int = 2

# 支持的段落类型
_SECTIONS: tuple[str, ...] = ("experience", "projects", "skills")

_SUGGEST_PROMPT = """你是简历内容补全专家。我会给你一些内容不足的字段和对应的知识库检索素材。
请为每个字段生成一条具体的补充建议。

要求：
1. 严格基于检索到的知识库素材，禁止编造未在素材中出现的内容
2. 每条建议包含：suggested_text（建议补充的文本）、reason（为什么要补充）
3. 如果检索素材与该字段无关，跳过该字段（不生成建议）
4. 最多生成 3 条建议

输出 JSON：
{
  "suggestions": [
    {
      "field": "experience[0].highlights",
      "type": "add_highlight",
      "suggested_text": "具体的建议文本",
      "reason": "补充原因",
      "source": "知识库检索: source_file (相关度 score)"
    }
  ]
}"""


class SuggestRequest(BaseModel):
    """AI 智能补全请求体。"""

    structured_jd: dict[str, Any]
    section: str = "experience"
    content: dict[str, Any]
    gap_report: dict[str, Any] | None = None


def _find_thin_fields(
    section: str, content: dict[str, Any]
) -> list[dict[str, Any]]:
    """识别内容不足的字段。

    Args:
        section: 段落类型（experience / projects / skills）。
        content: 该段落的结构化内容。

    Returns:
        不足字段列表，每项形如::

            {
              "field": "experience[0].highlights",
              "type": "add_highlight",
              "reason": "该经历只有 1 条 highlight，建议补充量化成果",
              "context": {"company": "腾讯", "role": "算法工程师"},
            }
    """
    thin_fields: list[dict[str, Any]] = []

    if section == "experience":
        thin_fields.extend(_find_thin_experience(content))
    elif section == "projects":
        thin_fields.extend(_find_thin_projects(content))
    elif section == "skills":
        thin_fields.extend(_find_thin_skills(content))

    return thin_fields


def _find_thin_experience(content: dict[str, Any]) -> list[dict[str, Any]]:
    """识别 experience 段落中内容不足的字段。

    highlights 少于 2 条视为不足，type="add_highlight"。
    """
    thin: list[dict[str, Any]] = []
    experiences = content.get("experience", [])
    if not isinstance(experiences, list):
        return thin

    for idx, exp in enumerate(experiences):
        if not isinstance(exp, dict):
            continue
        highlights = exp.get("highlights", [])
        if not isinstance(highlights, list):
            highlights = []
        if len(highlights) < _MIN_HIGHLIGHTS_COUNT:
            thin.append({
                "field": f"experience[{idx}].highlights",
                "type": "add_highlight",
                "reason": (
                    f"该经历只有 {len(highlights)} 条 highlight，"
                    "建议补充量化成果"
                ),
                "context": {
                    "company": exp.get("company", ""),
                    "role": exp.get("role", ""),
                },
            })
    return thin


def _find_thin_projects(content: dict[str, Any]) -> list[dict[str, Any]]:
    """识别 projects 段落中内容不足的字段。

    description 少于 20 字 → type="add_detail"；
    tech_stack 为空 → type="add_tech_stack"。
    """
    thin: list[dict[str, Any]] = []
    projects = content.get("projects", [])
    if not isinstance(projects, list):
        return thin

    for idx, proj in enumerate(projects):
        if not isinstance(proj, dict):
            continue
        description = proj.get("description", "")
        if not isinstance(description, str):
            description = str(description) if description else ""
        if len(description) < _MIN_DESCRIPTION_LEN:
            thin.append({
                "field": f"projects[{idx}].description",
                "type": "add_detail",
                "reason": (
                    f"项目描述只有 {len(description)} 字，"
                    "建议补充项目内容与个人贡献"
                ),
                "context": {
                    "name": proj.get("name", ""),
                    "role": proj.get("role", ""),
                },
            })

        tech_stack = proj.get("tech_stack", [])
        if not isinstance(tech_stack, list):
            tech_stack = []
        if len(tech_stack) == 0:
            thin.append({
                "field": f"projects[{idx}].tech_stack",
                "type": "add_tech_stack",
                "reason": "项目缺少技术栈信息，建议补充使用的技术",
                "context": {
                    "name": proj.get("name", ""),
                    "role": proj.get("role", ""),
                },
            })
    return thin


def _find_thin_skills(content: dict[str, Any]) -> list[dict[str, Any]]:
    """识别 skills 段落中内容不足的字段。

    某项 context 为空或少于 5 字 → type="add_skill_context"。
    """
    thin: list[dict[str, Any]] = []
    skills = content.get("skills", {})
    if not isinstance(skills, dict):
        return thin

    for category in ("tech_stack", "hard_skills", "soft_skills"):
        items = skills.get(category, [])
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            context_text = item.get("context", "")
            if not isinstance(context_text, str):
                context_text = str(context_text) if context_text else ""
            if len(context_text) < _MIN_SKILL_CONTEXT_LEN:
                skill_name = item.get("name", "")
                thin.append({
                    "field": f"skills.{category}[{idx}].context",
                    "type": "add_skill_context",
                    "reason": (
                        f"技能 {skill_name} 的使用场景说明"
                        f"只有 {len(context_text)} 字，建议补充实际使用场景"
                    ),
                    "context": {
                        "name": skill_name,
                        "category": category,
                    },
                })
    return thin


async def _generate_suggestions(
    thin_fields: list[dict[str, Any]],
    structured_jd: dict[str, Any],
    section: str,
) -> list[dict[str, Any]]:
    """基于不足字段和知识库检索生成补充建议。

    流程：
    1. 从 JD 提取检索查询词（复用 generate._collect_search_queries）。
    2. 在知识库检索相关素材（复用 generate._search_knowledge_base）。
    3. 调用 LLM 生成建议文本（基于检索素材，不编造）。

    Args:
        thin_fields: ``_find_thin_fields`` 返回的不足字段列表。
        structured_jd: JD 结构化数据。
        section: 段落类型。

    Returns:
        建议列表，每项含 field / type / suggested_text / reason / source。
        知识库为空或 LLM 未配置时返回空列表。
    """
    if not thin_fields:
        return []

    # 1. 从 JD 提取检索查询词
    queries = _collect_search_queries(structured_jd)
    if not queries:
        return []

    # 2. 知识库检索
    evidence = _search_knowledge_base(queries)
    if not evidence:
        # 知识库为空，返回空建议列表
        return []

    # 取 top-3 素材
    evidence = evidence[:_MAX_EVIDENCE_FOR_SUGGEST]

    # 3. 调用 LLM 生成建议
    from resume_agent.llm.client import LLMClient

    llm = LLMClient()
    if not llm.configured:
        # LLM 未配置，返回空建议列表
        return []

    evidence_text = _format_evidence_for_prompt(evidence)
    thin_fields_text = json.dumps(thin_fields, ensure_ascii=False, indent=2)
    jd_summary = json.dumps(structured_jd, ensure_ascii=False, indent=2)

    user_content = f"""目标 JD：
{jd_summary}

内容不足的字段：
{thin_fields_text}

知识库检索到的素材：
{evidence_text}

请为每个不足字段生成补充建议（最多 {_MAX_SUGGESTIONS} 条）。"""

    try:
        response = await llm.chat(
            system_prompt=_SUGGEST_PROMPT,
            user_content=user_content,
            response_format_json=True,
        )
        result = _parse_json_safely(response)
    except Exception as exc:  # noqa: BLE001
        logger.warning("生成建议失败: %s", exc)
        return []

    suggestions = result.get("suggestions", [])
    if not isinstance(suggestions, list):
        return []

    # 过滤无效项并限制数量 ≤ 3
    valid: list[dict[str, Any]] = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        suggested_text = s.get("suggested_text", "")
        if not suggested_text:
            continue
        valid.append({
            "field": s.get("field", ""),
            "type": s.get("type", ""),
            "suggested_text": suggested_text,
            "reason": s.get("reason", ""),
            "source": s.get("source", ""),
        })
        if len(valid) >= _MAX_SUGGESTIONS:
            break

    return valid


@router.post("")
async def suggest(req: SuggestRequest) -> dict[str, Any]:
    """AI 智能补全。

    识别内容不足的字段，结合 JD 需求和知识库语义检索，
    主动推荐可补充的素材。

    Args:
        req: 补全请求。

    Returns:
        统一响应 envelope，data 含::

            {"suggestions": [...], "total": len(...)}
    """
    # 校验 section
    if req.section not in _SECTIONS:
        return error(
            "INVALID_SECTION",
            f"不支持的段落类型: {req.section}，仅支持 {list(_SECTIONS)}",
        )

    # 校验 content
    if not req.content:
        return error("INVALID_REQUEST", "content 不能为空")

    # 1. 识别内容不足字段
    thin_fields = _find_thin_fields(req.section, req.content)

    # 2. 定向检索 + LLM 生成建议
    suggestions = await _generate_suggestions(
        thin_fields, req.structured_jd, req.section
    )

    return success({
        "suggestions": suggestions,
        "total": len(suggestions),
    })
