"""AI 导师学习建议端点（US-11）。

基于 Gap 报告中"未涉及"和"部分缺口"的技能项，调用 LLM 生成
结构化学习路径建议（概念→实践→验证）和学习资源推荐。

混合模式（搜索优先 → LLM 整合，并行调用）：
1. 先用 Tavily 搜索每项技能的真实资源链接。
2. 对每项技能并行调用 LLM，将搜索结果作为上下文传给 LLM。
3. LLM 基于真实 URL 生成中文学习路径和资源描述。
4. 合并所有技能的建议返回。

并行优势：N 个技能同时调用 LLM，总耗时 ≈ 单次调用时间（而非 N 倍）。

对齐 PRD US-11 / openspec/changes/ai-tutor/proposal.md。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from resume_agent.api.response import error, success

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/tutor", tags=["tutor"])

# 单次最多处理的技能数
_MAX_SKILLS: int = 10

# System prompt：中文输出 + 单技能聚焦
_SYSTEM_PROMPT = """你是技术学习路径规划专家。我会给你一个存在缺口的技能项，以及该技能的 Web 搜索结果（真实资源链接）。

请基于搜索结果中的真实 URL 生成学习建议。你需要生成：
1. learning_path: { "concept": 概念学习要点, "practice": 实践练习建议, "validation": 验证方法 }
2. resources: 资源列表，每项含 { "type": "document"|"course"|"project"|"interview", "title": 标题, "url": 链接, "description": 简短描述 }

要求：
- 所有内容必须用中文描述
- 优先使用搜索结果中的真实 URL，不要自己编造链接
- 如果搜索结果不够 4 个，可以少给，不要凑数
- 不要重复同一个 URL
- 每项技能推荐 ≤ 4 个资源
- 输出必须是合法的 JSON 对象，格式为 { "learning_path": {...}, "resources": [...] }
- 不要输出任何 JSON 之外的解释性文字"""

_USER_PROMPT_TEMPLATE = """请为以下技能生成学习建议：

技能：{skill}
状态：{status}

搜索结果：
{search_results}

请基于搜索结果中的真实 URL 生成中文学习建议，输出 JSON 对象。"""


class TutorRequest(BaseModel):
    """AI 导师建议请求体。"""

    items: list[dict[str, Any]]


def _filter_skills(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤出 missing / partial 的技能项，限制最多 _MAX_SKILLS 项。"""
    result: list[dict[str, Any]] = []
    for item in items:
        status = item.get("status", "")
        if status in ("missing", "partial"):
            result.append({
                "skill": item.get("skill", ""),
                "category": item.get("category", ""),
                "status": status,
            })
            if len(result) >= _MAX_SKILLS:
                break
    return result


def _template_suggestion(skill: str, status: str) -> dict[str, Any]:
    """生成模板化建议（LLM 未配置或解析失败时兜底）。"""
    return {
        "skill": skill,
        "status": status,
        "learning_path": {
            "concept": f"系统学习 {skill} 的核心概念和原理",
            "practice": f"通过实际项目练习 {skill} 的使用",
            "validation": f"通过面试题或项目验收 {skill} 掌握程度",
        },
        "resources": [
            {
                "type": "document",
                "title": f"{skill} 官方文档",
                "url": f"https://www.google.com/search?q={skill}+official+documentation",
                "description": f"搜索 {skill} 官方文档",
            },
            {
                "type": "course",
                "title": f"{skill} 系统课程",
                "url": f"https://www.coursera.org/search?query={skill}",
                "description": f"Coursera 搜索 {skill} 相关课程",
            },
            {
                "type": "project",
                "title": f"{skill} 开源项目",
                "url": f"https://github.com/search?q={skill}&type=repositories",
                "description": f"GitHub 搜索 {skill} 相关项目",
            },
            {
                "type": "interview",
                "title": f"{skill} 面试题汇总",
                "url": f"https://www.google.com/search?q={skill}+interview+questions",
                "description": f"搜索 {skill} 面试题",
            },
        ],
    }


def _search_resources_for_skills(
    skills: list[dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    """为技能列表搜索真实资源。

    对每项技能搜索 4 类资源（文档/课程/项目/面试题），
    返回真实 URL 列表。

    Args:
        skills: 技能项列表。

    Returns:
        {技能名: [{type, title, url, description}, ...]} 映射。
        Tavily 未配置时返回空 dict。
    """
    from resume_agent.tools.tavily_search import search_skill_resources

    result: dict[str, list[dict[str, str]]] = {}
    for s in skills:
        skill_name = s["skill"]
        resources = search_skill_resources(skill_name)
        if resources:
            result[skill_name] = resources
    return result


async def _generate_single_suggestion(
    skill_info: dict[str, Any],
    search_resources: list[dict[str, str]],
) -> dict[str, Any]:
    """为单个技能调用 LLM 生成建议。

    将 Tavily 搜索结果作为上下文传给 LLM，LLM 基于真实 URL
    生成中文学习路径和资源描述。

    Args:
        skill_info: 技能信息（含 skill / category / status）。
        search_resources: 该技能的 Tavily 搜索结果。

    Returns:
        单项建议字典。
    """
    from resume_agent.llm.client import LLMClient

    llm = LLMClient()
    skill_name = skill_info["skill"]

    # LLM 未配置时用搜索结果直接组装
    if not llm.configured:
        return _build_single_from_search(skill_info, search_resources)

    # 构造 prompt
    search_results_str = json.dumps(search_resources, ensure_ascii=False, indent=2)
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        skill=skill_name,
        status=skill_info["status"],
        search_results=search_results_str,
    )

    try:
        response_text = await llm.chat(
            system_prompt=_SYSTEM_PROMPT,
            user_content=user_prompt,
            response_format_json=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 生成建议失败 (%s): %s", skill_name, exc)
        return _build_single_from_search(skill_info, search_resources)

    # 解析 LLM 返回的 JSON
    cleaned = response_text.strip()
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
                logger.warning("LLM 返回内容无法解析 (%s)", skill_name)
                data = {}
        else:
            logger.warning("LLM 返回内容无法解析 (%s)", skill_name)
            data = {}

    # 组装建议
    if not isinstance(data, dict):
        data = {}

    return {
        "skill": skill_name,
        "category": skill_info.get("category", ""),
        "status": skill_info["status"],
        "learning_path": data.get("learning_path", {
            "concept": f"系统学习 {skill_name} 的核心概念和原理",
            "practice": f"通过实际项目练习 {skill_name} 的使用",
            "validation": f"通过面试题或项目验收 {skill_name} 掌握程度",
        }),
        "resources": data.get("resources", search_resources[:4]),
    }


async def _generate_suggestions(
    skills: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """并行调用 LLM 为每项技能生成学习建议。

    1. 先用 Tavily 搜索每项技能的真实资源链接。
    2. 对每项技能并行调用 LLM（asyncio.gather），互不阻塞。
    3. 合并所有技能的建议返回。

    Args:
        skills: 过滤后的技能项列表（missing / partial）。

    Returns:
        学习建议列表。
    """
    # 1. 先用 Tavily 搜索真实资源
    search_results = _search_resources_for_skills(skills)

    # 2. 并行调用 LLM，每个技能一个独立任务
    tasks = [
        _generate_single_suggestion(
            s,
            search_results.get(s["skill"], []),
        )
        for s in skills
    ]
    suggestions = await asyncio.gather(*tasks, return_exceptions=False)

    return list(suggestions)


def _build_single_from_search(
    skill_info: dict[str, Any],
    search_resources: list[dict[str, str]],
) -> dict[str, Any]:
    """用搜索结果直接组装单项建议（LLM 漏掉时的 fallback）。

    Args:
        skill_info: 技能信息（含 skill / category / status）。
        search_resources: Tavily 搜索结果列表。

    Returns:
        组装的建议字典。
    """
    skill_name = skill_info["skill"]
    return {
        "skill": skill_name,
        "category": skill_info.get("category", ""),
        "status": skill_info["status"],
        "learning_path": {
            "concept": f"系统学习 {skill_name} 的核心概念和原理",
            "practice": f"通过实际项目练习 {skill_name} 的使用",
            "validation": f"通过面试题或项目验收 {skill_name} 掌握程度",
        },
        "resources": search_resources[:4],
    }


@router.post("/suggest")
async def generate_tutor_suggestions(req: TutorRequest) -> dict[str, Any]:
    """基于 Gap 报告技能缺口生成 AI 导师学习建议。

    混合模式：先用 Tavily 搜索真实资源链接，
    再将搜索结果传给 LLM 整合为中文学习建议。

    Args:
        req: 包含 Gap 报告 items 的请求体。

    Returns:
        统一响应 envelope，data 含 suggestions 列表。
    """
    items = req.items
    if not isinstance(items, list):
        return error("INVALID_REQUEST", "items 必须是列表")

    # 1. 过滤 missing / partial 技能
    skills = _filter_skills(items)
    if not skills:
        return success({"suggestions": []})

    # 2. 搜索 + LLM 整合
    suggestions = await _generate_suggestions(skills)

    return success({"suggestions": suggestions})
