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


def test_run_continues_done_session(initialized_db: Any) -> None:
    """US-29：done 会话收到新用户消息时续聊（而非报错）。

    对话式工作台要求自然连续对话：用户在 Agent 完成回答后继续
    发消息（如「算了我先不改了」）应正常回复。历史消息保留。
    """
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([_msg("第一轮回答"), _msg("第二轮回答")])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )

    # 第一轮：正常完成 → done
    result1 = _run(runner.run(session.id, user_message="帮我优化"))
    assert result1.status == "done"

    # 第二轮：done 会话继续发消息 → 不报错，正常续聊
    result2 = _run(runner.run(session.id, user_message="算了我先不改了"))
    assert result2.status == "done"
    assert result2.final_message == "第二轮回答"

    # 历史完整保留：两轮 user + 两轮 assistant + system
    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    assert fetched.status == "done"
    user_msgs = [m for m in fetched.messages if m["role"] == "user"]
    assert [m["content"] for m in user_msgs] == ["帮我优化", "算了我先不改了"]
    assistant_msgs = [m for m in fetched.messages if m["role"] == "assistant"]
    assert [m["content"] for m in assistant_msgs] == [
        "第一轮回答", "第二轮回答",
    ]


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


# === 事件钩子（US-28 agent-sse-stream Task 1）===


def _collect_events() -> tuple[list[dict[str, Any]], Any]:
    """构造事件收集回调与列表。"""
    events: list[dict[str, Any]] = []

    async def on_event(event: dict[str, Any]) -> None:
        events.append(event)

    return events, on_event


def test_run_emits_event_sequence(initialized_db: Any) -> None:
    """多轮工具调用事件序列：thinking → tool_call → tool_result → thinking → done。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _tool_call_msg([{
            "id": "tc1", "name": "echo",
            "arguments": json.dumps({"text": "hi"}),
        }]),
        _msg("完成。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )
    events, on_event = _collect_events()

    result = _run(runner.run(session.id, on_event=on_event))

    assert result.status == "done"
    types = [e["type"] for e in events]
    assert types == ["thinking", "tool_call", "tool_result", "thinking", "done"]
    assert events[0]["round"] == 1
    assert events[1]["tool_call_id"] == "tc1"
    assert events[1]["name"] == "echo"
    assert events[1]["arguments"] == {"text": "hi"}
    assert events[2]["result"] == {"echo": "hi"}
    assert events[-1]["status"] == "done"
    assert events[-1]["final_message"] == "完成。"
    assert events[-1]["rounds_used"] == 2


def test_run_emits_events_for_parallel_tool_calls(initialized_db: Any) -> None:
    """同一轮多个 tool_calls：每个调用各发一对 tool_call/tool_result。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _tool_call_msg([
            {"id": "tc1", "name": "echo", "arguments": json.dumps({"text": "a"})},
            {"id": "tc2", "name": "echo", "arguments": json.dumps({"text": "b"})},
        ]),
        _msg("两个都完成了。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )
    events, on_event = _collect_events()

    _run(runner.run(session.id, on_event=on_event))

    types = [e["type"] for e in events]
    assert types == [
        "thinking", "tool_call", "tool_result",
        "tool_call", "tool_result", "thinking", "done",
    ]
    assert events[2]["result"] == {"echo": "a"}
    assert events[4]["result"] == {"echo": "b"}


def test_run_emits_ask_user_events(initialized_db: Any) -> None:
    """ask_user 暂停事件序列：thinking → ask_user → done(awaiting_user)。"""
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
    events, on_event = _collect_events()

    result = _run(runner.run(session.id, on_event=on_event))

    assert result.status == "awaiting_user"
    types = [e["type"] for e in events]
    assert types == ["thinking", "ask_user", "done"]
    assert events[1]["question"] == "你的毕业年份？"
    assert events[-1]["status"] == "awaiting_user"
    assert events[-1]["pending_question"] == "你的毕业年份？"


def test_resume_emits_events(initialized_db: Any) -> None:
    """resume 恢复同样发事件：thinking → done。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _tool_call_msg([{
            "id": "tc9", "name": "ask_user",
            "arguments": json.dumps({"question": "毕业年份？"}),
        }]),
        _msg("明白了。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )
    _run(runner.run(session.id))

    events, on_event = _collect_events()
    result = _run(runner.resume(session.id, "2025", on_event=on_event))

    assert result.status == "done"
    types = [e["type"] for e in events]
    assert types == ["thinking", "done"]
    assert events[-1]["final_message"] == "明白了。"


def test_run_emits_error_event_on_exception(initialized_db: Any) -> None:
    """LLM 调用异常 → thinking → error 事件。"""

    class _BoomLLM:
        async def chat_raw(self, messages: list[Any], tools: Any = None) -> Any:
            raise RuntimeError("LLM 炸了")

    session = store.create_session(db_path=initialized_db)
    runner = AgentRunner(
        llm=_BoomLLM(), registry=_registry_with_echo(), db_path=initialized_db
    )
    events, on_event = _collect_events()

    result = _run(runner.run(session.id, on_event=on_event))

    assert result.status == "failed"
    types = [e["type"] for e in events]
    assert types == ["thinking", "error"]
    assert "LLM 炸了" in events[-1]["message"]


def test_run_emits_done_event_on_rounds_exhausted(initialized_db: Any) -> None:
    """轮次耗尽强制终结：事件序列以 done 收尾。"""
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([])
    call_count = {"n": 0}

    async def raw(messages: list[Any], tools: Any = None) -> Any:
        call_count["n"] += 1
        if call_count["n"] <= 3:
            return _tool_call_msg([{
                "id": f"tc-{call_count['n']}", "name": "echo",
                "arguments": "{}",
            }])
        return _msg("被强制终结")

    llm.chat_raw = raw  # type: ignore[method-assign]
    runner = AgentRunner(
        llm=llm, registry=_registry_with_echo(), db_path=initialized_db
    )
    events, on_event = _collect_events()

    from unittest.mock import patch

    with patch("resume_agent.agents.runner.settings") as mock_settings:
        mock_settings.agent_max_rounds = 3
        result = _run(runner.run(session.id, on_event=on_event))

    assert result.status == "done"
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "done"
    assert events[-1]["final_message"] == "被强制终结"


# === write_node 门禁（agent-write-guard）===

_WRITE_CONTENT: dict[str, Any] = {
    "experience": [],
    "skills": [{"name": "Python", "context": "FastAPI 服务开发"}],
}


def _registry_with_write_node(recorder: list[dict[str, Any]]):
    """echo + 记录调用的 write_node 桩（模拟真实写入语义）。"""
    from resume_agent.agents.registry import ToolSpec

    async def write_node_stub(args: dict[str, Any]) -> dict[str, Any]:
        recorder.append(args)
        node_id = str(args.get("node_id", ""))
        if not node_id:
            return {"error": "node_id 不能为空"}
        return {"ok": True, "node_id": node_id}

    r = _registry_with_echo()
    r.register(ToolSpec(
        name="write_node",
        description="write stub",
        parameters={"type": "object", "properties": {}},
        execute=write_node_stub,
    ))
    return r


def _write_call(call_id: str, node_id: str = "master") -> Any:
    """构造 write_node tool_call 的 assistant message mock。"""
    return _tool_call_msg([{
        "id": call_id, "name": "write_node",
        "arguments": json.dumps({"node_id": node_id, "content": _WRITE_CONTENT}),
    }])


def test_run_write_node_gates_for_confirmation(initialized_db: Any) -> None:
    """write_node 合法调用不直接写入：暂停等待用户确认。"""
    recorder: list[dict[str, Any]] = []
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _write_call("tcw1"),
        _msg("已写入。"),  # 若未暂停会被消费（脚本余量暴露行为）
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_write_node(recorder),
        db_path=initialized_db,
    )
    events, on_event = _collect_events()

    result = _run(runner.run(session.id, on_event=on_event))

    assert result.status == "awaiting_user"
    assert result.pending_question is not None
    # 写入未执行
    assert recorder == []
    # 事件序列：thinking → write_confirm → done(awaiting_user)
    types = [e["type"] for e in events]
    assert types == ["thinking", "write_confirm", "done"]
    assert events[1]["node_id"] == "master"
    assert events[1]["content"] == _WRITE_CONTENT
    assert events[1]["question"] is not None
    assert events[-1]["status"] == "awaiting_user"

    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    assert fetched.status == "awaiting_user"
    assert fetched.pending_write == {
        "tool_call_id": "tcw1",
        "node_id": "master",
        "content": _WRITE_CONTENT,
    }
    # 尾部是未闭合的 assistant tool_calls
    assert fetched.messages[-1]["role"] == "assistant"
    assert fetched.messages[-1]["tool_calls"][0]["function"]["name"] == "write_node"


def test_resume_confirmation_executes_write(initialized_db: Any) -> None:
    """用户明确确认 → 执行写入，tool result 与 trace 记录 written。"""
    recorder: list[dict[str, Any]] = []
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _write_call("tcw1"),
        _msg("已写入。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_write_node(recorder),
        db_path=initialized_db,
    )
    _run(runner.run(session.id))

    result = _run(runner.resume(session.id, "确认"))

    assert result.status == "done"
    assert result.final_message == "已写入。"
    # 写入已执行（且仅一次）
    assert recorder == [{"node_id": "master", "content": _WRITE_CONTENT}]

    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    assert fetched.status == "done"
    assert fetched.pending_write is None
    assert fetched.pending_question is None
    # write_node tool_call 已闭合，结果是 written:true
    tool_msgs = [m for m in fetched.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "tcw1"
    payload = json.loads(tool_msgs[0]["content"])
    assert payload["written"] is True
    assert payload["ok"] is True

    # trace 记录写入结果（round=0 表示恢复阶段解决）
    traces = store.list_traces(session.id, initialized_db)
    write_traces = [t for t in traces if t["tool_name"] == "write_node"]
    assert len(write_traces) == 1
    assert json.loads(write_traces[0]["output"])["written"] is True


def test_resume_non_confirmation_skips_write(initialized_db: Any) -> None:
    """非确认回复不写入：回复全文作为 user_reply 回传 LLM。"""
    recorder: list[dict[str, Any]] = []
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _write_call("tcw1"),
        _msg("好的，我先不改了。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_write_node(recorder),
        db_path=initialized_db,
    )
    _run(runner.run(session.id))

    result = _run(runner.resume(session.id, "先别写，把技能改成 Java"))

    assert result.status == "done"
    assert recorder == []

    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    assert fetched.pending_write is None
    tool_msgs = [m for m in fetched.messages if m["role"] == "tool"]
    payload = json.loads(tool_msgs[0]["content"])
    assert payload["written"] is False
    assert payload["user_reply"] == "先别写，把技能改成 Java"

    traces = store.list_traces(session.id, initialized_db)
    write_traces = [t for t in traces if t["tool_name"] == "write_node"]
    assert len(write_traces) == 1
    assert json.loads(write_traces[0]["output"])["written"] is False


def test_write_node_re_gates_after_confirmation(initialized_db: Any) -> None:
    """确认写入后 Agent 再次发起写入 → 再次进入门禁（每轮都需确认）。"""
    recorder: list[dict[str, Any]] = []
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _write_call("tcw1"),
        _write_call("tcw2"),
        _msg("两次都写入了。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_write_node(recorder),
        db_path=initialized_db,
    )

    result1 = _run(runner.run(session.id))
    assert result1.status == "awaiting_user"

    result2 = _run(runner.resume(session.id, "确认"))
    # 第二次 write_node 再次门禁
    assert result2.status == "awaiting_user"
    assert recorder == [{"node_id": "master", "content": _WRITE_CONTENT}]

    result3 = _run(runner.resume(session.id, "好的"))
    assert result3.status == "done"
    assert recorder == [
        {"node_id": "master", "content": _WRITE_CONTENT},
        {"node_id": "master", "content": _WRITE_CONTENT},
    ]


def test_write_node_invalid_args_skips_gate(initialized_db: Any) -> None:
    """非法参数（缺 node_id）不触发门禁：错误 tool result 原路返回。"""
    recorder: list[dict[str, Any]] = []
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _tool_call_msg([{
            "id": "tcw1", "name": "write_node",
            "arguments": json.dumps({"content": _WRITE_CONTENT}),  # 缺 node_id
        }]),
        _msg("参数错了。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_write_node(recorder),
        db_path=initialized_db,
    )

    result = _run(runner.run(session.id))

    # 不暂停：参数错误直接作为 tool result 回传
    assert result.status == "done"
    fetched = store.get_session(session.id, initialized_db)
    assert fetched is not None
    assert fetched.pending_write is None
    tool_msgs = [m for m in fetched.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    payload = json.loads(tool_msgs[0]["content"])
    assert "error" in payload


def test_is_write_confirmation_lexicon() -> None:
    """确认词表：整句明确同意才确认（安全默认，误判方向必须安全）。"""
    from resume_agent.agents.runner import is_write_confirmation

    # 明确确认
    for reply in [
        "确认", "确认。", "确认！", "同意", "同意写入", "确认写入",
        "好的", "好", "好的吧", "可以", "没问题", "嗯", "行",
        "写入", "执行", " OK ", "ok!", "Okay", "yes", "Y",
    ]:
        assert is_write_confirmation(reply), reply

    # 拒绝 / 自由文本 / 疑问一律不确认
    for reply in [
        "", "不要", "取消", "先别写", "改一下再写",
        "确认吗", "确认一下再写", "好的，但是项目名要改成 X",
        "帮我确认一下", "再想想", "不对",
    ]:
        assert not is_write_confirmation(reply), reply


def test_ask_user_path_unaffected_by_write_guard(initialized_db: Any) -> None:
    """ask_user 暂停/恢复不因 pending_write 机制受影响（回归）。"""
    recorder: list[dict[str, Any]] = []
    session = store.create_session(db_path=initialized_db)
    llm = _ScriptedLLM([
        _tool_call_msg([{
            "id": "tc9", "name": "ask_user",
            "arguments": json.dumps({"question": "你的毕业年份？"}),
        }]),
        _msg("明白了。"),
    ])
    runner = AgentRunner(
        llm=llm, registry=_registry_with_write_node(recorder),
        db_path=initialized_db,
    )
    result1 = _run(runner.run(session.id))
    assert result1.status == "awaiting_user"

    result2 = _run(runner.resume(session.id, "2025 届"))
    assert result2.status == "done"
    assert result2.final_message == "明白了。"


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
