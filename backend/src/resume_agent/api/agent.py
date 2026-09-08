"""Agent 会话端点（US-27 agent-runtime，同步 JSON 版本）。

提供会话生命周期与消息运行入口：
- POST   /api/agent/sessions               创建会话
- GET    /api/agent/sessions               会话列表（摘要）
- GET    /api/agent/sessions/{id}          会话详情（含 messages）
- GET    /api/agent/sessions/{id}/traces   工具调用轨迹
- POST   /api/agent/sessions/{id}/messages 发送消息并运行至终止

SSE 流式版本属 US-28，届时 /messages 升级为事件流，契约向前兼容。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from resume_agent.agents import store
from resume_agent.agents.runner import AgentRunner
from resume_agent.api.response import error, success

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/agent", tags=["agent"])


class CreateSessionRequest(BaseModel):
    """创建会话请求体。"""

    context: dict[str, Any] = Field(default_factory=dict)


class PostMessageRequest(BaseModel):
    """发送消息请求体。"""

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


__all__ = ["router"]
