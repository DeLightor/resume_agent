"""Agent 会话端点（US-27 agent-runtime + US-28 agent-sse-stream）。

提供会话生命周期与消息运行入口：
- POST   /api/agent/sessions               创建会话
- GET    /api/agent/sessions               会话列表（摘要）
- GET    /api/agent/sessions/{id}          会话详情（含 messages）
- GET    /api/agent/sessions/{id}/traces   工具调用轨迹
- POST   /api/agent/sessions/{id}/messages 发送消息并运行至终止（阻塞 JSON）
- POST   /api/agent/chat                   发送消息并以 SSE 事件流返回运行过程

事件协议（design.md §2）：thinking / tool_call / tool_result / ask_user /
done / error；review / draft 预留 US-30。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from resume_agent.agents import store
from resume_agent.agents.runner import AgentRunner
from resume_agent.api.response import error, success

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/agent", tags=["agent"])

# 心跳间隔（秒）：SSE 空闲时发注释行防代理断连
_SSE_KEEPALIVE_SECONDS: float = 15.0

# 运行中的后台 Agent task（防 GC；完成即丢弃）
_background_runs: set[asyncio.Task[None]] = set()


class CreateSessionRequest(BaseModel):
    """创建会话请求体。"""

    context: dict[str, Any] = Field(default_factory=dict)


class PostMessageRequest(BaseModel):
    """发送消息请求体。"""

    message: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """SSE 对话请求体。"""

    session_id: str
    message: str = Field(min_length=1)


def _get_runner() -> AgentRunner:
    """构造默认 AgentRunner（LLM 未配置时也允许创建，运行时报错）。"""
    return AgentRunner()


@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    """创建 Agent 会话。"""
    session = store.create_session(context=req.context)
    return success({
        "id": session.id,
        "status": session.status,
        "context": session.context,
        "messages": session.messages,
        "created_at": session.created_at,
    })


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    """列出所有会话摘要（新→旧）。"""
    return success(store.list_sessions())


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    """获取会话详情（含完整消息历史）。"""
    session = store.get_session(session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content=error("SESSION_NOT_FOUND", f"会话不存在: {session_id}"),
        )
    return success({
        "id": session.id,
        "status": session.status,
        "context": session.context,
        "messages": session.messages,
        "pending_question": session.pending_question,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    })


@router.get("/sessions/{session_id}/traces")
async def get_traces(session_id: str) -> dict[str, Any]:
    """获取会话的工具调用轨迹。"""
    session = store.get_session(session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content=error("SESSION_NOT_FOUND", f"会话不存在: {session_id}"),
        )
    return success(store.list_traces(session_id))


@router.post("/sessions/{session_id}/messages")
async def post_message(session_id: str, req: PostMessageRequest) -> dict[str, Any]:
    """发送用户消息并运行 Agent 至终止。

    awaiting_user 状态下发送消息 = 回答 pending_question 并恢复循环；
    其他状态（running 以外）按新一轮输入处理。
    """
    session = store.get_session(session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content=error("SESSION_NOT_FOUND", f"会话不存在: {session_id}"),
        )

    if not req.message.strip():
        return error("INVALID_REQUEST", "message 不能为空")

    runner = _get_runner()

    # LLM 未配置直接给出明确错误
    if not getattr(runner.llm, "configured", True):
        return error("LLM_NOT_CONFIGURED", "LLM 未配置，无法运行 Agent")

    if session.status == "awaiting_user":
        result = await runner.resume(session_id, req.message)
    else:
        result = await runner.run(session_id, user_message=req.message)

    return success({
        "session_id": session_id,
        "status": result.status,
        "final_message": result.final_message,
        "pending_question": result.pending_question,
        "error": result.error,
        "rounds_used": result.rounds_used,
    })


@router.post("/chat")
async def chat(req: ChatRequest) -> Any:
    """SSE 对话：事件流式返回 Agent 运行过程（US-28）。

    Runner 在后台 task 中执行，客户端断开仅取消 SSE 读端，
    运行继续至终态并持久化（断线会话不丢失）。
    """
    session = store.get_session(req.session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content=error("SESSION_NOT_FOUND", f"会话不存在: {req.session_id}"),
        )

    if not req.message.strip():
        return error("INVALID_REQUEST", "message 不能为空")

    runner = _get_runner()
    if not getattr(runner.llm, "configured", True):
        return error("LLM_NOT_CONFIGURED", "LLM 未配置，无法运行 Agent")

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    # 是否已发出 error 事件（Runner 进入循环前失败时兜底发一条）
    error_emitted = False

    async def on_event(event: dict[str, Any]) -> None:
        nonlocal error_emitted
        if event.get("type") == "error":
            error_emitted = True
        await queue.put(event)

    async def run_agent() -> None:
        try:
            if session.status == "awaiting_user":
                result = await runner.resume(
                    req.session_id, req.message, on_event=on_event
                )
            else:
                result = await runner.run(
                    req.session_id, user_message=req.message, on_event=on_event
                )
            # run/resume 在进入循环前失败（如会话已结束）不会发 error 事件
            if result.status == "failed" and not error_emitted:
                await queue.put({
                    "type": "error",
                    "message": result.error or "运行失败",
                    "rounds_used": result.rounds_used,
                })
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent chat 后台运行异常")
            await queue.put({"type": "error", "message": str(exc)})
        finally:
            await queue.put(None)  # 流结束哨兵

    # 独立 task：SSE 读端被取消后运行仍能收敛
    task = asyncio.create_task(run_agent())
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)

    async def event_stream() -> AsyncGenerator[str, None]:
        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=_SSE_KEEPALIVE_SECONDS
                )
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if event is None:
                break
            yield (
                f"event: {event['type']}\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
