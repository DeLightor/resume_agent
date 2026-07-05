"""AI 简历生成端点（US-6）。

3 步工作流：检索 → 反思 → 撰写。

1. 检索：对 JD 中每项技能（tech_stack + hard_skills），在知识库中检索 top-3
   经历切片，合并去重。
2. 反思：LLM 审核检索到的内容，检测套话、前后矛盾、夸大表述。
3. 撰写：LLM 基于检索内容 + 反思结果，生成目标段落。

不引入 LangGraph，用简单函数链实现等价工作流。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from resume_agent.api.response import error, success

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/generate", tags=["generate"])

# 检索配置
_SEARCH_TOP_K: int = 3
_MAX_EVIDENCE_CHUNKS: int = 10  # 合并后最多保留的切片数

# 段落类型
_SECTIONS: tuple[str, ...] = ("experience", "projects", "skills")

# === System Prompts ===

_REFLECTION_PROMPT = """你是简历内容审核专家。我会给你一些从知识库中检索到的真实经历片段。
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

_WRITER_PROMPT_EXPERIENCE = """你是资深简历撰写专家。基于以下知识库检索到的真实经历片段和审核反馈，生成定制化的工作经历段落。

要求：
1. 严格基于检索到的内容撰写，禁止编造未在材料中出现的经历
2. 每段经历包含：company, role, period, highlights（2-3 条）
3. highlights 用 STAR 法则描述（情境-任务-行动-结果），优先包含量化数据
4. 参考审核反馈，避免套话和夸大
5. 如果 JD 提供了目标岗位，经历描述应向该岗位靠拢

输出 JSON：
{
  "experience": [
    {
      "company": "string",
      "role": "string",
      "period": "string",
      "highlights": ["string", ...]
    }
  ]
}"""

_WRITER_PROMPT_PROJECTS = """你是资深简历撰写专家。基于以下知识库检索到的真实经历片段和审核反馈，生成定制化的项目经历段落。

要求：
1. 严格基于检索到的内容撰写，禁止编造
2. 每个项目包含：name, role, period, description, tech_stack
3. description 用 2-3 句话说明项目内容和你的贡献
4. 参考审核反馈，避免套话和夸大

输出 JSON：
{
  "projects": [
    {
      "name": "string",
      "role": "string",
      "period": "string",
      "description": "string",
      "tech_stack": ["string", ...]
    }
  ]
}"""

_WRITER_PROMPT_SKILLS = """你是资深简历撰写专家。基于以下知识库检索到的真实经历片段和 JD 要求，生成技能总结段落。

要求：
1. 严格基于检索到的内容，只列出知识库中有实际使用记录的技能
2. 按 JD 中的分类组织：技术栈、硬技能、软技能
3. 每项技能附一句简短的实际使用场景说明
4. 参考审核反馈，避免夸大

输出 JSON：
{
  "skills": {
    "tech_stack": [{"name": "string", "context": "string"}],
    "hard_skills": [{"name": "string", "context": "string"}],
    "soft_skills": [{"name": "string", "context": "string"}]
  }
}"""

_SECTION_PROMPTS = {
    "experience": _WRITER_PROMPT_EXPERIENCE,
    "projects": _WRITER_PROMPT_PROJECTS,
    "skills": _WRITER_PROMPT_SKILLS,
}


class GenerateRequest(BaseModel):
    """AI 生成请求体。"""

    structured_jd: dict[str, Any]
    gap_report: dict[str, Any] | None = None
    section: str = "experience"


def _collect_search_queries(structured_jd: dict[str, Any]) -> list[str]:
    """从 JD 结构化数据中收集检索查询词。"""
    queries: list[str] = []
    for key in ("tech_stack", "hard_skills", "soft_skills", "bonus_items"):
        items = structured_jd.get(key, [])
        if isinstance(items, list):
            queries.extend(s for s in items if isinstance(s, str) and s)
    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


def _search_knowledge_base(queries: list[str]) -> list[dict[str, Any]]:
    """对多个查询词在知识库中检索，合并去重。

    Returns:
        [{"chunk_text": ..., "source_file": ..., "score": ...}, ...]
    """
    if not queries:
        return []

    from resume_agent.rag.chroma_client import get_knowledge_collection

    collection = get_knowledge_collection()
    if collection.count() == 0:
        return []

    all_results: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    for query in queries:
        try:
            result = collection.query(
                query_texts=[query], n_results=_SEARCH_TOP_K
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("检索 %s 失败: %s", query, exc)
            continue

        ids = result.get("ids", [[]])
        documents = result.get("documents", [[]])
        metadatas = result.get("metadatas", [[]])
        distances = result.get("distances", [[]])

        if not ids or not ids[0]:
            continue

        for idx in range(len(ids[0])):
            doc = documents[0][idx] if idx < len(documents[0]) else ""
            meta = metadatas[0][idx] if idx < len(metadatas[0]) else {}
            distance = distances[0][idx] if idx < len(distances[0]) else 1.0
            score = max(0.0, 1.0 - distance) if distance is not None else 0.0
            source_file = (
                meta.get("source_file", "") if isinstance(meta, dict) else ""
            )

            # 用 chunk_text 前 100 字做去重键
            dedup_key = doc[:100] if doc else ""
            if dedup_key in seen_texts:
                continue
            seen_texts.add(dedup_key)

            all_results.append({
                "chunk_text": doc[:300],  # 截断避免 prompt 过长
                "source_file": source_file,
                "score": round(score, 4),
            })

    # 按 score 降序，取 top N
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:_MAX_EVIDENCE_CHUNKS]


def _format_evidence_for_prompt(evidence: list[dict[str, Any]]) -> str:
    """格式化检索结果为 LLM prompt 中的文本。"""
    if not evidence:
        return "（知识库为空，无检索结果）"
    lines = []
    for i, e in enumerate(evidence, 1):
        lines.append(
            f"[{i}] 来源: {e['source_file']} (相关度: {e['score']})\n"
            f"内容: {e['chunk_text']}"
        )
    return "\n\n".join(lines)


def _parse_json_safely(text: str) -> dict[str, Any]:
    """安全解析 JSON 文本，处理 markdown 包裹。"""
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
                raise RuntimeError(f"JSON 解析失败: {exc}") from exc
        else:
            raise RuntimeError("无法解析为 JSON") from None

    if not isinstance(data, dict):
        raise RuntimeError(f"期望 JSON 对象，得到 {type(data).__name__}")
    return data


async def _run_reflection(
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """第 2 步：反思审核。"""
    from resume_agent.llm.client import LLMClient

    llm = LLMClient()
    if not llm.configured:
        return {"issues_found": 0, "issues": [], "notes": "LLM 未配置，跳过审核"}

    evidence_text = _format_evidence_for_prompt(evidence)
    user_content = f"请审核以下知识库检索到的经历片段：\n\n{evidence_text}"

    try:
        response = await llm.chat(
            system_prompt=_REFLECTION_PROMPT,
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


async def _run_writer(
    section: str,
    structured_jd: dict[str, Any],
    evidence: list[dict[str, Any]],
    reflection: dict[str, Any],
) -> dict[str, Any]:
    """第 3 步：撰写段落。"""
    from resume_agent.llm.client import LLMClient

    llm = LLMClient()
    if not llm.configured:
        raise RuntimeError("LLM 未配置，无法生成简历内容")

    system_prompt = _SECTION_PROMPTS.get(section, _WRITER_PROMPT_EXPERIENCE)
    evidence_text = _format_evidence_for_prompt(evidence)
    jd_summary = json.dumps(structured_jd, ensure_ascii=False, indent=2)
    reflection_text = json.dumps(reflection, ensure_ascii=False, indent=2)

    user_content = f"""目标 JD：
{jd_summary}

知识库检索到的经历片段：
{evidence_text}

审核反馈：
{reflection_text}

请生成 {section} 段落。"""

    try:
        response = await llm.chat(
            system_prompt=system_prompt,
            user_content=user_content,
            response_format_json=True,
        )
        return _parse_json_safely(response)
    except Exception as exc:
        raise RuntimeError(f"撰写失败: {exc}") from exc


@router.post("")
async def generate(req: GenerateRequest) -> dict[str, Any]:
    """AI 生成简历内容。

    3 步工作流：检索 → 反思 → 撰写。

    Args:
        req: 生成请求。

    Returns:
        统一响应 envelope。
    """
    if req.section not in _SECTIONS:
        return error(
            "INVALID_SECTION",
            f"不支持的段落类型: {req.section}，仅支持 {list(_SECTIONS)}",
        )

    if not req.structured_jd:
        return error("INVALID_REQUEST", "structured_jd 不能为空")

    # 1. 检索知识库
    queries = _collect_search_queries(req.structured_jd)
    evidence = _search_knowledge_base(queries)
    sources_used = len(evidence)

    if sources_used == 0:
        return error(
            "EMPTY_KNOWLEDGE_BASE",
            "知识库为空，请先上传素材文档",
        )

    # 2. 反思审核
    reflection = await _run_reflection(evidence)

    # 3. 撰写段落
    try:
        content = await _run_writer(
            req.section, req.structured_jd, evidence, reflection
        )
    except RuntimeError as exc:
        logger.warning("撰写失败: %s", exc)
        return error("GENERATE_FAILED", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("撰写异常")
        return error("GENERATE_FAILED", f"生成异常: {exc}")

    return success({
        "section": req.section,
        "content": content,
        "reflection": reflection,
        "sources_used": sources_used,
    })
