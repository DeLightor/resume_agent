"""JD 文本结构化提取服务（US-27 agent-runtime 抽取自 api/jd.py）。

原 jd.py 端点中的 LLM 结构化提取逻辑纯移动，行为不变。
截图 / PDF → 文本的 MinerU 解析不在本服务范围（属上传链路）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from resume_agent.llm.client import LLMClient

logger = logging.getLogger("resume_agent")

# 结构化提取 system prompt（原 jd.py 模块常量）
SYSTEM_PROMPT = """你是 JD（职位描述）解析专家，擅长从职位描述文本中提取结构化信息。

要求：
1. 严格基于文本内容提取，禁止编造未在 JD 中出现的字段。
2. 输入文本可能来自多张截图 / PDF / 纯文本的合并，可能包含重复内容。请去重后提取，确保各字段值不重复。
3. 找不到的字段返回空字符串（字符串字段）或空数组（列表字段）。
4. 输出必须是合法的 JSON 对象，字段固定为：
   - job_title: string           # 职位名称
   - company: string             # 公司名称
   - tech_stack: [string]        # 技术栈（如 Python、React、K8s）
   - hard_skills: [string]       # 硬技能（如模型训练、系统设计）
   - soft_skills: [string]       # 软技能（如沟通、团队协作）
   - bonus_items: [string]       # 加分项（如顶会论文、开源贡献）
5. 不要输出任何 JSON 之外的解释性文字。"""

_USER_PROMPT_TEMPLATE = """请解析以下 JD 文本，按规范输出 JSON（注意去重）：

---
{raw_text}
---"""


def _parse_json_safely(text: str) -> dict[str, Any]:
    """安全解析可能包含前后噪声的 JSON 文本。"""
    cleaned = text.strip()
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
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                data = json.loads(cleaned[first : last + 1])
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"LLM 返回内容无法解析为 JSON: {exc}"
                ) from exc
        else:
            raise RuntimeError("LLM 返回内容无法解析为 JSON") from None

    if not isinstance(data, dict):
        raise RuntimeError(
            f"LLM 返回的 JSON 不是对象: {type(data).__name__}"
        )
    return data


async def extract_jd_fields(raw_text: str) -> dict[str, Any]:
    """对 JD 纯文本做 LLM 结构化提取。

    Args:
        raw_text: 已解析为文本的 JD 内容（可多份合并）。

    Returns:
        结构化字段 dict（job_title / company / tech_stack / ...）。

    Raises:
        RuntimeError: LLM 未配置，或返回内容无法解析。
    """
    llm = LLMClient()
    if not llm.configured:
        raise RuntimeError("LLM 未配置，无法进行结构化提取")

    user_prompt = _USER_PROMPT_TEMPLATE.format(raw_text=raw_text)
    response_text = await llm.chat(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_prompt,
        response_format_json=True,
    )
    return _parse_json_safely(response_text)


__all__ = ["extract_jd_fields", "SYSTEM_PROMPT"]
