"""Agent 会话 API 测试（US-27 agent-runtime Task 5）。

覆盖四端点契约：创建 / 列表 / 详情 / 发消息运行（含 awaiting_user 恢复）。
AgentRunner 与 LLM 全部 mock，不发真实请求。
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


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
