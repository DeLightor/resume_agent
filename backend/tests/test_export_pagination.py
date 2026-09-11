"""US-34: PDF 导出分页与一致性校验测试。"""
from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from resume_agent.export.pdf_builder import build_pdf, get_pdf_page_count
from resume_agent.main import app


def _make_single_page_resume() -> dict:
    """构造标准 1 页技术简历数据。"""
    return {
        "name": "张三",
        "email": "zhangsan@example.com",
        "phone": "13800138000",
        "experience": [
            {
                "company": "腾讯",
                "role": "推荐算法工程师",
                "period": "2021-至今",
                "highlights": [
                    "主导推荐召回模型升级，离线 AUC 提升 2%",
                    "设计分布式训练 pipeline，日均处理 10 亿条样本",
                ],
            }
        ],
        "projects": [
            {
                "name": "实时推荐系统",
                "role": "核心开发",
                "period": "2022-2023",
                "description": "从零搭建实时推荐服务",
                "tech_stack": ["Python", "PyTorch", "Kafka"],
            }
        ],
        "skills": {
            "tech_stack": [
                {"name": "Python", "context": "3 年后端开发经验"},
                {"name": "PyTorch", "context": "模型训练与部署"},
            ],
            "hard_skills": [
                {"name": "模型训练", "context": "推荐系统召回排序"},
            ],
            "soft_skills": [
                {"name": "跨团队协作", "context": "与产品/设计团队对接"},
            ],
        },
    }


def _make_multi_page_resume() -> dict:
    """构造故意超长的多页简历数据。"""
    experiences = []
    for i in range(8):
        experiences.append({
            "company": f"科技公司 {i+1}",
            "role": f"资深架构师 {i+1}",
            "period": f"201{i}-201{i+1}",
            "highlights": [
                f"负责核心分布式系统重构，QPS 从 10K 提升至 100K，系统可用性达到 99.999%（第 {i+1} 期）",
                "主导跨机房容灾建设，完成 5 个数据中心多活架构部署，降低故障恢复时间至 30 秒内",
                "带领 20 人研发团队，推进敏捷开发规范与代码门禁机制，缺陷率下降 45%",
                "设计高吞吐实时数据流处理管道，日均处理数据量达 50TB",
            ],
        })

    projects = []
    for i in range(5):
        projects.append({
            "name": f"大型分布式平台项目 {i+1}",
            "role": "技术负责人",
            "period": "2020-2022",
            "description": "面向海量高并发场景的企业级分布式微服务与数据服务底座。",
            "tech_stack": ["Go", "Kubernetes", "Kafka", "Redis", "MySQL"],
        })

    return {
        "name": "李四 (超长经历)",
        "email": "lisi_architect@example.com",
        "phone": "13900139000",
        "summary": "10 年以上分布式系统架构经验，精通高并发高可用架构设计与团队管理。",
        "experience": experiences,
        "projects": projects,
        "skills": {
            "tech_stack": [{"name": f"技能 {k}", "context": "深入掌握"} for k in range(15)],
            "hard_skills": [{"name": f"专业硬实力 {k}", "context": "专家级"} for k in range(10)],
            "soft_skills": [{"name": f"综合软技能 {k}", "context": "精通"} for k in range(5)],
        },
    }


def test_get_pdf_page_count_helper() -> None:
    """测试 PDF 页数提取辅助函数。"""
    single_data = _make_single_page_resume()
    pdf_bytes = build_pdf(single_data, template_id="modern")
    page_count = get_pdf_page_count(pdf_bytes)
    assert page_count == 1

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count == 1


def test_single_page_resume_all_templates() -> None:
    """测试标准单页简历在常见模板下生成 1 页。"""
    single_data = _make_single_page_resume()
    # 测试主要模板
    for template_id in ["modern", "classic", "tech", "minimal"]:
        pdf_bytes = build_pdf(single_data, template_id=template_id)
        page_count = get_pdf_page_count(pdf_bytes)
        assert page_count == 1, f"模板 {template_id} 预期 1 页，实际生成 {page_count} 页"


def test_multi_page_resume_overflow() -> None:
    """测试超长内容多页简历生成页数大于 1。"""
    multi_data = _make_multi_page_resume()
    pdf_bytes = build_pdf(multi_data, template_id="modern")
    page_count = get_pdf_page_count(pdf_bytes)
    assert page_count >= 2, f"超长简历预期至少 2 页，实际生成 {page_count} 页"


def test_export_pdf_response_header() -> None:
    """测试 /api/export/pdf 响应头返回 X-Page-Count。"""
    client = TestClient(app)
    response = client.post(
        "/api/export/pdf",
        json={"resume_data": _make_single_page_resume(), "template_id": "modern"},
    )
    assert response.status_code == 200
    assert "x-page-count" in response.headers
    assert response.headers["x-page-count"] == "1"


def test_export_page_count_endpoint() -> None:
    """测试 /api/export/page_count 端点直接返回页数。"""
    client = TestClient(app)
    # 单页
    resp1 = client.post(
        "/api/export/page_count",
        json={"resume_data": _make_single_page_resume(), "template_id": "modern"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["data"]["page_count"] == 1

    # 多页
    resp2 = client.post(
        "/api/export/page_count",
        json={"resume_data": _make_multi_page_resume(), "template_id": "modern"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["data"]["page_count"] >= 2
