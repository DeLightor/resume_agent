"""Tavily Web 搜索工具模块（US-11 导师建议增强）。

为 AI 导师学习建议提供真实有效的 Web 搜索资源链接。

流程：
1. 对每项技能构造搜索查询（"{skill} 学习教程 文档"、"面试题" 等）。
2. 调用 Tavily Search API 获取搜索结果。
3. 将结果分类映射为 document / course / project / interview 资源类型。

Tavily API 未配置时返回空列表，调用方走 LLM 训练数据兜底。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("resume_agent")

# 每项技能搜索的资源类型和查询模板
_SEARCH_QUERIES: list[dict[str, str]] = [
    {
        "type": "document",
        "query_template": "{skill} official documentation tutorial",
    },
    {
        "type": "course",
        "query_template": "{skill} course tutorial beginner",
    },
    {
        "type": "project",
        "query_template": "{skill} github open source project example",
    },
    {
        "type": "interview",
        "query_template": "{skill} interview questions answers",
    },
]


def _is_configured() -> bool:
    """检查 Tavily API Key 是否已配置。"""
    from resume_agent.config import settings
    return bool(settings.tavily_api_key)


def _search_single(
    client: Any,
    query: str,
    max_results: int = 3,
) -> list[dict[str, str]]:
    """执行单次 Tavily 搜索，返回精简结果列表。

    Args:
        client: TavilyClient 实例。
        query: 搜索查询字符串。
        max_results: 最大返回结果数。

    Returns:
        结果列表，每项含 title / url / content。
    """
    try:
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=False,
        )
        results: list[dict[str, str]] = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("content") or "")[:200],
            })
        return results
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tavily 搜索失败 (query=%s): %s", query, exc)
        return []


def search_skill_resources(
    skill: str,
) -> list[dict[str, str]]:
    """为单项技能搜索学习资源。

    对每项技能执行 4 类搜索（文档/课程/项目/面试题），
    每类取第 1 个结果，组装为资源列表。

    Args:
        skill: 技能名称。

    Returns:
        资源列表，每项含 type / title / url / description。
        Tavily 未配置时返回空列表。
    """
    if not _is_configured():
        return []

    from tavily import TavilyClient
    from resume_agent.config import settings

    client = TavilyClient(api_key=settings.tavily_api_key)

    resources: list[dict[str, str]] = []

    for query_spec in _SEARCH_QUERIES:
        resource_type = query_spec["type"]
        query = query_spec["query_template"].format(skill=skill)
        results = _search_single(client, query, max_results=1)

        if results:
            top = results[0]
            resources.append({
                "type": resource_type,
                "title": top["title"],
                "url": top["url"],
                "description": top["content"],
            })

    return resources


def search_batch_skills(
    skills: list[str],
) -> dict[str, list[dict[str, str]]]:
    """批量搜索多技能的资源。

    Args:
        skills: 技能名称列表。

    Returns:
        {技能名: 资源列表} 映射。Tavily 未配置时返回空 dict。
    """
    if not _is_configured():
        return {}

    result: dict[str, list[dict[str, str]]] = {}
    for skill in skills:
        result[skill] = search_skill_resources(skill)
    return result


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """执行通用 Web 搜索，返回精简结果列表。

    供 LLM tool use 调用：LLM 自主构造查询词，调用此函数获取真实搜索结果。

    Args:
        query: 搜索查询字符串（LLM 构造）。
        max_results: 最大返回结果数。

    Returns:
        结果列表，每项含 title / url / content。
        Tavily 未配置时返回空列表。
    """
    if not _is_configured():
        return []

    from tavily import TavilyClient
    from resume_agent.config import settings

    client = TavilyClient(api_key=settings.tavily_api_key)
    return _search_single(client, query, max_results=max_results)


__all__ = ["search_skill_resources", "search_batch_skills", "search_web"]
