"""Agent 工具注册表（US-27 agent-runtime Task 3.1）。

ToolSpec 描述一个可被 LLM function calling 调用的工具；
ToolRegistry 负责注册、schema 转换与安全执行。

设计约定：
- 工具执行失败不抛异常中断 Agent 循环，而是返回 ``{"error": ...}``
  结构作为 tool result 喂回 LLM，让模型有机会自救（对齐
  ``LLMClient.chat_with_tools`` 的既有语义）。
- ``ask_user`` 由 AgentRunner 特判，不走 ``execute``。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("resume_agent")

# 工具执行函数类型：(args: dict) -> awaitable result
ToolExecute = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass
class ToolSpec:
    """一个 Agent 工具的完整定义。

    Attributes:
        name: 工具名（LLM function calling 的 function.name）。
        description: 给 LLM 看的工具用途描述。
        parameters: JSON Schema（OpenAI function calling 的 parameters）。
        execute: 异步执行函数，入参为 LLM 解析出的参数字典。
    """

    name: str
    description: str
    parameters: dict[str, Any]
    execute: ToolExecute


class ToolRegistry:
    """Agent 工具注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """注册工具，重名抛 ``ValueError``。"""
        if spec.name in self._tools:
            raise ValueError(f"工具已注册: {spec.name}")
        self._tools[spec.name] = spec

    def get_spec(self, name: str) -> ToolSpec | None:
        """按名查询工具定义，未注册返回 None。"""
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        """导出 OpenAI function calling 格式的工具定义列表。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    async def execute(self, name: str, args: dict[str, Any]) -> Any:
        """安全执行工具。

        未知工具或执行异常都返回 ``{"error": ...}`` 字典，
        不向上抛异常以维持 Agent 循环。
        """
        spec = self._tools.get(name)
        if spec is None:
            logger.warning("调用了未注册的工具: %s", name)
            return {"error": f"未知工具: {name}"}

        try:
            return await spec.execute(args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("工具执行失败 (%s): %s", name, exc)
            return {"error": f"工具 {name} 执行失败: {exc}"}


__all__ = ["ToolRegistry", "ToolSpec", "ToolExecute"]
