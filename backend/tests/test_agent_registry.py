"""Agent 工具注册表测试（US-27 agent-runtime Task 3.1）。

覆盖：注册、schema 转 OpenAI 格式、未知工具错误、执行异常返回 error。
"""

from __future__ import annotations

from typing import Any

import pytest

from resume_agent.agents.registry import ToolRegistry, ToolSpec


def _echo_tool() -> ToolSpec:
    """构造一个 echo 测试工具。"""

    async def echo(args: dict[str, Any]) -> dict[str, Any]:
        return {"echo": args.get("text", "")}

    return ToolSpec(
        name="echo",
        description="回显输入文本",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "输入文本"}},
            "required": ["text"],
        },
        execute=echo,
    )


def test_register_and_schemas() -> None:
    """注册后 schemas() 输出 OpenAI function calling 格式。"""
    registry = ToolRegistry()
    registry.register(_echo_tool())

    schemas = registry.schemas()
    assert len(schemas) == 1
    assert schemas[0] == {
        "type": "function",
        "function": {
            "name": "echo",
            "description": "回显输入文本",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "输入文本"}},
                "required": ["text"],
            },
        },
    }


def test_register_duplicate_rejected() -> None:
    """重复注册同名工具抛 ValueError。"""
    registry = ToolRegistry()
    registry.register(_echo_tool())
    with pytest.raises(ValueError, match="echo"):
        registry.register(_echo_tool())


def test_execute_tool() -> None:
    """正常执行返回工具输出。"""
    import asyncio

    registry = ToolRegistry()
    registry.register(_echo_tool())

    result = asyncio.run(registry.execute("echo", {"text": "你好"}))
    assert result == {"echo": "你好"}


def test_execute_unknown_tool_returns_error() -> None:
    """未知工具不抛异常，返回 error 结构（喂回 LLM 自救）。"""
    import asyncio

    registry = ToolRegistry()
    result = asyncio.run(registry.execute("no_such_tool", {}))
    assert isinstance(result, dict)
    assert "error" in result


def test_execute_exception_returns_error() -> None:
    """工具执行抛异常时返回 error 结构，不中断。"""
    import asyncio

    async def boom(text: str) -> dict[str, Any]:
        raise ValueError("炸了")

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="boom",
        description="总是失败",
        parameters={"type": "object", "properties": {}},
        execute=boom,
    ))

    result = asyncio.run(registry.execute("boom", {"text": "x"}))
    assert isinstance(result, dict)
    assert "error" in result
    assert "炸了" in result["error"]


def test_get_spec() -> None:
    """可按名查询已注册 spec。"""
    registry = ToolRegistry()
    tool = _echo_tool()
    registry.register(tool)
    assert registry.get_spec("echo") is tool
    assert registry.get_spec("missing") is None
