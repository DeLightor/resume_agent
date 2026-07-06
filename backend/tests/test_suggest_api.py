"""AI 智能补全 API 测试（US-9）。

覆盖：
- _find_thin_fields 单元测试（experience / projects / skills / 充分内容）
- 知识库为空时返回空建议列表
- LLM 未配置时返回空建议列表（不报错）
- 建议数量不超过 3 条
- 完整请求返回正确结构（mock LLM）
- 无效 section 返回错误
- 空 content 返回错误

使用 conftest.py 的 ``_isolated_env`` fixture 隔离存储。
Chroma 默认使用 all-MiniLM-L6-v2 本地模型，无需外部 API。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from resume_agent.api.suggest import _find_thin_fields
from resume_agent.db.init_db import init_database

# === 辅助函数 ===


def _init_db() -> None:
    """初始化隔离环境下的数据库并重置 Chroma 客户端单例。

    conftest 的 ``_isolated_env`` fixture 会重置 ``config_module.settings``，
    但 ``chroma_client._client`` 单例不会自动重置，导致跨测试数据泄漏。
    此处显式重置，确保每个测试都使用全新的 Chroma 实例与临时路径。
    """
    from resume_agent.config import settings
    from resume_agent.rag.chroma_client import reset_client

    reset_client()
    init_database(settings.sqlite_path)


def _upload_knowledge(client: TestClient, filename: str, content: str) -> str:
    """上传知识库文档并返回 upload_id。"""
    response = client.post(
        "/api/knowledge/upload",
        files={"file": (filename, content.encode("utf-8"), "text/markdown")},
    )
    body = response.json()
    assert body["ok"] is True, f"上传失败: {body}"
    return body["data"]["upload_id"]


def _make_structured_jd(
    tech_stack: list[str] | None = None,
    hard_skills: list[str] | None = None,
    soft_skills: list[str] | None = None,
) -> dict[str, Any]:
    """构造 structured_jd 字典。"""
    return {
        "job_title": "推荐算法工程师",
        "company": "测试公司",
        "tech_stack": tech_stack or [],
        "hard_skills": hard_skills or [],
        "soft_skills": soft_skills or [],
    }


def _call_suggest(
    client: TestClient,
    structured_jd: dict[str, Any],
    section: str,
    content: dict[str, Any],
) -> dict[str, Any]:
    """调用 suggest 端点并返回响应 JSON。"""
    response = client.post(
        "/api/suggest",
        json={
            "structured_jd": structured_jd,
            "section": section,
            "content": content,
        },
    )
    return response.json()


def _install_mock_llm(
    monkeypatch: pytest.MonkeyPatch,
    response_text: str,
) -> None:
    """mock LLMClient.configured=True 且 chat 返回指定响应。"""
    from resume_agent.llm.client import LLMClient

    async def fake_chat(
        self: Any,
        system_prompt: str,
        user_content: str,
        response_format_json: bool = False,
    ) -> str:
        return response_text

    monkeypatch.setattr(LLMClient, "configured", property(lambda self: True))
    monkeypatch.setattr(LLMClient, "chat", fake_chat)


def _install_mock_llm_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """mock LLMClient.configured=False。"""
    from resume_agent.llm.client import LLMClient

    monkeypatch.setattr(LLMClient, "configured", property(lambda self: False))


# === 知识库文档内容 ===

_KNOWLEDGE_MD = (
    "# 工作经历\n\n"
    "## 字节跳动 - 推荐算法工程师（2021-2024）\n"
    "负责推荐召回模型升级，使用 Python 和 TensorFlow 训练深度学习模型，"
    "离线 AUC 提升 2%。设计分布式训练 pipeline，日均处理 10 亿条样本。\n\n"
    "## 项目经历\n"
    "开发了基于 BERT 的语义召回系统，使用 FastAPI 部署在线推理服务，"
    "QPS 达到 5000。使用 React 开发了内部数据标注平台。"
)

_SUGGESTIONS_RESPONSE = json.dumps(
    {
        "suggestions": [
            {
                "field": "experience[0].highlights",
                "type": "add_highlight",
                "suggested_text": "设计分布式训练 pipeline，日均处理 10 亿条样本",
                "reason": "该经历只有 1 条 highlight，建议补充量化成果",
                "source": "知识库检索: work_notes.md (相关度 0.78)",
            }
        ]
    },
    ensure_ascii=False,
)


# === _find_thin_fields 单元测试 ===


def test_find_thin_fields_experience() -> None:
    """experience highlights < 2 条被识别为不足。"""
    content = {
        "experience": [
            {
                "company": "腾讯",
                "role": "算法工程师",
                "highlights": ["负责推荐系统优化"],  # 只有 1 条
            },
            {
                "company": "字节跳动",
                "role": "高级工程师",
                "highlights": [  # 2 条，充分
                    "主导模型升级",
                    "优化推理性能",
                ],
            },
        ]
    }
    thin = _find_thin_fields("experience", content)

    assert len(thin) == 1
    assert thin[0]["field"] == "experience[0].highlights"
    assert thin[0]["type"] == "add_highlight"
    assert "1 条 highlight" in thin[0]["reason"]
    assert thin[0]["context"]["company"] == "腾讯"
    assert thin[0]["context"]["role"] == "算法工程师"


def test_find_thin_fields_projects() -> None:
    """projects description < 20 字被识别为不足。"""
    content = {
        "projects": [
            {
                "name": "推荐系统",
                "role": "开发",
                "description": "短描述",  # < 20 字
                "tech_stack": ["Python"],
            },
            {
                "name": "完整项目",
                "role": "核心开发",
                "description": "这是一个内容充分的项目描述，超过二十个字符的长度。",
                "tech_stack": ["Python", "FastAPI"],
            },
        ]
    }
    thin = _find_thin_fields("projects", content)

    assert len(thin) == 1
    assert thin[0]["field"] == "projects[0].description"
    assert thin[0]["type"] == "add_detail"
    assert thin[0]["context"]["name"] == "推荐系统"


def test_find_thin_fields_projects_empty_tech_stack() -> None:
    """projects tech_stack 为空被识别为不足。"""
    content = {
        "projects": [
            {
                "name": "推荐系统",
                "role": "开发",
                "description": "这是一个内容充分的项目描述，超过二十个字符的长度。",
                "tech_stack": [],  # 空技术栈
            },
        ]
    }
    thin = _find_thin_fields("projects", content)

    assert len(thin) == 1
    assert thin[0]["field"] == "projects[0].tech_stack"
    assert thin[0]["type"] == "add_tech_stack"


def test_find_thin_fields_skills() -> None:
    """skills context 为空被识别为不足。"""
    content = {
        "skills": {
            "tech_stack": [
                {"name": "Python", "context": ""},  # 空 context
                {"name": "TensorFlow", "context": "用于训练推荐模型"},  # 充分
            ],
            "hard_skills": [
                {"name": "模型训练", "context": "训"},  # < 5 字
            ],
            "soft_skills": [],
        }
    }
    thin = _find_thin_fields("skills", content)

    assert len(thin) == 2
    fields = [t["field"] for t in thin]
    assert "skills.tech_stack[0].context" in fields
    assert "skills.hard_skills[0].context" in fields
    for t in thin:
        assert t["type"] == "add_skill_context"


def test_find_thin_fields_all_sufficient() -> None:
    """内容充分时返回空列表。"""
    content = {
        "experience": [
            {
                "company": "腾讯",
                "role": "算法工程师",
                "highlights": ["主导模型升级", "优化推理性能"],
            },
        ],
        "projects": [
            {
                "name": "推荐系统",
                "role": "开发",
                "description": "这是一个内容充分的项目描述，超过二十个字符的长度。",
                "tech_stack": ["Python", "FastAPI"],
            },
        ],
        "skills": {
            "tech_stack": [
                {"name": "Python", "context": "用于推荐模型训练与服务部署"},
            ],
            "hard_skills": [],
            "soft_skills": [],
        },
    }

    # experience 充分
    assert _find_thin_fields("experience", content) == []
    # projects 充分
    assert _find_thin_fields("projects", content) == []
    # skills 充分
    assert _find_thin_fields("skills", content) == []


# === API 集成测试 ===


def test_suggest_empty_knowledge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """知识库为空时返回空建议列表。"""
    _init_db()
    _install_mock_llm(monkeypatch, _SUGGESTIONS_RESPONSE)

    from resume_agent.main import app

    client = TestClient(app)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    content = {
        "experience": [
            {
                "company": "腾讯",
                "role": "算法工程师",
                "highlights": ["负责推荐系统优化"],
            },
        ]
    }
    body = _call_suggest(client, structured_jd, "experience", content)

    assert body["ok"] is True
    assert body["data"]["suggestions"] == []
    assert body["data"]["total"] == 0


def test_suggest_llm_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 未配置时返回空建议列表（不报错）。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "notes.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    content = {
        "experience": [
            {
                "company": "腾讯",
                "role": "算法工程师",
                "highlights": ["负责推荐系统优化"],
            },
        ]
    }
    body = _call_suggest(client, structured_jd, "experience", content)

    assert body["ok"] is True
    assert body["data"]["suggestions"] == []
    assert body["data"]["total"] == 0


def test_suggest_max_3_suggestions(monkeypatch: pytest.MonkeyPatch) -> None:
    """建议数量不超过 3 条。"""
    _init_db()
    # LLM 返回 5 条建议，应被截断为 3 条
    many_suggestions = json.dumps(
        {
            "suggestions": [
                {
                    "field": f"experience[{i}].highlights",
                    "type": "add_highlight",
                    "suggested_text": f"建议 {i}",
                    "reason": f"原因 {i}",
                    "source": f"知识库检索: notes.md (相关度 0.{i + 1})",
                }
                for i in range(5)
            ]
        },
        ensure_ascii=False,
    )
    _install_mock_llm(monkeypatch, many_suggestions)

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "notes.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    # 多条不足经历
    content = {
        "experience": [
            {"company": "腾讯", "role": "工程师", "highlights": ["一条"]},
            {"company": "阿里", "role": "工程师", "highlights": ["一条"]},
            {"company": "字节", "role": "工程师", "highlights": ["一条"]},
            {"company": "美团", "role": "工程师", "highlights": ["一条"]},
            {"company": "百度", "role": "工程师", "highlights": ["一条"]},
        ]
    }
    body = _call_suggest(client, structured_jd, "experience", content)

    assert body["ok"] is True
    assert body["data"]["total"] <= 3
    assert len(body["data"]["suggestions"]) <= 3


def test_suggest_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """完整请求返回正确结构（mock LLM）。"""
    _init_db()
    _install_mock_llm(monkeypatch, _SUGGESTIONS_RESPONSE)

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "notes.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(tech_stack=["Python", "TensorFlow"])
    content = {
        "experience": [
            {
                "company": "腾讯",
                "role": "算法工程师",
                "highlights": ["负责推荐系统优化"],
            },
        ]
    }
    body = _call_suggest(client, structured_jd, "experience", content)

    assert body["ok"] is True
    data = body["data"]
    assert "suggestions" in data
    assert "total" in data
    assert data["total"] == len(data["suggestions"])
    assert data["total"] >= 1

    suggestion = data["suggestions"][0]
    assert "field" in suggestion
    assert "type" in suggestion
    assert "suggested_text" in suggestion
    assert "reason" in suggestion
    assert "source" in suggestion
    assert suggestion["suggested_text"]


def test_suggest_invalid_section(monkeypatch: pytest.MonkeyPatch) -> None:
    """无效 section 返回错误。"""
    _init_db()
    _install_mock_llm(monkeypatch, _SUGGESTIONS_RESPONSE)

    from resume_agent.main import app

    client = TestClient(app)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    content = {"experience": []}
    body = _call_suggest(client, structured_jd, "invalid_section", content)

    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_SECTION"


def test_suggest_empty_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """空 content 返回错误。"""
    _init_db()
    _install_mock_llm(monkeypatch, _SUGGESTIONS_RESPONSE)

    from resume_agent.main import app

    client = TestClient(app)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    body = _call_suggest(client, structured_jd, "experience", {})

    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_REQUEST"
