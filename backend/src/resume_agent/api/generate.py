"""AI 简历生成端点（US-6）。

3 步工作流：检索 → 反思 → 撰写。

1. 检索：对 JD 中每项技能（tech_stack + hard_skills），在知识库中检索 top-3
   经历切片，合并去重。
2. 反思：LLM 审核检索到的内容，检测套话、前后矛盾、夸大表述
   （US-30 迁移至 ReviewerAgent.review_evidence，本模块不再持有实现）。
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
from resume_agent.services.knowledge_search import search_knowledge
from resume_agent.services.node_content import (
    get_node_content,
    save_node_content,
)

logger = logging.getLogger("resume_agent")

router = APIRouter(prefix="/generate", tags=["generate"])

# 段落类型
_SECTIONS: tuple[str, ...] = ("experience", "projects", "skills")

# === System Prompts ===

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

_WRITER_PROMPT_SUMMARY = """你是资深简历撰写专家。基于以下知识库检索到的真实经历片段和 JD 要求，生成 2-3 句自我评价。

要求：
1. 严格基于检索到的内容，不编造
2. 突出核心竞争力和与目标岗位的匹配度
3. 简洁有力，避免套话
4. 2-3 句话，总字数 50-100 字

输出 JSON：
{
  "summary": "string"
}"""

_SECTION_PROMPTS = {
    "experience": _WRITER_PROMPT_EXPERIENCE,
    "projects": _WRITER_PROMPT_PROJECTS,
    "skills": _WRITER_PROMPT_SKILLS,
    "summary": _WRITER_PROMPT_SUMMARY,
}

# 全量生成时的段落列表
_FULL_SECTIONS: tuple[str, ...] = ("summary", "experience", "projects", "skills")


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
    """第 2 步：反思审核（US-30 迁移至 ReviewerAgent.review_evidence）。"""
    from resume_agent.agents.reviewer import ReviewerAgent

    return await ReviewerAgent().review_evidence(evidence)


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
    evidence = search_knowledge(queries)
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


# === US-14: 一键生成整份简历 ===


class FullGenerateRequest(BaseModel):
    """一键生成请求体。"""

    node_id: str
    structured_jd: dict[str, Any] | None = None
    gap_report: dict[str, Any] | None = None


class SectionRegenerateRequest(BaseModel):
    """单段重新生成请求体。"""

    node_id: str
    section: str
    structured_jd: dict[str, Any] | None = None
    gap_report: dict[str, Any] | None = None


def _resolve_personal_info(node_id: str) -> dict[str, Any]:
    """从当前节点向上追溯父节点链，找到第一个非空 personal_info。

    Args:
        node_id: 起始节点 ID。

    Returns:
        personal_info dict（可能为空 dict，但不会为 None）。
    """
    from resume_agent.db.connection import get_connection

    current = node_id
    visited: set[str] = set()

    with get_connection() as conn:
        while current and current not in visited:
            visited.add(current)
            row = conn.execute(
                "SELECT content_json, parent_id FROM resume_versions WHERE node_id = ?",
                [current],
            ).fetchone()
            if not row:
                break

            raw = row["content_json"]
            if raw:
                try:
                    content = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(content, dict):
                        pi = content.get("personal_info")
                        if pi and isinstance(pi, dict):
                            # 检查是否有实质内容（至少 name 不为空）
                            contact = pi.get("contact", {})
                            if isinstance(contact, dict) and contact.get("name"):
                                return pi
                except (json.JSONDecodeError, TypeError):
                    pass

            current = row["parent_id"] if row["parent_id"] else ""

    return {}


async def _extract_personal_info_from_knowledge() -> dict[str, Any]:
    """从知识库向量搜索 + LLM 提取个人信息。

    当节点链上找不到 personal_info 时，fallback 到知识库提取。
    """
    from resume_agent.rag.chroma_client import get_knowledge_collection

    collection = get_knowledge_collection()

    # 向量搜索个人信息相关文本
    search_queries = ["姓名 电话 邮箱 地址", "教育背景 学校 学历", "个人简介 自我介绍"]
    all_chunks: list[str] = []
    seen_ids: set[str] = set()

    for query in search_queries:
        try:
            result = collection.query(query_texts=[query], n_results=3)
            ids = result.get("ids", [[]])[0]
            documents = result.get("documents", [[]])[0]
            for idx, doc in enumerate(documents):
                chunk_id = ids[idx] if idx < len(ids) else ""
                if chunk_id and chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    all_chunks.append(doc)
        except Exception:  # noqa: BLE001
            continue

    if not all_chunks:
        return {}

    # LLM 提取
    from resume_agent.llm.client import LLMClient

    llm = LLMClient()
    if not llm.configured:
        return {}

    context = "\n---\n".join(all_chunks[:5])
    system_prompt = """你是信息提取助手。从给定的文本片段中提取个人信息，输出 JSON 对象。
提取以下字段（找不到的留空）：
{
  "contact": { "name": "", "gender": "", "birth_date": "", "phone": "", "email": "", "location": "", "website": "", "github": "", "linkedin": "" },
  "education": [ { "school": "", "degree": "", "major": "", "period": "" } ],
  "summary": ""
}
只输出 JSON，不要输出其他内容。"""

    user_prompt = f"请从以下文本中提取个人信息：\n\n{context}"

    try:
        response = await llm.chat(
            system_prompt=system_prompt,
            user_content=user_prompt,
            response_format_json=True,
        )
    except Exception:  # noqa: BLE001
        return {}

    # 解析返回
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                data = json.loads(cleaned[first : last + 1])
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
    return {}


async def _generate_one_section(
    section: str,
    structured_jd: dict[str, Any],
    queries: list[str],
) -> dict[str, Any]:
    """生成单个段落（检索 → 反思 → 撰写）。

    Returns:
        段落数据 dict，含 section/content/reflection/sources_used。
        如果知识库为空，返回空内容并标注。
    """
    evidence = search_knowledge(queries)
    if not evidence:
        return {
            "section": section,
            "content": {} if section != "summary" else {"summary": ""},
            "reflection": {"issues_found": 0, "issues": [], "notes": "知识库无素材"},
            "sources_used": 0,
            "empty": True,
        }

    reflection = await _run_reflection(evidence)
    try:
        content = await _run_writer(section, structured_jd, evidence, reflection)
    except RuntimeError as exc:
        logger.warning("段落 %s 生成失败: %s", section, exc)
        return {
            "section": section,
            "content": {},
            "reflection": reflection,
            "sources_used": len(evidence),
            "error": str(exc),
        }

    return {
        "section": section,
        "content": content,
        "reflection": reflection,
        "sources_used": len(evidence),
    }


@router.post("/full")
async def generate_full(req: FullGenerateRequest) -> dict[str, Any]:
    """一键生成整份简历。

    并行调用各段落生成（asyncio.gather）：
    - summary：AI 生成自我评价
    - experience/projects/skills：从知识库检索素材生成
    - personal_info：从节点读取，不生成

    生成结果写入节点 content_json。
    """
    import asyncio

    # 获取节点数据
    content = get_node_content(req.node_id)
    if content is None:
        return error("NODE_NOT_FOUND", f"节点 {req.node_id} 不存在")

    # 构建 JD（如果没有传入，从节点或空 dict 读取）
    structured_jd = req.structured_jd or content.get("structured_jd") or {}
    if not structured_jd:
        # 无 JD 时用通用查询词
        structured_jd = {
            "tech_stack": ["Java", "Python", "SQL"],
            "hard_skills": ["数据分析", "系统设计"],
            "soft_skills": ["团队协作", "沟通能力"],
        }

    queries = _collect_search_queries(structured_jd)

    # 并行生成所有段落
    tasks = [
        _generate_one_section(section, structured_jd, queries)
        for section in _FULL_SECTIONS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 合并结果到 content
    section_results: list[dict[str, Any]] = []
    for i, result in enumerate(results):
        section_name = _FULL_SECTIONS[i]
        if isinstance(result, Exception):
            section_results.append({
                "section": section_name,
                "content": {},
                "error": str(result),
                "empty": True,
            })
            continue

        section_data = result.get("content", {})
        # 写入 content_json
        if section_name == "summary":
            content["summary"] = section_data.get("summary", "")
            # 也同步到 personal_info.summary
            pi = content.get("personal_info", {})
            pi["summary"] = section_data.get("summary", "")
            content["personal_info"] = pi
        else:
            content[section_name] = section_data.get(section_name, [])

        section_results.append(result)

    # 个人信息：从父节点链追溯查找（US-14 修复）
    personal_info = _resolve_personal_info(req.node_id)

    # 如果节点链上没找到，从知识库向量搜索提取
    if not personal_info:
        personal_info = await _extract_personal_info_from_knowledge()

    if personal_info:
        content["personal_info"] = personal_info

    # 保存到节点（在 personal_info 赋值之后）
    save_node_content(req.node_id, content)

    return success({
        "node_id": req.node_id,
        "sections": section_results,
        "personal_info": personal_info,
        "content": content,
    })


@router.post("/section")
async def regenerate_section(req: SectionRegenerateRequest) -> dict[str, Any]:
    """单段重新生成。

    只重新生成指定段落，不影响其他段落。
    """
    if req.section not in _FULL_SECTIONS:
        return error(
            "INVALID_SECTION",
            f"不支持的段落类型: {req.section}，仅支持 {list(_FULL_SECTIONS)}",
        )

    content = get_node_content(req.node_id)
    if content is None:
        return error("NODE_NOT_FOUND", f"节点 {req.node_id} 不存在")

    structured_jd = req.structured_jd or content.get("structured_jd") or {}
    if not structured_jd:
        structured_jd = {
            "tech_stack": ["Java", "Python", "SQL"],
            "hard_skills": ["数据分析", "系统设计"],
            "soft_skills": ["团队协作", "沟通能力"],
        }

    queries = _collect_search_queries(structured_jd)

    result = await _generate_one_section(req.section, structured_jd, queries)

    # 更新 content_json 中对应段落
    section_data = result.get("content", {})
    if req.section == "summary":
        content["summary"] = section_data.get("summary", "")
        pi = content.get("personal_info", {})
        pi["summary"] = section_data.get("summary", "")
        content["personal_info"] = pi
    else:
        content[req.section] = section_data.get(req.section, [])

    save_node_content(req.node_id, content)

    return success({
        "node_id": req.node_id,
        "section": req.section,
        "content": section_data,
        "reflection": result.get("reflection"),
        "sources_used": result.get("sources_used", 0),
    })
