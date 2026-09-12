"""素材挖掘端点（US-36 graduate-material-mining）。

覆盖：
- GET /api/mining/templates        获取分类追问模板
- POST /api/mining/sessions        创建新挖掘会话
- GET /api/mining/sessions         查询挖掘会话列表
- GET /api/mining/sessions/{id}    获取挖掘会话详情
- POST /api/mining/sessions/{id}/answer      提交阶段问答
- POST /api/mining/sessions/{id}/synthesize  提炼 STAR 结构成果与向量查重
- POST /api/mining/sessions/{id}/commit      确认沉淀并写入知识库与向量库
- DELETE /api/mining/sessions/{id} 放弃或删除挖掘草稿
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from resume_agent.api.response import error, success
from resume_agent.llm.client import LLMClient
from resume_agent.services import material_mining

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/mining", tags=["mining"])


class CreateSessionRequest(BaseModel):
    category: str = Field(..., description="经历分类 (course_project/competition/research/club/internship)")
    title: str = Field(..., description="项目或经历标题")


class AnswerStepRequest(BaseModel):
    step: int = Field(..., ge=1, le=4, description="步骤编号 (1-4)")
    answer: str = Field(..., min_length=1, description="用户回答内容")


class SynthesizeRequest(BaseModel):
    check_duplicate: bool = Field(True, description="是否同时执行知识库向量查重")


class CommitMiningRequest(BaseModel):
    star_result: dict[str, Any] | None = Field(default=None, description="用户编辑后的 STAR 成果")


@router.get("/templates")
async def get_templates() -> dict[str, Any]:
    """获取预置的五大经历分类追问模板。"""
    templates = material_mining.get_mining_templates()
    return success(templates)


@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    """创建新的素材挖掘会话。"""
    try:
        session = material_mining.create_mining_session(
            category=req.category,
            title=req.title,
        )
        return success(session.to_dict())
    except ValueError as exc:
        return error("INVALID_ARGUMENT", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("创建挖掘会话失败")
        return error("INTERNAL_ERROR", f"创建挖掘会话失败: {exc}")


@router.get("/sessions")
async def list_sessions(status: str | None = None) -> dict[str, Any]:
    """查询素材挖掘会话列表，支持按状态筛选。"""
    sessions = material_mining.list_mining_sessions(status_filter=status)
    return success([s.to_dict() for s in sessions])


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    """查询指定素材挖掘会话详情与历史草稿。"""
    session = material_mining.get_mining_session(session_id)
    if not session:
        return error("NOT_FOUND", f"会话不存在: {session_id}")
    return success(session.to_dict())


@router.post("/sessions/{session_id}/answer")
async def submit_answer(session_id: str, req: AnswerStepRequest) -> dict[str, Any]:
    """提交某个阶段的问答回答，推进步骤并获取师兄追问反馈。"""
    llm = LLMClient()
    try:
        res = await material_mining.submit_step_answer(
            session_id=session_id,
            step=req.step,
            answer=req.answer,
            llm=llm,
        )
        return success(res)
    except ValueError as exc:
        return error("INVALID_ARGUMENT", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("提交阶段问答失败")
        return error("INTERNAL_ERROR", f"提交阶段问答失败: {exc}")


@router.post("/sessions/{session_id}/synthesize")
async def synthesize_result(session_id: str, req: SynthesizeRequest | None = None) -> dict[str, Any]:
    """将问答历史提炼为 STAR 结构化成果并执行向量语义查重。"""
    llm = LLMClient()
    try:
        star = await material_mining.synthesize_star_result(
            session_id=session_id,
            llm=llm,
        )
        dup_check = None
        should_check = req.check_duplicate if req else True
        if should_check:
            # 拼接核心文本进行向量语义查重
            full_text = f"{star.get('summary', '')}\n" + "\n".join(star.get("bullet_points", []))
            dup_check = material_mining.check_duplicate_in_knowledge(full_text)

        return success({
            "star_result": star,
            "duplicate_check": dup_check,
        })
    except ValueError as exc:
        return error("INVALID_ARGUMENT", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("提炼 STAR 成果失败")
        return error("INTERNAL_ERROR", f"提炼 STAR 成果失败: {exc}")


@router.post("/sessions/{session_id}/commit")
async def commit_to_knowledge(session_id: str, req: CommitMiningRequest | None = None) -> dict[str, Any]:
    """用户确认提炼成果无误，打包生成 Markdown 文件并写入知识库与 Chroma 向量索引。"""
    try:
        result = material_mining.commit_mining_to_knowledge(
            session_id, star_result=req.star_result if req else None
        )
        return success(result)
    except ValueError as exc:
        return error("INVALID_ARGUMENT", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("提交入库失败")
        return error("INTERNAL_ERROR", f"提交入库失败: {exc}")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    """删除或放弃指定素材挖掘会话。"""
    ok = material_mining.delete_mining_session(session_id)
    if not ok:
        return error("NOT_FOUND", f"会话不存在或已删除: {session_id}")
    return success({"deleted": True, "id": session_id})
