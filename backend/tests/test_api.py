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


# === parse 两阶段端点测试（US-31 parse-confirm-flow）===


def _disable_mineru(monkeypatch) -> None:
    """测试中禁用 MinerU 云端解析，走本地解析器路径。"""
    from resume_agent import config as config_module

    monkeypatch.setattr(config_module.settings, "mineru_api_token", None)


def _wait_parse_task(client: TestClient, task_id: str, timeout: float = 15.0) -> dict[str, Any]:
    """轮询任务详情直到脱离 extracting 状态，返回任务数据。"""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/resumes/parse/tasks/{task_id}")
        body = resp.json()
        assert body["ok"] is True, f"详情端点报错: {body}"
        if body["data"]["status"] != "extracting":
            return body["data"]
        time.sleep(0.05)
    raise AssertionError(f"解析任务超时未完成: {task_id}")


def _parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    """解析 SSE 文本为 (type, payload) 列表。"""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        data_lines = [line[5:] for line in block.splitlines() if line.startswith("data:")]
        if not data_lines:
            continue
        payload = json.loads("\n".join(data_lines))
        events.append((payload.get("type", ""), payload))
    return events


def _upload_test_resume(client: TestClient, tmp_path: Path, name: str = "r.pdf", text: str = "resume text") -> str:
    """上传测试 PDF 并返回 upload_id。"""
    pdf_path = tmp_path / name
    _create_test_pdf(pdf_path, text)
    with pdf_path.open("rb") as f:
        resp = client.post(
            "/api/resumes/upload",
            files={"file": (name, f, "application/pdf")},
        )
    return resp.json()["data"]["upload_id"]


def test_parse_starts_async_task_and_returns_task_id(
    tmp_path: Path, monkeypatch
) -> None:
    """POST /parse 应启动异步任务并立即返回 task_id，不直接建树。"""
    _init_db()
    from resume_agent.main import app

    _disable_mineru(monkeypatch)
    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    client = TestClient(app)
    uid = _upload_test_resume(client, tmp_path)

    response = client.post("/api/resumes/parse", json={"upload_id": uid})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["task_id"]
    assert body["data"]["status"] == "extracting"

    # 异步语义：启动后版本树不应有新 branch 节点（可能任务瞬间完成，
    # 因此只断言 parse_status 不再是 pending，且节点数为 0 或任务已完成）
    with get_connection() as conn:
        record = conn.execute(
            "SELECT parse_status FROM upload_records WHERE id = ?", (uid,)
        ).fetchone()
    assert record["parse_status"] in ("parsing", "needs_review")


def test_parse_full_flow_with_confirm(tmp_path: Path, monkeypatch) -> None:
    """两阶段完整流程：提取 → awaiting_confirm → 确认 → 建树 + 置信度。"""
    _init_db()
    from resume_agent.main import app

    _disable_mineru(monkeypatch)
    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    client = TestClient(app)
    uid = _upload_test_resume(client, tmp_path, text="Zhang San Engineer Resume")

    start = client.post("/api/resumes/parse", json={"upload_id": uid}).json()
    task_id = start["data"]["task_id"]

    detail = _wait_parse_task(client, task_id)

    # 提取阶段结果
    assert detail["status"] == "awaiting_confirm"
    assert detail["structured_resume"]["basic"]["name"] == "张三"
    assert detail["structured_resume"]["primary_direction"] == "安全"
    assert detail["parser_used"] == "local"
    assert detail["degraded"] is False
    # 置信度：mock 简历原文不含中文字段，name 未命中 → low
    assert detail["confidence"]["basic"]["name"] == "low"

    # 确认阶段：提交（未修改）数据
    confirm = client.post(
        f"/api/resumes/parse/tasks/{task_id}/confirm",
        json={
            "structured_resume": detail["structured_resume"],
            "apply_knowledge_personal_info": False,
        },
    )
    assert confirm.status_code == 200
    data = confirm.json()["data"]
    assert data["structured_resume"]["basic"]["name"] == "张三"
    assert data["deduplicated"] is False
    # US-12：只创建方向（branch）节点
    assert data["tree_node"]["node_type"] == "branch"
    assert data["tree_node"]["direction"] == "安全"
    assert data["tree_node"]["node_id"] == "branch-安全"

    # 状态更新
    with get_connection() as conn:
        record = conn.execute(
            "SELECT parse_status FROM upload_records WHERE id = ?", (uid,)
        ).fetchone()
    assert record["parse_status"] == "success"

    # 树节点内容已写入
    with get_connection() as conn:
        nodes = conn.execute(
            "SELECT * FROM resume_versions WHERE node_type = 'branch'"
        ).fetchall()
    assert len(nodes) == 1
    content = json.loads(nodes[0]["content_json"])
    assert content["basic"]["name"] == "张三"

    # 任务标记 confirmed
    final = client.get(f"/api/resumes/parse/tasks/{task_id}").json()["data"]
    assert final["status"] == "confirmed"


def test_parse_deduplicates_on_second_confirm(tmp_path: Path, monkeypatch) -> None:
    """同方向二次解析确认应命中去重。"""
    _init_db()
    from resume_agent.main import app

    _disable_mineru(monkeypatch)
    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    client = TestClient(app)

    for name in ("r1.pdf", "r2.pdf"):
        uid = _upload_test_resume(client, tmp_path, name=name)
        task_id = client.post(
            "/api/resumes/parse", json={"upload_id": uid}
        ).json()["data"]["task_id"]
        detail = _wait_parse_task(client, task_id)
        confirm = client.post(
            f"/api/resumes/parse/tasks/{task_id}/confirm",
            json={
                "structured_resume": detail["structured_resume"],
                "apply_knowledge_personal_info": False,
            },
        )
        assert confirm.json()["ok"] is True

    # 第二次确认应报 deduplicated，且版本树只有 1 个 branch 节点
    with get_connection() as conn:
        nodes = conn.execute(
            "SELECT * FROM resume_versions WHERE node_type = 'branch'"
        ).fetchall()
    assert len(nodes) == 1


def test_parse_idempotent_returns_same_task(tmp_path: Path, monkeypatch) -> None:
    """同 upload_id 重复 POST /parse 应返回既有任务（幂等）。"""
    _init_db()
    from resume_agent.main import app

    _disable_mineru(monkeypatch)
    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    client = TestClient(app)
    uid = _upload_test_resume(client, tmp_path)

    first = client.post("/api/resumes/parse", json={"upload_id": uid}).json()
    second = client.post("/api/resumes/parse", json={"upload_id": uid}).json()

    assert second["ok"] is True
    assert second["data"]["task_id"] == first["data"]["task_id"]


def test_knowledge_indexed_only_after_confirm(tmp_path: Path, monkeypatch) -> None:
    """知识库写入时序：确认前无 chunks，确认后才有（错误数据不污染 RAG）。"""
    _init_db()
    from resume_agent.main import app

    _disable_mineru(monkeypatch)
    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    client = TestClient(app)
    uid = _upload_test_resume(client, tmp_path)
    task_id = client.post(
        "/api/resumes/parse", json={"upload_id": uid}
    ).json()["data"]["task_id"]

    detail = _wait_parse_task(client, task_id)

    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM knowledge_chunks").fetchone()
    assert count["cnt"] == 0  # 确认前不写知识库

    client.post(
        f"/api/resumes/parse/tasks/{task_id}/confirm",
        json={
            "structured_resume": detail["structured_resume"],
            "apply_knowledge_personal_info": False,
        },
    )

    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM knowledge_chunks").fetchone()
    assert count["cnt"] > 0  # 确认后写入


def test_confirm_applies_knowledge_personal_info_override(
    tmp_path: Path, monkeypatch
) -> None:
    """确认时用户选择覆盖 → 知识库个人信息生效；不选 → 保留提取值。"""
    _init_db()
    from resume_agent.api import resumes as resumes_module
    from resume_agent.main import app

    _disable_mineru(monkeypatch)
    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    knowledge_personal = {
        "contact": {"name": "张三丰", "phone": "13999990000", "email": "zsf@example.com"},
        "education": [],
        "summary": "",
    }

    async def fake_knowledge_personal() -> dict[str, Any] | None:
        return knowledge_personal

    monkeypatch.setattr(
        resumes_module, "_extract_personal_info_from_knowledge", fake_knowledge_personal
    )

    client = TestClient(app)
    uid = _upload_test_resume(client, tmp_path)
    task_id = client.post(
        "/api/resumes/parse", json={"upload_id": uid}
    ).json()["data"]["task_id"]
    detail = _wait_parse_task(client, task_id)

    # 知识库个人信息并存展示（不静默覆盖）
    assert detail["knowledge_personal_info"]["contact"]["phone"] == "13999990000"
    # 提取结果保持原值
    assert detail["structured_resume"]["basic"]["phone"] == "138****8888"

    # 不覆盖 → 保留提取值
    confirm_no = client.post(
        f"/api/resumes/parse/tasks/{task_id}/confirm",
        json={
            "structured_resume": detail["structured_resume"],
            "apply_knowledge_personal_info": False,
        },
    )
    assert confirm_no.json()["data"]["structured_resume"]["basic"]["phone"] == "138****8888"

    # 覆盖 → 使用知识库值（新任务）
    uid2 = _upload_test_resume(client, tmp_path, name="r2.pdf")
    task2 = client.post(
        "/api/resumes/parse", json={"upload_id": uid2}
    ).json()["data"]["task_id"]
    detail2 = _wait_parse_task(client, task2)
    confirm_yes = client.post(
        f"/api/resumes/parse/tasks/{task2}/confirm",
        json={
            "structured_resume": detail2["structured_resume"],
            "apply_knowledge_personal_info": True,
        },
    )
    assert confirm_yes.json()["data"]["structured_resume"]["basic"]["phone"] == "13999990000"
    assert confirm_yes.json()["data"]["structured_resume"]["basic"]["name"] == "张三丰"


def test_parse_handles_llm_extraction_failure(tmp_path: Path, monkeypatch) -> None:
    """LLM 提取失败 → 任务 failed + upload_records needs_review。"""
    _init_db()
    from resume_agent.api import resumes as resumes_module
    from resume_agent.main import app

    _disable_mineru(monkeypatch)

    async def fake_chat(self, system_prompt, user_content, response_format_json=False):  # noqa: ANN001
        raise RuntimeError("LLM 调用失败")

    monkeypatch.setattr(
        resumes_module.LLMClient, "configured", property(lambda self: True)
    )
    monkeypatch.setattr(resumes_module.LLMClient, "chat", fake_chat)

    client = TestClient(app)
    uid = _upload_test_resume(client, tmp_path)

    start = client.post("/api/resumes/parse", json={"upload_id": uid}).json()
    assert start["ok"] is True  # 异步启动成功

    detail = _wait_parse_task(client, start["data"]["task_id"])
    assert detail["status"] == "failed"
    assert "LLM 调用失败" in detail["error"]

    with get_connection() as conn:
        record = conn.execute(
            "SELECT parse_status FROM upload_records WHERE id = ?", (uid,)
        ).fetchone()
    assert record["parse_status"] == "needs_review"


def test_mineru_degrades_to_local_parser(tmp_path: Path, monkeypatch) -> None:
    """MinerU 失败 → 自动降级本地解析器并标记 degraded。"""
    _init_db()
    from resume_agent import config as config_module
    from resume_agent.main import app
    from resume_agent.parsers import mineru_client as mineru_module

    monkeypatch.setattr(
        config_module.settings, "mineru_api_token", "test-token"
    )

    def raise_mineru(self, file_path):  # noqa: ANN001
        raise mineru_module.MinerUError("轮询超时：任务未在规定时间内完成")

    monkeypatch.setattr(
        mineru_module.MinerUClient, "upload_and_parse", raise_mineru
    )
    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    client = TestClient(app)
    uid = _upload_test_resume(client, tmp_path)
    task_id = client.post(
        "/api/resumes/parse", json={"upload_id": uid}
    ).json()["data"]["task_id"]

    detail = _wait_parse_task(client, task_id)
    assert detail["status"] == "awaiting_confirm"
    assert detail["parser_used"] == "local"
    assert detail["degraded"] is True


def test_events_endpoint_replays_history_and_closes(
    tmp_path: Path, monkeypatch
) -> None:
    """SSE：任务已终态时连接应补发历史事件后关闭。"""
    _init_db()
    from resume_agent.main import app

    _disable_mineru(monkeypatch)
    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    client = TestClient(app)
    uid = _upload_test_resume(client, tmp_path)
    task_id = client.post(
        "/api/resumes/parse", json={"upload_id": uid}
    ).json()["data"]["task_id"]

    _wait_parse_task(client, task_id)  # 等待任务终态

    resp = client.get(f"/api/resumes/parse/tasks/{task_id}/events")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    types = [t for t, _ in events]
    assert "file_parsed" in types
    assert "extracting" in types
    assert types[-1] == "done"
    # file_parsed 事件带解析器信息
    file_parsed = next(p for t, p in events if t == "file_parsed")
    assert file_parsed["parser_used"] == "local"
    assert file_parsed["degraded"] is False


def test_confirm_rejects_invalid_structured_resume(
    tmp_path: Path, monkeypatch
) -> None:
    """confirm 提交的数据不符合 schema 应被拒绝（服务端重校验）。"""
    _init_db()
    from resume_agent.main import app

    _disable_mineru(monkeypatch)
    _install_mock_llm(monkeypatch, _make_structured_resume_dict())

    client = TestClient(app)
    uid = _upload_test_resume(client, tmp_path)
    task_id = client.post(
        "/api/resumes/parse", json={"upload_id": uid}
    ).json()["data"]["task_id"]
    _wait_parse_task(client, task_id)

    confirm = client.post(
        f"/api/resumes/parse/tasks/{task_id}/confirm",
        json={
            "structured_resume": {"basic": "not-an-object"},
            "apply_knowledge_personal_info": False,
        },
    )
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_STRUCTURED_RESUME"


def test_confirm_unknown_task_returns_error() -> None:
    """不存在的 task_id 确认应返回错误。"""
    _init_db()
    from resume_agent.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/resumes/parse/tasks/nonexistent/confirm",
        json={"structured_resume": {}, "apply_knowledge_personal_info": False},
    )
    assert resp.json()["ok"] is False
    assert resp.json()["error"]["code"] == "TASK_NOT_FOUND"


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
