"""简历上传与解析端点。

实现 US-1 资产冷启动的简历上传、解析、列表三个端点。
对齐 design.md 第 3.1-3.3 节。

US-12 增强：上传简历时同时将文本存入知识库，
然后从知识库提取个人信息（向量搜索 + LLM），提高提取准确度。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from resume_agent.api.response import error, success
from resume_agent.config import settings
from resume_agent.db.connection import get_connection
from resume_agent.llm.client import LLMClient
from resume_agent.parsers.docx_parser import extract_text_from_docx
from resume_agent.parsers.extractor import ResumeExtractor
from resume_agent.parsers.pdf_parser import extract_text_from_pdf
from resume_agent.rag.chunker import chunk_text
from resume_agent.services.tree_builder import TreeBuilder

router = APIRouter(prefix="/resumes", tags=["resumes"])

# 支持的文件类型
_ALLOWED_FILE_TYPES: tuple[str, ...] = ("pdf", "docx")


class ParseRequest(BaseModel):
    """解析简历请求体。"""

    upload_id: str


def _get_file_ext(filename: str | None) -> str | None:
    """从文件名提取小写扩展名（不含点）。"""
    if not filename or "." not in filename:
        return None
    return filename.rsplit(".", 1)[-1].lower()


def _extract_text(file_path: Path, file_type: str) -> str:
    """根据文件类型调用对应解析器提取纯文本。

    优先使用 MinerU 云端解析（效果更好），未配置或失败时 fallback 到本地解析器。

    Args:
        file_path: 文件绝对路径。
        file_type: 文件扩展名（pdf / docx）。

    Returns:
        提取的纯文本（Markdown 或纯文本）。

    Raises:
        ValueError: 不支持的文件类型。
    """
    # 优先使用 MinerU 云端解析（对复杂排版/图片/表格效果更好）
    from resume_agent.config import settings

    if settings.mineru_api_token:
        try:
            from resume_agent.parsers.mineru_client import MinerUClient, MinerUError

            client = MinerUClient(
                token=settings.mineru_api_token,
                base_url=settings.mineru_api_base,
            )
            md_text = client.upload_and_parse(file_path)
            if md_text and md_text.strip():
                return md_text
        except MinerUError:
            pass  # fallback 到本地解析器
        except Exception:  # noqa: BLE001
            pass  # fallback 到本地解析器

    # Fallback: 本地解析器
    if file_type == "pdf":
        return extract_text_from_pdf(file_path)
    if file_type == "docx":
        return extract_text_from_docx(file_path)
    raise ValueError(f"不支持的文件类型: {file_type}")


@router.post("/upload")
async def upload_resume(file: UploadFile) -> dict[str, Any]:
    """上传简历文件。

    验证文件扩展名（pdf/docx），保存到 ``{files_root}/resumes/{uuid}.{ext}``，
    并写入 ``upload_records`` 表。

    Args:
        file: 上传的文件对象。

    Returns:
        统一响应 envelope，``data`` 含上传记录信息（upload_id、file_name、
        file_type、parse_status="pending"）。
    """
    file_ext = _get_file_ext(file.filename)
    if file_ext not in _ALLOWED_FILE_TYPES:
        return error(
            "INVALID_FILE_TYPE",
            f"不支持的文件类型: {file_ext}，仅支持 {list(_ALLOWED_FILE_TYPES)}",
        )

    # 保存文件
    upload_id = str(uuid.uuid4())
    resumes_dir = settings.files_root / "resumes"
    resumes_dir.mkdir(parents=True, exist_ok=True)
    saved_filename = f"{upload_id}.{file_ext}"
    saved_path = resumes_dir / saved_filename
    content = await file.read()
    saved_path.write_bytes(content)

    # 写入 DB（file_path 存储相对路径，相对 files_root）
    relative_path = f"resumes/{saved_filename}"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO upload_records (id, file_name, file_type, file_path, parse_status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (upload_id, file.filename or saved_filename, file_ext, relative_path, "pending"),
        )

    data = {
        "upload_id": upload_id,
        "file_name": file.filename or saved_filename,
        "file_type": file_ext,
        "file_path": relative_path,
        "parse_status": "pending",
    }
    return success(data)


@router.post("/parse")
async def parse_resume(req: ParseRequest) -> dict[str, Any]:
    """解析已上传的简历为结构化 JSON 并构建版本树节点。

    流程：
    1. 从 DB 获取 upload_record，不存在返回错误。
    2. 若 LLM 未配置，返回错误并保持 parse_status=pending。
    3. 根据文件类型调用解析器提取文本。
    4. 调用 ``ResumeExtractor.extract`` 提取结构化简历。
    5. 调用 ``TreeBuilder.build_from_resume`` 创建/更新版本树节点。
    6. 更新 upload_records.parse_status=success。
    7. 解析失败 → parse_status=needs_review。

    Args:
        req: 解析请求，含上传记录 ID。

    Returns:
        统一响应 envelope，``data`` 含 structured_resume、tree_node、deduplicated。
    """
    # 1. 获取上传记录
    with get_connection() as conn:
        record = conn.execute(
            "SELECT * FROM upload_records WHERE id = ?",
            (req.upload_id,),
        ).fetchone()

    if record is None:
        return error("UPLOAD_NOT_FOUND", f"上传记录不存在: {req.upload_id}")

    # 2. 检查 LLM 配置
    llm_client = LLMClient()
    if not llm_client.configured:
        return error(
            "LLM_NOT_CONFIGURED",
            "LLM 未配置，请先在设置中配置 API Key 后再解析简历",
        )

    # 3. 标记为 parsing 中
    _update_parse_status(req.upload_id, "parsing")

    file_path = settings.files_root / record["file_path"]
    try:
        raw_text = _extract_text(Path(file_path), record["file_type"])
    except Exception as exc:  # noqa: BLE001 - 解析失败需标记 needs_review
        _update_parse_status(req.upload_id, "needs_review")
        return error("PARSE_FAILED", f"文件解析失败: {exc}")

    # 3.5 将简历文本存入知识库（US-12）
    try:
        chunk_count = _index_resume_to_knowledge(
            raw_text,
            record["file_name"],
            req.upload_id,
        )
    except Exception:  # noqa: BLE001 - 知识库存入失败不阻断主流程
        chunk_count = 0

    # 4. LLM 结构化提取（experience/projects/skills 仍用 extractor）
    try:
        extractor = ResumeExtractor(llm_client)
        structured_resume = await extractor.extract(raw_text)
    except Exception as exc:  # noqa: BLE001 - LLM 提取失败需标记 needs_review
        _update_parse_status(req.upload_id, "needs_review")
        return error("EXTRACT_FAILED", f"LLM 结构化提取失败: {exc}")

    # 4.5 从知识库提取个人信息（向量搜索 + LLM），覆盖 extractor 的 basic
    personal_info_data = await _extract_personal_info_from_knowledge()
    if personal_info_data:
        # 用知识库提取的数据覆盖 structured_resume.basic
        contact = personal_info_data.get("contact", {})
        structured_resume.basic.name = contact.get("name") or structured_resume.basic.name
        structured_resume.basic.gender = contact.get("gender") or structured_resume.basic.gender or None
        structured_resume.basic.birth_date = contact.get("birth_date") or structured_resume.basic.birth_date or None
        structured_resume.basic.phone = contact.get("phone") or structured_resume.basic.phone
        structured_resume.basic.email = contact.get("email") or structured_resume.basic.email
        structured_resume.basic.location = contact.get("location") or structured_resume.basic.location
        structured_resume.basic.website = contact.get("website") or structured_resume.basic.website or None
        structured_resume.basic.github = contact.get("github") or structured_resume.basic.github or None
        structured_resume.basic.linkedin = contact.get("linkedin") or structured_resume.basic.linkedin or None

        # 如果知识库提取到教育背景，也覆盖
        edu_list = personal_info_data.get("education", [])
        if edu_list and isinstance(edu_list, list):
            from resume_agent.parsers.extractor import EducationItem
            structured_resume.education = [
                EducationItem(
                    school=e.get("school", ""),
                    degree=e.get("degree", ""),
                    major=e.get("major", ""),
                    period=e.get("period", ""),
                )
                for e in edu_list
                if isinstance(e, dict)
            ]

    # 5. 构建版本树节点
    try:
        builder = TreeBuilder()
        tree_result = builder.build_from_resume(structured_resume)
    except Exception as exc:  # noqa: BLE001 - 版本树构建失败需标记 needs_review
        _update_parse_status(req.upload_id, "needs_review")
        return error("TREE_BUILD_FAILED", f"版本树构建失败: {exc}")

    # 6. 更新状态为成功
    _update_parse_status(req.upload_id, "success")

    data = {
        "upload_id": req.upload_id,
        "structured_resume": structured_resume.model_dump(),
        "tree_node": tree_result["node"],
        "deduplicated": tree_result["deduplicated"],
    }
    return success(data)


@router.get("/list")
def list_resumes() -> dict[str, Any]:
    """列出所有上传记录。

    Returns:
        统一响应 envelope，``data`` 为上传记录列表
        （id、file_name、file_type、parse_status、created_at）。
    """
    with get_connection() as conn:
        records = conn.execute(
            """
            SELECT id, file_name, file_type, file_path, parse_status, created_at
            FROM upload_records
            ORDER BY created_at DESC
            """
        ).fetchall()

    return success(records)


def _update_parse_status(upload_id: str, status: str) -> None:
    """更新上传记录的解析状态。"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE upload_records SET parse_status = ? WHERE id = ?",
            (status, upload_id),
        )


def _index_resume_to_knowledge(
    raw_text: str,
    source_file_name: str,
    upload_id: str,
) -> int:
    """将简历文本存入知识库（分块 + 嵌入 + 写入 Chroma + SQLite）。

    Args:
        raw_text: 简历纯文本。
        source_file_name: 源文件名（用于 metadata）。
        upload_id: 上传记录 ID（用于关联）。

    Returns:
        分块数量。
    """
    from resume_agent.rag.chroma_client import get_knowledge_collection

    chunks = chunk_text(raw_text)
    if not chunks:
        return 0

    collection = get_knowledge_collection()
    chunk_ids: list[str] = []
    chunk_documents: list[str] = []
    chunk_metadatas: list[dict[str, Any]] = []
    sqlite_rows: list[tuple[str, str, str, str, str]] = []
    total = len(chunks)

    for idx, chunk_text_content in enumerate(chunks):
        embedding_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        meta = {
            "upload_id": upload_id,
            "source_file": source_file_name,
            "file_type": "resume",
            "chunk_index": idx,
            "total_chunks": total,
        }
        chunk_ids.append(embedding_id)
        chunk_documents.append(chunk_text_content)
        chunk_metadatas.append(meta)
        sqlite_rows.append(
            (
                chunk_id,
                source_file_name,
                chunk_text_content,
                embedding_id,
                json.dumps(meta, ensure_ascii=False),
            )
        )

    # Chroma 写入
    collection.add(
        ids=chunk_ids,
        documents=chunk_documents,
        metadatas=chunk_metadatas,
    )

    # SQLite 写入
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO knowledge_chunks
                (id, source_file, chunk_text, embedding_id, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            sqlite_rows,
        )

    return len(chunks)


async def _extract_personal_info_from_knowledge() -> dict[str, Any] | None:
    """从知识库向量搜索 + LLM 提取个人信息。

    Returns:
        PersonalInfo dict 或 None（提取失败）。
    """
    from resume_agent.rag.chroma_client import get_knowledge_collection

    collection = get_knowledge_collection()

    # 1. 向量搜索个人信息相关文本
    search_queries = ["姓名 电话 邮箱 地址", "教育背景 学校 学历", "个人简介 自我介绍"]
    all_chunks: list[str] = []
    seen_ids: set[str] = set()

    for query in search_queries:
        try:
            result = collection.query(query_texts=[query], n_results=3)
            ids = result.get("ids", [[]])[0]
            documents = result.get("documents", [[]])[0]
            for idx, doc in enumerate(documents):
                chunk_id = ids[idx] if idx < len(ids) else ""
                if chunk_id and chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    all_chunks.append(doc)
        except Exception:  # noqa: BLE001
            continue

    if not all_chunks:
        return None

    # 2. LLM 提取
    llm = LLMClient()
    if not llm.configured:
        return None

    context = "\n---\n".join(all_chunks[:5])
    system_prompt = """你是信息提取助手。从给定的文本片段中提取个人信息，输出 JSON 对象。
提取以下字段（找不到的留空）：
{
  "contact": { "name": "", "gender": "", "birth_date": "", "phone": "", "email": "", "location": "", "website": "", "github": "", "linkedin": "" },
  "education": [ { "school": "", "degree": "", "major": "", "period": "" } ],
  "summary": ""
}
只输出 JSON，不要输出其他内容。"""

    user_prompt = f"请从以下文本中提取个人信息：\n\n{context}"

    try:
        response = await llm.chat(
            system_prompt=system_prompt,
            user_content=user_prompt,
            response_format_json=True,
        )
    except Exception:  # noqa: BLE001
        return None

    # 3. 解析返回
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                return json.loads(cleaned[first : last + 1])
            except json.JSONDecodeError:
                return None
        return None
