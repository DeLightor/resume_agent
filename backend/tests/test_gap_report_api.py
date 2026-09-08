"""技能 Gap 报告 API 集成测试。

覆盖：
- 空知识库时所有技能为 missing
- 有知识库数据时部分覆盖
- LLM 未配置时用模板兜底
- LLM 配置时正常生成描述
- JD 无技能项时返回 NO_SKILLS
- 三色阈值边界测试
- overall_score 计算正确
- 技能去重
- LLM 返回 markdown 包裹 JSON / 非法 JSON 兜底
- LLM 调用异常时兜底
- INVALID_REQUEST 校验

使用 conftest.py 的 ``_isolated_env`` fixture 隔离存储。
Chroma 默认使用 all-MiniLM-L6-v2 本地模型，无需外部 API。
"""

from __future__ import annotations

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
        "job_title": "测试岗位",
        "company": "测试公司",
        "tech_stack": tech_stack or [],
        "hard_skills": hard_skills or [],
        "soft_skills": soft_skills or [],
        "bonus_items": bonus_items or [],
    }


def _call_gap_report(
    client: TestClient, structured_jd: dict[str, Any]
) -> dict[str, Any]:
    """调用 Gap 报告端点并返回响应 JSON。"""
    response = client.post("/api/gap-report", json={"structured_jd": structured_jd})
    return response.json()


def _install_mock_llm(
    monkeypatch: pytest.MonkeyPatch, descriptions: list[dict[str, str]]
) -> None:
    """mock LLMClient.configured=True 且 chat 返回 JSON 数组。"""
    from resume_agent.llm.client import LLMClient

    async def fake_chat(
        self: Any,
        system_prompt: str,
        user_content: str,
        response_format_json: bool = False,
    ) -> str:
        return json.dumps(descriptions, ensure_ascii=False)

    monkeypatch.setattr(LLMClient, "configured", property(lambda self: True))
    monkeypatch.setattr(LLMClient, "chat", fake_chat)


def _install_mock_llm_raw(
    monkeypatch: pytest.MonkeyPatch, raw_response: str
) -> None:
    """mock LLMClient.configured=True 且 chat 返回原始字符串。"""
    from resume_agent.llm.client import LLMClient

    async def fake_chat(
        self: Any,
        system_prompt: str,
        user_content: str,
        response_format_json: bool = False,
    ) -> str:
        return raw_response

    monkeypatch.setattr(LLMClient, "configured", property(lambda self: True))
    monkeypatch.setattr(LLMClient, "chat", fake_chat)


def _install_mock_llm_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """mock LLMClient.configured=False。"""
    from resume_agent.llm.client import LLMClient

    monkeypatch.setattr(LLMClient, "configured", property(lambda self: False))


def _mock_search_skill(
    monkeypatch: pytest.MonkeyPatch,
    score_map: dict[str, float],
) -> None:
    """mock gap_analyzer._search_skill 返回指定分数的检索结果。"""
    from resume_agent.services import gap_analyzer as gap_analyzer_module

    def fake_search_skill(skill: str) -> list[dict[str, Any]]:
        score = score_map.get(skill, 0.0)
        if score == 0.0:
            return []
        return [
            {
                "chunk_text": f"mock content for {skill}",
                "source_file": "mock.md",
                "score": score,
            }
        ]

    monkeypatch.setattr(gap_analyzer_module, "_search_skill", fake_search_skill)


# === 空知识库测试 ===


def test_empty_kb_all_skills_missing() -> None:
    """空知识库时所有技能应为 missing，描述为模板。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd(
        tech_stack=["Python", "React"],
        hard_skills=["系统设计"],
    )
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    assert data["summary"]["missing"] == 3
    assert data["summary"]["covered"] == 0
    assert data["summary"]["partial"] == 0
    assert data["overall_score"] == 0
    for item in data["items"]:
        assert item["status"] == "missing"
        assert item["score"] == 0.0
        assert item["description"] == "知识库中暂无相关记录"
        assert item["evidence"] == []


# === 有知识库数据时部分覆盖 ===


def test_kb_with_matching_content_some_covered() -> None:
    """上传含 Python 内容的知识库文档后，Python 技能应为 covered 或 partial。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    md_content = (
        "# Python 开发经验\n\n"
        "使用 Python 开发后端服务，熟悉 FastAPI、Django 等框架。\n"
        "有丰富的 Python 项目经验，包括数据处理、API 开发和自动化脚本。"
    )
    _upload_knowledge(client, "python_notes.md", md_content)

    structured_jd = _make_structured_jd(
        tech_stack=["Python", "QuantumComputing"],
        hard_skills=["模型训练"],
    )
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    items = {item["skill"]: item for item in data["items"]}

    # Python 应该至少是 partial（有匹配内容）
    assert items["Python"]["status"] in ("covered", "partial")
    assert items["Python"]["score"] > 0
    assert len(items["Python"]["evidence"]) > 0
    assert items["Python"]["evidence"][0]["source_file"] == "python_notes.md"

    # QuantumComputing 应该是 missing（低相似度分数，< 0.3）
    # Chroma 会返回最近邻结果即使不相关，但分数很低
    assert items["QuantumComputing"]["status"] == "missing"
    assert items["QuantumComputing"]["score"] < 0.3


# === LLM 未配置时用模板兜底 ===


def test_llm_not_configured_uses_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 未配置时描述应为模板文本。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    # mock 检索：Python 有证据，Java 无证据
    _mock_search_skill(monkeypatch, {"Python": 0.8})

    from resume_agent.main import app

    client = TestClient(app)

    structured_jd = _make_structured_jd(tech_stack=["Python", "Java"])
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    items = {item["skill"]: item for item in data["items"]}

    # Python 有证据 → 模板 "知识库有相关记录"
    assert items["Python"]["description"] == "知识库有相关记录"
    # Java 无证据 → 模板 "知识库中暂无相关记录"
    assert items["Java"]["description"] == "知识库中暂无相关记录"


# === LLM 配置时正常生成描述 ===


def test_llm_configured_generates_descriptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 配置时应使用 LLM 生成的描述。"""
    _init_db()

    descriptions = [
        {"skill": "Python", "description": "有多个 Python 项目经验"},
        {"skill": "Java", "description": "知识库中暂无 Java 记录"},
    ]
    _install_mock_llm(monkeypatch, descriptions)

    from resume_agent.main import app

    client = TestClient(app)
    md_content = "# Python 笔记\n\n使用 Python 进行开发。"
    _upload_knowledge(client, "notes.md", md_content)

    structured_jd = _make_structured_jd(tech_stack=["Python", "Java"])
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    items = {item["skill"]: item for item in data["items"]}

    assert items["Python"]["description"] == "有多个 Python 项目经验"
    assert items["Java"]["description"] == "知识库中暂无 Java 记录"


# === LLM 返回 markdown 包裹的 JSON 数组 ===


def test_llm_returns_markdown_wrapped_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返回 markdown 代码块包裹的 JSON 数组也能正确解析。"""
    _init_db()

    descriptions = [
        {"skill": "Python", "description": "熟练掌握 Python 开发"},
        {"skill": "React", "description": "有 React 前端经验"},
    ]
    raw_response = f"```json\n{json.dumps(descriptions, ensure_ascii=False)}\n```"
    _install_mock_llm_raw(monkeypatch, raw_response)

    from resume_agent.main import app

    client = TestClient(app)
    md_content = "# Python 笔记\n\n使用 Python 进行开发。"
    _upload_knowledge(client, "notes.md", md_content)

    structured_jd = _make_structured_jd(tech_stack=["Python", "React"])
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    items = {item["skill"]: item for item in data["items"]}

    assert items["Python"]["description"] == "熟练掌握 Python 开发"
    assert items["React"]["description"] == "有 React 前端经验"


# === LLM 返回非法 JSON 时兜底 ===


def test_llm_returns_invalid_json_falls_back_to_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返回非法 JSON 时应兜底为模板描述。"""
    _init_db()
    _install_mock_llm_raw(monkeypatch, "this is not json at all [[[")
    # mock 检索：Python 有证据，Java 无证据
    _mock_search_skill(monkeypatch, {"Python": 0.8})

    from resume_agent.main import app

    client = TestClient(app)

    structured_jd = _make_structured_jd(tech_stack=["Python", "Java"])
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    items = {item["skill"]: item for item in data["items"]}

    # 兜底为模板
    assert items["Python"]["description"] == "知识库有相关记录"
    assert items["Java"]["description"] == "知识库中暂无相关记录"


# === LLM 调用异常时兜底 ===


def test_llm_chat_exception_falls_back_to_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 调用抛出异常时应兜底为模板描述。"""
    _init_db()

    from resume_agent.llm.client import LLMClient

    async def fake_chat(
        self: Any,
        system_prompt: str,
        user_content: str,
        response_format_json: bool = False,
    ) -> str:
        raise RuntimeError("LLM 调用失败")

    monkeypatch.setattr(LLMClient, "configured", property(lambda self: True))
    monkeypatch.setattr(LLMClient, "chat", fake_chat)

    from resume_agent.main import app

    client = TestClient(app)
    md_content = "# Python 笔记\n\n使用 Python 进行开发。"
    _upload_knowledge(client, "notes.md", md_content)

    structured_jd = _make_structured_jd(tech_stack=["Python"])
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    items = {item["skill"]: item for item in data["items"]}

    # 异常兜底为模板
    assert items["Python"]["description"] == "知识库有相关记录"


# === JD 无技能项时返回 NO_SKILLS ===


def test_no_skills_returns_error() -> None:
    """JD 无技能项时应返回 NO_SKILLS 错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    # 非空 dict 但无技能列表
    structured_jd = {"job_title": "测试岗位", "company": "测试公司"}
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is False
    assert body["error"]["code"] == "NO_SKILLS"


def test_no_skills_with_empty_lists_returns_error() -> None:
    """所有技能列表为空时应返回 NO_SKILLS。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd()  # 所有列表为空
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is False
    assert body["error"]["code"] == "NO_SKILLS"


# === INVALID_REQUEST 校验 ===


def test_invalid_request_empty_dict() -> None:
    """空 structured_jd 字典应返回 INVALID_REQUEST。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post("/api/gap-report", json={"structured_jd": {}})
    body = response.json()

    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_invalid_request_non_dict() -> None:
    """structured_jd 为非 dict 类型应被 Pydantic 拒绝（422 校验错误）。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    # structured_jd 为列表而非字典 → Pydantic 校验失败
    response = client.post(
        "/api/gap-report",
        json={"structured_jd": ["Python", "React"]},
    )
    # FastAPI/Pydantic 对类型不匹配返回 422
    assert response.status_code == 422


# === 三色阈值边界测试（单元） ===


def test_determine_status_thresholds() -> None:
    """测试 _determine_status 在阈值边界的判定。"""
    from resume_agent.services.gap_analyzer import _determine_status

    # covered: score >= 0.6
    assert _determine_status(0.6) == "covered"
    assert _determine_status(0.7) == "covered"
    assert _determine_status(1.0) == "covered"

    # partial: 0.3 <= score < 0.6
    assert _determine_status(0.3) == "partial"
    assert _determine_status(0.5) == "partial"
    assert _determine_status(0.59) == "partial"

    # missing: score < 0.3
    assert _determine_status(0.29) == "missing"
    assert _determine_status(0.0) == "missing"
    assert _determine_status(-0.1) == "missing"


# === 三色阈值边界测试（集成，mock 检索分数） ===


def test_threshold_boundary_with_mocked_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """通过 mock 检索分数测试三色边界。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    score_map = {
        "CoveredSkill": 0.6,  # 边界 covered
        "PartialSkill": 0.3,  # 边界 partial
        "MissingSkill": 0.29,  # 边界 missing
    }
    _mock_search_skill(monkeypatch, score_map)

    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd(
        tech_stack=["CoveredSkill", "PartialSkill", "MissingSkill"],
    )
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    items = {item["skill"]: item for item in data["items"]}

    assert items["CoveredSkill"]["status"] == "covered"
    assert items["CoveredSkill"]["score"] == 0.6
    assert items["PartialSkill"]["status"] == "partial"
    assert items["PartialSkill"]["score"] == 0.3
    assert items["MissingSkill"]["status"] == "missing"
    assert items["MissingSkill"]["score"] == 0.29


# === overall_score 计算正确 ===


def test_overall_score_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试 overall_score 计算：covered*100 + partial*50，除以总数。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    # 3 covered, 1 partial, 1 missing → (3*100 + 1*50) / 5 = 70
    score_map = {
        "Skill1": 0.8,  # covered
        "Skill2": 0.7,  # covered
        "Skill3": 0.65,  # covered
        "Skill4": 0.4,  # partial
        "Skill5": 0.1,  # missing
    }
    _mock_search_skill(monkeypatch, score_map)

    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd(
        tech_stack=["Skill1", "Skill2", "Skill3"],
        hard_skills=["Skill4"],
        soft_skills=["Skill5"],
    )
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    assert data["summary"]["covered"] == 3
    assert data["summary"]["partial"] == 1
    assert data["summary"]["missing"] == 1
    assert data["overall_score"] == 70


def test_overall_score_all_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    """全部 covered 时 overall_score 应为 100。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    score_map = {
        "Skill1": 0.9,
        "Skill2": 0.8,
    }
    _mock_search_skill(monkeypatch, score_map)

    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd(tech_stack=["Skill1", "Skill2"])
    body = _call_gap_report(client, structured_jd)

    data = body["data"]
    assert data["summary"]["covered"] == 2
    assert data["summary"]["partial"] == 0
    assert data["summary"]["missing"] == 0
    assert data["overall_score"] == 100


def test_overall_score_all_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """全部 missing 时 overall_score 应为 0。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    # 空知识库 → 所有技能 missing
    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd(
        tech_stack=["Skill1", "Skill2"],
    )
    body = _call_gap_report(client, structured_jd)

    data = body["data"]
    assert data["summary"]["covered"] == 0
    assert data["summary"]["partial"] == 0
    assert data["summary"]["missing"] == 2
    assert data["overall_score"] == 0


# === 技能去重测试 ===


def test_collect_skills_dedup() -> None:
    """测试 _collect_skills 去重。"""
    from resume_agent.services.gap_analyzer import _collect_skills

    structured_jd = {
        "tech_stack": ["Python", "React", "Python"],  # Python 重复
        "hard_skills": ["系统设计", "Python"],  # Python 跨类重复
        "soft_skills": ["沟通"],
        "bonus_items": ["顶会论文"],
    }
    skills = _collect_skills(structured_jd)
    skill_names = [s[0] for s in skills]

    # Python 只出现一次（首次出现在 tech_stack）
    assert skill_names.count("Python") == 1
    assert len(skills) == 5  # Python, React, 系统设计, 沟通, 顶会论文
    # 验证 Python 的 category 为 tech_stack（首次出现）
    python_entry = [s for s in skills if s[0] == "Python"][0]
    assert python_entry[1] == "tech_stack"


def test_collect_skills_ignores_non_list_items() -> None:
    """非列表类型的字段应被忽略。"""
    from resume_agent.services.gap_analyzer import _collect_skills

    structured_jd = {
        "tech_stack": "Python",  # 字符串而非列表
        "hard_skills": ["系统设计"],
        "soft_skills": ["沟通"],
        "bonus_items": ["顶会论文"],
    }
    skills = _collect_skills(structured_jd)
    skill_names = [s[0] for s in skills]
    assert "系统设计" in skill_names
    assert "沟通" in skill_names
    assert "顶会论文" in skill_names
    assert len(skills) == 3


def test_collect_skills_ignores_empty_and_non_string() -> None:
    """空字符串和非字符串元素应被忽略。"""
    from resume_agent.services.gap_analyzer import _collect_skills

    structured_jd = {
        "tech_stack": ["Python", "", 123, "React"],  # 空串和数字被忽略
        "hard_skills": [],
        "soft_skills": ["沟通"],
    }
    skills = _collect_skills(structured_jd)
    skill_names = [s[0] for s in skills]
    assert skill_names == ["Python", "React", "沟通"]


# === 四类技能全覆盖测试 ===


def test_all_four_categories_included(monkeypatch: pytest.MonkeyPatch) -> None:
    """tech_stack / hard_skills / soft_skills / bonus_items 四类技能都应被处理。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    # 全部设为 covered
    score_map = {
        "Python": 0.8,
        "模型训练": 0.7,
        "沟通": 0.75,
        "顶会论文": 0.65,
    }
    _mock_search_skill(monkeypatch, score_map)

    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd(
        tech_stack=["Python"],
        hard_skills=["模型训练"],
        soft_skills=["沟通"],
        bonus_items=["顶会论文"],
    )
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]
    items = {item["skill"]: item for item in data["items"]}

    assert items["Python"]["category"] == "tech_stack"
    assert items["模型训练"]["category"] == "hard_skills"
    assert items["沟通"]["category"] == "soft_skills"
    assert items["顶会论文"]["category"] == "bonus_items"
    assert data["summary"]["covered"] == 4


# === 响应结构验证 ===


def test_response_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证响应结构包含所有必需字段。"""
    _init_db()
    _install_mock_llm_not_configured(monkeypatch)

    score_map = {"Python": 0.8}
    _mock_search_skill(monkeypatch, score_map)

    from resume_agent.main import app

    client = TestClient(app)
    structured_jd = _make_structured_jd(tech_stack=["Python"])
    body = _call_gap_report(client, structured_jd)

    assert body["ok"] is True
    data = body["data"]

    # 顶层字段
    assert "overall_score" in data
    assert "summary" in data
    assert "items" in data

    # summary 字段
    summary = data["summary"]
    assert "covered" in summary
    assert "partial" in summary
    assert "missing" in summary

    # items 字段
    item = data["items"][0]
    assert "skill" in item
    assert "category" in item
    assert "status" in item
    assert "score" in item
    assert "description" in item
    assert "evidence" in item

    # evidence 结构
    if item["evidence"]:
        ev = item["evidence"][0]
        assert "chunk_text" in ev
        assert "source_file" in ev
        assert "score" in ev
