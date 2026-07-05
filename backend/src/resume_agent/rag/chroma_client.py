"""Chroma 嵌入式向量库客户端。

使用 ``PersistentClient`` 模式，数据落盘到 ``settings.chroma_path``，零运维。
单例缓存避免重复初始化。

Note:
    ``settings`` 采用延迟导入（函数内导入），以确保测试期 ``conftest``
    重置 ``config_module.settings`` 单例后，客户端能读取到最新的配置
    （避免模块级引用过期导致跨测试数据泄漏）。
"""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models import Collection

# 简历切片集合名
RESUME_COLLECTION = "resume_chunks"
# 知识素材切片集合名
KNOWLEDGE_COLLECTION = "knowledge_chunks"

_client: ClientAPI | None = None


def get_chroma_client() -> ClientAPI:
    """获取 Chroma 嵌入式客户端（单例）。

    使用 ``PersistentClient`` 模式，数据落盘到 ``settings.chroma_path``。
    首次调用会创建目录与底层 DuckDB/Parquet 文件。

    Returns:
        Chroma 客户端实例。
    """
    global _client
    if _client is None:
        from resume_agent.config import settings

        settings.chroma_path.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(settings.chroma_path))
    return _client


def get_resume_collection() -> Collection:
    """获取简历切片集合。

    集合不存在则创建，使用余弦相似度（``cosine``）。
    """
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=RESUME_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def get_knowledge_collection() -> Collection:
    """获取知识素材切片集合。

    集合不存在则创建，使用余弦相似度（``cosine``）。
    """
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=KNOWLEDGE_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def is_chroma_ready() -> bool:
    """检查 Chroma 是否已初始化且可访问。

    供健康检查端点使用。初始化失败返回 False 而非抛出。
    """
    try:
        client = get_chroma_client()
        client.heartbeat()
        return True
    except Exception:  # noqa: BLE001 - 健康检查容忍任意异常
        return False


def reset_client() -> None:
    """重置单例缓存（仅供测试使用）。"""
    global _client
    _client = None


def collection_stats() -> dict[str, Any]:
    """返回集合统计信息，供健康检查使用。"""
    stats: dict[str, Any] = {}
    try:
        resume = get_resume_collection()
        knowledge = get_knowledge_collection()
        stats["resume_count"] = resume.count()
        stats["knowledge_count"] = knowledge.count()
    except Exception:  # noqa: BLE001 - 健康检查容忍异常
        stats["resume_count"] = 0
        stats["knowledge_count"] = 0
    return stats
