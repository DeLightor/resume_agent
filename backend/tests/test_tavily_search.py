"""Tavily Web 搜索工具模块测试（US-11 导师建议增强）。

测试搜索工具的核心逻辑，不依赖真实 Tavily API（mock 替代）。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from resume_agent.tools.tavily_search import (
    search_skill_resources,
    search_batch_skills,
)


def test_search_skill_resources_returns_results() -> None:
    """有 Tavily 配置时返回真实搜索结果。"""
    mock_response = {
        "results": [
            {
                "title": "Kubernetes Official Docs",
                "url": "https://kubernetes.io/docs/",
                "content": "Kubernetes documentation",
            },
        ],
    }
    mock_client = MagicMock()
    mock_client.search.return_value = mock_response

    with patch(
        "resume_agent.tools.tavily_search._is_configured",
        return_value=True,
    ), patch(
        "tavily.TavilyClient",
        return_value=mock_client,
    ):
        result = search_skill_resources("Kubernetes")

    assert len(result) > 0
    assert result[0]["type"] == "document"
    assert result[0]["title"] == "Kubernetes Official Docs"
    assert result[0]["url"] == "https://kubernetes.io/docs/"
    assert "description" in result[0]


def test_search_skill_resources_not_configured() -> None:
    """Tavily 未配置时返回空列表。"""
    with patch(
        "resume_agent.tools.tavily_search._is_configured",
        return_value=False,
    ):
        result = search_skill_resources("Python")

    assert result == []


def test_search_skill_resources_api_error() -> None:
    """Tavily API 报错时返回空列表，不抛异常。"""
    mock_client = MagicMock()
    mock_client.search.side_effect = Exception("API error")

    with patch(
        "resume_agent.tools.tavily_search._is_configured",
        return_value=True,
    ), patch(
        "tavily.TavilyClient",
        return_value=mock_client,
    ):
        result = search_skill_resources("Docker")

    assert result == []


def test_search_batch_skills() -> None:
    """批量搜索多技能。"""
    mock_response = {
        "results": [
            {
                "title": "Result",
                "url": "https://example.com",
                "content": "content",
            },
        ],
    }
    mock_client = MagicMock()
    mock_client.search.return_value = mock_response

    with patch(
        "resume_agent.tools.tavily_search._is_configured",
        return_value=True,
    ), patch(
        "tavily.TavilyClient",
        return_value=mock_client,
    ):
        result = search_batch_skills(["Go", "Rust"])

    assert "Go" in result
    assert "Rust" in result
    assert len(result["Go"]) > 0
    assert len(result["Rust"]) > 0


def test_search_batch_skills_not_configured() -> None:
    """Tavily 未配置时批量搜索返回空 dict。"""
    with patch(
        "resume_agent.tools.tavily_search._is_configured",
        return_value=False,
    ):
        result = search_batch_skills(["Go", "Rust"])

    assert result == {}


def test_search_skill_resources_four_types() -> None:
    """每项技能搜索 4 类资源（document/course/project/interview）。"""
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {
                "title": "Title",
                "url": "https://example.com",
                "content": "desc",
            },
        ],
    }

    with patch(
        "resume_agent.tools.tavily_search._is_configured",
        return_value=True,
    ), patch(
        "tavily.TavilyClient",
        return_value=mock_client,
    ):
        result = search_skill_resources("Python")

    types = [r["type"] for r in result]
    assert "document" in types
    assert "course" in types
    assert "project" in types
    assert "interview" in types
    assert len(result) == 4
