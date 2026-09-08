"""技能 Gap 报告端点。

接收 JD 结构化数据，对每项技能（tech_stack / hard_skills / soft_skills /
bonus_items）调用知识库语义检索，按匹配分数判定三色状态（已覆盖/部分缺口/
未涉及），再用 LLM 基于检索到的真实内容生成每项描述。

流程：
1. 收集 JD 中所有技能项（4 类合并，去重）。
2. 对每项技能调用 Chroma 知识库检索，取 top-3 结果。
3. 按最高相似度分数判定：≥0.6 covered / 0.3~0.6 partial / <0.3 missing。
4. 调用 LLM 一次性生成所有技能项的描述（基于检索命中内容，不编造）。
5. 返回汇总（overall_score + 三色计数）与明细列表。

对齐 PRD US-5 / openspec/changes/gap-report/proposal.md。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from resume_agent.api.response import error, success
from resume_agent.services.gap_analyzer import analyze_gap

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/gap-report", tags=["gap-report"])


class GapReportRequest(BaseModel):
    """Gap 报告请求体。"""

    structured_jd: dict[str, Any]


@router.post("")
async def generate_gap_report(req: GapReportRequest) -> dict[str, Any]:
    """生成技能 Gap 报告。

    Args:
        req: 包含 structured_jd 的请求体。

    Returns:
        统一响应 envelope，data 含 overall_score / summary / items。
    """
    structured = req.structured_jd
    if not structured or not isinstance(structured, dict):
        return error("INVALID_REQUEST", "structured_jd 不能为空")

    from resume_agent.services.gap_analyzer import _collect_skills

    if not _collect_skills(structured):
        return error("NO_SKILLS", "JD 结构化数据中未找到任何技能项")

    try:
        data = await analyze_gap(structured)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gap 分析异常")
        return error("GAP_FAILED", f"Gap 报告生成失败: {exc}")

    return success(data)
