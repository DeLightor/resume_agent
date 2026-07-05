"""AI 简历生成 API 集成测试（US-6）。

覆盖：
- 空知识库返回 EMPTY_KNOWLEDGE_BASE
- 无效段落类型返回 INVALID_SECTION
- 空 JD 返回 INVALID_REQUEST
- 正常生成 experience / projects / skills 段落（mock LLM，真实 Chroma 检索）
- LLM 反思异常时跳过（不阻断撰写）
- LLM 撰写异常返回 GENERATE_FAILED
- LLM 未配置时反思用模板兜底
- LLM 未配置时撰写返回错误
- 检索去重正确（同一切片不重复出现）
- evidence 数量不超过 _MAX_EVIDENCE_CHUNKS

使用 conftest.py 的 ``_isolated_env`` fixture 隔离存储。
Chroma 默认使用 all-MiniLM-L6-v2 本地模型，无需外部 API。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

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
    bonus_items: list[str] | None = None,
) -> dict[str, Any]:
    """构造 structured_jd 字典。"""
    return {
        "job_title": "推荐算法工程师",
        "company": "测试公司",
        "tech_stack": tech_stack or [],
        "hard_skills": hard_skills or [],
        "soft_skills": soft_skills or [],
        "bonus_items": bonus_items or [],
    }


def _call_generate(
    client: TestClient,
    structured_jd: dict[str, Any],
    section: str = "experience",
) -> dict[str, Any]:
    """调用 AI 生成端点并返回响应 JSON。"""
    response = client.post(
        "/api/generate",
        json={"structured_jd": structured_jd, "section": section},
    )
    return response.json()


def _install_mock_llm(
    monkeypatch: pytest.MonkeyPatch,
    response_map: dict[str, str] | str,
) -> None:
    """mock LLMClient.configured=True 且 chat 返回指定响应。

    response_map 可以是：
    - str: 所有调用返回同一响应
    - dict: {"reflection": "...", "writer": "..."} 按调用顺序返回
            {"default": "..."} 所有调用返回同一响应
    """
    from resume_agent.llm.client import LLMClient

    if isinstance(response_map, str):
        response_map = {"default": response_map}

    call_count = [0]

    async def fake_chat(
        self: Any,
        system_prompt: str,
        user_content: str,
        response_format_json: bool = False,
    ) -> str:
        call_count[0] += 1
        if call_count[0] == 1 and "reflection" in response_map:
            return response_map["reflection"]
        if "writer" in response_map:
            return response_map["writer"]
        return response_map.get("default", "{}")

    monkeypatch.setattr(LLMClient, "configured", property(lambda self: True))
    monkeypatch.setattr(LLMClient, "chat", fake_chat)


def _install_mock_llm_reflection_fails(
    monkeypatch: pytest.MonkeyPatch,
    writer_response: str,
) -> None:
    """mock LLM：反思调用抛异常，撰写调用返回指定响应。"""
    from resume_agent.llm.client import LLMClient

    call_count = [0]

    async def fake_chat(
        self: Any,
        system_prompt: str,
        user_content: str,
        response_format_json: bool = False,
    ) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("反思审核失败")
        return writer_response

    monkeypatch.setattr(LLMClient, "configured", property(lambda self: True))
    monkeypatch.setattr(LLMClient, "chat", fake_chat)


def _install_mock_llm_writer_fails(
    monkeypatch: pytest.MonkeyPatch,
    reflection_response: str,
) -> None:
    """mock LLM：反思调用返回指定响应，撰写调用抛异常。"""
    from resume_agent.llm.client import LLMClient

    call_count = [0]

    async def fake_chat(
        self: Any,
        system_prompt: str,
        user_content: str,
        response_format_json: bool = False,
    ) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            return reflection_response
        raise RuntimeError("撰写失败")

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
    "QPS 达到 5000。使用 React 开发了内部数据标注平台。\n\n"
    "## 技能\n"
    "熟练掌握 Python、TensorFlow、PyTorch。熟悉系统设计、模型训练、"
    "A/B 测试。具备良好的沟通能力和团队协作能力。"
)

_REFLECTION_RESPONSE = json.dumps(
    {
        "issues_found": 0,
        "issues": [],
        "notes": "内容质量良好，无套话或夸大表述",
    },
    ensure_ascii=False,
)

_EXPERIENCE_RESPONSE = json.dumps(
    {
        "experience": [
            {
                "company": "字节跳动",
                "role": "推荐算法工程师",
                "period": "2021-2024",
                "highlights": [
                    "主导推荐召回模型升级，离线 AUC 提升 2%",
                    "设计分布式训练 pipeline，日均处理 10 亿条样本",
                ],
            }
        ]
    },
    ensure_ascii=False,
)

_PROJECTS_RESPONSE = json.dumps(
    {
        "projects": [
            {
                "name": "语义召回系统",
                "role": "核心开发",
                "period": "2022-2023",
                "description": "基于 BERT 的语义召回系统，使用 FastAPI 部署在线推理服务。",
                "tech_stack": ["Python", "BERT", "FastAPI"],
            }
        ]
    },
    ensure_ascii=False,
)

_SKILLS_RESPONSE = json.dumps(
    {
        "skills": {
            "tech_stack": [
                {"name": "Python", "context": "用于推荐模型训练与服务部署"},
                {"name": "TensorFlow", "context": "训练深度学习推荐模型"},
            ],
            "hard_skills": [
                {"name": "模型训练", "context": "训练推荐召回模型"},
                {"name": "系统设计", "context": "设计分布式训练 pipeline"},
            ],
            "soft_skills": [
                {"name": "沟通", "context": "跨团队协作推进项目落地"},
            ],
        }
    },
    ensure_ascii=False,
)


# === 空知识库测试 ===


def test_empty_kb_returns_error() -> None:
    """空知识库时应返回 EMPTY_KNOWLEDGE_BASE 错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd(tech_stack=["Python", "React"])
    body = _call_generate(client, structured_jd)

    assert body["ok"] is False
    assert body["error"]["code"] == "EMPTY_KNOWLEDGE_BASE"


# === 无效段落类型测试 ===


def test_invalid_section_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """无效段落类型应返回 INVALID_SECTION 错误。"""
    _init_db()
    _install_mock_llm(monkeypatch, _REFLECTION_RESPONSE)

    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd(tech_stack=["Python"])
    body = _call_generate(client, structured_jd, section="invalid_section")

    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_SECTION"


# === 空 JD 测试 ===


def test_empty_jd_returns_error() -> None:
    """空 structured_jd 应返回 INVALID_REQUEST 错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    body = _call_generate(client, {}, section="experience")

    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_REQUEST"


# === 正常生成 experience 段落 ===


def test_generate_experience_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常生成 experience 段落（mock LLM，真实 Chroma 检索）。"""
    _init_db()
    _install_mock_llm(
        monkeypatch,
        {"reflection": _REFLECTION_RESPONSE, "writer": _EXPERIENCE_RESPONSE},
    )

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "experience.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(
        tech_stack=["Python", "TensorFlow"],
        hard_skills=["模型训练", "系统设计"],
    )
    body = _call_generate(client, structured_jd, section="experience")

    assert body["ok"] is True
    data = body["data"]
    assert data["section"] == "experience"
    assert data["sources_used"] > 0

    # 验证 reflection 结构
    reflection = data["reflection"]
    assert "issues_found" in reflection
    assert "issues" in reflection
    assert "notes" in reflection

    # 验证 content 结构
    content = data["content"]
    assert "experience" in content
    assert len(content["experience"]) > 0
    exp = content["experience"][0]
    assert "company" in exp
    assert "role" in exp
    assert "period" in exp
    assert "highlights" in exp
    assert len(exp["highlights"]) > 0


# === 正常生成 projects 段落 ===


def test_generate_projects_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常生成 projects 段落。"""
    _init_db()
    _install_mock_llm(
        monkeypatch,
        {"reflection": _REFLECTION_RESPONSE, "writer": _PROJECTS_RESPONSE},
    )

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "projects.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(
        tech_stack=["Python", "FastAPI"],
        hard_skills=["系统设计"],
    )
    body = _call_generate(client, structured_jd, section="projects")

    assert body["ok"] is True
    data = body["data"]
    assert data["section"] == "projects"
    assert data["sources_used"] > 0

    content = data["content"]
    assert "projects" in content
    assert len(content["projects"]) > 0
    proj = content["projects"][0]
    assert "name" in proj
    assert "role" in proj
    assert "period" in proj
    assert "description" in proj
    assert "tech_stack" in proj


# === 正常生成 skills 段落 ===


def test_generate_skills_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常生成 skills 段落。"""
    _init_db()
    _install_mock_llm(
        monkeypatch,
        {"reflection": _REFLECTION_RESPONSE, "writer": _SKILLS_RESPONSE},
    )

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "skills.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(
        tech_stack=["Python", "TensorFlow"],
        hard_skills=["模型训练", "系统设计"],
        soft_skills=["沟通"],
    )
    body = _call_generate(client, structured_jd, section="skills")

    assert body["ok"] is True
    data = body["data"]
    assert data["section"] == "skills"
    assert data["sources_used"] > 0

    content = data["content"]
    assert "skills" in content
    skills = content["skills"]
    assert "tech_stack" in skills
    assert "hard_skills" in skills
    assert "soft_skills" in skills
    assert len(skills["tech_stack"]) > 0
    assert len(skills["hard_skills"]) > 0
    assert len(skills["soft_skills"]) > 0


# === LLM 反思异常时跳过（不阻断撰写）===


def test_llm_reflection_exception_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 反思调用异常时应跳过，不阻断撰写流程。"""
    _init_db()
    _install_mock_llm_reflection_fails(monkeypatch, _EXPERIENCE_RESPONSE)

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "notes.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    body = _call_generate(client, structured_jd, section="experience")

    # 反思异常被捕获，撰写仍然成功
    assert body["ok"] is True
    data = body["data"]
    assert data["section"] == "experience"
    assert data["sources_used"] > 0

    # reflection 应包含审核跳过说明
    reflection = data["reflection"]
    assert reflection["issues_found"] == 0
    assert reflection["issues"] == []
    assert "审核跳过" in reflection["notes"]

    # content 仍然正确生成
    content = data["content"]
    assert "experience" in content
    assert len(content["experience"]) > 0


# === LLM 撰写异常返回 GENERATE_FAILED ===


def test_llm_writer_exception_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 撰写调用异常时应返回 GENERATE_FAILED 错误。"""
    _init_db()
    _install_mock_llm_writer_fails(monkeypatch, _REFLECTION_RESPONSE)

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "notes.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    body = _call_generate(client, structured_jd, section="experience")

    assert body["ok"] is False
    assert body["error"]["code"] == "GENERATE_FAILED"
    assert "撰写失败" in body["error"]["message"]


# === LLM 未配置时反思用模板兜底 ===


def test_llm_not_configured_reflection_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 未配置时 _run_reflection 返回模板兜底结果。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    from resume_agent.api.generate import _run_reflection

    evidence = [
        {
            "chunk_text": "测试经历内容",
            "source_file": "test.md",
            "score": 0.8,
        }
    ]

    # LLM 未配置时，_run_reflection 应返回模板兜底
    result = asyncio.run(_run_reflection(evidence))

    assert result["issues_found"] == 0
    assert result["issues"] == []
    assert "LLM 未配置" in result["notes"]


# === LLM 未配置时撰写返回错误 ===


def test_llm_not_configured_writer_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 未配置时撰写应返回 GENERATE_FAILED 错误。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "notes.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    body = _call_generate(client, structured_jd, section="experience")

    assert body["ok"] is False
    assert body["error"]["code"] == "GENERATE_FAILED"
    assert "LLM 未配置" in body["error"]["message"]


# === 检索去重测试（单元，mock collection）===


def test_search_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """检索去重：同一切片不重复出现。"""
    from resume_agent.api import generate as gen_module
    from resume_agent.rag import chroma_client

    same_doc = "这是相同的 Python 开发经历内容，包含详细的项目描述和技术细节。"

    class FakeCollection:
        def count(self) -> int:
            return 1

        def query(self, query_texts: list[str], n_results: int) -> dict[str, Any]:
            # 总是返回同一切片（不同查询命中同一切片）
            return {
                "ids": [["chunk_1"]],
                "documents": [[same_doc]],
                "metadatas": [[{"source_file": "notes.md"}]],
                "distances": [[0.2]],
            }

    monkeypatch.setattr(
        chroma_client, "get_knowledge_collection", lambda: FakeCollection()
    )

    queries = ["Python", "Java", "Go"]
    results = gen_module._search_knowledge_base(queries)

    # 3 个查询返回同一切片，去重后应只有 1 个
    assert len(results) == 1
    assert results[0]["chunk_text"] == same_doc
    assert results[0]["source_file"] == "notes.md"


# === 检索去重测试（集成，真实 Chroma）===


def test_search_dedup_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """检索去重集成测试：单切片知识库 + 多查询应去重为 1。"""
    _init_db()
    _install_mock_llm(
        monkeypatch,
        {"reflection": _REFLECTION_RESPONSE, "writer": _EXPERIENCE_RESPONSE},
    )

    from resume_agent.main import app

    client = TestClient(app)
    # 上传一个很短的文档（只产生 1 个切片）
    short_md = "# Python 开发\n\n使用 Python 进行后端开发，熟悉 FastAPI。"
    _upload_knowledge(client, "short.md", short_md)

    structured_jd = _make_structured_jd(
        tech_stack=["Python", "FastAPI", "Django"],
    )
    body = _call_generate(client, structured_jd, section="experience")

    assert body["ok"] is True
    data = body["data"]
    # 单切片知识库，多查询去重后 sources_used 应为 1
    assert data["sources_used"] == 1


# === evidence 数量不超过 _MAX_EVIDENCE_CHUNKS ===


def test_evidence_max_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """evidence 数量不超过 _MAX_EVIDENCE_CHUNKS。"""
    from resume_agent.api import generate as gen_module
    from resume_agent.rag import chroma_client

    class FakeCollection:
        def count(self) -> int:
            return 100

        def query(self, query_texts: list[str], n_results: int) -> dict[str, Any]:
            query = query_texts[0]
            results = []
            for i in range(n_results):
                # 每个结果都有不同的前 100 字（确保不被去重）
                doc = (
                    f"{query} 经历描述第 {i} 项："
                    f"在 {query} 项目中承担核心开发角色，"
                    f"负责架构设计与性能优化。"
                )
                results.append(
                    {
                        "doc": doc,
                        "meta": {"source_file": f"{query}.md"},
                        "distance": 0.1 + i * 0.1,
                    }
                )
            return {
                "ids": [[f"{query}_{i}" for i in range(n_results)]],
                "documents": [[r["doc"] for r in results]],
                "metadatas": [[r["meta"] for r in results]],
                "distances": [[r["distance"] for r in results]],
            }

    monkeypatch.setattr(
        chroma_client, "get_knowledge_collection", lambda: FakeCollection()
    )

    # 5 个查询，每个返回 3 个唯一结果 = 15 个原始结果，cap 后应为 10
    queries = ["Python", "Java", "Go", "Rust", "C++"]
    results = gen_module._search_knowledge_base(queries)

    assert len(results) == gen_module._MAX_EVIDENCE_CHUNKS
    assert len(results) <= gen_module._MAX_EVIDENCE_CHUNKS

    # 验证结果按 score 降序排列
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


# === 响应结构验证 ===


def test_response_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证响应结构包含所有必需字段。"""
    _init_db()
    _install_mock_llm(
        monkeypatch,
        {"reflection": _REFLECTION_RESPONSE, "writer": _EXPERIENCE_RESPONSE},
    )

    from resume_agent.main import app

    client = TestClient(app)
    _upload_knowledge(client, "notes.md", _KNOWLEDGE_MD)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    body = _call_generate(client, structured_jd, section="experience")

    assert body["ok"] is True
    data = body["data"]

    # 顶层字段
    assert "section" in data
    assert "content" in data
    assert "reflection" in data
    assert "sources_used" in data

    # reflection 字段
    reflection = data["reflection"]
    assert "issues_found" in reflection
    assert "issues" in reflection
    assert "notes" in reflection

    # sources_used 为正整数
    assert isinstance(data["sources_used"], int)
    assert data["sources_used"] > 0
