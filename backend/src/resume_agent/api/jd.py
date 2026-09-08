"""JD 截图分析端点。

上传 JD 文件（截图 / PDF / TXT），经 MinerU 云端 OCR 解析为 Markdown 文本
（TXT 直接读取），再用 DeepSeek LLM 做结构化提取（含多文件去重），返回职位
描述的结构化字段。

流程：
1. 接收 List[UploadFile]，验证格式。
2. 保存到 ``{files_root}/jd/{uuid}.{ext}``。
3. TXT 直接读取；其他文件批量调用 ``MinerUClient.upload_and_parse_multiple``。
4. 合并所有文本，调用 ``LLMClient.chat`` 做结构化提取（含去重）。
5. 返回 ``{"ok": True, "data": {"raw_text": ..., "structured": ...}}``。

对齐 design.md / US-4 JD 截图分析。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, File, UploadFile

from resume_agent.api.response import error, success
from resume_agent.parsers.mineru_client import MinerUClient, MinerUError
from resume_agent.services.jd_extract import extract_jd_fields

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/jd", tags=["jd"])

# 支持的文件格式
_ALLOWED_FILE_TYPES: tuple[str, ...] = (
    "png", "jpg", "jpeg", "webp", "pdf", "txt", "doc", "docx",
)

# 直接读取的格式（无需 MinerU OCR）
_DIRECT_READ_TYPES: tuple[str, ...] = ("txt",)


def _get_file_ext(filename: str | None) -> str | None:
    """从文件名提取小写扩展名（不含点）。"""
    if not filename or "." not in filename:
        return None
    return filename.rsplit(".", 1)[-1].lower()

@router.post("/analyze")
async def analyze_jd(
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """分析 JD 文件（支持多文件）。

    接收多个 JD 文件（截图 / PDF / TXT），经 MinerU OCR 解析或直接读取，
    合并后用 DeepSeek LLM 提取结构化字段（含去重）。

    Args:
        files: 上传的 JD 文件列表。

    Returns:
        统一响应 envelope，``data`` 含 ``raw_text`` 与 ``structured``。
    """
    from resume_agent.config import settings

    if not files:
        return error("INVALID_FILE_TYPE", "未上传任何文件")

    # 1. 验证所有文件格式
    for f in files:
        file_ext = _get_file_ext(f.filename)
        if file_ext not in _ALLOWED_FILE_TYPES:
            return error(
                "INVALID_FILE_TYPE",
                f"不支持的文件类型: {file_ext}，仅支持 {list(_ALLOWED_FILE_TYPES)}",
            )

    # 2. 保存所有文件
    jd_dir = settings.files_root / "jd"
    jd_dir.mkdir(parents=True, exist_ok=True)

    saved_info: list[tuple[Any, str]] = []  # (path, ext)
    for f in files:
        file_ext = _get_file_ext(f.filename)
        saved_filename = f"{uuid.uuid4()}.{file_ext}"
        saved_path = jd_dir / saved_filename
        content = await f.read()
        saved_path.write_bytes(content)
        saved_info.append((saved_path, file_ext))

    # 3. 解析：TXT 直接读取，其他走 MinerU 批量
    all_texts: list[str | None] = [None] * len(saved_info)
    mineru_paths = []
    mineru_indices = []

    for i, (path, ext) in enumerate(saved_info):
        if ext in _DIRECT_READ_TYPES:
            try:
                all_texts[i] = path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("读取 TXT 失败: %s", exc)
                return error("PARSE_FAILED", f"读取文本文件失败: {exc}")
        else:
            mineru_paths.append(path)
            mineru_indices.append(i)

    if mineru_paths:
        mineru = MinerUClient(
            token=settings.mineru_api_token,
            base_url=settings.mineru_api_base,
        )
        try:
            mineru_texts = mineru.upload_and_parse_multiple(mineru_paths)
        except MinerUError as exc:
            logger.warning("MinerU 解析失败: %s", exc)
            return error("PARSE_FAILED", f"JD 文件解析失败: {exc}")
        except Exception as exc:
            logger.exception("MinerU 解析异常")
            return error("PARSE_FAILED", f"JD 文件解析异常: {exc}")

        for idx, md_text in zip(mineru_indices, mineru_texts, strict=False):
            all_texts[idx] = md_text

    # 4. 合并文本
    merged_text = "\n\n---\n\n".join(t for t in all_texts if t)

    if not merged_text.strip():
        return error("PARSE_FAILED", "所有文件解析结果为空")

    # 5. 调用 LLM 结构化提取（前置检查保留原有 LLM_NOT_CONFIGURED 语义）
    from resume_agent.llm.client import LLMClient

    if not LLMClient().configured:
        return error("LLM_NOT_CONFIGURED", "LLM 未配置，无法进行结构化提取")

    try:
        structured = await extract_jd_fields(merged_text)
    except RuntimeError as exc:
        logger.warning("LLM 结构化提取失败: %s", exc)
        return error("EXTRACT_FAILED", f"JD 结构化提取失败: {exc}")
    except Exception as exc:
        logger.exception("LLM 结构化提取异常")
        return error("EXTRACT_FAILED", f"JD 结构化提取异常: {exc}")

    return success({"raw_text": merged_text, "structured": structured})
