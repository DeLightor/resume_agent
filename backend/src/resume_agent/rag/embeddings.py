"""Embedding 提供者接口与 OpenAI 实现。

定义抽象基类 ``EmbeddingProvider`` 与具体实现 ``OpenAIEmbedding``。
基于 ``openai`` SDK 的同步客户端 ``OpenAI``，通过 ``base_url`` 参数支持
OpenAI / DeepSeek / 兼容 OpenAI 协议的多提供商端点。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI

from resume_agent.config import settings

# 批处理上限：OpenAI embeddings 接口单次最多 2048 条，
# 这里保守取 100，兼顾延迟与配额限制。
_EMBED_BATCH_SIZE = 100


class EmbeddingProvider(ABC):
    """Embedding 提供者抽象基类。

    所有具体实现（OpenAI / DeepSeek / 本地模型）需实现 ``embed_texts``。
    """

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """将文本批量转换为向量。

        Args:
            texts: 待嵌入的文本列表。

        Returns:
            与输入等长的向量列表，每个向量为浮点数列表。
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """返回向量维度。"""
        ...


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI Embedding 提供者。

    使用 ``openai.OpenAI`` 同步客户端调用 ``embeddings.create`` 接口。
    通过 ``settings.llm_api_key`` / ``settings.llm_base_url`` / ``settings.embedding_model``
    读取配置，支持 OpenAI 与兼容协议（DeepSeek 等）。

    批处理：每批最多 100 条文本，逐批调用接口并合并结果，
    保证返回向量顺序与输入文本顺序一致。
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """初始化 Embedding 提供者。

        Args:
            model: 模型名，默认取 ``settings.embedding_model``。
            api_key: API Key，默认取 ``settings.llm_api_key``。
            base_url: 自定义端点 URL，默认取 ``settings.llm_base_url``。
        """
        self.model = model or settings.embedding_model
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.base_url = base_url if base_url is not None else settings.llm_base_url

    def _build_client(self) -> OpenAI:
        """构造 ``OpenAI`` 同步客户端实例。

        ``base_url`` 为空字符串时不传递，使用 SDK 默认值。
        """
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文本，返回向量列表。

        按每批 100 条切分，逐批调用 OpenAI embeddings 接口，
        合并所有批次结果保持输入顺序。

        Args:
            texts: 待嵌入的文本列表。

        Returns:
            与 ``texts`` 等长的向量列表，每个向量为 ``list[float]``。

        Raises:
            ValueError: ``texts`` 为空列表时抛出。
            RuntimeError: ``api_key`` 未配置或 OpenAI 接口调用失败时抛出。
        """
        if not texts:
            raise ValueError("embed_texts 输入文本列表不能为空")
        if not self.api_key:
            raise RuntimeError("LLM 未配置 API Key，无法调用 embedding 接口")

        client = self._build_client()
        results: list[list[float]] = []
        total = len(texts)
        for start in range(0, total, _EMBED_BATCH_SIZE):
            batch = texts[start : start + _EMBED_BATCH_SIZE]
            try:
                response = client.embeddings.create(
                    model=self.model,
                    input=batch,
                )
            except Exception as exc:  # noqa: BLE001 - 转为统一异常
                raise RuntimeError(
                    f"调用 embedding 接口失败 (batch {start}-{start + len(batch)}): {exc}"
                ) from exc
            # SDK 保证 response.data 顺序与 input 一致，但仍按 index 排序保险
            sorted_data = sorted(response.data, key=lambda item: item.index)
            for item in sorted_data:
                results.append(list(item.embedding))
        return results

    @property
    def dimension(self) -> int:
        """text-embedding-3-small 输出 1536 维向量。"""
        return 1536


_REGISTRY: dict[str, type[EmbeddingProvider]] = {
    "openai": OpenAIEmbedding,
}


def get_embedding_provider(provider: str | None = None) -> EmbeddingProvider:
    """按名称获取 Embedding 提供者实例。

    Args:
        provider: 提供者名称，默认使用 ``settings.embedding_provider``。

    Returns:
        Embedding 提供者实例。

    Raises:
        ValueError: 未知的提供者名称。
    """
    name = provider or settings.embedding_provider
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"未知的 embedding provider: {name}")
    return cls()


def available_providers() -> list[str]:
    """列出已注册的 Embedding 提供者名称。"""
    return list(_REGISTRY.keys())


def provider_info() -> dict[str, Any]:
    """返回 Embedding 配置信息，供健康检查使用。"""
    return {
        "provider": settings.embedding_provider,
        "model": settings.embedding_model,
        "configured": bool(settings.llm_api_key),
        "available": available_providers(),
    }
