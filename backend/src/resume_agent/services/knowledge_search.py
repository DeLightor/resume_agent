"""知识库语义检索服务（US-27 agent-runtime 抽取自 api/generate.py）。

对多个查询词在 Chroma 知识库中检索，合并去重后返回 top 结果。
原 ``_search_knowledge_base`` 纯移动，行为不变。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("resume_agent")

# 检索配置（原 generate.py 模块常量）
SEARCH_TOP_K: int = 3
MAX_EVIDENCE_CHUNKS: int = 10  # 合并后最多保留的切片数


def search_knowledge(
    queries: list[str],
    top_k: int = SEARCH_TOP_K,
    max_chunks: int = MAX_EVIDENCE_CHUNKS,
) -> list[dict[str, Any]]:
    """对多个查询词在知识库中检索，合并去重。

    Args:
        queries: 查询词列表（来自 JD 技能项等）。
        top_k: 单查询检索条数。
        max_chunks: 合并去重后保留的最大切片数。

    Returns:
        [{"chunk_text": ..., "source_file": ..., "score": ...}, ...]
        按 score 降序。
    """
    if not queries:
        return []

    from resume_agent.rag.chroma_client import get_knowledge_collection

    collection: Any = get_knowledge_collection()
    if collection.count() == 0:
        return []

    all_results: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    for query in queries:
        try:
            result = collection.query(query_texts=[query], n_results=top_k)
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
    return all_results[:max_chunks]


__all__ = ["search_knowledge", "SEARCH_TOP_K", "MAX_EVIDENCE_CHUNKS"]
