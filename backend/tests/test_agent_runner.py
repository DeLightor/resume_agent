"""AgentRunner 测试（US-27 agent-runtime Task 4）。

用脚本化 mock LLMClient.chat_raw 驱动完整状态机：
正常终结 / 多轮工具 / ask_user 暂停恢复 / 轮次耗尽 / 工具异常。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from resume_agent.agents import store
from resume_agent.agents.runner import AGENT_SYSTEM_PROMPT, AgentRunner


def _msg(content: str) -> Any:
    """构造无 tool_calls 的 assistant message mock。"""

    class _M:
        pass

    m = _M()
    m.content = content
    m.tool_calls = None
    return m


def _tool_call_msg(calls: list[dict[str, str]]) -> Any:
    """构造含 tool_calls 的 assistant message mock。

    calls: [{"id": "tc1", "name": "retrieve_knowledge", "arguments": "{...}"}]
    """
    from unittest.mock import MagicMock

    m = MagicMock()
    m.content = ""
    real_calls = []
    for c in calls:
        tc = MagicMock()
        tc.id = c["id"]
        tc.function = MagicMock()
        tc.function.name = c["name"]
        tc.function.arguments = c["arguments"]
        real_calls.append(tc)
    m.tool_calls = real_calls
    return m


class _ScriptedLLM:
    """按脚本顺序返回 message 的假 LLM。"""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def chat_raw(self, messages: list[Any], tools: Any = None) -> Any:
        self.calls.append({"messages": messages, "tools": tools})
        return self.script.pop(0)


def _registry_with_echo():
    """注册一个 echo 工具的 registry。"""
    from resume_agent.agents.registry import ToolRegistry, ToolSpec

    async def echo(args: dict[str, Any]) -> dict[str, Any]:
        return {"echo": args.get("text", "")}

    r = ToolRegistry()
    r.register(ToolSpec(
        name="echo", description="echo",
        parameters={"type": "object", "properties": {}},
        execute=echo,
    ))
    return r


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# === 4.1 基本循环 ===


def test_run_direct_finish(initialized_db: Any) -> None:
    """LLM 无 tool_calls 直接终结：status=done、messages 持久化。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([_msg("好的，我明白了。")])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )

    result = _run(runner.run(session.id))

    assert result.status == "done"
    assert result.final_message == "好的，我明白了。"

    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    assert fetched.status == "done"
    # system + assistant（未传 user_message）
    assert len(fetched.messages) == 2
    assert fetched.messages[0]["role"] == "system"
    assert fetched.messages[-1]["role"] == "assistant"


def test_run_injects_user_message(initialized_db: Any) -> None:
    """run(user_message=...) 会把用户消息追加进会话再启动循环。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([_msg("ok")])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )

    _run(runner.run(session.id, user_message="帮我优化简历"))

    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    user_msgs = [m for m in fetched.messages if m["role"] == "user"]
    assert user_msgs[-1]["content"] == "帮我优化简历"


# === 4.2 多轮工具调用 ===


def test_run_multi_round_tool_calls(initialized_db: Any) -> None:
    """LLM 先调工具再终结：trace 落库（轮次编号、输入输出）。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _tool_call_msg([{
            "id": "tc1", "name": "echo",
            "arguments": json.dumps({"text": "hi"}),
        }]),
        _msg("工具结果已处理。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )

    result = _run(runner.run(session.id))

    assert result.status == "done"
    assert result.rounds_used == 2

    traces = store.list_traces(session.id, initialized_db)
    assert len(traces) == 1
    assert traces[0]["tool_name"] == "echo"
    assert traces[0]["round"] == 1
    assert traces[0]["input"] == {"text": "hi"}

    # tool result 消息已进会话历史
    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    tool_msgs = [m for m in fetched.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "tc1"


# === 4.3 ask_user 暂停 ===


def test_run_ask_user_pauses(initialized_db: Any) -> None:
    """LLM 调 ask_user：status=awaiting_user、pending_question 持久化。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _tool_call_msg([{
            "id": "tc9", "name": "ask_user",
            "arguments": json.dumps({"question": "你的毕业年份？"}),
        }]),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )

    result = _run(runner.run(session.id))

    assert result.status == "awaiting_user"
    assert result.pending_question == "你的毕业年份？"

    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    assert fetched.status == "awaiting_user"
    assert fetched.pending_question == "你的毕业年份？"
    # 尾部是未闭合的 assistant tool_calls（无 tool result）
    assert fetched.messages[-1]["role"] == "assistant"
    assert fetched.messages[-1]["tool_calls"][0]["function"]["name"] == "ask_user"


# === 4.4 ask_user 恢复 ===


def test_resume_after_ask_user(initialized_db: Any) -> None:
    """用户回答后恢复：答案作为 tool result 续跑至终结。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _tool_call_msg([{
            "id": "tc9", "name": "ask_user",
            "arguments": json.dumps({"question": "你的毕业年份？"}),
        }]),
        _msg("明白了，2025 届。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )
    _run(runner.run(session.id))

    result = _run(runner.resume(session.id, "2025 届"))

    assert result.status == "done"
    assert result.final_message == "明白了，2025 届。"

    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    assert fetched.status == "done"
    assert fetched.pending_question is None
    # ask_user 的 tool result 已闭合
    tool_msgs = [m for m in fetched.messages if m["role"] == "tool"]
    assert any(m.get("tool_call_id") == "tc9" for m in tool_msgs)


def test_resume_invalid_session_state(initialized_db: Any) -> None:
    """非 awaiting_user 状态 resume 返回失败。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([_msg("done")])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )
    _run(runner.run(session.id))  # done

    result = _run(runner.resume(session.id, "回答"))
    assert result.status == "failed"
    assert result.error is not None


def test_resume_with_broken_messages_fails(initialized_db: Any) -> None:
    """messages 尾部无未闭合 ask_user 时恢复 → failed。"""
    session = store.create_session(db_path=initialized_db)
    session.status = "awaiting_user"
    session.pending_question = "假问题"
    session.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        # 尾部没有 assistant tool_calls
        {"role": "assistant", "content": "hello"},
    ]
    store.save_session(session, initialized_db)

    llm = _ScriptedLLM([])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )
    result = _run(runner.resume(session.id, "回答"))
    assert result.status == "failed"
    assert result.error is not None


# === 4.5 轮次耗尽 ===


def test_run_max_rounds_exhausted(initialized_db: Any) -> None:
    """轮次耗尽：强制无 tools 最终响应，trace 完整。"""
    session = store.create_session(db_path=initialized_db)
    # 每轮都调 echo，永不终结（mock 每轮新建 tool_call id，避免同 id 覆盖消息）
    llm = _ScriptedLLM([])
    llm.script = None  # 用动态脚本替代
    call_count = {"n": 0}

    async def raw(messages, tools=None):
        call_count["n"] += 1
        if call_count["n"] <= 3:  # max_rounds 由 monkeypatch 调小
            return _tool_call_msg([{
                "id": f"tc-{call_count['n']}", "name": "echo",
                "arguments": "{}",
            }])
        return _msg("被强制终结")

    llm.chat_raw = raw  # type: ignore[method-assign]

    from unittest.mock import patch

    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )
    with patch("resume_agent.agents.runner.settings") as mock_settings:
        mock_settings.agent_max_rounds = 3
        result = _run(runner.run(session.id))

    assert result.status == "done"
    assert result.final_message == "被强制终结"

    traces = store.list_traces(session.id, initialized_db)
    assert len(traces) == 3


# === 4.6 工具执行异常 ===


def test_tool_error_does_not_break_loop(initialized_db: Any) -> None:
    """工具执行异常：error 作为 tool result 回传，循环继续。"""
    from resume_agent.agents.registry import ToolRegistry, ToolSpec

    async def boom(args: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("工具炸了")

    r = ToolRegistry()
    r.register(ToolSpec(
        name="boom", description="boom",
        parameters={"type": "object", "properties": {}},
        execute=boom,
    ))

    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _tool_call_msg([{"id": "tc1", "name": "boom", "arguments": "{}"}]),
        _msg("工具失败了，但我可以继续。"),
    ])
    runner = AgentRunner(llm=llm, registry=r, db_path=initialized_db)

    result = _run(runner.run(session.id))
    assert result.status == "done"

    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    tool_msgs = [m for m in fetched.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "炸了" in tool_msgs[0]["content"]


# === system prompt ===


def test_system_prompt_presented_to_llm(initialized_db: Any) -> None:
    """发给 LLM 的 messages 必须以 system prompt 开头。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([_msg("ok")])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )
    _run(runner.run(session.id, user_message="hi"))

    first_call = llm.calls[0]
    assert first_call["messages"][0]["role"] == "system"
    assert first_call["messages"][0]["content"] == AGENT_SYSTEM_PROMPT
    # 工具 schema 传递给了 LLM
    assert first_call["tools"] is not None
