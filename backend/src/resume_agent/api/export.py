"""PDF 导出端点（US-7 / US-8）。

接收 AI 生成结果（experience / projects / skills），渲染为 ATS 友好 PDF。
使用 reportlab 生成文本可选、可解析的 PDF。

US-8 起支持 template_id 参数（modern / classic / tech），默认 modern，向后兼容。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from resume_agent.api.response import error

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
    """PDF 导出请求体。"""

    resume_data: dict[str, Any]
    job_title: str = ""
    company: str = ""
    template_id: str = "modern"


@router.post("/pdf")
async def export_pdf(req: ExportRequest) -> Any:
    """导出简历为 PDF。

    接收 AI 生成结果，渲染为 ATS 友好 PDF 文件并返回。

    Args:
        req: 导出请求，含简历数据、目标岗位信息与模板 id。

    Returns:
        PDF 文件响应（application/pdf）。
    """
    from resume_agent.config import settings
    from resume_agent.export.pdf_builder import build_pdf

    if not req.resume_data:
        return error("INVALID_REQUEST", "resume_data 不能为空")

    try:
        pdf_bytes = build_pdf(
            resume_data=req.resume_data,
            job_title=req.job_title,
            company=req.company,
            template_id=req.template_id,
        )
    except Exception as exc:
        logger.exception("PDF 生成失败")
        return error("EXPORT_FAILED", f"PDF 生成失败: {exc}")

    # 保存到临时文件
    export_dir = settings.files_root / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"resume_{uuid.uuid4().hex[:8]}.pdf"
    file_path = export_dir / filename
    file_path.write_bytes(pdf_bytes)

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=f"resume_{req.job_title or 'export'}.pdf",
    )
