"""Agent 长期记忆管理 API（US-35 agent-long-term-memory）。

提供记忆规则的列表获取、新增、更新（启用/禁用开关）与删除。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from resume_agent.agents import memory_store
from resume_agent.api.response import error, success

router = APIRouter(prefix="/agent/memories", tags=["agent-memory"])


class CreateMemoryRequest(BaseModel):
    """创建记忆规则请求体。"""

    content: str = Field(min_length=1, description="记忆规则内容")
    type: str = Field(default="preference", description="类型: preference / correction / style_sample")
    source: str = Field(default="manual", description="来源: manual / auto_inferred")
    session_id: str | None = Field(default=None, description="来源会话 ID")
    active: bool = Field(default=True, description="是否生效")


class UpdateMemoryRequest(BaseModel):
    """更新记忆规则请求体。"""

    content: str | None = Field(default=None, description="更新规则内容")
    type: str | None = Field(default=None, description="更新类型")
    active: bool | None = Field(default=None, description="更新生效状态")


@router.get("")
def list_memories_endpoint(
    active_only: bool = False,
    type: str | None = None,
) -> Any:
    """获取记忆列表。"""
    memories = memory_store.list_memories(
        active_only=active_only,
        type_filter=type,
    )
    return success([m.to_dict() for m in memories])


@router.post("")
def create_memory_endpoint(req: CreateMemoryRequest) -> Any:
    """手动或接口创建记忆规则。"""
    try:
        mem = memory_store.create_memory(
            content=req.content,
            type=req.type,
            source=req.source,
            session_id=req.session_id,
            active=req.active,
        )
        return success(mem.to_dict())
    except ValueError as exc:
        return error("BAD_REQUEST", str(exc))


@router.patch("/{memory_id}")
def update_memory_endpoint(memory_id: str, req: UpdateMemoryRequest) -> Any:
    """更新记忆规则内容或开关状态。"""
    try:
        updated = memory_store.update_memory(
            memory_id=memory_id,
            content=req.content,
            active=req.active,
            type=req.type,
        )
        if updated is None:
            return error("NOT_FOUND", "记忆规则不存在")
        return success(updated.to_dict())
    except ValueError as exc:
        return error("BAD_REQUEST", str(exc))


@router.delete("/{memory_id}")
def delete_memory_endpoint(memory_id: str) -> Any:
    """删除记忆规则。"""
    ok = memory_store.delete_memory(memory_id)
    if not ok:
        return error("NOT_FOUND", "记忆规则不存在")
    return success({"deleted": True})

