"""文本分块器。

将长文本按固定字符窗口切分为多个切片，相邻切片间保留一定重叠，
避免在切片边界处丢失上下文，提升 RAG 检索质量。

对齐 design.md 第 2.3 节。
"""

from __future__ import annotations

# 默认切片大小（字符）
CHUNK_SIZE = 512

# 默认切片重叠（字符）
CHUNK_OVERLAP = 50


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """按字符窗口将文本切分为多个切片。

    使用滑动窗口从前往后切分，步长 = ``chunk_size - overlap``。
    每个切片长度最多为 ``chunk_size``；最后一个切片可能更短。

    Args:
        text: 待切分的原始文本。
        chunk_size: 单个切片最大字符数，必须 > 0。
        overlap: 相邻切片重叠字符数，必须满足 ``0 <= overlap < chunk_size``。

    Returns:
        切片字符串列表。

        - 空文本（``""``）返回空列表 ``[]``。
        - 文本长度小于等于 ``chunk_size`` 时返回单元素列表 ``[text]``。

    Raises:
        ValueError: ``chunk_size`` 非正，或 ``overlap`` 不满足 ``0 <= overlap < chunk_size``。
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size 必须为正整数，实际为 {chunk_size}")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            f"overlap 必须满足 0 <= overlap < chunk_size，实际 overlap={overlap}, "
            f"chunk_size={chunk_size}"
        )

    stripped = text.strip()
    if not stripped:
        return []

    # 短文本无需切分
    if len(stripped) <= chunk_size:
        return [stripped]

    chunks: list[str] = []
    step = chunk_size - overlap
    total = len(stripped)
    start = 0
    while start < total:
        end = start + chunk_size
        chunks.append(stripped[start:end])
        if end >= total:
            break
        start += step

    return chunks
