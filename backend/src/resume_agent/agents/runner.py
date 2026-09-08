"""AgentRunner：Agent Loop 运行时（US-27 agent-runtime）。

职责：
- 驱动 LLM ↔ 工具的多轮循环（DeepSeek function calling 协议）
- 持有并持久化完整消息历史（agent_sessions.messages_json）
- ask_user 特判：暂停循环等待用户输入，resume 恢复
- 每次工具调用写 agent_traces
- 可选 on_event 回调：循环各阶段发出事件（US-28 SSE 流式消费）

不负责：Reviewer 审查（US-30）、对话 UI（US-29）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from resume_agent.agents import store
from resume_agent.agents.registry import ToolRegistry
from resume_agent.config import settings
from resume_agent.tools.agent_tools import ASK_USER_TOOL_NAME, build_registry

logger = logging.getLogger("resume_agent")

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]

AGENT_SYSTEM_PROMPT = """你是 Resume-Agent 的简历助理 Agent，帮助用户管理简历、分析 JD、生成与优化简历内容。

行为准则：
1. 诚实优先：简历内容必须基于知识库中的真实素材，先调用 retrieve_knowledge 检索证据，禁止编造经历或量化数据。
2. 需要澄清时直接调用 ask_user 向用户提问，不要自行猜测。
3. 修改用户简历节点前，先 read_node 了解现状。
4. 每次回复使用简洁的中文，先给结论再说理由。"""


@dataclass
class AgentRunResult:
    """一次 run 的终止结果。"""

    status: str  # done / awaiting_user / failed
    final_message: str | None = None
    pending_question: str | None = None
    error: str | None = None
    rounds_used: int = 0


class AgentRunner:
    """Agent Loop 运行时。

    每个实例绑定一个数据库路径与工具注册表，
    通过 ``run`` / ``resume`` 驱动会话状态机。
    """

    def __init__(
        self,
        llm: Any | None = None,
        registry: ToolRegistry | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        if llm is None:
            from resume_agent.llm.client import LLMClient

            llm = LLMClient()
        self.llm = llm
        self.registry = registry if registry is not None else build_registry()
        self.db_path = db_path

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def run(
        self,
        session_id: str,
        user_message: str | None = None,
        on_event: EventCallback | None = None,
    ) -> AgentRunResult:
        """运行（或续跑）一个会话循环。

        Args:
            session_id: 会话 ID。
            user_message: 用户消息（新一轮输入），None 表示从既有历史续跑。
            on_event: 可选事件回调（US-28 SSE），None 时行为与阻塞版一致。

        Returns:
            终止结果（done / awaiting_user / failed）。
        """
        session = store.get_session(session_id, self.db_path)
        if session is None:
            return AgentRunResult(status="failed", error=f"会话不存在: {session_id}")

        if session.status in ("done", "failed"):
            return AgentRunResult(
                status="failed",
                error=f"会话已结束（{session.status}），请创建新会话",
            )

        # 首次运行：注入 system prompt
        if not session.messages:
            session.messages.append({
                "role": "system",
                "content": AGENT_SYSTEM_PROMPT,
            })
            if session.context:
                session.messages.append({
                    "role": "system",
                    "content": (
                        "当前会话上下文："
                        + json.dumps(session.context, ensure_ascii=False)
                    ),
                })

        if user_message:
            session.messages.append({
                "role": "user",
                "content": user_message,
            })

        session.status = "running"
        store.save_session(session, self.db_path)
        return await self._loop(session, on_event)

    async def resume(
        self,
        session_id: str,
        answer: str,
        on_event: EventCallback | None = None,
    ) -> AgentRunResult:
        """从 awaiting_user 恢复：把用户回答作为 ask_user 的 tool result。"""
        session = store.get_session(session_id, self.db_path)
        if session is None:
            return AgentRunResult(status="failed", error=f"会话不存在: {session_id}")

        if session.status != "awaiting_user":
            return AgentRunResult(
                status="failed",
                error=f"会话不在待回答状态（当前: {session.status}），无法恢复",
            )

        ask_call_id = self._find_unclosed_ask_user(session.messages)
        if ask_call_id is None:
            session.status = "failed"
            session.pending_question = None
            session.error_hint = None  # type: ignore[attr-defined]
            store.save_session(session, self.db_path)
            return AgentRunResult(
                status="failed",
                error="会话消息序列非法：未找到待闭合的 ask_user 调用",
            )

        session.messages.append({
            "role": "tool",
            "tool_call_id": ask_call_id,
            "content": answer,
        })
        session.status = "running"
        session.pending_question = None
        store.save_session(session, self.db_path)

        return await self._loop(session, on_event)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    async def _loop(
        self,
        session: store.AgentSession,
        on_event: EventCallback | None = None,
    ) -> AgentRunResult:
        """核心循环：LLM → tool_calls → LLM，直至终结/暂停/耗尽。"""
        max_rounds = settings.agent_max_rounds
        tools_schema = self.registry.schemas()
        rounds_used = 0

        try:
            for _ in range(max_rounds):
                rounds_used += 1
                await self._emit(on_event, {"type": "thinking", "round": rounds_used})
                message = await self.llm.chat_raw(
                    session.messages, tools=tools_schema
                )
                session.messages.append(self._message_to_dict(message))

                tool_calls = getattr(message, "tool_calls", None)
                if not tool_calls:
                    session.status = "done"
                    store.save_session(session, self.db_path)
                    final = getattr(message, "content", None) or ""
                    await self._emit(on_event, {
                        "type": "done", "status": "done",
                        "final_message": final,
                        "rounds_used": rounds_used,
                    })
                    return AgentRunResult(
                        status="done",
                        final_message=final,
                        rounds_used=rounds_used,
                    )

                # 逐个处理本轮 tool_calls
                for tc in tool_calls:
                    tc_name = tc.function.name
                    tc_args = self._parse_arguments(tc.function.arguments)

                    if tc_name == ASK_USER_TOOL_NAME:
                        question = str(tc_args.get("question", ""))
                        session.status = "awaiting_user"
                        session.pending_question = question
                        store.save_session(session, self.db_path)
                        await self._emit(on_event, {
                            "type": "ask_user", "question": question,
                        })
                        await self._emit(on_event, {
                            "type": "done", "status": "awaiting_user",
                            "pending_question": question,
                            "rounds_used": rounds_used,
                        })
                        return AgentRunResult(
                            status="awaiting_user",
                            pending_question=question,
                            rounds_used=rounds_used,
                        )

                    await self._emit(on_event, {
                        "type": "tool_call",
                        "round": rounds_used,
                        "tool_call_id": tc.id,
                        "name": tc_name,
                        "arguments": tc_args,
                    })
                    result = await self.registry.execute(tc_name, tc_args)
                    store.append_trace(
                        session_id=session.id,
                        round=rounds_used,
                        tool_name=tc_name,
                        input_data=tc_args,
                        output_data=result,
                        db_path=self.db_path,
                    )
                    await self._emit(on_event, {
                        "type": "tool_result",
                        "round": rounds_used,
                        "tool_call_id": tc.id,
                        "name": tc_name,
                        "result": result,
                    })
                    session.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": self._result_to_content(result),
                    })

                store.save_session(session, self.db_path)

            # 轮次耗尽：强制无 tools 最终响应
            logger.warning("Agent 轮次耗尽 (%d)，强制生成最终响应", max_rounds)
            message = await self.llm.chat_raw(session.messages, tools=None)
            session.messages.append(self._message_to_dict(message))
            session.status = "done"
            store.save_session(session, self.db_path)
            final = getattr(message, "content", None) or ""
            await self._emit(on_event, {
                "type": "done", "status": "done",
                "final_message": final,
                "rounds_used": rounds_used,
            })
            return AgentRunResult(
                status="done",
                final_message=final,
                rounds_used=rounds_used,
                error=f"已达最大轮数 {max_rounds}，最终响应为强制生成",
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent 循环异常")
            session.status = "failed"
            store.save_session(session, self.db_path)
            await self._emit(on_event, {
                "type": "error",
                "message": str(exc),
                "rounds_used": rounds_used,
            })
            return AgentRunResult(
                status="failed", error=str(exc), rounds_used=rounds_used
            )

    # ------------------------------------------------------------------
    # 序列化辅助
    # ------------------------------------------------------------------

    @staticmethod
    async def _emit(on_event: EventCallback | None, event: dict[str, Any]) -> None:
        """发出事件（无回调时为空操作）。"""
        if on_event is not None:
            await on_event(event)

    @staticmethod
    def _message_to_dict(message: Any) -> dict[str, Any]:
        """assistant message 对象 → OpenAI 协议 dict（含 tool_calls）。"""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": getattr(message, "content", None),
        }
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        return msg

    @staticmethod
    def _parse_arguments(raw: str | None) -> dict[str, Any]:
        """解析 tool call 的 arguments JSON 字符串。"""
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {"_raw_arguments": raw, "_parse_error": True}

    @staticmethod
    def _result_to_content(result: Any) -> str:
        """工具结果 → tool message content 字符串。"""
        return json.dumps(result, ensure_ascii=False, default=str)

    @staticmethod
    def _find_unclosed_ask_user(messages: list[dict[str, Any]]) -> str | None:
        """找到未闭合的 ask_user tool_call id（非法序列返回 None）。"""
        if not messages:
            return None
        # 收集已闭合的 tool_call id
        closed_ids = {
            m["tool_call_id"]
            for m in messages
            if m.get("role") == "tool" and m.get("tool_call_id")
        }
        # 从后向前找最后一条 assistant 消息
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            for tc in msg.get("tool_calls") or []:
                tc_id: str | None = tc.get("id")
                if (
                    tc.get("function", {}).get("name") == ASK_USER_TOOL_NAME
                    and tc_id not in closed_ids
                ):
                    return tc_id
            # 只检查最后一条 assistant 消息
            break
        return None


__all__ = ["AgentRunner", "AgentRunResult", "AGENT_SYSTEM_PROMPT"]
