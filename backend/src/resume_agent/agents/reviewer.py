"""Reviewer Agent（US-30 reviewer-agent）。

独立上下文审查者：每次审查都是全新的 LLM 调用（system prompt +
草稿/证据），**不复用 Orchestrator 的对话历史**——对草稿无「忠诚度」。

两类入口：
- ``review_draft``：审查 Agent 待写入草稿（write_node 门禁前双审），
  检查项与 PRD US-30 验收标准一一对应（知识库边界 / 套话 /
  JD 关键词覆盖 / 量化数字无来源）。
- ``review_evidence``：审核知识库检索片段（迁移自
  ``api/generate._run_reflection``，返回形状兼容）。

安全默认（fail-open）：LLM 未配置、调用异常或 JSON 解析失败时
放行（passed=True / 空兜底），审查是质量增强，不阻塞功能可用。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("resume_agent")

# 草稿审查：独立 system prompt（不携带 Orchestrator 历史）
_REVIEW_DRAFT_PROMPT = """你是 Resume-Agent 的独立简历审查官（Reviewer），在内容写入用户简历前做最终质量把关。
你与起草内容的 Agent 相互独立，必须以批判视角审查，不受起草者影响。

审查维度：
1. knowledge_boundary（知识库边界）：草稿中的经历/技能/项目能否在提供的知识库证据中找到依据？无依据的内容属于编造风险，必须标出。
2. cliche（套话）：空洞、缺乏具体事实的表述（如「负责优化系统性能」无量化结果、「精通」「熟练掌握」无佐证）。
3. jd_coverage（JD 关键词覆盖）：给定目标 JD 时，草稿是否覆盖 JD 的核心关键词？重要缺口需标出。
4. unverified_number（数字无来源）：草稿中的量化数字（百分比、金额、规模）是否能在证据中找到来源？无来源的数字必须标出。

判定原则：
- 证据为空时，knowledge_boundary 与 unverified_number 降级为「无法核验」，不要凭空标红；其余维度照常审查。
- passed 为 true 仅当不存在必须修改的问题；summary 用一句中文概括结论。

输出 JSON：
{
  "passed": bool,
  "issues": [
    {"type": "knowledge_boundary/cliche/jd_coverage/unverified_number/other", "message": "具体问题描述"}
  ],
  "summary": "一句话结论"
}"""

# 片段审核：迁移自 generate._REFLECTION_PROMPT（语义不变）
_EVIDENCE_REVIEW_PROMPT = """你是简历内容审核专家。我会给你一些从知识库中检索到的真实经历片段。
请审核这些内容，检测以下问题：

1. 套话：空洞、缺乏具体数据的表述（如"负责优化系统性能"无量化结果）
2. 前后矛盾：同一经历在不同片段中描述不一致
3. 夸大表述：超出知识库记录范围的夸大（如知识库说"参与"，描述为"主导"）

输出 JSON：
{
  "issues_found": int,        // 发现的问题数量
  "issues": [                // 问题列表
    {"type": "套话/矛盾/夸大", "description": "...", "source": "..."}
  ],
  "notes": "string"          // 总体评价
}

如果没有问题，issues_found 为 0，issues 为空数组，notes 说明内容质量良好。"""

__all__ = ["ReviewerAgent"]


def _parse_json_safely(response: str) -> dict[str, Any]:
    """宽松解析 LLM 返回的 JSON（容忍 markdown 代码块等包裹）。"""
    cleaned = (response or "").strip()
    if cleaned.startswith("```"):
        # 去掉 ```json / ``` 包裹
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            data = json.loads(cleaned[first : last + 1])
        else:
            raise
    if not isinstance(data, dict):
        raise ValueError(f"期望 JSON 对象，得到 {type(data).__name__}")
    return data


def _format_evidence(evidence: list[dict[str, Any]]) -> str:
    """证据列表 → prompt 文本。"""
    if not evidence:
        return "（无证据）"
    lines = []
    for i, e in enumerate(evidence, 1):
        source = str(e.get("source_file", ""))
        text = str(e.get("chunk_text", ""))
        lines.append(f"[{i}] 来源: {source}\n内容: {text}")
    return "\n\n".join(lines)


class ReviewerAgent:
    """独立上下文的审查 Agent（US-30）。"""

    def __init__(self, llm: Any | None = None) -> None:
        if llm is None:
            from resume_agent.llm.client import LLMClient

            llm = LLMClient()
        self.llm = llm

    async def review_draft(
        self,
        content: dict[str, Any],
        structured_jd: dict[str, Any] | None,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """审查待写入草稿。

        Args:
            content: write_node 的草稿内容。
            structured_jd: 会话上下文中的结构化 JD（可为 None）。
            evidence: 知识库检索证据（可为空，边界检查降级）。

        Returns:
            ``{passed: bool, issues: [{type, message}], summary: str}``；
            LLM 不可用/异常时 fail-open 放行。
        """
        if not getattr(self.llm, "configured", False):
            return {"passed": True, "issues": [], "summary": "LLM 未配置，跳过审查"}

        user_content = (
            "待写入草稿（JSON）：\n"
            + json.dumps(content, ensure_ascii=False, indent=2)
            + "\n\n目标 JD（JSON）：\n"
            + (
                json.dumps(structured_jd, ensure_ascii=False, indent=2)
                if structured_jd
                else "（无）"
            )
            + "\n\n知识库证据：\n"
            + _format_evidence(evidence)
            + "\n\n请按审查维度输出 JSON 判定。"
        )
        try:
            response = await self.llm.chat(
                system_prompt=_REVIEW_DRAFT_PROMPT,
                user_content=user_content,
                response_format_json=True,
            )
            data = _parse_json_safely(response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("草稿审查失败，fail-open 放行: %s", exc)
            return {"passed": True, "issues": [], "summary": f"审查跳过: {exc}"}

        raw_issues = data.get("issues")
        issues = [
            i for i in (raw_issues if isinstance(raw_issues, list) else [])
            if isinstance(i, dict)
        ]
        return {
            "passed": bool(data.get("passed")),
            "issues": issues,
            "summary": str(data.get("summary", "")),
        }

    async def review_evidence(
        self, evidence: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """审核知识库检索片段（迁移自 generate._run_reflection，行为兼容）。

        Returns:
            ``{issues_found: int, issues: [...], notes: str}``。
        """
        if not getattr(self.llm, "configured", False):
            return {"issues_found": 0, "issues": [], "notes": "LLM 未配置，跳过审核"}

        user_content = f"请审核以下知识库检索到的经历片段：\n\n{_format_evidence(evidence)}"

        try:
            response = await self.llm.chat(
                system_prompt=_EVIDENCE_REVIEW_PROMPT,
                user_content=user_content,
                response_format_json=True,
            )
            result = _parse_json_safely(response)
            return {
                "issues_found": result.get("issues_found", 0),
                "issues": result.get("issues", []),
                "notes": result.get("notes", ""),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("反思审核失败: %s", exc)
            return {
                "issues_found": 0,
                "issues": [],
                "notes": f"审核跳过: {exc}",
            }
