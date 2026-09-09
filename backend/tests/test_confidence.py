"""parsers/confidence.py 单元测试（US-31 解析确认流）。

置信度基于源文本回查的确定性判定：
- high：字段值归一化后命中简历原文；
- medium：列表条目关键字段部分命中；
- low：未命中或字段为空。
"""

from __future__ import annotations

from resume_agent.parsers.confidence import compute_confidence, normalize
from resume_agent.parsers.extractor import (
    BasicInfo,
    EducationItem,
    ExperienceItem,
    ProjectItem,
    StructuredResume,
)

RAW_TEXT = """张三
电话：13800138000
邮箱：zhangsan@example.com
北京
教育背景
某大学 硕士 计算机机 2018-2021
工作经历
Tencent 安全研究员 2021-至今
负责云安全
项目经历
漏洞平台 负责人
技能
Python 安全"""


def _make_resume(**overrides: object) -> StructuredResume:
    data: dict = {
        "basic": BasicInfo(name="张三", phone="13800138000", email="zhangsan@example.com"),
        "education": [
            EducationItem(school="某大学", degree="硕士", major="计算机", period="2018-2021")
        ],
        "experience": [ExperienceItem(company="Tencent", role="安全研究员", period="2021-至今")],
        "projects": [ProjectItem(name="漏洞平台", role="负责人", description="扫描")],
        "skills": ["Python", "安全"],
    }
    data.update(overrides)
    return StructuredResume.model_validate(
        {
            "basic": data["basic"].model_dump(),
            "education": [e.model_dump() for e in data["education"]],
            "experience": [e.model_dump() for e in data["experience"]],
            "projects": [p.model_dump() for p in data["projects"]],
            "skills": data["skills"],
        }
    )


class TestNormalize:
    def test_strips_whitespace_and_punct(self) -> None:
        assert normalize("  Zhang-San, PhD. ") == "zhangsanphd"

    def test_fullwidth_to_halfwidth(self) -> None:
        assert normalize("１３８００") == "13800"

    def test_cjk_untouched(self) -> None:
        assert normalize("张三") == "张三"


class TestBasicConfidence:
    def test_hit_is_high(self) -> None:
        resume = _make_resume()
        conf = compute_confidence(resume, RAW_TEXT)
        assert conf["basic"]["name"] == "high"
        assert conf["basic"]["phone"] == "high"
        assert conf["basic"]["email"] == "high"

    def test_miss_is_low(self) -> None:
        # 电话在原文中不存在（LLM 幻觉场景）
        resume = _make_resume()
        conf = compute_confidence(resume, "只有姓名张三的文本")
        assert conf["basic"]["phone"] == "low"

    def test_empty_field_is_low(self) -> None:
        resume = _make_resume()
        conf = compute_confidence(resume, RAW_TEXT)
        assert conf["basic"]["gender"] == "low"

    def test_formatting_difference_still_hits(self) -> None:
        # 原文带横线/空格，提取值不带 → 归一化后命中
        resume = _make_resume()
        conf = compute_confidence(resume, "电话 138-0013-8000 联系方式")
        assert conf["basic"]["phone"] == "high"


class TestListEntryConfidence:
    def test_all_key_fields_hit_is_high(self) -> None:
        resume = _make_resume()
        conf = compute_confidence(resume, RAW_TEXT)
        assert conf["experience"]["0"] == "high"
        assert conf["education"]["0"] == "high"
        assert conf["projects"]["0"] == "high"

    def test_partial_hit_is_medium(self) -> None:
        # 只命中 company，未命中 role
        raw = "曾在 Tencent 工作多年"
        resume = _make_resume()
        conf = compute_confidence(resume, raw)
        assert conf["experience"]["0"] == "medium"

    def test_no_hit_is_low(self) -> None:
        resume = _make_resume()
        conf = compute_confidence(resume, "完全不相关的文本")
        assert conf["experience"]["0"] == "low"
        assert conf["projects"]["0"] == "low"

    def test_skills_scored_individually(self) -> None:
        resume = _make_resume()
        conf = compute_confidence(resume, RAW_TEXT)
        assert conf["skills"]["0"] == "high"
        assert conf["skills"]["1"] == "high"

    def test_skill_miss_is_low(self) -> None:
        resume = _make_resume()
        conf = compute_confidence(resume, "技能：Python")
        assert conf["skills"]["0"] == "high"
        assert conf["skills"]["1"] == "low"

    def test_direction_not_scored(self) -> None:
        # primary_direction 是推断字段，不参与置信度
        resume = _make_resume()
        conf = compute_confidence(resume, RAW_TEXT)
        assert "primary_direction" not in conf


def test_punctuation_only_field_is_not_evidence() -> None:
    resume = _make_resume(basic=BasicInfo(name="---"))
    assert compute_confidence(resume, RAW_TEXT)["basic"]["name"] == "low"


def test_all_entry_leaves_have_independent_confidence() -> None:
    resume = _make_resume(
        experience=[
            ExperienceItem(
                company="Tencent",
                role="安全研究员",
                period="2099-2100",
                highlights=["负责云安全", "不存在的业绩"],
            )
        ]
    )
    result = compute_confidence(resume, RAW_TEXT)
    assert result["experience"]["0"] == "high"
    assert result["experience"]["0.company"] == "high"
    assert result["experience"]["0.period"] == "low"
    assert result["experience"]["0.highlights.0"] == "high"
    assert result["experience"]["0.highlights.1"] == "low"
    assert result["education"]["0.major"] == "high"
    assert result["projects"]["0.description"] == "low"
