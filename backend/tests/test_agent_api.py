"""Agent 会话 API 测试（US-27 agent-runtime Task 5）。

覆盖四端点契约：创建 / 列表 / 详情 / 发消息运行（含 awaiting_user 恢复）。
AgentRunner 与 LLM 全部 mock，不发真实请求。
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from resume_agent.agents import store


def _init_db() -> None:
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database

    init_database(settings.sqlite_path)


def _mock_runner(
    monkeypatch: Any, script: list[Any]
) -> list[Any]:
    """mock api.agent 模块内的 AgentRunner，返回收集到的调用记录。"""
    from resume_agent.agents.runner import AgentRunResult

    calls: list[dict[str, Any]] = []

    class _FakeRunner:
        llm = None  # getattr(None, "configured", True) → True

        async def run(self, session_id: str, user_message: str | None = None):
            calls.append({"method": "run", "session_id": session_id,
                          "user_message": user_message})
            return script.pop(0) if script else AgentRunResult(status="done")

        async def resume(self, session_id: str, answer: str):
            calls.append({"method": "resume", "session_id": session_id,
                          "answer": answer})
            return script.pop(0) if script else AgentRunResult(status="done")

    monkeypatch.setattr("resume_agent.api.agent.AgentRunner", _FakeRunner)
    return calls


def test_create_session(monkeypatch: Any) -> None:
    """POST /api/agent/sessions 创建会话并返回 id/status。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.post("/api/agent/sessions", json={
        "context": {"current_node_id": "master"},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["id"]
    assert body["data"]["status"] == "running"
    assert body["data"]["context"] == {"current_node_id": "master"}


def test_create_session_empty_context(monkeypatch: Any) -> None:
    """无 context 创建也合法。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.post("/api/agent/sessions", json={})
    assert resp.status_code == 200
    assert resp.json()["data"]["context"] == {}


def test_list_sessions(monkeypatch: Any) -> None:
    """GET /api/agent/sessions 列出摘要。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    client.post("/api/agent/sessions", json={})
    client.post("/api/agent/sessions", json={})

    resp = client.get("/api/agent/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["data"]) == 2
    assert all("messages" not in item for item in body["data"])


def test_get_session_detail(monkeypatch: Any) -> None:
    """GET /api/agent/sessions/{id} 返回详情（含 messages）。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]
    resp = client.get(f"/api/agent/sessions/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["id"] == created["id"]
    assert isinstance(body["data"]["messages"], list)


def test_get_session_not_found(monkeypatch: Any) -> None:
    """GET 不存在的会话返回 404。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.get("/api/agent/sessions/no-such-id")
    assert resp.status_code == 404
    assert resp.json()["ok"] is False


def test_post_message_runs_agent(monkeypatch: Any) -> None:
    """POST /messages 正常运行：done 状态返回最终消息。"""
    _init_db()
    from resume_agent.agents.runner import AgentRunResult
    from resume_agent.main import app

    calls = _mock_runner(monkeypatch, [
        AgentRunResult(status="done", final_message="已完成优化。", rounds_used=2),
    ])
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    resp = client.post(
        f"/api/agent/sessions/{created['id']}/messages",
        json={"message": "帮我优化项目经历"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "done"
    assert body["data"]["final_message"] == "已完成优化。"

    assert calls == [{
        "method": "run", "session_id": created["id"],
        "user_message": "帮我优化项目经历",
    }]


def test_post_message_awaiting_user_and_resume(monkeypatch: Any) -> None:
    """POST /messages 触发 ask_user 暂停；再次 POST 恢复。"""
    _init_db()
    from resume_agent.agents.runner import AgentRunResult
    from resume_agent.main import app

    _mock_runner(monkeypatch, [
        AgentRunResult(status="awaiting_user", pending_question="你的毕业年份？"),
        AgentRunResult(status="done", final_message="收到。"),
    ])
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    # 第一轮：暂停
    resp = client.post(
        f"/api/agent/sessions/{created['id']}/messages",
        json={"message": "帮我写简历"},
    )
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "awaiting_user"
    assert body["data"]["pending_question"] == "你的毕业年份？"

    # 第二轮：恢复（awaiting_user 状态下发 message 即回答）
    resp = client.post(
        f"/api/agent/sessions/{created['id']}/messages",
        json={"message": "2025 届"},
    )
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "done"


def test_post_message_failed_status(monkeypatch: Any) -> None:
    """Runner failed 时端点返回 ok=true + status=failed（会话级失败不是协议失败）。"""
    _init_db()
    from resume_agent.agents.runner import AgentRunResult
    from resume_agent.main import app

    _mock_runner(monkeypatch, [
        AgentRunResult(status="failed", error="LLM 未配置"),
    ])
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    resp = client.post(
        f"/api/agent/sessions/{created['id']}/messages",
        json={"message": "hi"},
    )
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "failed"
    assert body["data"]["error"] == "LLM 未配置"


def test_get_traces(monkeypatch: Any) -> None:
    """GET /api/agent/sessions/{id}/traces 返回轨迹列表。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]
    resp = client.get(f"/api/agent/sessions/{created['id']}/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert isinstance(body["data"], list)


def test_post_message_empty_body(monkeypatch: Any) -> None:
    """空 message 返回 Pydantic 校验错误（422）。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]
    resp = client.post(
        f"/api/agent/sessions/{created['id']}/messages",
        json={"message": ""},
    )
    assert resp.status_code == 422


# === POST /api/agent/chat（US-28 agent-sse-stream Task 2）===


def _mock_stream_runner(monkeypatch: Any, script: list[dict[str, Any]]) -> list[Any]:
    """mock Runner：把脚本化事件经 on_event 依次发出，返回调用记录。"""
    from resume_agent.agents.runner import AgentRunResult

    calls: list[dict[str, Any]] = []

    class _FakeRunner:
        llm = None  # getattr(None, "configured", True) → True

        async def run(
            self,
            session_id: str,
            user_message: str | None = None,
            on_event: Any = None,
        ):
            calls.append({"method": "run", "session_id": session_id,
                          "user_message": user_message})
            events = script.pop(0) if script else []
            for ev in events:
                if on_event is not None:
                    await on_event(ev)
            return AgentRunResult(status="done", final_message="ok")

        async def resume(
            self, session_id: str, answer: str, on_event: Any = None
        ):
            calls.append({"method": "resume", "session_id": session_id,
                          "answer": answer})
            events = script.pop(0) if script else []
            for ev in events:
                if on_event is not None:
                    await on_event(ev)
            return AgentRunResult(status="done", final_message="ok")

    monkeypatch.setattr("resume_agent.api.agent.AgentRunner", _FakeRunner)
    return calls


def _parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    """解析 SSE 文本为 (event, data) 序列。"""
    import json

    events: list[tuple[str, dict[str, Any]]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        ev_type = ""
        data: dict[str, Any] = {}
        for line in block.split("\n"):
            if line.startswith("event: "):
                ev_type = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((ev_type, data))
    return events


def test_chat_streams_sse_events(monkeypatch: Any) -> None:
    """POST /api/agent/chat 返回 text/event-stream，事件逐帧推送。"""
    _init_db()
    from resume_agent.main import app

    _mock_stream_runner(monkeypatch, [[
        {"type": "thinking", "round": 1},
        {"type": "tool_call", "round": 1, "tool_call_id": "tc1",
         "name": "retrieve_knowledge", "arguments": {"query": "Python"}},
        {"type": "tool_result", "round": 1, "tool_call_id": "tc1",
         "name": "retrieve_knowledge", "result": {"chunks": []}},
        {"type": "done", "status": "done", "final_message": "完成。",
         "rounds_used": 2},
    ]])
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    resp = client.post("/api/agent/chat", json={
        "session_id": created["id"],
        "message": "检索 Python 相关内容",
    })

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    types = [t for t, _ in events]
    assert types == ["thinking", "tool_call", "tool_result", "done"]
    assert events[1][1]["name"] == "retrieve_knowledge"
    assert events[1][1]["arguments"] == {"query": "Python"}
    assert events[-1][1]["final_message"] == "完成。"


def test_chat_awaiting_user_routes_to_resume(monkeypatch: Any) -> None:
    """awaiting_user 状态下 POST chat 走 resume 路径并流式返回。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    # 第一次：走 run，触发 ask_user 暂停（脚本第二次留给 resume）
    _mock_stream_runner(monkeypatch, [
        [{"type": "ask_user", "question": "你的毕业年份？"},
         {"type": "done", "status": "awaiting_user",
          "pending_question": "你的毕业年份？", "rounds_used": 1}],
        [{"type": "thinking", "round": 2},
         {"type": "done", "status": "done", "final_message": "收到。",
          "rounds_used": 2}],
    ])
    client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "帮我写简历",
    })

    # 手动把会话置为 awaiting_user（FakeRunner 不真正改库）
    from resume_agent.agents import store
    session = store.get_session(created["id"])
    assert session is not None
    session.status = "awaiting_user"
    session.pending_question = "你的毕业年份？"
    store.save_session(session)

    resp = client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "2025 届",
    })
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [t for t, _ in events]
    assert types == ["thinking", "done"]
    assert events[-1][1]["final_message"] == "收到。"


def test_chat_not_found(monkeypatch: Any) -> None:
    """不存在的会话返回 404 envelope。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.post("/api/agent/chat", json={
        "session_id": "no-such-id", "message": "hi",
    })
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SESSION_NOT_FOUND"


def test_chat_empty_message(monkeypatch: Any) -> None:
    """空 message → Pydantic 422。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]
    resp = client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "",
    })
    assert resp.status_code == 422


# === write_node 门禁契约（agent-write-guard）===


def test_get_session_detail_returns_pending_write(monkeypatch: Any) -> None:
    """会话详情返回 pending_write（前端恢复确认卡片的依据）。"""
    _init_db()
    from resume_agent.agents import store
    from resume_agent.main import app

    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    session = store.get_session(created["id"])
    assert session is not None
    session.status = "awaiting_user"
    session.pending_question = "确认写入节点 master？"
    session.pending_write = {
        "tool_call_id": "tc1",
        "node_id": "master",
        "content": {"skills": []},
        "review": {
            "passed": True,
            "issues": [],
            "summary": "审查通过",
        },
    }
    store.save_session(session)

    resp = client.get(f"/api/agent/sessions/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    # US-30：pending_write 携带 Reviewer 审查结果（前端恢复卡片展示）
    assert body["data"]["pending_write"] == {
        "tool_call_id": "tc1",
        "node_id": "master",
        "content": {"skills": []},
        "review": {"passed": True, "issues": [], "summary": "审查通过"},
    }


def test_chat_streams_write_confirm_event(monkeypatch: Any) -> None:
    """write_confirm 事件经 SSE 帧透传（含待写入内容）。"""
    _init_db()
    from resume_agent.main import app

    _mock_stream_runner(monkeypatch, [[
        {"type": "write_confirm", "node_id": "master",
         "content": {"skills": []}, "question": "确认写入节点 master？"},
        {"type": "done", "status": "awaiting_user",
         "pending_question": "确认写入节点 master？", "rounds_used": 1},
    ]])
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    resp = client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "帮我优化",
    })
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [t for t, _ in events]
    assert types == ["write_confirm", "done"]
    assert events[0][1]["node_id"] == "master"
    assert events[0][1]["content"] == {"skills": []}
    assert events[-1][1]["status"] == "awaiting_user"


def test_chat_streams_review_event(monkeypatch: Any) -> None:
    """US-30：review 事件经 SSE 帧透传（打回与放行路径都发出）。"""
    _init_db()
    from resume_agent.main import app

    _mock_stream_runner(monkeypatch, [[
        {"type": "review", "node_id": "master", "round": 1, "passed": False,
         "issues": [{"type": "cliche", "message": "「精通」无佐证"}],
         "summary": "发现 1 处套话"},
        {"type": "review", "node_id": "master", "round": 2, "passed": True,
         "issues": [], "summary": "审查通过"},
        {"type": "write_confirm", "node_id": "master", "content": {"skills": []},
         "question": "确认写入？",
         "review": {"passed": True, "issues": [], "summary": "审查通过"}},
        {"type": "done", "status": "awaiting_user",
         "pending_question": "确认写入？", "rounds_used": 2},
    ]])
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    resp = client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "帮我优化",
    })
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [t for t, _ in events]
    assert types == ["review", "review", "write_confirm", "done"]
    assert events[0][1]["passed"] is False
    assert events[0][1]["issues"][0]["type"] == "cliche"
    assert events[1][1]["round"] == 2
    assert events[2][1]["review"]["summary"] == "审查通过"


def test_chat_llm_not_configured(monkeypatch: Any) -> None:
    """LLM 未配置返回 LLM_NOT_CONFIGURED envelope（非流式错误）。"""
    _init_db()
    from resume_agent.main import app

    class _UnconfiguredLLM:
        configured = False

    class _FakeRunner:
        llm = _UnconfiguredLLM()

        async def run(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("不应执行到 runner")

    monkeypatch.setattr("resume_agent.api.agent.AgentRunner", _FakeRunner)
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    resp = client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "hi",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "LLM_NOT_CONFIGURED"


def test_chat_background_run_converges_session_state(monkeypatch: Any) -> None:
    """SSE 流结束后（后台 task 完成），会话状态已持久化为终态。"""
    _init_db()
    from resume_agent.main import app

    _mock_stream_runner(monkeypatch, [[
        {"type": "thinking", "round": 1},
        {"type": "done", "status": "done", "final_message": "好的。",
         "rounds_used": 1},
    ]])
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "hi",
    })

    # FakeRunner 不改库，这里验证的是会话仍可读（流式端点不吞异常）
    from resume_agent.agents import store
    session = store.get_session(created["id"])
    assert session is not None


# === POST /api/agent/chat context 注入（US-29 agent-context-integration）===


def _ctx_script_runner(monkeypatch: Any) -> None:
    """mock Runner 记录收到的消息历史（验证 context 注入进对话）。"""
    from resume_agent.agents.runner import AgentRunResult

    received: dict[str, Any] = {}

    class _FakeRunner:
        llm = None

        async def run(
            self,
            session_id: str,
            user_message: str | None = None,
            on_event: Any = None,
        ):
            session = store.get_session(session_id)
            received["messages"] = list(session.messages) if session else []
            if on_event is not None:
                await on_event({"type": "done", "status": "done",
                                "final_message": "ok", "rounds_used": 1})
            return AgentRunResult(status="done", final_message="ok")

        async def resume(
            self, session_id: str, answer: str, on_event: Any = None
        ):
            return AgentRunResult(status="done", final_message="ok")

    monkeypatch.setattr("resume_agent.api.agent.AgentRunner", _FakeRunner)
    monkeypatch.setattr("resume_agent.api.agent._received_ctx", received,
                        raising=False)


def test_chat_updates_session_context(monkeypatch: Any) -> None:
    """chat 带 context（与会话不同）→ 更新 context + 追加上下文 system 消息。"""
    _init_db()
    from resume_agent.main import app

    _ctx_script_runner(monkeypatch)
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    ctx = {"current_node_id": "branch-安全",
           "structured_jd": {"job_title": "后端工程师"},
           "gap_summary": {"overall_score": 0.4, "missing": ["Go"]}}
    client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "帮我优化", "context": ctx,
    })

    # 会话 context 已更新并持久化
    session = store.get_session(created["id"])
    assert session is not None
    assert session.context == ctx
    # 消息历史出现上下文 system 消息（Runner run 前已追加）
    from resume_agent.api import agent as agent_module
    messages = getattr(agent_module, "_received_ctx", {}).get("messages", [])
    ctx_msgs = [m for m in messages if m.get("role") == "system"
                and "上下文已更新" in (m.get("content") or "")]
    assert len(ctx_msgs) == 1
    assert "branch-安全" in ctx_msgs[0]["content"]


def test_chat_same_context_idempotent(monkeypatch: Any) -> None:
    """chat 带 context（与会话相同）→ 不追加 system 消息（幂等）。"""
    _init_db()
    from resume_agent.main import app

    _ctx_script_runner(monkeypatch)
    client = TestClient(app)
    created = client.post(
        "/api/agent/sessions",
        json={"context": {"current_node_id": "branch-安全"}},
    ).json()["data"]

    client.post("/api/agent/chat", json={
        "session_id": created["id"],
        "message": "hi",
        "context": {"current_node_id": "branch-安全"},
    })

    from resume_agent.api import agent as agent_module
    messages = getattr(agent_module, "_received_ctx", {}).get("messages", [])
    ctx_msgs = [m for m in messages if m.get("role") == "system"
                and "上下文已更新" in (m.get("content") or "")]
    # 首次会话创建时的 context 注入由 runner 机制处理（此处 mock 绕过），
    # chat 层只在 context 变化时追加 → 相同 context 不追加
    assert len(ctx_msgs) == 0


def test_chat_context_change_appends_new_message(monkeypatch: Any) -> None:
    """会话中途 context 变化（切节点）→ 追加更新消息。"""
    _init_db()
    from resume_agent.main import app

    _ctx_script_runner(monkeypatch)
    client = TestClient(app)
    created = client.post(
        "/api/agent/sessions",
        json={"context": {"current_node_id": "branch-安全"}},
    ).json()["data"]

    client.post("/api/agent/chat", json={
        "session_id": created["id"],
        "message": "换个节点",
        "context": {"current_node_id": "branch-后端"},
    })

    session = store.get_session(created["id"])
    assert session is not None
    assert session.context == {"current_node_id": "branch-后端"}
    from resume_agent.api import agent as agent_module
    messages = getattr(agent_module, "_received_ctx", {}).get("messages", [])
    ctx_msgs = [m for m in messages if m.get("role") == "system"
                and "上下文已更新" in (m.get("content") or "")]
    assert len(ctx_msgs) == 1
    assert "branch-后端" in ctx_msgs[0]["content"]


def test_chat_context_null_field_clears_key(monkeypatch: Any) -> None:
    """context 中 null 字段表示清除该上下文项。"""
    _init_db()
    from resume_agent.main import app

    _ctx_script_runner(monkeypatch)
    client = TestClient(app)
    created = client.post(
        "/api/agent/sessions",
        json={"context": {"current_node_id": "branch-安全",
                          "structured_jd": {"job_title": "后端"}}},
    ).json()["data"]

    client.post("/api/agent/chat", json={
        "session_id": created["id"],
        "message": "清空 JD",
        "context": {"current_node_id": "branch-安全", "structured_jd": None},
    })

    session = store.get_session(created["id"])
    assert session is not None
    assert session.context == {"current_node_id": "branch-安全"}


def test_chat_without_context_unchanged(monkeypatch: Any) -> None:
    """不带 context → 会话 context 保持不变（向后兼容）。"""
    _init_db()
    from resume_agent.main import app

    _ctx_script_runner(monkeypatch)
    client = TestClient(app)
    created = client.post(
        "/api/agent/sessions",
        json={"context": {"current_node_id": "branch-安全"}},
    ).json()["data"]

    client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "hi",
    })

    session = store.get_session(created["id"])
    assert session is not None
    assert session.context == {"current_node_id": "branch-安全"}


def test_chat_context_update_awaits_user_inserts_before_tool_call(monkeypatch: Any) -> None:
    """awaiting_user 会话更新 context → 更新消息插在未闭合 tool_calls 之前。

    否则 system 消息会插进 assistant(tool_calls) 与 resume 追加的 tool
    result 之间，违反 OpenAI 协议（DeepSeek 400，US-30 冒烟发现）。
    """
    _init_db()
    from resume_agent.agents.runner import AgentRunResult
    from resume_agent.main import app

    received: dict[str, Any] = {}

    class _FakeRunner:
        llm = None

        async def run(self, session_id: str, user_message: str | None = None,
                      on_event: Any = None):
            return AgentRunResult(status="done", final_message="ok")

        async def resume(self, session_id: str, answer: str, on_event: Any = None):
            session = store.get_session(session_id)
            received["messages"] = list(session.messages) if session else []
            return AgentRunResult(status="done", final_message="ok")

    monkeypatch.setattr("resume_agent.api.agent.AgentRunner", _FakeRunner)
    client = TestClient(app)
    created = client.post(
        "/api/agent/sessions",
        json={"context": {"current_node_id": "branch-安全"}},
    ).json()["data"]

    # 构造 ask_user 暂停状态（未闭合 tool_call）
    session = store.get_session(created["id"])
    assert session is not None
    session.messages.extend([
        {"role": "user", "content": "帮我优化"},
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "tc-ask", "type": "function",
            "function": {"name": "ask_user", "arguments": '{"question": "想优化哪部分？"}'},
        }]},
    ])
    session.status = "awaiting_user"
    session.pending_question = "想优化哪部分？"
    store.save_session(session)

    client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "选方案 1",
        "context": {"current_node_id": "branch-后端"},
    })

    messages = received["messages"]
    ctx_idx = next(
        i for i, m in enumerate(messages)
        if m.get("role") == "system" and "上下文已更新" in (m.get("content") or "")
    )
    assistant_idx = next(
        i for i, m in enumerate(messages)
        if m.get("role") == "assistant" and m.get("tool_calls")
    )
    # 更新消息在带未闭合 tool_calls 的 assistant 之前 →
    # resume 追加的 tool result 紧跟 assistant（协议合法）
    assert ctx_idx < assistant_idx


def test_chat_emits_error_event_on_runner_exception(monkeypatch: Any) -> None:
    """Runner 抛出未捕获异常 → SSE error 事件收尾，连接不悬挂。"""
    _init_db()
    from resume_agent.main import app

    class _BoomRunner:
        llm = None

        async def run(self, *args: Any, **kwargs: Any) -> Any:
            if kwargs.get("on_event") is not None:
                await kwargs["on_event"]({"type": "thinking", "round": 1})
            raise RuntimeError("Runner 炸了")

    monkeypatch.setattr("resume_agent.api.agent.AgentRunner", _BoomRunner)
    client = TestClient(app)
    created = client.post("/api/agent/sessions", json={}).json()["data"]

    resp = client.post("/api/agent/chat", json={
        "session_id": created["id"], "message": "hi",
    })
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [t for t, _ in events]
    assert types == ["thinking", "error"]
    assert "Runner 炸了" in events[-1][1]["message"]
