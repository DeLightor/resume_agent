"""字段置信度判定（US-31 解析确认流）。

基于**源文本回查**的确定性判定，不使用 LLM 自报（自报置信度不可验证，
与项目「诚实性结构性保证」原则冲突）：

- high：字段值归一化后命中简历原文；
- medium：列表条目关键字段部分命中；
- low：未命中或字段为空（缺失同样标低，供确认界面高亮关注）。

条目级关键字段：education=(school, degree)、experience=(company, role)、
projects=(name, role)。叶子字段（包括 highlights/description）分别回查；条目级汇总保留兼容。
"""

from __future__ import annotations

import unicodedata

from resume_agent.parsers.extractor import StructuredResume

# 归一化时剔除的标点（不含空白，空白单独判）
_STRIP_CHARS = set("-_—–·、，。：:;；()（）[]【】.,\"'’‘“”|/\\!?！？…<>《》")

# 列表条目级关键字段
_ENTRY_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "education": ("school", "degree"),
    "experience": ("company", "role"),
    "projects": ("name", "role"),
}

# basic 参与判定的叶子字段
_BASIC_FIELDS: tuple[str, ...] = (
    "name",
    "gender",
    "birth_date",
    "phone",
    "email",
    "location",
    "website",
    "github",
    "linkedin",
)


def normalize(text: str) -> str:
    """归一化文本：NFKC 全角转半角 + 小写 + 去空白与常见标点。

    Args:
        text: 原始文本。

    Returns:
        归一化后的字符串（可能为空）。
    """
    s = unicodedata.normalize("NFKC", str(text)).lower()
    return "".join(ch for ch in s if not ch.isspace() and ch not in _STRIP_CHARS)


def _hit(value: str | None, raw_norm: str) -> bool:
    """判断字段值归一化后是否命中原文。"""
    if not value or not str(value).strip():
        return False
    normalized = normalize(value)
    return bool(normalized) and normalized in raw_norm


def _score_entry(item: object, key_fields: tuple[str, ...], raw_norm: str) -> str:
    """按关键字段聚合条目级置信度。

    全部非空关键字段命中 → high；部分命中 → medium；全未命中或全为空 → low。
    """
    values = [getattr(item, f, None) for f in key_fields]
    non_empty = [v for v in values if v and str(v).strip()]
    if not non_empty:
        return "low"
    hits = sum(1 for v in non_empty if _hit(v, raw_norm))
    if hits == len(non_empty):
        return "high"
    if hits > 0:
        return "medium"
    return "low"


def compute_confidence(resume: StructuredResume, raw_text: str) -> dict[str, dict[str, str]]:
    """计算结构化简历各字段的置信度。

    Args:
        resume: LLM 提取的结构化简历。
        raw_text: 简历原文（用于回查）。

    Returns:
        归属结构 ``{section: {field_or_index: "high"|"medium"|"low"}}``。
        ``primary_direction`` 为推断字段，不参与计分。
    """
    raw_norm = normalize(raw_text)

    result: dict[str, dict[str, str]] = {
        "basic": {
            field: ("high" if _hit(getattr(resume.basic, field), raw_norm) else "low")
            for field in _BASIC_FIELDS
        }
    }

    for section, items in (
        ("education", resume.education),
        ("experience", resume.experience),
        ("projects", resume.projects),
    ):
        key_fields = _ENTRY_KEY_FIELDS[section]
        result[section] = {
            str(idx): _score_entry(item, key_fields, raw_norm) for idx, item in enumerate(items)
        }

        for idx, item in enumerate(items):
            for field, value in item.model_dump().items():
                if isinstance(value, list):
                    for leaf_idx, leaf in enumerate(value):
                        result[section][f"{idx}.{field}.{leaf_idx}"] = (
                            "high" if _hit(leaf, raw_norm) else "low"
                        )
                else:
                    result[section][f"{idx}.{field}"] = "high" if _hit(value, raw_norm) else "low"

    result["skills"] = {
        str(idx): ("high" if _hit(skill, raw_norm) else "low")
        for idx, skill in enumerate(resume.skills)
    }

    return result


__all__ = ["compute_confidence", "normalize"]
