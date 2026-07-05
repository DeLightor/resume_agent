"""API 路由聚合。

将所有子路由模块聚合为单一 ``api_router``，由 ``main.py`` 挂载到 ``/api`` 前缀。
"""

from __future__ import annotations

from fastapi import APIRouter

from resume_agent.api import (
    export,
    gap,
    generate,
    health,
    jd,
    knowledge,
    resumes,
    templates,
    tree,
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
api_router.include_router(export.router)
api_router.include_router(templates.router)


__all__ = ["api_router"]
