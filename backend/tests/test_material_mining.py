"""应届生素材挖掘测试（US-36 graduate-material-mining）。

覆盖：
1. 五大分类模板元数据加载。
2. 挖掘会话 CRUD、状态流转与断点续挖草稿保存。
3. 师兄追问递进与上下文收集。
4. STAR 结构化成果提炼引擎。
5. Chroma 向量相似度语义查重检测。
6. 一键打包生成 Markdown 文件与知识库切片向量化入库全流程。
7. /api/mining API 路由集成测试。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from resume_agent.main import app
from resume_agent.services import material_mining
from resume_agent.services.material_mining import (
    MINING_CATEGORIES,
    check_duplicate_in_knowledge,
    commit_mining_to_knowledge,
    create_mining_session,
    delete_mining_session,
    get_mining_session,
    get_mining_templates,
    list_mining_sessions,
    submit_step_answer,
    synthesize_star_result,
)

# ---------------------------------------------------------------------------
# 1. 模板加载与元数据
# ---------------------------------------------------------------------------


def test_get_mining_templates() -> None:
    """五大类别模板均存在且包含完整的 STAR 引导问题与输入示例。"""
    templates = get_mining_templates()
    categories = {t["category"] for t in templates}
    assert categories == set(MINING_CATEGORIES)
    assert len(templates) == 5

    course_t = next(t for t in templates if t["category"] == "course_project")
    assert "steps" in course_t
    assert len(course_t["steps"]) == 4  # S, T, A, R 四步
    for step in course_t["steps"]:
        assert "step" in step
        assert "title" in step
        assert "question" in step
        assert "example" in step


# ---------------------------------------------------------------------------
# 2. 挖掘会话 CRUD 与断点续挖
# ---------------------------------------------------------------------------


def test_mining_session_crud(initialized_db: Any) -> None:
    """创建会话、查询会话、状态筛选与删除。"""
    session = create_mining_session(
        category="course_project",
        title="分布式 KV 存储大作业",
        db_path=initialized_db,
    )
    assert session.id is not None
    assert session.category == "course_project"
    assert session.title == "分布式 KV 存储大作业"
    assert session.status == "in_progress"
    assert session.current_step == 1
    assert session.context == {}
    assert session.star_result is None

    # 按 ID 获取
    fetched = get_mining_session(session.id, db_path=initialized_db)
    assert fetched is not None
    assert fetched.id == session.id

    # 列表获取
    sessions = list_mining_sessions(db_path=initialized_db)
    assert len(sessions) == 1
    assert sessions[0].id == session.id

    # 删除
    ok = delete_mining_session(session.id, db_path=initialized_db)
    assert ok is True
    assert get_mining_session(session.id, db_path=initialized_db) is None


def test_mining_session_validation(initialized_db: Any) -> None:
    """非法分类与空标题校验。"""
    with pytest.raises(ValueError, match="非法经历分类"):
        create_mining_session(category="invalid_cat", title="test", db_path=initialized_db)

    with pytest.raises(ValueError, match="标题不能为空"):
        create_mining_session(category="course_project", title="   ", db_path=initialized_db)


# ---------------------------------------------------------------------------
# 3. 师兄追问流转与断点保存
# ---------------------------------------------------------------------------


def test_submit_step_answer_progression(initialized_db: Any) -> None:
    """提交步骤回答自动推进步骤并保存问答历史（支持断点恢复）。"""
    session = create_mining_session(
        category="competition",
        title="数学建模竞赛算法设计",
        db_path=initialized_db,
    )

    class _MockLLM:
        configured = True

        async def chat(self, system_prompt: str, user_content: str, response_format_json: bool = False) -> str:
            return "收到！这个选题很有亮点。接下来跟我聊聊你在算法中遇到的最大挑战是什么？"

    llm = _MockLLM()

    # 提交第 1 步 (S: 背景与目标)
    res1 = asyncio.run(
        submit_step_answer(
            session_id=session.id,
            step=1,
            answer="参加了全国大学生数学建模竞赛，三人团队，我负责核心数据清洗和算法建模。",
            llm=llm,
            db_path=initialized_db,
        )
    )
    assert res1["session"]["current_step"] == 2
    assert "收到" in res1["feedback"]
    assert "step_1" in res1["session"]["context"]
    assert "数学建模" in res1["session"]["context"]["step_1"]

    # 验证数据库持久化断点
    updated_session = get_mining_session(session.id, db_path=initialized_db)
    assert updated_session is not None
    assert updated_session.current_step == 2
    assert updated_session.context["step_1"] == "参加了全国大学生数学建模竞赛，三人团队，我负责核心数据清洗和算法建模。"


# ---------------------------------------------------------------------------
# 4. STAR 成果结构化提炼
# ---------------------------------------------------------------------------


def test_synthesize_star_result(initialized_db: Any) -> None:
    """调用提炼引擎将问答历史转化为 STAR 结构化成果。"""
    session = create_mining_session(
        category="research",
        title="多模态大模型幻觉抑制算法",
        db_path=initialized_db,
    )

    # 预设 4 步回答
    session.context = {
        "step_1": "在实验室参与多模态大模型幻觉抑制课题，负责视觉特征对齐模块。",
        "step_2": "挑战是高分辨率图片在交叉注意力层计算量过大且对细粒度语义失真。",
        "step_3": "采用动态稀疏注意力机制并设计了基于语义熵的自适应路由算法，使用 PyTorch 实装。",
        "step_4": "在 POPE 基准评测集上幻觉率降低 28.5%，显存占用减少 40%，论文被顶会录用。",
    }
    material_mining.save_mining_session(session, db_path=initialized_db)

    class _SynthesizeLLM:
        configured = True

        async def chat(self, system_prompt: str, user_content: str, response_format_json: bool = False) -> str:
            import json
            return json.dumps({
                "summary": "基于动态稀疏注意力的多模态大模型细粒度幻觉抑制研究",
                "situation": "针对高分辨率多模态大模型图文对齐中细粒度特征失真与计算开销大问题",
                "task": "主导视觉特征对齐优化算法设计与显存开销调优",
                "action": "提出动态稀疏注意力机制与语义熵自适应路由算法，编写 PyTorch 算子实现加速",
                "result": "POPE 基准幻觉率显著下降 28.5%，显存峰值降低 40%",
                "tech_stack": ["Python", "PyTorch", "Transformer", "CUDA"],
                "bullet_points": [
                    "主导多模态大模型视觉对齐模块重构，设计动态稀疏注意力机制解决细粒度语义失真问题",
                    "基于语义熵自适应路由算法优化交叉注意力开销，实现显存峰值降低 40%",
                    "在标准 POPE 评估集上将幻觉识别错误率降低 28.5%，成果被顶级学术会议录用为 Oral",
                ],
            })

    llm = _SynthesizeLLM()
    star = asyncio.run(synthesize_star_result(session.id, llm=llm, db_path=initialized_db))

    assert star["summary"] == "基于动态稀疏注意力的多模态大模型细粒度幻觉抑制研究"
    assert len(star["bullet_points"]) == 3
    assert "PyTorch" in star["tech_stack"]

    # 确认已存入会话
    s = get_mining_session(session.id, db_path=initialized_db)
    assert s is not None
    assert s.star_result is not None
    assert s.star_result["summary"] == star["summary"]


# ---------------------------------------------------------------------------
# 5. Chroma 向量相似度语义查重
# ---------------------------------------------------------------------------


def test_check_duplicate_in_knowledge(initialized_db: Any, monkeypatch: Any) -> None:
    """查重检测：当知识库存在高相似素材时预警，无重合时通过。"""
    class _MockCollection:
        def __init__(self, distance: float) -> None:
            self._distance = distance

        def count(self) -> int:
            return 5

        def query(self, query_texts: list[str], n_results: int = 3) -> dict[str, Any]:
            return {
                "ids": [["chunk_1"]],
                "documents": [["已存在相似内容：基于动态稀疏注意力的视觉对齐模块设计..."]],
                "metadatas": [[{"source_file": "existing_project.md"}]],
                "distances": [[self._distance]],
            }

    # 1. 距离很小（相似度高，如 score = 1.0 - 0.1 = 0.90 >= 0.85）
    from resume_agent.rag import chroma_client
    monkeypatch.setattr(chroma_client, "get_knowledge_collection", lambda: _MockCollection(distance=0.10))

    dup_res = check_duplicate_in_knowledge("基于动态稀疏注意力的视觉特征对齐模块设计与调优")
    assert dup_res["is_duplicate"] is True
    assert dup_res["score"] >= 0.85
    assert "existing_project.md" in dup_res["top_match"]["source_file"]

    # 2. 距离较大（不重复，如 score = 1.0 - 0.5 = 0.50 < 0.85）
    monkeypatch.setattr(chroma_client, "get_knowledge_collection", lambda: _MockCollection(distance=0.50))
    non_dup = check_duplicate_in_knowledge("全新的社团志愿者策划经历")
    assert non_dup["is_duplicate"] is False


# ---------------------------------------------------------------------------
# 6. 一键沉淀打包入库全流程
# ---------------------------------------------------------------------------


def test_commit_mining_to_knowledge(initialized_db: Any, monkeypatch: Any, tmp_path: Any) -> None:
    """将提炼完成的素材保存为物理 Markdown、创建 upload_records 与 knowledge_chunks 并完成向量索引。"""
    from resume_agent.config import settings

    monkeypatch.setattr(settings, "sqlite_path", initialized_db)
    monkeypatch.setattr(settings, "files_root", tmp_path)

    # 模拟向量集合
    indexed_docs: list[str] = []

    class _MockChromaColl:
        def delete(self, ids: list[str]) -> None:
            pass

        def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict]) -> None:
            indexed_docs.extend(documents)

    from resume_agent.rag import chroma_client
    monkeypatch.setattr(chroma_client, "get_knowledge_collection", lambda: _MockChromaColl())

    session = create_mining_session(
        category="course_project",
        title="基于 Raft 的分布式 KV 存储",
        db_path=initialized_db,
    )
    session.star_result = {
        "summary": "基于 Go 语言的高可用分布式键值存储系统",
        "situation": "计算机系统大作业，需要设计实现分布式一致性存储系统",
        "task": "独立负责一致性算法与网络 RPC 模块",
        "action": "实现 Raft 算法选举、日志复制和快照机制，采用 gRPC 与 Protocol Buffers",
        "result": "单节点支持 15000+ QPS，通过 Jepsen 分布式测试并获得专业第一名",
        "tech_stack": ["Go", "Raft", "gRPC", "RocksDB"],
        "bullet_points": [
            "基于 Go 独立设计高可用分布式 KV 存储引擎，完整实装 Raft 选主、日志复制与成员变更机制",
            "设计心跳超时自适应调整策略与快照压缩方案，在网络异常分区场景下达到零数据丢失",
            "经 Jepsen 混沌测试验证线性一致性，单集群写吞吐突破 1.5 万 QPS，获评期末优秀设计第一名",
        ],
    }
    material_mining.save_mining_session(session, db_path=initialized_db)

    # 执行提交入库
    result = commit_mining_to_knowledge(session.id, db_path=initialized_db)

    assert result["ok"] is True
    assert result["upload_id"] is not None
    assert result["chunk_count"] > 0
    assert "分布式" in result["file_name"]

    # 物理文件已落地
    target_file = tmp_path / result["file_path"]
    assert target_file.exists()
    content = target_file.read_text(encoding="utf-8")
    assert "分布式 KV 存储" in content
    assert "Raft" in content

    # 数据库 upload_records 与 knowledge_chunks 已持久化
    from resume_agent.db.connection import get_connection
    with get_connection(initialized_db) as conn:
        record = conn.execute(
            "SELECT * FROM upload_records WHERE id = ?", [result["upload_id"]]
        ).fetchone()
        assert record is not None
        assert record["file_path"].startswith("knowledge/")

        chunks = conn.execute(
            "SELECT * FROM knowledge_chunks WHERE source_file = ?", [result["file_name"]]
        ).fetchall()
        assert len(chunks) > 0

    # 会话标记为 completed
    updated_session = get_mining_session(session.id, db_path=initialized_db)
    assert updated_session is not None
    assert updated_session.status == "completed"


# ---------------------------------------------------------------------------
# 7. API 路由集成测试 (/api/mining)
# ---------------------------------------------------------------------------


def test_api_mining_endpoints(initialized_db: Any, monkeypatch: Any) -> None:
    """测试 /api/mining 的全部 REST 接口。"""
    from resume_agent.config import settings

    monkeypatch.setattr(settings, "sqlite_path", initialized_db)
    client = TestClient(app)

    # 1. GET /api/mining/templates
    t_resp = client.get("/api/mining/templates")
    assert t_resp.status_code == 200
    assert t_resp.json()["ok"] is True
    assert len(t_resp.json()["data"]) == 5

    # 2. POST /api/mining/sessions (创建)
    c_resp = client.post(
        "/api/mining/sessions",
        json={"category": "club", "title": "开源技术沙龙主办"},
    )
    assert c_resp.status_code == 200
    session_data = c_resp.json()["data"]
    session_id = session_data["id"]
    assert session_data["category"] == "club"

    # 3. GET /api/mining/sessions (列表)
    l_resp = client.get("/api/mining/sessions")
    assert l_resp.status_code == 200
    assert len(l_resp.json()["data"]) == 1

    # 4. GET /api/mining/sessions/{id} (详情)
    d_resp = client.get(f"/api/mining/sessions/{session_id}")
    assert d_resp.status_code == 200
    assert d_resp.json()["data"]["id"] == session_id

    # 5. POST /api/mining/sessions/{id}/answer (提交回答)
    a_resp = client.post(
        f"/api/mining/sessions/{session_id}/answer",
        json={"step": 1, "answer": "负责开源沙龙的技术分享策划与 200+ 人场地协调。"},
    )
    assert a_resp.status_code == 200
    assert a_resp.json()["ok"] is True
    assert a_resp.json()["data"]["session"]["current_step"] == 2

    # 6. DELETE /api/mining/sessions/{id} (删除)
    del_resp = client.delete(f"/api/mining/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["deleted"] is True
