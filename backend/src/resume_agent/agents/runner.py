"""AgentRunner：Agent Loop 运行时（US-27 agent-runtime）。

职责：
- 驱动 LLM ↔ 工具的多轮循环（DeepSeek function calling 协议）
- 持有并持久化完整消息历史（agent_sessions.messages_json）
- ask_user 特判：暂停循环等待用户输入，resume 恢复
- write_node 门禁（agent-write-guard）：合法写入先暂停，用户确认后执行
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

from resume_agent.agents import memory_store, store
from resume_agent.agents.registry import ToolRegistry
from resume_agent.agents.reviewer import ReviewerAgent
from resume_agent.config import settings
from resume_agent.tools.agent_tools import (
    ASK_USER_TOOL_NAME,
    WRITE_NODE_TOOL_NAME,
    build_registry,
)

logger = logging.getLogger("resume_agent")

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]
_MEMORY_SNAPSHOT_PREFIX = "【会话最新记忆规则】"

AGENT_SYSTEM_PROMPT = """你是 Resume-Agent 的简历助理 Agent，帮助用户管理简历、分析 JD、生成与优化简历内容。

行为准则：
1. 诚实优先：简历内容必须基于知识库中的真实素材，先调用 retrieve_knowledge 检索证据，禁止编造经历或量化数据。
2. 需要澄清时直接调用 ask_user 向用户提问，不要自行猜测。
3. 修改用户简历节点前，先 read_node 了解现状。
4. 修改前必须 read_node，write_node 的 content 必须保留读取到的 version，不得猜测或更换版本。
   修改简历内容通过 write_node 发起：系统会先由独立 Reviewer 审查草稿
   （不合格会带意见打回，请按意见修改后重新发起，不要原样重发），
   通过后暂停向用户展示待写入内容，用户明确同意后才真正写入；
   被用户拒绝时根据用户反馈调整后重新发起。
5. 每次回复使用简洁的中文，先给结论再说理由。
6. 关注长期偏好：用户在对话中可能会自然提出个人偏好、工作习惯或红线要求（如「不要写精通」、「突出高并发」），系统会自动沉淀为长期记忆。你在后续回复和简历内容生成中需严格遵守，并在回复中自然响应用户的偏好。
7. 管理长期记忆：当用户要求删除、撤销或清理某条记忆规则（例如「把刚刚记的xxx删掉」、「删除关于精通的记忆」、「撤销刚才的偏好」）时，主动调用 delete_memory 工具，传入用户提到的关键词或使用 query="latest" 删除刚刚添加的记忆；也可以在不确定时先调用 list_memories 查看已有记忆。删除成功后向用户确认删除结果。"""

# ---------------------------------------------------------------------------
# write_node 确认词表（agent-write-guard）
# ---------------------------------------------------------------------------

# 整句命中才算确认；误判方向必须安全：
# 假阴性（本意同意但未写入）无害——LLM 会再发起；
# 假阳性（本意拒绝但写入了）危险——自由文本一律不匹配。
_WRITE_CONFIRM_LEXICON = frozenset({
    "确认", "确认写入", "同意", "同意写入", "写入", "执行",
    "好的", "好", "可以", "没问题", "行", "嗯", "恩",
    "ok", "okay", "yes", "y",
})

# 规范化时去除的首尾标点与结尾语气词
_WRITE_STRIP_CHARS = "。！？!?,，.、~～ \t\n"
_WRITE_TONE_SUFFIXES = ("吧", "呢", "啊", "呀", "哈")

# US-30 reviewer-agent：同一轮 run 内 write_node 被审查打回的最大次数
# （最多 2 次重写，第 3 次审查仍不合格则如实放行进门禁）
_WRITE_REVIEW_MAX_REJECTS = 2


def is_write_confirmation(reply: str) -> bool:
    """判断用户回复是否为对 pending_write 的明确确认（整句匹配）。"""
    text = (reply or "").strip().lower().strip(_WRITE_STRIP_CHARS)
    while text and text[-1] in _WRITE_TONE_SUFFIXES:
        text = text[:-1].strip(_WRITE_STRIP_CHARS)
    return text in _WRITE_CONFIRM_LEXICON


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
        reviewer: Any | None = None,
    ) -> None:
        if llm is None:
            from resume_agent.llm.client import LLMClient

            llm = LLMClient()
        self.llm = llm
        self.registry = registry if registry is not None else build_registry()
        self.db_path = db_path
        # US-30 reviewer-agent：独立上下文的审查者（测试可注入脚本 mock）
        self.reviewer = reviewer if reviewer is not None else ReviewerAgent()

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

        # US-29：done/failed 会话带新用户消息时续聊（对话式工作台的自然
        # 连续对话）；不带消息的空跑（如误触发）仍然拒绝。
        if session.status in ("done", "failed") and not user_message:
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
            active_memory = memory_store.get_active_memory_prompt(self.db_path)
            if active_memory:
                # 记忆单独作为可替换快照保存。不能拼进基础 system prompt，
                # 否则用户删除规则后，正在进行的会话仍会携带过期约束。
                session.messages.append({
                    "role": "system",
                    "content": f"{_MEMORY_SNAPSHOT_PREFIX}\n{active_memory}",
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
            # US-35: 智能记忆识别与长期记忆沉淀（LLM 语义分析 + 规则兜底，无固定句式限制）
            try:
                extracted_list = await memory_store.extract_memories_smart(
                    self.llm, user_message
                )
                for item in extracted_list:
                    mem_item = memory_store.create_memory(
                        content=item["content"],
                        type=item["type"],
                        source="auto_inferred",
                        session_id=session.id,
                        db_path=self.db_path,
                    )
                    if on_event:
                        await self._emit(on_event, {
                            "type": "memory_created",
                            "memory": mem_item.to_dict(),
                        })
            except Exception as exc:  # noqa: BLE001
                logger.warning("自动沉淀记忆失败: %s", exc)
            active_memory = memory_store.get_active_memory_prompt(self.db_path)
            snapshot_index = next(
                (
                    index
                    for index in range(len(session.messages) - 1, -1, -1)
                    if session.messages[index].get("role") == "system"
                    and str(session.messages[index].get("content", "")).startswith(
                        _MEMORY_SNAPSHOT_PREFIX
                    )
                ),
                None,
            )
            if active_memory:
                snapshot = f"{_MEMORY_SNAPSHOT_PREFIX}\n{active_memory}"
                if snapshot_index is not None:
                    session.messages[snapshot_index]["content"] = snapshot
                else:
                    session.messages.append({"role": "system", "content": snapshot})
            elif snapshot_index is not None:
                # 用户删空全部活跃记忆时，立即撤掉该会话的旧规则。
                session.messages.pop(snapshot_index)
            session.messages.append({"role": "user", "content": user_message})

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

        # agent-write-guard：待确认写入优先仲裁（与 ask_user 互斥）
        if session.pending_write:
            return await self._resume_pending_write(session, answer, on_event)

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

    async def _resume_pending_write(
        self,
        session: store.AgentSession,
        answer: str,
        on_event: EventCallback | None = None,
    ) -> AgentRunResult:
        """write 确认仲裁（agent-write-guard）。

        确认词命中 → 执行写入；其余回复（含拒绝/修改意见）一律不写入，
        回复全文作为 tool result 回传 LLM 继续编排。
        """
        pending = session.pending_write or {}
        tool_call_id = str(pending.get("tool_call_id", ""))
        node_id = str(pending.get("node_id", ""))
        content = pending.get("content")

        session.pending_write = None
        session.pending_question = None

        if is_write_confirmation(answer):
            result = await self.registry.execute(
                WRITE_NODE_TOOL_NAME, {"node_id": node_id, "content": content}
            )
            written = isinstance(result, dict) and result.get("ok") is True
            tool_result: dict[str, Any] = {
                "ok": written,
                "written": written,
                "node_id": node_id,
            }
            if not written:
                tool_result["error"] = (
                    result.get("error")
                    if isinstance(result, dict)
                    else f"写入失败: {result}"
                )
        else:
            tool_result = {"ok": False, "written": False, "user_reply": answer}

        session.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": self._result_to_content(tool_result),
        })
        store.append_trace(
            session_id=session.id,
            round=0,  # 0 = 恢复阶段解决的写入确认，非循环轮次
            tool_name=WRITE_NODE_TOOL_NAME,
            input_data={"node_id": node_id, "content": content},
            output_data=tool_result,
            db_path=self.db_path,
        )
        session.status = "running"
        store.save_session(session, self.db_path)
        return await self._loop(session, on_event)

    async def _loop(
        self,
        session: store.AgentSession,
        on_event: EventCallback | None = None,
    ) -> AgentRunResult:
        """核心循环：LLM → tool_calls → LLM，直至终结/暂停/耗尽。"""
        max_rounds = settings.agent_max_rounds
        tools_schema = self.registry.schemas()
        rounds_used = 0
        # US-30：本轮 run 内 write_node 被审查打回的次数（不跨 run 持久化）
        write_review_rounds = 0

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

                    # agent-write-guard：合法 write_node 不直接写入，
                    # 暂停等待用户确认（非法参数走下方正常执行路径回错误）。
                    # US-30 reviewer-agent：进门禁前先过独立 Reviewer 双审。
                    if tc_name == WRITE_NODE_TOOL_NAME and self._is_gated_write(tc_args):
                        node_id = str(tc_args.get("node_id", "")).strip()
                        content = tc_args.get("content")
                        review = await self._run_write_review(
                            session, node_id, content, on_event, write_review_rounds
                        )

                        # 不合格且未达打回上限：带意见打回，LLM 依据
                        # review 重写后重新发起（同一循环内继续，不暂停会话）
                        if (
                            not review.get("passed", True)
                            and write_review_rounds < _WRITE_REVIEW_MAX_REJECTS
                        ):
                            write_review_rounds += 1
                            tool_result = {
                                "ok": False,
                                "written": False,
                                "rejected_by_review": True,
                                "review": review,
                            }
                            session.messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": self._result_to_content(tool_result),
                            })
                            store.append_trace(
                                session_id=session.id,
                                round=rounds_used,
                                tool_name=WRITE_NODE_TOOL_NAME,
                                input_data={"node_id": node_id, "content": content},
                                output_data=tool_result,
                                db_path=self.db_path,
                            )
                            continue

                        # 通过或打回耗尽（如实携带问题）→ 进入写入门禁
                        question = (
                            f"Agent 请求写入节点「{node_id}」的简历内容（整段覆盖）。"
                            "回复「确认」执行写入，或说明你的修改意见。"
                        )
                        session.status = "awaiting_user"
                        session.pending_question = question
                        session.pending_write = {
                            "tool_call_id": tc.id,
                            "node_id": node_id,
                            "content": content,
                            "review": review,
                        }
                        store.save_session(session, self.db_path)
                        await self._emit(on_event, {
                            "type": "write_confirm",
                            "node_id": node_id,
                            "content": content,
                            "question": question,
                            "review": review,
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
                    # 若涉及数据库路径且 runner 指定了 db_path，透传给工具
                    if self.db_path and tc_name in ("delete_memory", "list_memories"):
                        tc_args.setdefault("db_path", str(self.db_path))

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

                    # 若成功删除长期记忆，发射 memory_deleted SSE 事件通知前端
                    if tc_name == "delete_memory" and isinstance(result, dict) and result.get("ok"):
                        for del_item in result.get("deleted", []):
                            await self._emit(on_event, {
                                "type": "memory_deleted",
                                "memory_id": del_item.get("id"),
                                "content": del_item.get("content"),
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

    async def _run_write_review(
        self,
        session: store.AgentSession,
        node_id: str,
        content: Any,
        on_event: EventCallback | None,
        write_review_rounds: int,
    ) -> dict[str, Any]:
        """US-30：门禁前的独立双审（fail-open，异常放行）。"""
        evidence = self._collect_review_evidence(content)
        structured_jd = (
            session.context.get("structured_jd")
            if isinstance(session.context, dict)
            else None
        )
        try:
            import inspect

            kwargs: dict[str, Any] = {}
            sig = inspect.signature(self.reviewer.review_draft)
            if "db_path" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                kwargs["db_path"] = self.db_path

            review = await self.reviewer.review_draft(
                content, structured_jd, evidence, **kwargs
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reviewer 审查异常，fail-open 放行: %s", exc)
            review = {"passed": True, "issues": [], "summary": f"审查跳过: {exc}"}
        if not isinstance(review, dict):
            review = {"passed": True, "issues": [], "summary": "审查结果非法，已放行"}

        await self._emit(on_event, {
            "type": "review",
            "node_id": node_id,
            "round": write_review_rounds + 1,
            "passed": bool(review.get("passed")),
            "issues": review.get("issues", []),
            "summary": review.get("summary", ""),
        })
        return review

    @staticmethod
    def _collect_review_evidence(content: Any) -> list[dict[str, Any]]:
        """为审查检索知识库证据（从草稿提取关键词）。"""
        query = AgentRunner._review_query(content)
        if not query:
            return []
        try:
            from resume_agent.services.knowledge_search import search_knowledge

            return search_knowledge([query], top_k=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning("审查证据检索失败: %s", exc)
            return []

    @staticmethod
    def _review_query(content: Any) -> str:
        """从草稿内容提取文本关键词（叶子字符串拼接，截断防超长）。"""
        parts: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, str):
                if node.strip():
                    parts.append(node.strip()[:50])
            elif isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(content)
        return " ".join(parts)[:200]

    @staticmethod
    async def _emit(on_event: EventCallback | None, event: dict[str, Any]) -> None:
        """发出事件（无回调时为空操作）。"""
        if on_event is not None:
            await on_event(event)

    @staticmethod
    def _is_gated_write(tc_args: dict[str, Any]) -> bool:
        """write_node 参数合法（node_id 非空 + content 为对象）才走门禁。

        非法参数直接按普通工具执行，错误 envelope 原路返回，不打扰用户。
        """
        node_id = str(tc_args.get("node_id", "") or "").strip()
        return bool(node_id) and isinstance(tc_args.get("content"), dict)

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
