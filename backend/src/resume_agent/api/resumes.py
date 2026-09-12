"""简历上传与两阶段解析端点。

实现 US-1 资产冷启动的上传/解析/列表，US-31 parse-confirm-flow 将 parse
改为两阶段：提取（异步任务 + SSE 进度）→ 用户确认 → 入库（建树 + 写知识库）。
对齐 openspec/changes/parse-confirm-flow/design.md。

关键语义：
- 提取结果带字段置信度（parsers/confidence.py，源文本回查）；
- 知识库个人信息不再静默覆盖，结果并存供用户选择；
- 知识库写入推迟到确认之后，错误数据不再污染 RAG。
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

from resume_agent.api.response import error, success
from resume_agent.db.connection import get_connection
from resume_agent.llm.client import LLMClient
from resume_agent.parsers.confidence import compute_confidence
from resume_agent.parsers.docx_parser import extract_text_from_docx
from resume_agent.parsers.extractor import ResumeExtractor, StructuredResume
from resume_agent.parsers.pdf_parser import extract_text_from_pdf
from resume_agent.rag.chunker import chunk_text
from resume_agent.services.tree_builder import TreeBuilder

router = APIRouter(prefix="/resumes", tags=["resumes"])

# 支持的文件类型
_ALLOWED_FILE_TYPES: tuple[str, ...] = ("pdf", "docx")

# 提取任务终态
_TERMINAL_STATUSES: tuple[str, ...] = ("awaiting_confirm", "confirmed", "failed")


@router.delete("/parse/tasks/{task_id}")
def cancel_parse(task_id: str) -> dict[str, Any]:
    """Cancel an unconfirmed parse and remove its upload artifact."""
    with get_connection() as conn:
        task = conn.execute(
            "SELECT p.*, u.file_path FROM parse_tasks p JOIN upload_records u ON u.id = p.upload_id WHERE p.id = ?",
            (task_id,),
        ).fetchone()
        if task is None:
            return error("TASK_NOT_FOUND", f"解析任务不存在: {task_id}")
        if task["status"] == "confirmed":
            return error("TASK_ALREADY_CONFIRMED", "已确认入库的任务不能取消")
        conn.execute("DELETE FROM parse_tasks WHERE id = ?", (task_id,))
        conn.execute("DELETE FROM upload_records WHERE id = ?", (task["upload_id"],))
    _tasks.pop(task_id, None)
    from resume_agent.config import settings
    path = settings.files_root / task["file_path"]
    if path.exists():
        path.unlink()
    return success({"task_id": task_id, "cancelled": True})


class ParseRequest(BaseModel):
    """解析简历请求体。"""

    upload_id: str


class ConfirmRequest(BaseModel):
    """解析确认请求体（US-31）。"""

    structured_resume: dict[str, Any]
    apply_knowledge_personal_info: bool = False
    custom_direction: str | None = None


def _normalize_knowledge_personal_info(value: Any) -> dict[str, Any] | None:
    """Keep optional knowledge suggestions safe for the confirmation UI."""
    if not isinstance(value, dict):
        return None
    raw_contact = value.get("contact")
    if raw_contact is not None and not isinstance(raw_contact, dict):
        return None
    contact: dict[str, str | None] = dict.fromkeys((
            "name", "gender", "birth_date", "phone", "email", "location",
            "website", "github", "linkedin",
        ))
    if isinstance(raw_contact, dict):
        for key in contact:
            item = raw_contact.get(key)
            if isinstance(item, (str, int, float)):
                contact[key] = str(item)
            elif item is not None:
                return None
    raw_education = value.get("education")
    education: list[dict[str, str]] = []
    if raw_education is not None and not isinstance(raw_education, list):
        return None
    if isinstance(raw_education, list):
        for item in raw_education:
            if not isinstance(item, dict):
                return None
            education.append({
                key: str(item[key])
                for key in ("school", "degree", "major", "period")
                if isinstance(item.get(key), (str, int, float))
            })
    summary = value.get("summary")
    return {
        "contact": contact,
        "education": education,
        "summary": str(summary) if isinstance(summary, (str, int, float)) else "",
    }


class _TaskState:
    """进程内解析任务的内存事件缓冲（线程写，SSE 读）。"""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)


# 进程内任务注册表：task_id → state。服务重启后清空，
# 详情端点对「extracting 但不在注册表」的孤儿任务按失败处理。
_tasks: dict[str, _TaskState] = {}


def _get_file_ext(filename: str | None) -> str | None:
    """从文件名提取小写扩展名（不含点）。"""
    if not filename or "." not in filename:
        return None
    return filename.rsplit(".", 1)[-1].lower()


def _extract_text(file_path: Path, file_type: str) -> tuple[str, str, bool]:
    """根据文件类型调用解析器提取纯文本。

    优先 MinerU 云端解析；未配置或失败时降级本地解析器并标记 degraded。

    Returns:
        ``(raw_text, parser_used, degraded)`` 三元组，
        ``parser_used`` 为 "mineru" 或 "local"。

    Raises:
        ValueError: 不支持的文件类型。
    """
    from resume_agent.config import settings

    if settings.mineru_api_token:
        try:
            from resume_agent.parsers.mineru_client import MinerUClient

            client = MinerUClient(
                token=settings.mineru_api_token,
                base_url=settings.mineru_api_base,
            )
            md_text = client.upload_and_parse(file_path)
            if md_text and md_text.strip():
                return md_text, "mineru", False
        except Exception:  # noqa: BLE001 - MinerU 任何失败都降级本地解析器
            pass

    if file_type == "pdf":
        return extract_text_from_pdf(file_path), "local", bool(settings.mineru_api_token)
    if file_type == "docx":
        return extract_text_from_docx(file_path), "local", bool(settings.mineru_api_token)
    raise ValueError(f"不支持的文件类型: {file_type}")


@router.post("/upload")
async def upload_resume(file: UploadFile) -> dict[str, Any]:
    """上传简历文件。

    验证文件扩展名（pdf/docx），保存到 ``{files_root}/resumes/{uuid}.{ext}``，
    并写入 ``upload_records`` 表。
    """
    file_ext = _get_file_ext(file.filename)
    if file_ext not in _ALLOWED_FILE_TYPES:
        return error(
            "INVALID_FILE_TYPE",
            f"不支持的文件类型: {file_ext}，仅支持 {list(_ALLOWED_FILE_TYPES)}",
        )

    # 延迟导入 settings：测试期 conftest 会重置 config 模块的 settings 单例，
    # 此处每次调用都读取最新引用，避免持有过期实例（对齐 connection.py 惯例）。
    from resume_agent.config import settings

    upload_id = str(uuid.uuid4())
    resumes_dir = settings.files_root / "resumes"
    resumes_dir.mkdir(parents=True, exist_ok=True)
    saved_filename = f"{upload_id}.{file_ext}"
    saved_path = resumes_dir / saved_filename
    content = await file.read()
    saved_path.write_bytes(content)

    # file_path 存相对路径（POSIX 分隔符保证跨平台一致）
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
async def start_parse(req: ParseRequest) -> dict[str, Any]:
    """启动异步解析任务（两阶段第一步）。

    创建 ``parse_tasks`` 记录并在后台线程执行提取（文件解析 → LLM 结构化 →
    置信度 → 知识库个人信息提取），立即返回 ``task_id``。进度通过
    ``GET /parse/tasks/{id}/events``（SSE）或详情端点轮询获取。
    确认入库见 ``confirm_parse``。同 upload_id 存在进行中的任务时幂等返回。

    Args:
        req: 解析请求，含上传记录 ID。
    """
    with get_connection() as conn:
        record = conn.execute(
            "SELECT * FROM upload_records WHERE id = ?",
            (req.upload_id,),
        ).fetchone()

    if record is None:
        return error("UPLOAD_NOT_FOUND", f"上传记录不存在: {req.upload_id}")

    llm_client = LLMClient()
    if not llm_client.configured:
        return error(
            "LLM_NOT_CONFIGURED",
            "LLM 未配置，请先在设置中配置 API Key 后再解析简历",
        )

    # 幂等：进行中（extracting/awaiting_confirm）的任务直接返回
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id, status FROM parse_tasks
            WHERE upload_id = ? AND status IN ('extracting', 'awaiting_confirm')
            ORDER BY created_at DESC LIMIT 1
            """,
            (req.upload_id,),
        ).fetchone()
    if existing is not None:
        existing = _get_task_row(existing["id"])
    if existing is not None and existing["status"] != "failed":
        return success({"task_id": existing["id"], "status": existing["status"]})

    task_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO parse_tasks (id, upload_id, status) VALUES (?, ?, 'extracting')",
            (task_id, req.upload_id),
        )
        conn.execute(
            "UPDATE upload_records SET parse_status = 'parsing' WHERE id = ?",
            (req.upload_id,),
        )

    state = _TaskState()
    _tasks[task_id] = state
    thread = threading.Thread(
        target=_run_parse_task,
        args=(task_id, req.upload_id, dict(record)),
        daemon=True,
        name=f"parse-task-{task_id[:8]}",
    )
    thread.start()

    return success({"task_id": task_id, "status": "extracting"})


def _run_parse_task(task_id: str, upload_id: str, record: dict[str, Any]) -> None:
    """后台线程执行提取流水线（不触碰版本树与知识库）。

    文件解析（MinerU 优先，失败降级本地）→ LLM 结构化提取 → 置信度计算 →
    知识库个人信息提取（不覆盖，仅并存）→ parse_tasks 落库 awaiting_confirm。
    """
    state = _tasks.get(task_id)
    if state is None:  # 理论不可达，防御
        state = _TaskState()
        _tasks[task_id] = state

    try:
        state.emit({"type": "status", "task_id": task_id, "status": "extracting"})

        llm_client = LLMClient()
        if not llm_client.configured:
            raise RuntimeError("LLM 未配置，请先在设置中配置 API Key 后再解析简历")

        from resume_agent.config import settings

        file_path = settings.files_root / record["file_path"]
        raw_text, parser_used, degraded = _extract_text(Path(file_path), record["file_type"])
        state.emit(
            {
                "type": "file_parsed",
                "parser_used": parser_used,
                "degraded": degraded,
            }
        )

        state.emit({"type": "extracting"})
        extractor = ResumeExtractor(llm_client)
        structured_resume = asyncio.run(extractor.extract(raw_text))

        confidence = compute_confidence(structured_resume, raw_text)

        personal_info_data = _normalize_knowledge_personal_info(
            asyncio.run(_extract_personal_info_from_knowledge())
        )

        result_json = json.dumps(
            {
                "structured_resume": structured_resume.model_dump(),
                "confidence": confidence,
            },
            ensure_ascii=False,
        )
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE parse_tasks
                SET status = 'awaiting_confirm', raw_text = ?, parser_used = ?,
                    degraded = ?, result_json = ?, knowledge_personal_json = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    raw_text,
                    parser_used,
                    1 if degraded else 0,
                    result_json,
                    json.dumps(personal_info_data, ensure_ascii=False)
                    if personal_info_data
                    else None,
                    task_id,
                ),
            )

        state.emit({"type": "done", "task_id": task_id})
    except Exception as exc:  # noqa: BLE001 - 后台任务兜底：失败落库 + 事件通知
        message = str(exc)
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE parse_tasks
                SET status = 'failed', error = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (message, task_id),
            )
            conn.execute(
                "UPDATE upload_records SET parse_status = 'needs_review' WHERE id = ?",
                (upload_id,),
            )
        state.emit({"type": "error", "message": message})
    finally:
        _tasks.pop(task_id, None)


@router.get("/parse/tasks/{task_id}")
def get_parse_task(task_id: str) -> dict[str, Any]:
    """查询解析任务详情（轮询兜底）。

    服务重启后内存任务丢失：``extracting`` 状态但不在注册表中的孤儿任务
    按失败返回，前端可重新发起解析。
    """
    row = _get_task_row(task_id)
    if row is None:
        return error("TASK_NOT_FOUND", f"解析任务不存在: {task_id}")
    status = row["status"]

    result = json.loads(row["result_json"]) if row["result_json"] else {}
    try:
        raw_knowledge = json.loads(row["knowledge_personal_json"]) if row["knowledge_personal_json"] else None
    except json.JSONDecodeError:
        raw_knowledge = None
    knowledge_personal = _normalize_knowledge_personal_info(raw_knowledge)

    return success(
        {
            "task_id": task_id,
            "upload_id": row["upload_id"],
            "status": status,
            "parser_used": row["parser_used"],
            "degraded": bool(row["degraded"]),
            "structured_resume": result.get("structured_resume"),
            "confidence": result.get("confidence"),
            "knowledge_personal_info": knowledge_personal,
            "error": row["error"],
        }
    )


@router.get("/parse/tasks/{task_id}/events")
async def stream_parse_events(task_id: str) -> StreamingResponse:
    """SSE 推送解析任务进度事件。

    事件类型：``status`` / ``file_parsed`` / ``extracting`` / ``done`` / ``error``。
    连接建立时任务已终态（或服务重启后内存任务丢失）→ 从 DB 合成事件序列
    补发后关闭，保证不丢事件。
    """
    return StreamingResponse(
        _parse_event_stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: dict[str, Any]) -> str:
    """格式化一条 SSE 数据帧（event/data 双行，对齐 agent.py 协议）。"""
    return (
        f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
    )


async def _parse_event_stream(task_id: str):  # type: ignore[no-untyped-def]
    """解析任务的事件流生成器。"""
    row = _get_task_row(task_id)

    if row is None:
        yield _sse({"type": "error", "message": f"解析任务不存在: {task_id}"})
        return

    state = _tasks.get(task_id)
    if state is None:
        row = _get_task_row(task_id)
        if row is None:
            yield _sse({"type": "error", "message": "解析任务不存在"})
            return
        # 任务不在内存（已结束被清理 / 服务重启）：从 DB 状态合成重放
        yield _sse({"type": "status", "task_id": task_id, "status": "extracting"})
        if row["status"] in ("awaiting_confirm", "confirmed"):
            yield _sse(
                {
                    "type": "file_parsed",
                    "parser_used": row["parser_used"] or "local",
                    "degraded": bool(row["degraded"]),
                }
            )
            yield _sse({"type": "extracting"})
            yield _sse({"type": "done", "task_id": task_id})
        elif row["status"] == "failed":
            yield _sse({"type": "error", "message": row["error"] or "解析任务失败"})
        else:
            yield _sse({"type": "error", "message": "服务重启导致任务中断，请重新发起解析"})
        return

    sent = 0
    while True:
        events = state.snapshot()
        while sent < len(events):
            yield _sse(events[sent])
            sent += 1

        row = _get_task_row(task_id)
        db_status = row["status"] if row else None
        has_terminal_event = any(e.get("type") in ("done", "error") for e in events)
        if db_status in _TERMINAL_STATUSES and has_terminal_event:
            break
        if db_status in _TERMINAL_STATUSES:
            # DB terminal state can precede the worker's last event by one poll.
            if db_status == "failed":
                yield _sse({"type": "error", "message": row["error"] or "解析任务失败"})
            else:
                yield _sse({"type": "done", "task_id": task_id})
            break
        await asyncio.sleep(0.1)


def _get_task_row(task_id: str) -> dict[str, Any] | None:
    """读取 parse_tasks 行（dict 形式）。"""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM parse_tasks WHERE id = ?", (task_id,)).fetchone()
        if row and row["status"] == "extracting" and task_id not in _tasks:
            message = "服务重启导致任务中断，请重新发起解析"
            changed = conn.execute(
                "UPDATE parse_tasks SET status='failed', error=?, updated_at=datetime('now') "
                "WHERE id=? AND status='extracting'",
                (message, task_id),
            ).rowcount
            if changed:
                conn.execute(
                    "UPDATE upload_records SET parse_status='needs_review' WHERE id=?",
                    (row["upload_id"],),
                )
            row = conn.execute("SELECT * FROM parse_tasks WHERE id=?", (task_id,)).fetchone()
    return dict(row) if row is not None else None


@router.post("/parse/tasks/{task_id}/confirm")
async def confirm_parse(task_id: str, req: ConfirmRequest) -> dict[str, Any]:
    """确认解析结果并入库（两阶段第二步）。

    服务端对提交数据重新校验（不信任客户端原样落库）；按用户选择决定是否
    用知识库个人信息覆盖；随后建版本树节点、将确认后的结构化内容写入知识库——
    确认后的数据才进入 RAG。

    Returns:
        与旧同步 parse 成功响应同形状：structured_resume / tree_node / deduplicated。
    """
    with get_connection() as conn:
        task = conn.execute("SELECT * FROM parse_tasks WHERE id = ?", (task_id,)).fetchone()

    if task is None:
        return error("TASK_NOT_FOUND", f"解析任务不存在: {task_id}")
    if task["status"] == "confirmed":
        return error("TASK_ALREADY_CONFIRMED", "该任务已确认入库，请勿重复提交")
    if task["status"] == "failed":
        return error("TASK_FAILED", f"解析任务已失败: {task['error']}")
    if task["status"] == "extracting":
        return error("TASK_NOT_READY", "解析尚未完成，请稍后再确认")

    try:
        structured_resume = StructuredResume.model_validate(req.structured_resume)
        if req.custom_direction and req.custom_direction.strip():
            structured_resume.primary_direction = req.custom_direction.strip()[:80]
    except ValidationError as exc:
        return error("INVALID_STRUCTURED_RESUME", f"提交的结构化简历不符合规范: {exc}")

    # 用户选择覆盖 → 应用知识库个人信息
    if req.apply_knowledge_personal_info and task["knowledge_personal_json"]:
        try:
            personal_info_data = json.loads(task["knowledge_personal_json"])
            _apply_personal_info_override(structured_resume, personal_info_data)
            structured_resume = StructuredResume.model_validate(
                structured_resume.model_dump(warnings=False)
            )
        except (ValueError, TypeError, AttributeError):
            return error(
                "INVALID_KNOWLEDGE_PERSONAL_INFO", "知识库个人信息格式有误，请取消覆盖后确认"
            )

    # 建版本树节点
    try:
        builder = TreeBuilder()
        tree_result = builder.build_from_resume(structured_resume)
    except Exception as exc:  # noqa: BLE001 - 建树失败标记 needs_review
        with get_connection() as conn:
            conn.execute(
                "UPDATE upload_records SET parse_status = 'needs_review' WHERE id = ?",
                (task["upload_id"],),
            )
        return error("TREE_BUILD_FAILED", f"版本树构建失败: {exc}")

    # 确认后才写知识库（US-31：错误数据不进 RAG）
    chunk_count = 0
    knowledge_warning = None
    try:
        with get_connection() as conn:
            upload = conn.execute(
                "SELECT file_name FROM upload_records WHERE id = ?",
                (task["upload_id"],),
            ).fetchone()
        if upload is not None:
            chunk_count = _index_resume_to_knowledge(
                structured_resume.model_dump_json(indent=2), upload["file_name"], task["upload_id"]
            )
    except Exception:  # noqa: BLE001 - 知识库存入失败不阻断主流程
        chunk_count = 0
        knowledge_warning = "简历已保存到版本树，但知识库索引失败。"

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE parse_tasks
            SET status = 'confirmed', result_json = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                json.dumps(
                    {
                        "structured_resume": structured_resume.model_dump(),
                        "confidence": compute_confidence(structured_resume, task["raw_text"] or ""),
                    },
                    ensure_ascii=False,
                ),
                task_id,
            ),
        )
        conn.execute(
            "UPDATE upload_records SET parse_status = 'success' WHERE id = ?",
            (task["upload_id"],),
        )
        conn.execute(
            "UPDATE upload_records SET direction = ? WHERE id = ?",
            (structured_resume.primary_direction, task["upload_id"]),
        )

    _tasks.pop(task_id, None)

    data = {
        "upload_id": task["upload_id"],
        "structured_resume": structured_resume.model_dump(),
        "tree_node": tree_result["node"],
        "deduplicated": tree_result["deduplicated"],
        "knowledge_chunks": chunk_count,
        "knowledge_warning": knowledge_warning,
    }
    return success(data)


def _apply_personal_info_override(
    structured_resume: StructuredResume, personal_info_data: dict[str, Any]
) -> None:
    """用知识库个人信息覆盖提取结果的 basic 与 education（用户显式选择后调用）。"""
    contact = personal_info_data.get("contact", {})
    structured_resume.basic.name = contact.get("name") or structured_resume.basic.name
    structured_resume.basic.gender = contact.get("gender") or structured_resume.basic.gender or None
    structured_resume.basic.birth_date = (
        contact.get("birth_date") or structured_resume.basic.birth_date or None
    )
    structured_resume.basic.phone = contact.get("phone") or structured_resume.basic.phone
    structured_resume.basic.email = contact.get("email") or structured_resume.basic.email
    structured_resume.basic.location = contact.get("location") or structured_resume.basic.location
    structured_resume.basic.website = (
        contact.get("website") or structured_resume.basic.website or None
    )
    structured_resume.basic.github = contact.get("github") or structured_resume.basic.github or None
    structured_resume.basic.linkedin = (
        contact.get("linkedin") or structured_resume.basic.linkedin or None
    )

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


@router.get("/list")
def list_resumes() -> dict[str, Any]:
    """列出所有上传简历记录（排除纯知识素材文件）。"""
    with get_connection() as conn:
        records = conn.execute(
            """
            SELECT id, file_name, file_type, file_path, parse_status, direction, created_at
            FROM upload_records
            WHERE file_path LIKE 'resumes/%'
            ORDER BY created_at DESC
            """
        ).fetchall()

    return success(records)


@router.delete("/uploads/{upload_id}")
def delete_uploaded_resume(upload_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT file_path FROM upload_records WHERE id = ?", (upload_id,)).fetchone()
        if row is None:
            return error("UPLOAD_NOT_FOUND", f"上传记录不存在: {upload_id}")
        ids = [r["embedding_id"] for r in conn.execute(
            "SELECT embedding_id FROM knowledge_chunks WHERE json_extract(metadata_json, '$.upload_id') = ?",
            (upload_id,),
        ).fetchall()]
        conn.execute("DELETE FROM knowledge_chunks WHERE json_extract(metadata_json, '$.upload_id') = ?", (upload_id,))
        conn.execute("DELETE FROM upload_records WHERE id = ?", (upload_id,))
    if ids:
        try:
            from resume_agent.rag.chroma_client import get_knowledge_collection
            get_knowledge_collection().delete(ids=ids)
        except Exception:
            pass
    from resume_agent.config import settings
    path = settings.files_root / row["file_path"]
    if path.exists():
        path.unlink()
    return success({"upload_id": upload_id, "deleted": True})


def _index_resume_to_knowledge(
    raw_text: str,
    source_file_name: str,
    upload_id: str,
) -> int:
    """将简历文本存入知识库（分块 + 嵌入 + 写入 Chroma + SQLite）。

    US-31 起仅在用户确认后调用。

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

    collection.add(
        ids=chunk_ids,
        documents=chunk_documents,
        metadatas=chunk_metadatas,
    )

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
    """从知识库向量搜索 + LLM 提取个人信息（并存展示，不静默覆盖）。"""
    from resume_agent.rag.chroma_client import get_knowledge_collection

    collection = get_knowledge_collection()

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

    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        return _normalize_knowledge_personal_info(json.loads(cleaned))
    except json.JSONDecodeError:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                return _normalize_knowledge_personal_info(json.loads(cleaned[first : last + 1]))
            except json.JSONDecodeError:
                return None
        return None
