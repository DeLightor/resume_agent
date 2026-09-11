"""Agent 长期记忆测试（US-35 agent-long-term-memory）。

覆盖：
1. MemoryStore CRUD、去重、状态切换与筛选。
2. 活跃记忆格式化、预算截断 (Top-K / max_chars) 与 Fail-open 容错。
3. 对话指令规则抽取 (extract_memory_intent)。
4. /api/agent/memories API 路由测试。
5. AgentRunner / ReviewerAgent 记忆注入测试。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from resume_agent.agents import memory_store, store
from resume_agent.agents.memory_store import (
    create_memory,
    delete_memory,
    extract_memory_intent,
    get_active_memory_prompt,
    get_memory,
    list_memories,
    update_memory,
)
from resume_agent.agents.registry import ToolRegistry
from resume_agent.agents.reviewer import ReviewerAgent
from resume_agent.agents.runner import AgentRunner
from resume_agent.main import app

# ---------------------------------------------------------------------------
# 1. 存储层基础 CRUD 与约束
# ---------------------------------------------------------------------------


def test_create_memory_success(initialized_db: Any) -> None:
    """创建记忆项成功，包含默认字段。"""
    mem = create_memory(
        content="重点突出架构设计与性能量化指标",
        type="preference",
        source="manual",
        db_path=initialized_db,
    )
    assert mem.id is not None
    assert mem.content == "重点突出架构设计与性能量化指标"
    assert mem.type == "preference"
    assert mem.source == "manual"
    assert mem.active is True
    assert mem.created_at is not None
    assert mem.updated_at is not None

    fetched = get_memory(mem.id, db_path=initialized_db)
    assert fetched is not None
    assert fetched.id == mem.id
    assert fetched.content == mem.content


def test_create_memory_validation(initialized_db: Any) -> None:
    """非法类型与空内容应拒绝。"""
    with pytest.raises(ValueError, match="非法记忆类型"):
        create_memory(content="test", type="invalid_type", db_path=initialized_db)

    with pytest.raises(ValueError, match="内容不能为空"):
        create_memory(content="   ", type="preference", db_path=initialized_db)


def test_create_memory_deduplication(initialized_db: Any) -> None:
    """相同内容的活跃记忆再次创建时，应复用已有记录并更新时间戳，不产生重复垃圾数据。"""
    mem1 = create_memory(
        content="技术栈不要写精通只写熟悉",
        type="correction",
        db_path=initialized_db,
    )
    mem2 = create_memory(
        content="技术栈不要写精通只写熟悉",
        type="correction",
        db_path=initialized_db,
    )
    assert mem1.id == mem2.id
    all_mems = list_memories(db_path=initialized_db)
    assert len(all_mems) == 1


def test_list_memories_filtering(initialized_db: Any) -> None:
    """支持按 active_only 和 type 过滤，按更新时间降序。"""
    create_memory("偏好1", type="preference", db_path=initialized_db)
    m2 = create_memory("纠偏1", type="correction", db_path=initialized_db)
    create_memory("风格1", type="style_sample", db_path=initialized_db)

    # 将 m2 置为禁用
    update_memory(m2.id, active=False, db_path=initialized_db)

    # 查询全部
    all_mems = list_memories(db_path=initialized_db)
    assert len(all_mems) == 3

    # 查询 active
    active_mems = list_memories(active_only=True, db_path=initialized_db)
    assert len(active_mems) == 2
    assert all(m.active for m in active_mems)

    # 按 type 查询
    corrections = list_memories(type_filter="correction", db_path=initialized_db)
    assert len(corrections) == 1
    assert corrections[0].id == m2.id


def test_update_and_delete_memory(initialized_db: Any) -> None:
    """更新内容/状态与删除。"""
    mem = create_memory("原始规则", type="preference", db_path=initialized_db)

    # 更新内容与状态
    updated = update_memory(
        mem.id,
        content="更新后的规则",
        active=False,
        type="correction",
        db_path=initialized_db,
    )
    assert updated is not None
    assert updated.content == "更新后的规则"
    assert updated.active is False
    assert updated.type == "correction"

    # 删除
    ok = delete_memory(mem.id, db_path=initialized_db)
    assert ok is True
    assert get_memory(mem.id, db_path=initialized_db) is None
    assert delete_memory("non-existent-id", db_path=initialized_db) is False


# ---------------------------------------------------------------------------
# 2. 活跃记忆格式化与预算控制
# ---------------------------------------------------------------------------


def test_get_active_memory_prompt_empty(initialized_db: Any) -> None:
    """无活跃记忆时返回空字符串。"""
    prompt = get_active_memory_prompt(db_path=initialized_db)
    assert prompt == ""


def test_get_active_memory_prompt_formatting_and_caps(initialized_db: Any) -> None:
    """格式化正确挂载类型标签，并受 max_items 和 max_chars 预算截断。"""
    create_memory("量化项目成果指标", type="preference", db_path=initialized_db)
    create_memory("禁用精通一词", type="correction", db_path=initialized_db)
    create_memory("采用 STAR 结构书写", type="style_sample", db_path=initialized_db)

    prompt = get_active_memory_prompt(db_path=initialized_db)
    assert "用户个性化长期偏好与历史纠偏" in prompt
    assert "[偏好] 量化项目成果指标" in prompt
    assert "[纠偏] 禁用精通一词" in prompt
    assert "[风格] 采用 STAR 结构书写" in prompt

    # 测试 Top-K 条数限制
    prompt_top1 = get_active_memory_prompt(db_path=initialized_db, max_items=1)
    # 只包含最新一条规则
    lines = [line for line in prompt_top1.split("\n") if line.startswith("- ")]
    assert len(lines) == 1

    # 测试 max_chars 预算截断
    prompt_short = get_active_memory_prompt(db_path=initialized_db, max_chars=40)
    assert len(prompt_short) <= 60  # 含截断保护


# ---------------------------------------------------------------------------
# 3. 对话意图规则抽取
# ---------------------------------------------------------------------------


def test_extract_memory_intent() -> None:
    """常见模式识别为规则，普通对话返回 None。"""
    # 纠偏模式
    res1 = extract_memory_intent("请记住：技能不要写精通只写熟悉")
    assert res1 is not None
    assert res1[0] == "correction"
    assert "不要写精通" in res1[1]

    res2 = extract_memory_intent("以后都不要在简历里出现主观夸大评价")
    assert res2 is not None
    assert res2[0] == "correction"
    assert "主观夸大评价" in res2[1]

    # 偏好模式
    res3 = extract_memory_intent("记住：经历中重点突出性能优化与吞吐量提升")
    assert res3 is not None
    assert res3[0] == "preference"
    assert "性能优化" in res3[1]

    res4 = extract_memory_intent("偏好：按照时间倒序排列工作经历")
    assert res4 is not None
    assert res4[0] == "preference"
    assert "时间倒序" in res4[1]

    # 风格模式
    res5 = extract_memory_intent("请记住以 STAR 原则来组织所有项目描述")
    assert res5 is not None
    assert res5[0] == "style_sample"
    assert "STAR" in res5[1]

    # 普通对话不误触
    assert extract_memory_intent("帮我写一个自我介绍") is None
    assert extract_memory_intent("你看这个项目的技术难点够不够？") is None
    assert extract_memory_intent("你好") is None


def test_extract_memories_smart_with_llm() -> None:
    """智能从自然表达（无固定句式前缀）中通过 LLM 识别偏好与纠偏。"""
    import json

    class _SmartLLM:
        configured = True

        async def chat(
            self,
            system_prompt: str,
            user_content: str,
            response_format_json: bool = False,
        ) -> str:
            if "别写精通" in user_content:
                return json.dumps({
                    "has_memory": True,
                    "memories": [
                        {"type": "correction", "rule": "技能清单不写精通，只写熟练"},
                        {"type": "preference", "rule": "重点突出分布式微服务架构经验"},
                    ],
                })
            return json.dumps({"has_memory": False, "memories": []})

    smart_llm = _SmartLLM()

    # 自然表达 1：夹杂个人看法和偏好
    res1 = asyncio.run(
        memory_store.extract_memories_smart(
            smart_llm,
            "刚才那版还凑合，不过我技术栈里千万别写精通，另外经历尽量突出分布式微服务架构",
        )
    )
    assert len(res1) == 2
    assert res1[0]["type"] == "correction"
    assert "不写精通" in res1[0]["content"]
    assert res1[1]["type"] == "preference"
    assert "分布式微服务" in res1[1]["content"]

    # 自然表达 2：普通询问不提取
    res2 = asyncio.run(
        memory_store.extract_memories_smart(smart_llm, "帮我看看这个工作经历的错别字")
    )
    assert len(res2) == 0



# ---------------------------------------------------------------------------
# 4. API 路由集成测试 (/api/agent/memories)
# ---------------------------------------------------------------------------


def test_api_memories_crud(initialized_db: Any, monkeypatch: Any) -> None:
    """API 路由增删改查全流程。"""
    from resume_agent.config import settings

    monkeypatch.setattr(settings, "sqlite_path", initialized_db)
    client = TestClient(app)

    # 1. 初始为空
    resp = client.get("/api/agent/memories")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["data"] == []

    # 2. 创建
    create_resp = client.post(
        "/api/agent/memories",
        json={
            "content": "API测试规则：量化数据优先",
            "type": "preference",
            "source": "manual",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()["data"]
    memory_id = created["id"]
    assert created["content"] == "API测试规则：量化数据优先"
    assert created["active"] is True

    # 3. 列表查询
    list_resp = client.get("/api/agent/memories")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 1

    # 4. 更新状态与内容
    patch_resp = client.patch(
        f"/api/agent/memories/{memory_id}",
        json={"active": False, "content": "API测试规则：已更新"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["active"] is False
    assert patch_resp.json()["data"]["content"] == "API测试规则：已更新"

    # 5. active_only 过滤
    active_resp = client.get("/api/agent/memories?active_only=true")
    assert active_resp.status_code == 200
    assert len(active_resp.json()["data"]) == 0

    # 6. 删除
    del_resp = client.delete(f"/api/agent/memories/{memory_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["deleted"] is True

    # 再次查询确认已删除
    after_del = client.get("/api/agent/memories")
    assert len(after_del.json()["data"]) == 0


# ---------------------------------------------------------------------------
# 5. AgentRunner 与 ReviewerAgent 记忆集成测试
# ---------------------------------------------------------------------------


def test_runner_memory_injection_and_extraction(initialized_db: Any) -> None:
    """AgentRunner 初始化注入已有记忆，且识别用户指令沉淀新记忆。"""
    # 1. 预置一条活跃偏好
    create_memory(
        content="优先采用量化指标描述成果",
        type="preference",
        db_path=initialized_db,
    )

    class _MockLLM:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def chat_raw(self, messages: list[Any], tools: Any = None) -> Any:
            self.calls.append({"messages": list(messages), "tools": tools})
            m = MagicMock()
            m.content = "好的，已为您记住该偏好并作为后续规则遵守。"
            m.tool_calls = None
            return m

    llm = _MockLLM()
    registry = ToolRegistry()
    runner = AgentRunner(llm=llm, registry=registry, db_path=initialized_db)

    session = store.create_session(db_path=initialized_db)
    user_msg = "请记住：技术栈禁止出现精通，只写熟练"

    result = asyncio.run(runner.run(session.id, user_message=user_msg))
    assert result.status == "done"

    # 验证新规则已被自动提取落库
    new_memories = list_memories(type_filter="correction", db_path=initialized_db)
    assert len(new_memories) == 1
    assert "技术栈禁止出现精通" in new_memories[0].content
    assert new_memories[0].type == "correction"
    assert new_memories[0].source == "auto_inferred"

    # 验证初次调用 LLM 时 system prompt 包含预置记忆
    first_call_msgs = llm.calls[0]["messages"]
    sys_msg = first_call_msgs[0]["content"]
    assert "用户个性化长期偏好与历史纠偏" in sys_msg
    assert "优先采用量化指标描述成果" in sys_msg


def test_reviewer_memory_injection(initialized_db: Any) -> None:
    """ReviewerAgent 在草稿审查时挂载长期记忆与纠偏红线。"""
    create_memory(
        content="经历中不得编造任何未在证据中出现的项目",
        type="correction",
        db_path=initialized_db,
    )

    class _ReviewLLM:
        configured = True

        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def chat(
            self,
            system_prompt: str,
            user_content: str,
            response_format_json: bool = False,
        ) -> str:
            self.calls.append({
                "system_prompt": system_prompt,
                "user_content": user_content,
            })
            return '{"passed": true, "issues": [], "summary": "符合所有用户长期记忆规范"}'

    mock_llm = _ReviewLLM()
    reviewer = ReviewerAgent(llm=mock_llm)


    draft = {"basic": {"name": "张三"}, "experience": []}
    res = asyncio.run(
        reviewer.review_draft(
            content=draft,
            structured_jd=None,
            evidence=[],
            db_path=initialized_db,
        )
    )
    assert res["passed"] is True
    assert len(mock_llm.calls) == 1
    review_input = mock_llm.calls[0]["user_content"]
    assert "用户个性化长期偏好与历史纠偏" in review_input
    assert "经历中不得编造任何未在证据中出现的项目" in review_input


# ---------------------------------------------------------------------------
# 6. 长期记忆检索删除（根据文本、最新记录或 ID）与工具集成
# ---------------------------------------------------------------------------


def test_search_and_delete_memory(initialized_db: Any) -> None:
    """根据文本关键词检索删除、按最新删除、按 ID 删除。"""
    # 准备数据
    m1 = create_memory("工作经历多用数字量化，控制在3条以内", type="preference", db_path=initialized_db)
    m2 = create_memory("技术栈千万不要写精通，只写熟练", type="correction", db_path=initialized_db)

    # 1. 关键词文本检索删除
    res = memory_store.search_and_delete_memory(query="不要写精通", db_path=initialized_db)
    assert res["ok"] is True
    assert len(res["deleted"]) == 1
    assert res["deleted"][0]["id"] == m2.id
    assert get_memory(m2.id, db_path=initialized_db) is None
    assert get_memory(m1.id, db_path=initialized_db) is not None

    # 2. 按最新/刚刚删除 (latest / 刚刚)
    m3 = create_memory("不要出现空话套话", type="correction", db_path=initialized_db)
    res_latest = memory_store.search_and_delete_memory(query="刚刚添加的那条", db_path=initialized_db)
    assert res_latest["ok"] is True
    assert res_latest["deleted"][0]["id"] == m3.id
    assert get_memory(m3.id, db_path=initialized_db) is None

    # 3. 按 ID 删除
    res_id = memory_store.search_and_delete_memory(memory_id=m1.id, db_path=initialized_db)
    assert res_id["ok"] is True
    assert res_id["deleted"][0]["id"] == m1.id
    assert get_memory(m1.id, db_path=initialized_db) is None

    # 4. 未找到记忆时友好提示
    create_memory("保留的记忆规则", type="preference", db_path=initialized_db)
    res_none = memory_store.search_and_delete_memory(query="不存在的关键词", db_path=initialized_db)
    assert res_none["ok"] is False
    assert "未找到" in res_none["message"]


def test_delete_memory_tool_in_registry(initialized_db: Any, monkeypatch: Any) -> None:
    """build_registry 包含 delete_memory 与 list_memories，且执行成功。"""
    from resume_agent.config import settings
    from resume_agent.tools.agent_tools import build_registry

    monkeypatch.setattr(settings, "sqlite_path", initialized_db)
    m = create_memory("经历中多突出微服务与高并发", type="preference", db_path=initialized_db)

    registry = build_registry()
    names = {tc["function"]["name"] for tc in registry.schemas()}
    assert "delete_memory" in names
    assert "list_memories" in names

    # 1. 执行 list_memories
    list_res = asyncio.run(registry.execute("list_memories", {}))
    assert list_res["ok"] is True
    assert any(item["id"] == m.id for item in list_res["memories"])

    # 2. 执行 delete_memory 删除
    del_res = asyncio.run(registry.execute("delete_memory", {"query": "微服务"}))
    assert del_res["ok"] is True
    assert del_res["deleted"][0]["id"] == m.id
    assert get_memory(m.id, db_path=initialized_db) is None


def test_runner_emits_memory_deleted_event(initialized_db: Any) -> None:
    """AgentRunner 在调用 delete_memory 工具时发射 memory_deleted SSE 事件。"""
    m = create_memory("不要在技术栈中写精通", type="correction", db_path=initialized_db)

    from resume_agent.tools.agent_tools import build_registry

    class _ToolCallingLLM:
        def __init__(self) -> None:
            self.first = True

        async def chat_raw(self, messages: list[Any], tools: Any = None) -> Any:
            resp = MagicMock()
            if self.first:
                self.first = False
                tc = MagicMock()
                tc.id = "call_del_1"
                tc.function.name = "delete_memory"
                tc.function.arguments = '{"query": "精通"}'
                resp.content = None
                resp.tool_calls = [tc]
                return resp
            resp.content = "已经帮您删除了关于「不要在技术栈中写精通」的记忆。"
            resp.tool_calls = None
            return resp

    llm = _ToolCallingLLM()
    registry = build_registry()
    runner = AgentRunner(llm=llm, registry=registry, db_path=initialized_db)

    events: list[dict[str, Any]] = []

    async def _on_event(evt: dict[str, Any]) -> None:
        events.append(evt)

    session = store.create_session(db_path=initialized_db)
    result = asyncio.run(runner.run(session.id, user_message="帮我把不要精通的记忆删掉", on_event=_on_event))

    assert result.status == "done"
    del_events = [e for e in events if e.get("type") == "memory_deleted"]
    assert len(del_events) == 1
    assert del_events[0]["memory_id"] == m.id
    assert "精通" in del_events[0]["content"]


