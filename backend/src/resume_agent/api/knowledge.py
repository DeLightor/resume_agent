"""知识库端点：上传、索引、检索、删除、统计。

实现 US-3 知识库 RAG 后端，覆盖以下端点：

- ``POST /api/knowledge/upload``：上传知识素材文件，保存物理文件并创建 upload_records。
- ``POST /api/knowledge/index/{upload_id}``：解析文本 → 分块 → 嵌入 → 写入 Chroma 与 SQLite。
- ``POST /api/knowledge/search``：语义检索知识库切片。
- ``GET /api/knowledge/documents``：列出知识库文档。
- ``DELETE /api/knowledge/documents/{upload_id}``：删除文档及关联切片与物理文件。
- ``GET /api/knowledge/stats``：返回切片数、文档数与索引状态。

对齐 design.md 第 3.4 节。

Note:
    ``settings`` 与 ``get_knowledge_collection`` 均采用延迟导入（函数内导入），
    以确保测试期 ``conftest`` 重置 ``config_module.settings`` 单例后，
    端点代码能读取到最新的配置（避免模块级引用过期）。
"""

from __future__ import annotations

import json
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from resume_agent.api.response import error, success
from resume_agent.db.connection import get_connection
from resume_agent.parsers.docx_parser import extract_text_from_docx
from resume_agent.parsers.pdf_parser import extract_text_from_pdf
from resume_agent.rag.chunker import chunk_text

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# 支持的文件类型
_ALLOWED_FILE_TYPES: tuple[str, ...] = ("pdf", "docx", "md", "txt")


class SearchRequest(BaseModel):
    """语义检索请求体。"""

    query: str
    top_k: int = 5


def _get_file_ext(filename: str | None) -> str | None:
    """从文件名提取小写扩展名（不含点）。"""
    if not filename or "." not in filename:
        return None
    return filename.rsplit(".", 1)[-1].lower()


def _extract_text(file_path: Path, file_type: str) -> str:
    """根据文件类型调用对应解析器提取纯文本。

    Args:
        file_path: 文件绝对路径。
        file_type: 文件扩展名（pdf / docx / md / txt）。

    Returns:
        提取的纯文本。

    Raises:
        ValueError: 不支持的文件类型。
    """
    if file_type == "pdf":
        return extract_text_from_pdf(file_path)
    if file_type == "docx":
        return extract_text_from_docx(file_path)
    if file_type in ("md", "txt"):
        return file_path.read_text(encoding="utf-8")
    raise ValueError(f"不支持的文件类型: {file_type}")


def _update_parse_status(upload_id: str, status: str) -> None:
    """更新 upload_records 的解析状态。"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE upload_records SET parse_status = ? WHERE id = ?",
            (status, upload_id),
        )


def _delete_chunks_for_upload(upload_id: str, conn: Any) -> list[str]:
    """删除指定 upload 关联的 SQLite knowledge_chunks 记录。

    通过 ``metadata_json`` 中的 ``upload_id`` 字段定位切片
    （SQLite ``json_extract`` 支持），避免依赖文件名可能的重复。

    Args:
        upload_id: 上传记录 ID。
        conn: 已打开的 SQLite 连接（不提交，由调用方控制事务）。

    Returns:
        被删除记录的 ``embedding_id`` 列表，供调用方同步删除 Chroma 向量。
    """
    rows: list[dict[str, Any]] = conn.execute(
        "SELECT embedding_id FROM knowledge_chunks "
        "WHERE json_extract(metadata_json, '$.upload_id') = ?",
        (upload_id,),
    ).fetchall()
    embedding_ids = [row["embedding_id"] for row in rows]
    if embedding_ids:
        placeholders = ",".join(["?"] * len(embedding_ids))
        conn.execute(
            f"DELETE FROM knowledge_chunks WHERE embedding_id IN ({placeholders})",  # noqa: S608
            embedding_ids,
        )
    return embedding_ids


@router.post("/upload")
async def upload_knowledge(file: UploadFile) -> dict[str, Any]:
    """上传知识素材文件。

    支持的文件类型：pdf / docx / md / txt。
    文件保存到 ``{files_root}/knowledge/{uuid}.{ext}``，
    并写入 ``upload_records`` 表（``parse_status='pending'``），
    随后自动调用索引逻辑完成解析与嵌入。

    Args:
        file: 上传的文件对象。

    Returns:
        统一响应 envelope，``data`` 含 upload 记录与 ``chunk_count``。
        失败时返回 ``error`` envelope（如不支持的文件类型、索引失败等）。
    """
    from resume_agent.config import settings

    file_ext = _get_file_ext(file.filename)
    if file_ext not in _ALLOWED_FILE_TYPES:
        return error(
            "INVALID_FILE_TYPE",
            f"不支持的文件类型: {file_ext}，仅支持 {list(_ALLOWED_FILE_TYPES)}",
        )

    # 保存文件
    upload_id = str(uuid.uuid4())
    knowledge_dir = settings.files_root / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    saved_filename = f"{upload_id}.{file_ext}"
    saved_path = knowledge_dir / saved_filename
    content = await file.read()
    saved_path.write_bytes(content)

    # 写入 DB（file_path 存储相对路径，相对 files_root）
    relative_path = f"knowledge/{saved_filename}"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO upload_records (id, file_name, file_type, file_path, parse_status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                file.filename or saved_filename,
                file_ext,
                relative_path,
                "pending",
            ),
        )

    record = {
        "upload_id": upload_id,
        "file_name": file.filename or saved_filename,
        "file_type": file_ext,
        "file_path": relative_path,
        "parse_status": "pending",
    }

    # 自动调用索引逻辑
    index_result = _index_upload(upload_id, record)
    if not index_result["ok"]:
        data = {**record, "chunk_count": 0, "index_error": index_result["error"]}
        return success(data)

    data = {
        **record,
        "parse_status": "success",
        "chunk_count": index_result["chunk_count"],
    }
    return success(data)


def _index_upload(upload_id: str, record: dict[str, Any]) -> dict[str, Any]:
    """对指定 upload 执行索引流程（解析 → 分块 → 嵌入 → 写入）。

    供 ``upload_knowledge`` 与 ``index_knowledge`` 复用。
    若该 upload 已存在切片，会先清除旧的 SQLite 与 Chroma 记录再重建，
    保证幂等。

    Args:
        upload_id: 上传记录 ID。
        record: 上传记录字典（含 file_path、file_type 等）。

    Returns:
        ``{"ok": True, "chunk_count": int}`` 或 ``{"ok": False, "error": str}``。
    """
    from resume_agent.config import settings
    from resume_agent.rag.chroma_client import get_knowledge_collection

    file_path = settings.files_root / record["file_path"]
    file_type = record["file_type"]

    # 0. 清除旧切片（幂等：重复索引不会产生重复数据）
    with get_connection() as conn:
        old_embedding_ids = _delete_chunks_for_upload(upload_id, conn)
    if old_embedding_ids:
        with suppress(Exception):  # noqa: BLE001 - 旧向量删除失败不阻断流程
            old_collection = get_knowledge_collection()
            old_collection.delete(ids=old_embedding_ids)

    # 1. 提取文本
    try:
        raw_text = _extract_text(Path(file_path), file_type)
    except Exception as exc:  # noqa: BLE001 - 解析失败需标记 failed
        _update_parse_status(upload_id, "failed")
        return {"ok": False, "error": f"文件解析失败: {exc}"}

    if not raw_text.strip():
        _update_parse_status(upload_id, "failed")
        return {"ok": False, "error": "文件内容为空"}

    # 2. 分块
    chunks = chunk_text(raw_text)
    if not chunks:
        _update_parse_status(upload_id, "failed")
        return {"ok": False, "error": "分块结果为空"}

    # 3. 写入 Chroma（Chroma 自带本地 embedding 模型，无需外部 API）
    _update_parse_status(upload_id, "parsing")
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
            "source_file": record["file_name"],
            "file_type": file_type,
            "chunk_index": idx,
            "total_chunks": total,
        }
        chunk_ids.append(embedding_id)
        chunk_documents.append(chunk_text_content)
        chunk_metadatas.append(meta)
        sqlite_rows.append(
            (
                chunk_id,
                record["file_name"],
                chunk_text_content,
                embedding_id,
                json.dumps(meta, ensure_ascii=False),
            )
        )

    # Chroma 写入（不传 embeddings，让 Chroma 使用默认本地 embedding 模型）
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

    # 5. 更新状态为成功
    _update_parse_status(upload_id, "success")
    return {"ok": True, "chunk_count": len(chunks)}


@router.post("/index/{upload_id}")
def index_knowledge(upload_id: str) -> dict[str, Any]:
    """手动触发知识素材索引。

    Args:
        upload_id: 上传记录 ID。

    Returns:
        统一响应 envelope，``data`` 含 upload_id、status、chunk_count。
    """
    with get_connection() as conn:
        record = conn.execute(
            "SELECT * FROM upload_records WHERE id = ?",
            (upload_id,),
        ).fetchone()

    if record is None:
        return error("UPLOAD_NOT_FOUND", f"上传记录不存在: {upload_id}")

    result = _index_upload(upload_id, record)
    if not result["ok"]:
        return error("INDEX_FAILED", result["error"])

    data = {
        "upload_id": upload_id,
        "status": "success",
        "chunk_count": result["chunk_count"],
    }
    return success(data)


@router.post("/search")
def search_knowledge(req: SearchRequest) -> dict[str, Any]:
    """语义检索知识库。

    Args:
        req: 检索请求，含查询文本与 top_k。

    Returns:
        统一响应 envelope，``data`` 含 query 与 results 列表
        （每项含 chunk_id、source_file、chunk_text、score）。
    """
    from resume_agent.rag.chroma_client import get_knowledge_collection

    if not req.query.strip():
        return error("INVALID_QUERY", "查询文本不能为空")

    collection = get_knowledge_collection()
    try:
        # Chroma 自带本地 embedding，直接传 query_texts 让 Chroma 自己向量化
        query_result = collection.query(
            query_texts=[req.query],
            n_results=req.top_k,
        )
    except Exception as exc:  # noqa: BLE001 - Chroma 查询失败需返回错误
        return error("SEARCH_FAILED", f"向量检索失败: {exc}")

    results: list[dict[str, Any]] = []
    ids_list = query_result.get("ids", [[]])
    documents_list = query_result.get("documents", [[]])
    metadatas_list = query_result.get("metadatas", [[]])
    distances_list = query_result.get("distances", [[]])
    if not ids_list:
        return success({"query": req.query, "results": []})

    ids = ids_list[0] if ids_list else []
    documents = documents_list[0] if documents_list else []
    metadatas = metadatas_list[0] if metadatas_list else []
    distances = distances_list[0] if distances_list else []

    for idx, embedding_id in enumerate(ids):
        doc = documents[idx] if idx < len(documents) else ""
        meta = metadatas[idx] if idx < len(metadatas) else {}
        distance = distances[idx] if idx < len(distances) else 0.0
        source_file = meta.get("source_file", "") if isinstance(meta, dict) else ""
        # Chroma 余弦距离越小越相似，转换为 0-1 的相似度分数
        score = max(0.0, 1.0 - distance) if distance is not None else 0.0
        # 通过 embedding_id 反查 SQLite 拿到 chunk_id 与 chunk_text（权威源）
        chunk_id = ""
        chunk_text_value = doc
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, chunk_text FROM knowledge_chunks WHERE embedding_id = ?",
                (embedding_id,),
            ).fetchone()
        if row is not None:
            chunk_id = row["id"]
            chunk_text_value = row["chunk_text"]
        results.append(
            {
                "chunk_id": chunk_id,
                "source_file": source_file,
                "chunk_text": chunk_text_value,
                "score": score,
            }
        )

    return success({"query": req.query, "results": results})


@router.get("/documents")
def list_documents() -> dict[str, Any]:
    """列出知识库文档。

    仅返回知识库类型的上传记录（即 ``file_path`` 以 ``knowledge/`` 开头）。

    Returns:
        统一响应 envelope，``data`` 为文档列表
        （id、file_name、file_type、file_path、parse_status、created_at）。
    """
    with get_connection() as conn:
        records = conn.execute(
            """
            SELECT id, file_name, file_type, file_path, parse_status, created_at
            FROM upload_records
            WHERE file_path LIKE 'knowledge/%'
            ORDER BY created_at DESC
            """
        ).fetchall()

    return success(records)


@router.delete("/documents/{upload_id}")
def delete_document(upload_id: str) -> dict[str, Any]:
    """删除知识库文档及其切片。

    删除顺序：
    1. SQLite ``knowledge_chunks`` 中关联的切片记录（同时拿到 embedding_id）。
    2. Chroma ``knowledge_chunks`` 集合中对应的向量。
    3. SQLite ``upload_records`` 记录。
    4. 物理文件。

    Args:
        upload_id: 上传记录 ID。

    Returns:
        统一响应 envelope，``data`` 含 upload_id 与删除统计。
    """
    from resume_agent.config import settings
    from resume_agent.rag.chroma_client import get_knowledge_collection

    with get_connection() as conn:
        record = conn.execute(
            "SELECT * FROM upload_records WHERE id = ?",
            (upload_id,),
        ).fetchone()
        if record is None:
            return error("UPLOAD_NOT_FOUND", f"上传记录不存在: {upload_id}")

        # 删除 SQLite knowledge_chunks 并拿到 embedding_id
        embedding_ids = _delete_chunks_for_upload(upload_id, conn)
        # 删除 upload_records
        conn.execute("DELETE FROM upload_records WHERE id = ?", (upload_id,))

    # 删除 Chroma 向量
    if embedding_ids:
        collection = get_knowledge_collection()
        with suppress(Exception):  # noqa: BLE001 - Chroma 删除失败不阻断主流程
            collection.delete(ids=embedding_ids)

    # 删除物理文件
    file_path = settings.files_root / record["file_path"]
    deleted_file = False
    if file_path.exists():
        try:
            file_path.unlink()
            deleted_file = True
        except OSError:
            deleted_file = False

    data = {
        "upload_id": upload_id,
        "deleted_chunks": len(embedding_ids),
        "deleted_file": deleted_file,
    }
    return success(data)


@router.get("/stats")
def get_stats() -> dict[str, Any]:
    """返回知识库统计信息。

    Returns:
        统一响应 envelope，``data`` 含：
        - ``chunk_count``：SQLite knowledge_chunks 表行数。
        - ``document_count``：upload_records 中知识库文档数。
        - ``indexing_status``：聚合状态，``"ready"`` 表示存在已索引切片，
          ``"empty"`` 表示无知识库文档。
    """
    with get_connection() as conn:
        chunk_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM knowledge_chunks"
        ).fetchone()
        doc_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM upload_records
            WHERE file_path LIKE 'knowledge/%'
            """
        ).fetchone()
        success_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM upload_records
            WHERE file_path LIKE 'knowledge/%' AND parse_status = 'success'
            """
        ).fetchone()

    chunk_count = int(chunk_row["cnt"]) if chunk_row else 0
    document_count = int(doc_row["cnt"]) if doc_row else 0
    success_count = int(success_row["cnt"]) if success_row else 0

    indexing_status = "ready" if success_count > 0 else "empty"

    data = {
        "chunk_count": chunk_count,
        "document_count": document_count,
        "indexing_status": indexing_status,
    }
    return success(data)
