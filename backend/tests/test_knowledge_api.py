"""知识库 RAG API 集成测试。

覆盖：
- chunker 单元测试
- 上传 md/txt 文件
- 索引流程（Chroma 自带本地 embedding，无需 mock）
- 语义检索
- 文档列表
- 删除文档
- 不支持的文件类型
- 空文件
- 统计端点

使用 conftest.py 的 ``_isolated_env`` fixture 隔离存储。
Chroma 默认使用 all-MiniLM-L6-v2 本地模型，无需外部 API。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from resume_agent.db.connection import get_connection
from resume_agent.db.init_db import init_database
from resume_agent.rag.chunker import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    chunk_text,
)

# === 辅助函数 ===


def _init_db() -> None:
    """初始化隔离环境下的数据库并重置 Chroma 客户端单例。

    conftest 的 ``_isolated_env`` fixture 会重置 ``config_module.settings``，
    但 ``chroma_client._client`` 单例不会自动重置，导致跨测试数据泄漏。
    此处显式重置，确保每个测试都使用全新的 Chroma 实例与临时路径。
    """
    from resume_agent.config import settings
    from resume_agent.rag.chroma_client import reset_client

    reset_client()
    init_database(settings.sqlite_path)


# === chunker 单元测试 ===


def test_chunk_text_empty_returns_empty_list() -> None:
    """空文本返回空列表。"""
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    assert chunk_text("\n\n  \t") == []


def test_chunk_text_short_returns_single_element() -> None:
    """短文本返回单元素列表。"""
    text = "这是一段短文本。"
    result = chunk_text(text)
    assert len(result) == 1
    assert result[0] == text


def test_chunk_text_exact_chunk_size() -> None:
    """文本长度等于 chunk_size 时返回单元素。"""
    text = "a" * CHUNK_SIZE
    result = chunk_text(text)
    assert len(result) == 1
    assert result[0] == text


def test_chunk_text_long_text_multiple_chunks() -> None:
    """长文本应切分为多个切片。"""
    text = "a" * (CHUNK_SIZE * 3)
    result = chunk_text(text)
    assert len(result) >= 3
    # 每个切片长度不超过 chunk_size
    for chunk in result:
        assert len(chunk) <= CHUNK_SIZE


def test_chunk_text_overlap_present() -> None:
    """相邻切片应存在重叠。"""
    # 构造足够长的文本，内容可区分位置
    text = "".join(str(i % 10) for i in range(CHUNK_SIZE * 2))
    result = chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    assert len(result) >= 2
    # 第一个切片的末尾应出现在第二个切片的开头（重叠部分）
    overlap_part = result[0][-CHUNK_OVERLAP:]
    assert result[1].startswith(overlap_part)


def test_chunk_text_custom_params() -> None:
    """支持自定义 chunk_size 与 overlap。"""
    text = "abcdefghij" * 10  # 100 chars
    chunks = chunk_text(text, chunk_size=20, overlap=5)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 20


def test_chunk_text_invalid_params() -> None:
    """非法参数抛出 ValueError。"""
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("hello", chunk_size=0)
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("hello", chunk_size=-1)
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("hello", chunk_size=10, overlap=10)
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("hello", chunk_size=10, overlap=-1)


def test_chunk_text_strips_whitespace() -> None:
    """文本前后空白被剥离。"""
    text = "  hello world  "
    result = chunk_text(text)
    assert result == ["hello world"]


def test_chunk_text_default_constants() -> None:
    """默认常量为 512 / 50。"""
    assert CHUNK_SIZE == 512
    assert CHUNK_OVERLAP == 50


# === 上传端点测试 ===


def test_upload_md_file_creates_record(tmp_path: Path) -> None:
    """上传 md 文件应保存文件、创建记录并自动索引。"""
    _init_db()
    from resume_agent.config import settings
    from resume_agent.main import app

    client = TestClient(app)
    md_content = "# 知识库文档\n\n这是第一段内容。\n\n这是第二段内容。"
    response = client.post(
        "/api/knowledge/upload",
        files={"file": ("notes.md", md_content.encode("utf-8"), "text/markdown")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["file_type"] == "md"
    assert data["parse_status"] == "success"
    assert data["chunk_count"] >= 1

    # 验证文件已保存
    saved_path = settings.files_root / data["file_path"]
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == md_content

    # 验证 DB 记录
    upload_id = data["upload_id"]
    with get_connection() as conn:
        record = conn.execute(
            "SELECT * FROM upload_records WHERE id = ?", (upload_id,)
        ).fetchone()
    assert record is not None
    assert record["file_name"] == "notes.md"
    assert record["file_type"] == "md"
    assert record["parse_status"] == "success"


def test_upload_txt_file_creates_record() -> None:
    """上传 txt 文件应保存并索引。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    txt_content = "这是一段纯文本知识素材，用于测试 txt 上传。"
    response = client.post(
        "/api/knowledge/upload",
        files={"file": ("notes.txt", txt_content.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["file_type"] == "txt"
    assert body["data"]["parse_status"] == "success"
    assert body["data"]["chunk_count"] >= 1


def test_upload_rejects_unsupported_file_type() -> None:
    """上传不支持的文件类型应返回错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post(
        "/api/knowledge/upload",
        files={"file": ("file.xlsx", b"fake", "application/vnd.ms-excel")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_FILE_TYPE"


def test_upload_empty_file_returns_index_error() -> None:
    """空文件上传后索引应失败（内容为空）。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post(
        "/api/knowledge/upload",
        files={"file": ("empty.md", b"", "text/markdown")},
    )

    assert response.status_code == 200
    body = response.json()
    # 上传本身成功，但索引失败
    assert body["ok"] is True
    data = body["data"]
    assert data["chunk_count"] == 0
    assert "index_error" in data

    # 验证 parse_status 为 failed
    upload_id = data["upload_id"]
    with get_connection() as conn:
        record = conn.execute(
            "SELECT parse_status FROM upload_records WHERE id = ?", (upload_id,)
        ).fetchone()
    assert record["parse_status"] == "failed"


# === 索引端点测试 ===


def test_index_endpoint_triggers_full_flow() -> None:
    """手动索引端点应完成解析 → 分块 → 写入流程。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    md_content = "# 测试文档\n\n" + "内容段落。\n" * 20
    upload_resp = client.post(
        "/api/knowledge/upload",
        files={"file": ("doc.md", md_content.encode("utf-8"), "text/markdown")},
    )
    upload_id = upload_resp.json()["data"]["upload_id"]

    # 手动再次触发索引（测试幂等性）
    response = client.post(f"/api/knowledge/index/{upload_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["upload_id"] == upload_id
    assert data["status"] == "success"
    assert data["chunk_count"] >= 1

    # 验证 knowledge_chunks 表有记录
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_chunks WHERE source_file = ?", ("doc.md",)
        ).fetchall()
    assert len(rows) == data["chunk_count"]

    # 验证 Chroma 集合有向量
    from resume_agent.rag.chroma_client import get_knowledge_collection

    collection = get_knowledge_collection()
    assert collection.count() >= data["chunk_count"]


def test_index_returns_error_for_unknown_upload() -> None:
    """不存在的 upload_id 应返回错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post("/api/knowledge/index/nonexistent-uuid")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "UPLOAD_NOT_FOUND"


# === 检索端点测试 ===


def test_search_returns_results() -> None:
    """检索应返回相关切片。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    md_content = "# RAG 知识库\n\n这是关于向量检索的知识素材。\n\nChroma 是嵌入式向量库。"
    client.post(
        "/api/knowledge/upload",
        files={"file": ("rag-notes.md", md_content.encode("utf-8"), "text/markdown")},
    )

    response = client.post(
        "/api/knowledge/search",
        json={"query": "向量检索", "top_k": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["query"] == "向量检索"
    assert isinstance(data["results"], list)
    assert len(data["results"]) >= 1
    result = data["results"][0]
    assert "chunk_id" in result
    assert "source_file" in result
    assert "chunk_text" in result
    assert "score" in result
    assert result["source_file"] == "rag-notes.md"


def test_search_rejects_empty_query() -> None:
    """空查询应返回错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post(
        "/api/knowledge/search",
        json={"query": "  ", "top_k": 5},
    )
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_QUERY"


def test_search_returns_empty_when_no_documents() -> None:
    """无知识库文档时检索返回空结果。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post(
        "/api/knowledge/search",
        json={"query": "测试查询", "top_k": 5},
    )
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["results"] == []


# === 文档列表端点测试 ===


def test_documents_returns_knowledge_records() -> None:
    """文档列表应只返回知识库文档（非简历）。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    # 上传两个知识库文档
    for name in ("doc1.md", "doc2.txt"):
        client.post(
            "/api/knowledge/upload",
            files={
                "file": (
                    name,
                    f"内容 {name}".encode(),
                    "text/plain",
                )
            },
        )

    # 手动插入一条简历类型的 upload_record（不应出现在知识库列表）
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO upload_records (id, file_name, file_type, file_path, parse_status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("fake-resume-id", "resume.pdf", "pdf", "resumes/fake.pdf", "success"),
        )

    response = client.get("/api/knowledge/documents")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    records = body["data"]
    assert len(records) == 2
    for r in records:
        assert r["file_path"].startswith("knowledge/")


def test_documents_empty_when_no_uploads() -> None:
    """无知识库文档时返回空列表。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.get("/api/knowledge/documents")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"] == []


# === 删除端点测试 ===


def test_delete_removes_chunks_and_file() -> None:
    """删除应移除 SQLite 切片、Chroma 向量、upload_records 与物理文件。"""
    _init_db()
    from resume_agent.config import settings
    from resume_agent.main import app
    from resume_agent.rag.chroma_client import get_knowledge_collection

    client = TestClient(app)
    md_content = "# 待删除文档\n\n内容段落一。\n\n内容段落二。"
    upload_resp = client.post(
        "/api/knowledge/upload",
        files={"file": ("to-delete.md", md_content.encode("utf-8"), "text/markdown")},
    )
    upload_id = upload_resp.json()["data"]["upload_id"]
    chunk_count = upload_resp.json()["data"]["chunk_count"]
    assert chunk_count >= 1

    # 记录文件路径与 Chroma 数量
    with get_connection() as conn:
        record = conn.execute(
            "SELECT file_path FROM upload_records WHERE id = ?", (upload_id,)
        ).fetchone()
    file_path = settings.files_root / record["file_path"]
    assert file_path.exists()
    collection = get_knowledge_collection()
    chroma_count_before = collection.count()

    # 执行删除
    response = client.delete(f"/api/knowledge/documents/{upload_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["deleted_chunks"] == chunk_count
    assert data["deleted_file"] is True

    # 验证 SQLite 切片已删除
    with get_connection() as conn:
        chunks = conn.execute(
            "SELECT * FROM knowledge_chunks "
            "WHERE json_extract(metadata_json, '$.upload_id') = ?",
            (upload_id,),
        ).fetchall()
    assert len(chunks) == 0

    # 验证 upload_records 已删除
    with get_connection() as conn:
        rec = conn.execute(
            "SELECT * FROM upload_records WHERE id = ?", (upload_id,)
        ).fetchone()
    assert rec is None

    # 验证物理文件已删除
    assert not file_path.exists()

    # 验证 Chroma 向量已删除
    assert collection.count() < chroma_count_before


def test_delete_returns_error_for_unknown_upload() -> None:
    """删除不存在的 upload_id 应返回错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.delete("/api/knowledge/documents/nonexistent-uuid")
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "UPLOAD_NOT_FOUND"


# === 统计端点测试 ===


def test_stats_empty_when_no_documents() -> None:
    """无文档时统计应为 0 与 empty。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.get("/api/knowledge/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["chunk_count"] == 0
    assert data["document_count"] == 0
    assert data["indexing_status"] == "empty"


def test_stats_returns_counts_after_index() -> None:
    """索引后统计应反映切片数与文档数。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    md_content = "# 统计测试\n\n" + "段落内容。\n" * 30
    upload_resp = client.post(
        "/api/knowledge/upload",
        files={"file": ("stats.md", md_content.encode("utf-8"), "text/markdown")},
    )
    chunk_count = upload_resp.json()["data"]["chunk_count"]

    response = client.get("/api/knowledge/stats")
    body = response.json()
    data = body["data"]
    assert data["chunk_count"] == chunk_count
    assert data["document_count"] == 1
    assert data["indexing_status"] == "ready"


# === 端到端流程测试 ===


def test_full_workflow_upload_search_delete() -> None:
    """端到端：上传 → 检索 → 删除。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)

    # 1. 上传
    md_content = "# 端到端测试\n\n这是关于 FastAPI 的知识素材。\n\nChroma 用于向量检索。"
    upload_resp = client.post(
        "/api/knowledge/upload",
        files={"file": ("e2e.md", md_content.encode("utf-8"), "text/markdown")},
    )
    upload_id = upload_resp.json()["data"]["upload_id"]
    assert upload_resp.json()["data"]["chunk_count"] >= 1

    # 2. 检索
    search_resp = client.post(
        "/api/knowledge/search",
        json={"query": "FastAPI", "top_k": 3},
    )
    assert search_resp.status_code == 200
    search_body = search_resp.json()
    assert search_body["ok"] is True
    assert len(search_body["data"]["results"]) >= 1

    # 3. 文档列表
    docs_resp = client.get("/api/knowledge/documents")
    assert docs_resp.status_code == 200
    assert len(docs_resp.json()["data"]) == 1

    # 4. 统计
    stats_resp = client.get("/api/knowledge/stats")
    assert stats_resp.json()["data"]["document_count"] == 1

    # 5. 删除
    del_resp = client.delete(f"/api/knowledge/documents/{upload_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    # 6. 验证已清空
    docs_after = client.get("/api/knowledge/documents").json()["data"]
    assert len(docs_after) == 0
    stats_after = client.get("/api/knowledge/stats").json()["data"]
    assert stats_after["chunk_count"] == 0
    assert stats_after["document_count"] == 0


# === OpenAIEmbedding 单元测试 ===


def test_embedding_embed_texts_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """embed_texts 应正确分批调用 OpenAI 接口。"""
    from resume_agent.rag.embeddings import OpenAIEmbedding

    embedder = OpenAIEmbedding(api_key="sk-test")

    # mock OpenAI 客户端
    call_count = {"value": 0}

    def fake_create(model: str, input: list[str]) -> Any:
        call_count["value"] += 1
        response = type(
            "Response",
            (),
            {
                "data": [
                    type(
                        "Item",
                        (),
                        {"index": i, "embedding": [0.1] * 8},
                    )()
                    for i in range(len(input))
                ]
            },
        )()
        return response

    mock_client = type("Client", (), {})()
    mock_client.embeddings = type("Embeddings", (), {})()
    mock_client.embeddings.create = fake_create

    monkeypatch.setattr(embedder, "_build_client", lambda: mock_client)

    # 测试单批（< 100）
    texts = [f"文本 {i}" for i in range(50)]
    result = embedder.embed_texts(texts)
    assert len(result) == 50
    assert all(len(vec) == 8 for vec in result)
    assert call_count["value"] == 1

    # 测试多批（> 100）
    call_count["value"] = 0
    texts = [f"文本 {i}" for i in range(250)]
    result = embedder.embed_texts(texts)
    assert len(result) == 250
    # 250 / 100 = 3 批
    assert call_count["value"] == 3


def test_embedding_raises_on_empty_input() -> None:
    """空列表应抛出 ValueError。"""
    from resume_agent.rag.embeddings import OpenAIEmbedding

    embedder = OpenAIEmbedding(api_key="sk-test")
    with pytest.raises(ValueError, match="不能为空"):
        embedder.embed_texts([])


def test_embedding_raises_when_not_configured() -> None:
    """未配置 API Key 应抛出 RuntimeError。"""
    from resume_agent.rag.embeddings import OpenAIEmbedding

    embedder = OpenAIEmbedding(api_key="")
    with pytest.raises(RuntimeError, match="API Key"):
        embedder.embed_texts(["test"])
