"""API 路由聚合。

将所有子路由模块聚合为单一 ``api_router``，由 ``main.py`` 挂载到 ``/api`` 前缀。
"""

from __future__ import annotations

from fastapi import APIRouter

from resume_agent.api import (
    completeness,
    diff,
    export,
    gap,
    generate,
    health,
    jd,
    knowledge,
    personal_info,
    resumes,
    section_order,
    suggest,
    templates,
    tree,
    tutor,
)

api_router = APIRouter()

# 健康检查（无前缀，直接挂在 /api/health）
api_router.include_router(health.router)

# 业务路由
api_router.include_router(tree.router)
api_router.include_router(resumes.router)
api_router.include_router(knowledge.router)
api_router.include_router(jd.router)
api_router.include_router(gap.router)
api_router.include_router(generate.router)
api_router.include_router(suggest.router)
api_router.include_router(export.router)
api_router.include_router(templates.router)
api_router.include_router(diff.router)
api_router.include_router(tutor.router)
api_router.include_router(personal_info.router)
api_router.include_router(section_order.router)
api_router.include_router(completeness.router)


__all__ = ["api_router"]
