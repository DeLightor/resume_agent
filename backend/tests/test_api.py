"""API 集成测试：resumes 端点 + tree 端点。

用 FastAPI TestClient + 临时 DB（通过 conftest 的 _isolated_env fixture 隔离）。
LLM 调用通过 monkeypatch mock，不发送真实 HTTP 请求。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz  # type: ignore[import-not-found]
from docx import Document
from fastapi.testclient import TestClient

from resume_agent.db.connection import get_connection
from resume_agent.db.init_db import init_database

# === fixtures ===


def _create_test_pdf(path: Path, text: str = "Zhang San Resume Content") -> None:
    """创建测试用 PDF 文件。"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()


def _create_test_docx(path: Path, paragraphs: list[str]) -> None:
    """创建测试用 DOCX 文件。"""
    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.save(str(path))


def _init_db() -> None:
    """初始化隔离环境下的数据库。"""
    from resume_agent.config import settings

    init_database(settings.sqlite_path)


def _make_structured_resume_dict() -> dict[str, Any]:
    """构造一份样例结构化简历字典（用于 mock LLM 返回）。"""
    return {
        "basic": {
            "name": "张三",
            "phone": "138****8888",
            "email": "zhangsan@example.com",
            "location": "北京",
        },
        "education": [
            {
                "school": "某大学",
                "degree": "硕士",
                "major": "计算机",
                "period": "2018-2021",
            }
        ],
        "experience": [
            {
                "company": "Tencent",
                "role": "安全研究员",
                "period": "2021-至今",
                "highlights": ["负责云安全"],
            }
        ],
        "projects": [{"name": "漏洞平台", "role": "负责人", "description": "扫描"}],
        "skills": ["Python", "安全"],
        "primary_direction": "安全",
    }


# === upload 端点测试 ===


def test_upload_pdf_creates_record_and_file(tmp_path: Path) -> None:
    """上传 PDF 应保存文件并创建 upload_records 记录。"""
    _init_db()
    from resume_agent.config import settings
    from resume_agent.main import app

    # 准备测试 PDF
    pdf_path = tmp_path / "resume.pdf"
    _create_test_pdf(pdf_path)

    client = TestClient(app)
    with pdf_path.open("rb") as f:
        response = client.post(
            "/api/resumes/upload",
            files={"file": ("resume.pdf", f, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["file_type"] == "pdf"
    assert data["parse_status"] == "pending"
    upload_id = data["upload_id"]

    # 验证文件已保存
    saved_path = settings.files_root / data["file_path"]
    assert saved_path.exists()

    # 验证 DB 记录
    with get_connection() as conn:
        record = conn.execute(
            "SELECT * FROM upload_records WHERE id = ?", (upload_id,)
        ).fetchone()
    assert record is not None
    assert record["file_name"] == "resume.pdf"
    assert record["file_type"] == "pdf"
    assert record["parse_status"] == "pending"


def test_upload_docx_creates_record(tmp_path: Path) -> None:
    """上传 DOCX 应保存文件并创建记录。"""
    _init_db()
    from resume_agent.main import app

    docx_path = tmp_path / "cv.docx"
    _create_test_docx(docx_path, ["Hello World", "Second para"])

    client = TestClient(app)
    with docx_path.open("rb") as f:
        response = client.post(
            "/api/resumes/upload",
            files={"file": ("cv.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["file_type"] == "docx"


def test_upload_rejects_invalid_file_type() -> None:
    """上传非 pdf/docx 文件应返回错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post(
        "/api/resumes/upload",
        files={"file": ("file.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_FILE_TYPE"


# === parse 端点测试 ===


def test_parse_returns_error_when_llm_not_configured(
    tmp_path: Path, monkeypatch
) -> None:
    """LLM 未配置时 parse 端点返回错误提示。"""
    _init_db()
    from resume_agent.api import resumes as resumes_module
    from resume_agent.main import app

    # 强制 LLM 未配置（本机 backend/.env 可能提供真实 key，需隔离）
    monkeypatch.setattr(
        resumes_module.LLMClient, "configured", property(lambda self: False)
    )

    # 先上传文件
    pdf_path = tmp_path / "r.pdf"
    _create_test_pdf(pdf_path)
    client = TestClient(app)
    with pdf_path.open("rb") as f:
        upload_resp = client.post(
            "/api/resumes/upload",
            files={"file": ("r.pdf", f, "application/pdf")},
        )
    upload_id = upload_resp.json()["data"]["upload_id"]

    # 调用 parse
    response = client.post("/api/resumes/parse", json={"upload_id": upload_id})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "LLM_NOT_CONFIGURED"


def _install_mock_llm(monkeypatch, resume_dict: dict[str, Any]) -> None:
    """monkeypatch LLMClient 使其返回 mock JSON。"""
    from resume_agent.api import resumes as resumes_module

    async def fake_chat(self, system_prompt, user_content, response_format_json=False):  # noqa: ANN001
        return json.dumps(resume_dict, ensure_ascii=False)

    # patch LLMClient.configured 属性与 chat 方法
    monkeypatch.setattr(
        resumes_module.LLMClient, "configured", property(lambda self: True)
    )
    monkeypatch.setattr(resumes_module.LLMClient, "chat", fake_chat)


def test_parse_success_full_flow(tmp_path: Path, monkeypatch) -> None:
    """完整解析流程：上传 → mock LLM → 结构化 → 版本树节点。"""
    _init_db()
    from resume_agent.main import app

    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    # 上传 PDF
    pdf_path = tmp_path / "resume.pdf"
    _create_test_pdf(pdf_path, "Zhang San Engineer Resume")
    client = TestClient(app)
    with pdf_path.open("rb") as f:
        upload_resp = client.post(
            "/api/resumes/upload",
            files={"file": ("resume.pdf", f, "application/pdf")},
        )
    upload_id = upload_resp.json()["data"]["upload_id"]

    # 调用 parse
    response = client.post("/api/resumes/parse", json={"upload_id": upload_id})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["upload_id"] == upload_id
    assert data["structured_resume"]["basic"]["name"] == "张三"
    assert data["structured_resume"]["primary_direction"] == "安全"
    assert data["deduplicated"] is False
    # US-12：只创建方向（branch）节点，不再创建 company 节点
    assert data["tree_node"]["node_type"] == "branch"
    assert data["tree_node"]["direction"] == "安全"
    assert data["tree_node"]["node_id"] == "branch-安全"

    # 验证 DB 状态更新为 success
    with get_connection() as conn:
        record = conn.execute(
            "SELECT parse_status FROM upload_records WHERE id = ?", (upload_id,)
        ).fetchone()
    assert record["parse_status"] == "success"

    # 验证版本树 branch 节点已创建并写入简历内容
    with get_connection() as conn:
        nodes = conn.execute(
            "SELECT * FROM resume_versions WHERE node_type = 'branch'"
        ).fetchall()
    assert len(nodes) == 1
    content = json.loads(nodes[0]["content_json"])
    assert content["basic"]["name"] == "张三"


def test_parse_deduplicates_on_second_call(tmp_path: Path, monkeypatch) -> None:
    """同一公司同一方向二次上传应命中去重。"""
    _init_db()
    from resume_agent.main import app

    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    # 第一次上传 + 解析
    pdf_path = tmp_path / "r1.pdf"
    _create_test_pdf(pdf_path, "resume one")
    client = TestClient(app)
    with pdf_path.open("rb") as f:
        uid1 = client.post(
            "/api/resumes/upload",
            files={"file": ("r1.pdf", f, "application/pdf")},
        ).json()["data"]["upload_id"]
    resp1 = client.post("/api/resumes/parse", json={"upload_id": uid1})
    assert resp1.json()["data"]["deduplicated"] is False

    # 第二次上传 + 解析（同公司同方向）
    pdf_path2 = tmp_path / "r2.pdf"
    _create_test_pdf(pdf_path2, "resume two")
    with pdf_path2.open("rb") as f:
        uid2 = client.post(
            "/api/resumes/upload",
            files={"file": ("r2.pdf", f, "application/pdf")},
        ).json()["data"]["upload_id"]
    resp2 = client.post("/api/resumes/parse", json={"upload_id": uid2})

    assert resp2.json()["data"]["deduplicated"] is True
    # 版本树只应有 1 个 branch 节点（同方向去重）
    with get_connection() as conn:
        nodes = conn.execute(
            "SELECT * FROM resume_versions WHERE node_type = 'branch'"
        ).fetchall()
    assert len(nodes) == 1


def test_parse_returns_error_for_unknown_upload() -> None:
    """不存在的 upload_id 应返回错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.post(
        "/api/resumes/parse", json={"upload_id": "nonexistent-uuid"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "UPLOAD_NOT_FOUND"


def test_parse_handles_llm_extraction_failure(tmp_path: Path, monkeypatch) -> None:
    """LLM 提取失败时应标记 needs_review 并返回错误。"""
    _init_db()
    from resume_agent.api import resumes as resumes_module
    from resume_agent.main import app

    async def fake_chat(self, system_prompt, user_content, response_format_json=False):  # noqa: ANN001
        raise RuntimeError("LLM 调用失败")

    monkeypatch.setattr(
        resumes_module.LLMClient, "configured", property(lambda self: True)
    )
    monkeypatch.setattr(resumes_module.LLMClient, "chat", fake_chat)

    pdf_path = tmp_path / "r.pdf"
    _create_test_pdf(pdf_path, "some text")
    client = TestClient(app)
    with pdf_path.open("rb") as f:
        uid = client.post(
            "/api/resumes/upload",
            files={"file": ("r.pdf", f, "application/pdf")},
        ).json()["data"]["upload_id"]

    response = client.post("/api/resumes/parse", json={"upload_id": uid})
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "EXTRACT_FAILED"

    # 状态应为 needs_review
    with get_connection() as conn:
        record = conn.execute(
            "SELECT parse_status FROM upload_records WHERE id = ?", (uid,)
        ).fetchone()
    assert record["parse_status"] == "needs_review"


# === list 端点测试 ===


def test_list_returns_all_records(tmp_path: Path) -> None:
    """list 端点应返回所有上传记录。"""
    _init_db()
    from resume_agent.main import app

    pdf_path = tmp_path / "r.pdf"
    _create_test_pdf(pdf_path)
    client = TestClient(app)
    with pdf_path.open("rb") as f:
        client.post(
            "/api/resumes/upload",
            files={"file": ("r.pdf", f, "application/pdf")},
        )
    with pdf_path.open("rb") as f:
        client.post(
            "/api/resumes/upload",
            files={"file": ("r2.pdf", f, "application/pdf")},
        )

    response = client.get("/api/resumes/list")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert len(body["data"]) == 2


def test_list_empty_when_no_records() -> None:
    """无记录时 list 返回空数组。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.get("/api/resumes/list")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"] == []


# === tree 端点测试 ===


def test_tree_returns_nodes_and_edges() -> None:
    """tree 端点应从 DB 读取节点并构建 nodes + edges。"""
    _init_db()
    from resume_agent.main import app

    # 插入 master + branch + company 节点
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO resume_versions (id, node_id, parent_id, node_type, title, direction) "
            "VALUES (?, 'branch-sec', 'master', 'branch', '安全方向', '安全')",
            ("b1",),
        )
        conn.execute(
            "INSERT INTO resume_versions (id, node_id, parent_id, node_type, title, company, direction) "
            "VALUES (?, 'sec-tencent', 'branch-sec', 'company', 'Tencent 安全', 'Tencent', '安全')",
            ("c1",),
        )

    client = TestClient(app)
    response = client.get("/api/tree")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]

    # 3 个节点（master + branch + company）
    assert len(data["nodes"]) == 3
    node_ids = {n["node_id"] for n in data["nodes"]}
    assert {"master", "branch-sec", "sec-tencent"} == node_ids

    # 2 条边：master→branch-sec, branch-sec→sec-tencent
    assert len(data["edges"]) == 2
    edge_pairs = {(e["source"], e["target"]) for e in data["edges"]}
    assert ("master", "branch-sec") in edge_pairs
    assert ("branch-sec", "sec-tencent") in edge_pairs


def test_tree_empty_returns_only_master() -> None:
    """空版本树（仅 master）应返回 1 个节点 0 条边。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    response = client.get("/api/tree")
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["node_id"] == "master"
    assert data["edges"] == []
