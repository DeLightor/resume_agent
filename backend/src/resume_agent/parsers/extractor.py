"""简历结构化提取器。

使用 LLM 从简历纯文本提取结构化数据，输出 ``StructuredResume`` Pydantic 模型。
对齐 design.md 第 2.3 节。

Prompt 设计要点：
- System prompt 明确角色：「你是简历解析专家」
- 要求输出 JSON，字段固定
- 明确禁止编造：找不到的字段返回 null 或空数组
- 要求推断 ``primary_direction``：基于技能和经历关键词匹配
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from resume_agent.llm.client import LLMClient

# 合法的 primary_direction 取值，用于提示模型在受限集合内推断
_VALID_DIRECTIONS: tuple[str, ...] = (
    "安全",
    "算法",
    "后端",
    "前端",
    "数据",
    "产品",
    "其他",
)

_SYSTEM_PROMPT = f"""你是简历解析专家，擅长从简历纯文本中提取结构化信息。

要求：
1. 严格基于文本内容提取，禁止编造任何未在简历中出现的字段。
2. 找不到的字段返回 null（对象字段）或空数组（列表字段）。
3. 输出必须是合法的 JSON 对象，字段固定为：
   - basic: {{name, gender, birth_date, phone, email, location, website, github, linkedin}}
   - education: [{{school, degree, major, period}}]
   - experience: [{{company, role, period, highlights: [string]}}]
   - projects: [{{name, role, description}}]
   - skills: [string]
   - primary_direction: string  # 基于技能和经历关键词推断主方向
4. primary_direction 必须从以下取值中选择：
   {list(_VALID_DIRECTIONS)}
5. basic 字段说明：
   - name: 姓名
   - gender: 性别
   - birth_date: 出生年月
   - phone: 手机号码
   - email: 电子邮箱
   - location: 所在城市
   - website: 个人网站/博客
   - github: GitHub 主页地址
   - linkedin: LinkedIn 主页地址
6. 不要输出任何 JSON 之外的解释性文字。"""

_USER_PROMPT_TEMPLATE = """请解析以下简历文本，按规范输出 JSON：

---
{raw_text}
---"""


# === Pydantic 模型 ===


class BasicInfo(BaseModel):
    """基本信息。"""

    name: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    phone: str | None = None
    email: str | None = None
    location: str | None = None
    website: str | None = None
    github: str | None = None
    linkedin: str | None = None


class EducationItem(BaseModel):
    """教育经历条目。"""

    school: str | None = None
    degree: str | None = None
    major: str | None = None
    period: str | None = None


class ExperienceItem(BaseModel):
    """工作经历条目。"""

    company: str | None = None
    role: str | None = None
    period: str | None = None
    highlights: list[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    """项目经历条目。"""

    name: str | None = None
    role: str | None = None
    description: str | None = None


class StructuredResume(BaseModel):
    """结构化简历数据模型。

    对齐 design.md 第 2.3 节，由 LLM 提取后填充。
    """

    basic: BasicInfo = Field(default_factory=BasicInfo)
    education: list[EducationItem] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    primary_direction: str = "其他"

    @field_validator("primary_direction", mode="before")
    @classmethod
    def _normalize_direction(cls, value: Any) -> Any:
        """若方向不在合法集合内，归一为「其他」。"""
        if isinstance(value, str) and value in _VALID_DIRECTIONS:
            return value
        return "其他"


class ResumeExtractor:
    """使用 LLM 从简历纯文本提取结构化数据。

    Attributes:
        llm_client: ``LLMClient`` 实例，用于发送 chat completion 请求。
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """初始化提取器。

        Args:
            llm_client: 已配置的 LLM 客户端实例。
        """
        self.llm_client = llm_client

    async def extract(self, raw_text: str) -> StructuredResume:
        """从简历纯文本提取结构化数据。

        Args:
            raw_text: 简历纯文本（由 PDF/DOCX 解析器提取）。

        Returns:
            解析后的 ``StructuredResume`` 对象。

        Raises:
            RuntimeError: LLM 未配置或返回无法解析的 JSON。
            ValidationError: LLM 返回的 JSON 不符合 ``StructuredResume`` schema。
        """
        user_prompt = _USER_PROMPT_TEMPLATE.format(raw_text=raw_text)
        response_text = await self.llm_client.chat(
            system_prompt=_SYSTEM_PROMPT,
            user_content=user_prompt,
            response_format_json=True,
        )

        data = _parse_json_safely(response_text)
        try:
            return StructuredResume.model_validate(data)
        except ValidationError:
            # 重新抛出，由上层决定如何处理（标记为 needs_review 等）
            raise


def _parse_json_safely(text: str) -> dict[str, Any]:
    """安全解析可能包含前后噪声的 JSON 文本。

    LLM 偶尔会在 JSON 前后加 markdown 代码块标记或解释性文字，
    尝试提取第一个 ``{`` 到最后一个 ``}`` 之间的子串。

    Args:
        text: LLM 返回的原始文本。

    Returns:
        解析后的字典。

    Raises:
        RuntimeError: 文本无法解析为 JSON 对象。
    """
    cleaned = text.strip()
    # 去除可能的 markdown 代码块标记
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试截取首尾大括号之间的内容
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                data = json.loads(cleaned[first : last + 1])
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"LLM 返回内容无法解析为 JSON: {exc}") from exc
        else:
            raise RuntimeError("LLM 返回内容无法解析为 JSON") from None

    if not isinstance(data, dict):
        raise RuntimeError(f"LLM 返回的 JSON 不是对象: {type(data).__name__}")
    return data


__all__ = [
    "BasicInfo",
    "EducationItem",
    "ExperienceItem",
    "ProjectItem",
    "ResumeExtractor",
    "StructuredResume",
]
