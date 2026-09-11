"""Agent 工具集测试（US-27 agent-runtime Task 3.2-3.8）。

覆盖 build_registry 注册的全部工具的 schema 与执行（mock 外部依赖）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from resume_agent.tools.agent_tools import ASK_USER_TOOL_NAME, build_registry


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_registry_contains_all_tools() -> None:
    """11 个工具全部注册，schema 合法。"""
    registry = build_registry()
    names = {tc["function"]["name"] for tc in registry.schemas()}
    assert names == {
        "retrieve_knowledge",
        "parse_jd",
        "analyze_gap",
        "read_node",
        "write_node",
        "list_templates",
        "export_pdf",
        "web_search",
        "delete_memory",
        "list_memories",
        ASK_USER_TOOL_NAME,
    }
    # ask_user schema 必须含 question 参数描述
    ask = [s for s in registry.schemas()
           if s["function"]["name"] == ASK_USER_TOOL_NAME][0]
    assert "question" in ask["function"]["parameters"]["properties"]


def test_retrieve_knowledge_tool(monkeypatch: Any) -> None:
    """retrieve_knowledge 调用 service 并透传参数。"""
    from resume_agent.tools import agent_tools

    calls: list[Any] = []

    def fake_search(queries: list[str], top_k: int = 3,
                   max_chunks: int = 10) -> list[dict]:
        calls.append((queries, top_k))
        return [{"chunk_text": "k8s 经历", "source_file": "a.md", "score": 0.9}]

    monkeypatch.setattr(agent_tools, "search_knowledge", fake_search)
    registry = build_registry()

    result = _run(registry.execute(
        "retrieve_knowledge", {"query": "K8s 部署经验", "top_k": 5}))
    assert result == [{"chunk_text": "k8s 经历", "source_file": "a.md",
                       "score": 0.9}]
    assert calls == [(["K8s 部署经验"], 5)]

    # 默认 top_k
    _run(registry.execute("retrieve_knowledge", {"query": "x"}))
    assert calls[-1] == (["x"], 3)


def test_parse_jd_tool(monkeypatch: Any) -> None:
    """parse_jd 调用 extract_jd_fields。"""
    from resume_agent.tools import agent_tools

    async def fake_extract(text: str) -> dict[str, Any]:
        return {"job_title": "后端工程师", "company": "T"}

    monkeypatch.setattr(agent_tools, "extract_jd_fields", fake_extract)
    registry = build_registry()

    result = _run(registry.execute("parse_jd", {"jd_text": "岗位职责..."}))
    assert result["job_title"] == "后端工程师"


def test_analyze_gap_tool(monkeypatch: Any) -> None:
    """analyze_gap 调用 gap_analyzer.analyze_gap。"""
    from resume_agent.tools import agent_tools

    async def fake_gap(structured_jd: dict[str, Any]) -> dict[str, Any]:
        return {"overall_score": 50, "summary": {}, "items": []}

    monkeypatch.setattr(agent_tools, "analyze_gap", fake_gap)
    registry = build_registry()

    result = _run(registry.execute(
        "analyze_gap", {"structured_jd": {"tech_stack": ["Python"]}}))
    assert result["overall_score"] == 50


def test_read_write_node_tools(monkeypatch: Any) -> None:
    """read_node / write_node 操作节点内容，不存在节点返回 error。"""
    from resume_agent.tools import agent_tools

    fake_db = {"master": {"experience": [], "version": 0}}

    def fake_get(node_id: str) -> dict[str, Any] | None:
        return fake_db.get(node_id)

    def fake_save(node_id: str, content: dict[str, Any]) -> bool:
        if node_id not in fake_db:
            return False
        fake_db[node_id] = content
        return True

    monkeypatch.setattr(agent_tools, "get_node_content", fake_get)
    monkeypatch.setattr(agent_tools, "save_node_content", fake_save)
    registry = build_registry()

    result = _run(registry.execute("read_node", {"node_id": "master"}))
    assert result == {"experience": [], "version": 0}

    missing = _run(registry.execute("read_node", {"node_id": "ghost"}))
    assert "error" in missing

    ok = _run(registry.execute(
        "write_node", {"node_id": "master", "content": {"skills": [], "version": 0}}))
    assert ok["ok"] is True
    assert ok["node_id"] == "master"
    assert fake_db["master"] == {"skills": [], "version": 0}

    denied = _run(registry.execute(
        "write_node", {"node_id": "ghost", "content": {}}))
    assert "error" in denied


def test_list_templates_tool() -> None:
    """list_templates 返回内置模板列表。"""
    registry = build_registry()
    result = _run(registry.execute("list_templates", {}))
    assert isinstance(result, list)
    assert len(result) >= 3  # modern / classic / tech
    ids = {t["id"] for t in result}
    assert {"modern", "classic", "tech"} <= ids


def test_export_pdf_tool(monkeypatch: Any) -> None:
    """export_pdf 读取节点内容并生成 PDF 文件。"""
    from resume_agent.tools import agent_tools

    monkeypatch.setattr(
        agent_tools, "get_node_content",
        lambda node_id: {"experience": [], "projects": [], "skills": {}})
    monkeypatch.setattr(
        agent_tools, "build_pdf",
        lambda resume_data, job_title, company, template_id: b"%PDF-1.4 fake")

    registry = build_registry()
    result = _run(registry.execute(
        "export_pdf", {"node_id": "master", "template_id": "classic"}))
    assert result["ok"] is True
    assert result["filename"].endswith(".pdf")

    # 文件真实写出
    from pathlib import Path as P
    path = P(result["file_path"])
    assert path.exists()
    path.unlink()  # 清理


def test_export_pdf_tool_node_missing(monkeypatch: Any) -> None:
    """export_pdf 节点不存在时返回 error，不抛异常。"""
    from resume_agent.tools import agent_tools

    monkeypatch.setattr(
        agent_tools, "get_node_content", lambda node_id: None)
    registry = build_registry()
    result = _run(registry.execute("export_pdf", {"node_id": "ghost"}))
    assert "error" in result


def test_web_search_tool_unconfigured(monkeypatch: Any) -> None:
    """Tavily 未配置时返回提示性空结果。"""
    registry = build_registry()
    # conftest 隔离环境下默认无 tavily key
    result = _run(registry.execute("web_search", {"query": "react 教程"}))
    assert result == [] or "error" not in result


def test_ask_user_spec_not_executable() -> None:
    """ask_user 被直接 execute 时返回 error（Runner 应在之前特判暂停）。"""
    registry = build_registry()
    result = _run(registry.execute(ASK_USER_TOOL_NAME, {"question": "?"}))
    assert "error" in result
    assert "AgentRunner" in result["error"]
