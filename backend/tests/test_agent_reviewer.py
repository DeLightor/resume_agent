"""ReviewerAgent 测试（US-30 reviewer-agent Task 1）。

覆盖：
- review_draft：通过 / 打回（issues 透传）/ fail-open
  （LLM 未配置 / 调用异常 / 坏 JSON）
- review_evidence：迁移自 generate._run_reflection，
  形状兼容（issues_found/issues/notes）+ 未配置兜底
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from resume_agent.agents.reviewer import ReviewerAgent


class _ScriptedChatLLM:
    """chat() 按脚本返回字符串（或抛异常）的假 LLM。"""

    def __init__(self, script: list[Any], configured: bool = True) -> None:
        self.script = list(script)
        self.configured = configured
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        system_prompt: str,
        user_content: str,
        response_format_json: bool = False,
    ) -> str:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_content": user_content,
        })
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


_PASS_JSON = json.dumps(
    {"passed": True, "issues": [], "summary": "无问题"}, ensure_ascii=False
)
_FAIL_JSON = json.dumps(
    {
        "passed": False,
        "issues": [{"type": "cliche", "message": "「负责优化系统性能」无量化结果"}],
        "summary": "发现 1 处套话",
    },
    ensure_ascii=False,
)

_EVIDENCE = [
    {"chunk_text": "参与 XX 系统开发", "source_file": "a.pdf", "score": 0.9},
]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# === review_draft ===


def test_review_draft_pass() -> None:
    llm = _ScriptedChatLLM([_PASS_JSON])
    reviewer = ReviewerAgent(llm=llm)

    result = _run(reviewer.review_draft({"skills": ["Python"]}, None, _EVIDENCE))

    assert result["passed"] is True
    assert result["issues"] == []
    assert result["summary"] == "无问题"
    # 独立上下文：单次 chat，草稿与证据都进入 prompt
    assert len(llm.calls) == 1
    assert "Python" in llm.calls[0]["user_content"]
    assert "参与 XX 系统开发" in llm.calls[0]["user_content"]


def test_review_draft_reject_with_jd() -> None:
    llm = _ScriptedChatLLM([_FAIL_JSON])
    reviewer = ReviewerAgent(llm=llm)

    result = _run(
        reviewer.review_draft({"skills": ["编造"]}, {"job_title": "后端工程师"}, [])
    )

    assert result["passed"] is False
    assert result["issues"][0]["type"] == "cliche"
    assert result["summary"] == "发现 1 处套话"
    # structured_jd 注入审查 prompt
    assert "后端工程师" in llm.calls[0]["user_content"]


def test_review_draft_llm_not_configured_fail_open() -> None:
    llm = _ScriptedChatLLM([], configured=False)
    reviewer = ReviewerAgent(llm=llm)

    result = _run(reviewer.review_draft({"skills": []}, None, []))

    assert result["passed"] is True
    assert result["issues"] == []
    assert "跳过" in result["summary"]
    assert llm.calls == []


def test_review_draft_llm_error_fail_open() -> None:
    llm = _ScriptedChatLLM([RuntimeError("boom")])
    reviewer = ReviewerAgent(llm=llm)

    result = _run(reviewer.review_draft({"skills": []}, None, []))

    assert result["passed"] is True
    assert "跳过" in result["summary"]


def test_review_draft_bad_json_fail_open() -> None:
    llm = _ScriptedChatLLM(["这不是 JSON"])
    reviewer = ReviewerAgent(llm=llm)

    result = _run(reviewer.review_draft({"skills": []}, None, []))

    assert result["passed"] is True
    assert "跳过" in result["summary"]


# === review_evidence（反思迁移）===

_EVIDENCE_JSON = json.dumps(
    {
        "issues_found": 2,
        "issues": [{"type": "套话", "description": "空泛", "source": "a.pdf"}],
        "notes": "发现 2 处问题",
    },
    ensure_ascii=False,
)


def test_review_evidence_shape_compatible() -> None:
    llm = _ScriptedChatLLM([_EVIDENCE_JSON])
    reviewer = ReviewerAgent(llm=llm)

    result = _run(reviewer.review_evidence(_EVIDENCE))

    assert result["issues_found"] == 2
    assert result["issues"][0]["type"] == "套话"
    assert result["notes"] == "发现 2 处问题"


def test_review_evidence_not_configured_fallback() -> None:
    llm = _ScriptedChatLLM([], configured=False)
    reviewer = ReviewerAgent(llm=llm)

    result = _run(reviewer.review_evidence(_EVIDENCE))

    assert result["issues_found"] == 0
    assert result["issues"] == []
    assert "LLM 未配置" in result["notes"]
    assert llm.calls == []


def test_review_evidence_error_fallback() -> None:
    llm = _ScriptedChatLLM([RuntimeError("断网")])
    reviewer = ReviewerAgent(llm=llm)

    result = _run(reviewer.review_evidence(_EVIDENCE))

    assert result["issues_found"] == 0
    assert result["issues"] == []
    assert "审核跳过" in result["notes"]
