"""模板列表端点（US-8）。

返回后端支持的简历模板配置摘要，供前端模板选择器使用。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from resume_agent.api.response import success
from resume_agent.export.templates import list_templates

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
async def get_templates() -> dict[str, Any]:
    """获取模板列表。

    返回所有内置模板的摘要信息（id / name / description / theme_color）。

    Returns:
        统一响应 envelope，``data`` 为模板摘要字典列表。
    """
    return success(list_templates())
