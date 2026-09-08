"""技能 Gap 分析服务（US-27 agent-runtime 抽取自 api/gap_report.py）。

原 gap_report.py 端点核心逻辑纯移动，行为不变：
技能收集 → 知识库检索 → 三色判定 → LLM 批量描述 → 汇总。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("resume_agent")

# 三色判定阈值（原 gap_report.py 模块常量）
COVERED_THRESHOLD: float = 0.6
PARTIAL_THRESHOLD: float = 0.3

# 检索 top-k
SEARCH_TOP_K: int = 3

# LLM system prompt
_SYSTEM_PROMPT = """你是技能匹配分析专家。我会给你一系列技能项和对应的知识库检索结果。
请为每项技能生成一句简短描述（不超过 30 字），说明用户在该技能上的实际情况。

要求：
1. 严格基于检索到的知识库内容描述，禁止编造未在证据中出现的能力。
2. 如果检索结果为空，描述应为"知识库中暂无相关记录"。
3. 输出必须是合法的 JSON 数组，每个元素形如 {"skill": "技能名", "description": "描述"}。
4. 不要输出任何 JSON 之外的解释性文字。"""

_USER_PROMPT_TEMPLATE = """请为以下技能项生成描述：

技能列表与检索结果：
{skills_data}

请输出 JSON 数组。"""


def _collect_skills(structured_jd: dict[str, Any]) -> list[tuple[str, str]]:
    """收集 JD 中所有技能项，去重。

    Returns:
        [(skill_name, category), ...]  category 为 tech_stack / hard_skills / ...
    """
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for category in ("tech_stack", "hard_skills", "soft_skills", "bonus_items"):
        items = structured_jd.get(category, [])
        if not isinstance(items, list):
            continue
        for skill in items:
            if isinstance(skill, str) and skill and skill not in seen:
                seen.add(skill)
                result.append((skill, category))
    return result


def _determine_status(score: float) -> str:
    """按相似度分数判定三色状态。"""
    if score >= COVERED_THRESHOLD:
        return "covered"
    if score >= PARTIAL_THRESHOLD:
        return "partial"
    return "missing"


def _search_skill(skill: str) -> list[dict[str, Any]]:
    """在知识库中检索单项技能，返回 top-3 结果。"""
    from resume_agent.rag.chroma_client import get_knowledge_collection

    collection: Any = get_knowledge_collection()
    if collection.count() == 0:
        return []

    try:
        query_result = collection.query(
            query_texts=[skill],
            n_results=SEARCH_TOP_K,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("检索技能 %s 失败: %s", skill, exc)
        return []

    results: list[dict[str, Any]] = []
    ids = query_result.get("ids", [[]])
    documents = query_result.get("documents", [[]])
    metadatas = query_result.get("metadatas", [[]])
    distances = query_result.get("distances", [[]])

    if not ids or not ids[0]:
        return []

    for idx, _embedding_id in enumerate(ids[0]):
        doc = documents[0][idx] if idx < len(documents[0]) else ""
        meta = metadatas[0][idx] if idx < len(metadatas[0]) else {}
        distance = distances[0][idx] if idx < len(distances[0]) else 1.0
        source_file = meta.get("source_file", "") if isinstance(meta, dict) else ""
        score = max(0.0, 1.0 - distance) if distance is not None else 0.0
        results.append(
            {
                "chunk_text": doc[:200],  # 截断避免 prompt 过长
                "source_file": source_file,
                "score": round(score, 4),
            }
        )
    return results


async def _generate_descriptions(
    skills_with_evidence: list[dict[str, Any]],
) -> dict[str, str]:
    """调用 LLM 批量生成技能描述。

    Args:
        skills_with_evidence: 每项含 skill, category, evidence 列表。

    Returns:
        {skill_name: description} 映射。
    """
    from resume_agent.llm.client import LLMClient

    llm = LLMClient()
    if not llm.configured:
        # LLM 未配置时用简单模板
        return {
            s["skill"]: (
                "知识库有相关记录" if s["evidence"]
                else "知识库中暂无相关记录"
            )
            for s in skills_with_evidence
        }

    # 构造 prompt 数据
    prompt_data = []
    for s in skills_with_evidence:
        evidence_texts = [
            e["chunk_text"] for e in s["evidence"][:2]
        ]
        prompt_data.append({
            "skill": s["skill"],
            "evidence": evidence_texts,
        })

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        skills_data=json.dumps(prompt_data, ensure_ascii=False, indent=2)
    )

    try:
        response_text = await llm.chat(
            system_prompt=_SYSTEM_PROMPT,
            user_content=user_prompt,
            response_format_json=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 生成描述失败: %s", exc)
        return {
            s["skill"]: (
                "知识库有相关记录" if s["evidence"]
                else "知识库中暂无相关记录"
            )
            for s in skills_with_evidence
        }

    # 解析 LLM 返回的 JSON 数组
    cleaned = response_text.strip()
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
        # 尝试提取 JSON 数组
        first = cleaned.find("[")
        last = cleaned.rfind("]")
        if first != -1 and last != -1 and last > first:
            try:
                data = json.loads(cleaned[first : last + 1])
            except json.JSONDecodeError:
                logger.warning("LLM 返回内容无法解析为 JSON 数组")
                data = []
        else:
            logger.warning("LLM 返回内容无法解析为 JSON 数组")
            data = []

    descriptions: dict[str, str] = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "skill" in item and "description" in item:
                descriptions[item["skill"]] = item["description"]

    # 对未匹配的技能用模板兜底
    for s in skills_with_evidence:
        if s["skill"] not in descriptions:
            descriptions[s["skill"]] = (
                "知识库有相关记录" if s["evidence"]
                else "知识库中暂无相关记录"
            )

    return descriptions


async def analyze_gap(structured_jd: dict[str, Any]) -> dict[str, Any]:
    """生成技能 Gap 报告（不含 API envelope）。

    Args:
        structured_jd: JD 结构化数据（tech_stack / hard_skills / ...）。

    Returns:
        {"overall_score": int, "summary": {...}, "items": [...]}。
    """
    # 1. 收集所有技能项
    skills = _collect_skills(structured_jd)

    # 2. 逐项检索知识库
    skills_data: list[dict[str, Any]] = []
    for skill_name, category in skills:
        evidence = _search_skill(skill_name)
        top_score = evidence[0]["score"] if evidence else 0.0
        status = _determine_status(top_score)
        skills_data.append({
            "skill": skill_name,
            "category": category,
            "status": status,
            "score": top_score,
            "evidence": evidence,
        })

    # 3. LLM 批量生成描述
    descriptions = await _generate_descriptions(skills_data)

    # 4. 组装结果
    items: list[dict[str, Any]] = []
    covered_count = 0
    partial_count = 0
    missing_count = 0
    for s in skills_data:
        status = s["status"]
        if status == "covered":
            covered_count += 1
        elif status == "partial":
            partial_count += 1
        else:
            missing_count += 1
        items.append({
            "skill": s["skill"],
            "category": s["category"],
            "status": status,
            "score": s["score"],
            "description": descriptions.get(s["skill"], "知识库中暂无相关记录"),
            "evidence": s["evidence"],
        })

    total = len(items)
    overall_score = round(
        (covered_count * 100 + partial_count * 50) / total if total > 0 else 0
    )

    return {
        "overall_score": overall_score,
        "summary": {
            "covered": covered_count,
            "partial": partial_count,
            "missing": missing_count,
        },
        "items": items,
    }


__all__ = ["analyze_gap"]
