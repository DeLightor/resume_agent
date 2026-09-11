"""Agent 长期记忆存储与意图抽取（US-35 agent-long-term-memory）。

提供用户级记忆规则的 SQLite CRUD、注入提示词格式化（预算限制与 Fail-open）、
以及对话中的记忆指令意图识别。
"""

from __future__ import annotations

import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from resume_agent.db.connection import get_connection

logger = logging.getLogger("resume_agent")

MEMORY_TYPES = ("preference", "correction", "style_sample")
DEFAULT_MAX_PROMPT_ITEMS = 8
DEFAULT_MAX_PROMPT_CHARS = 800

_TYPE_TAG_MAP = {
    "preference": "偏好",
    "correction": "纠偏",
    "style_sample": "风格",
}


@dataclass
class AgentMemory:
    """Agent 长期记忆数据类。"""

    id: str
    type: str  # preference / correction / style_sample
    content: str
    source: str = "auto_inferred"  # auto_inferred / manual
    session_id: str | None = None
    active: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "source": self.source,
            "session_id": self.session_id,
            "active": self.active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _row_to_memory(row: dict[str, Any]) -> AgentMemory:
    return AgentMemory(
        id=str(row["id"]),
        type=str(row["type"]),
        content=str(row["content"]),
        source=str(row.get("source") or "auto_inferred"),
        session_id=str(row["session_id"]) if row.get("session_id") else None,
        active=bool(row.get("active", 1)),
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


def create_memory(
    content: str,
    type: str = "preference",
    source: str = "manual",
    session_id: str | None = None,
    active: bool = True,
    db_path: Path | str | None = None,
) -> AgentMemory:
    """创建或复用记忆规则。"""
    cleaned = (content or "").strip()
    if not cleaned:
        raise ValueError("内容不能为空")
    if type not in MEMORY_TYPES:
        raise ValueError(f"非法记忆类型: {type}，支持: {MEMORY_TYPES}")

    with get_connection(db_path) as conn:
        # 去重检查：若完全相同的活跃规则已存在，仅更新 updated_at
        existing = conn.execute(
            "SELECT id FROM agent_memories WHERE content = ? AND active = 1",
            [cleaned],
        ).fetchone()
        if existing:
            existing_id = str(existing["id"])
            conn.execute(
                "UPDATE agent_memories SET type = ?, updated_at = datetime('now') WHERE id = ?",
                [type, existing_id],
            )
            row = conn.execute(
                "SELECT * FROM agent_memories WHERE id = ?", [existing_id]
            ).fetchone()
            return _row_to_memory(row)

        mem_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO agent_memories (
                id, type, content, source, session_id, active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            [mem_id, type, cleaned, source, session_id, 1 if active else 0],
        )
        row = conn.execute(
            "SELECT * FROM agent_memories WHERE id = ?", [mem_id]
        ).fetchone()
        return _row_to_memory(row)


def get_memory(
    memory_id: str,
    db_path: Path | str | None = None,
) -> AgentMemory | None:
    """按 ID 获取记忆规则。"""
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM agent_memories WHERE id = ?", [memory_id]
            ).fetchone()
        if not row:
            return None
        return _row_to_memory(row)
    except sqlite3.Error as exc:
        logger.warning("获取记忆失败: %s", exc)
        return None


def list_memories(
    db_path: Path | str | None = None,
    active_only: bool = False,
    type_filter: str | None = None,
) -> list[AgentMemory]:
    """查询记忆列表，支持生效状态与类型筛选，按更新时间降序。"""
    query = "SELECT * FROM agent_memories WHERE 1=1"
    params: list[Any] = []
    if active_only:
        query += " AND active = 1"
    if type_filter and type_filter in MEMORY_TYPES:
        query += " AND type = ?"
        params.append(type_filter)
    query += " ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC, rowid DESC"

    try:
        with get_connection(db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_memory(r) for r in rows]
    except sqlite3.Error as exc:
        logger.warning("查询记忆列表异常: %s", exc)
        return []


def update_memory(
    memory_id: str,
    content: str | None = None,
    active: bool | None = None,
    type: str | None = None,
    db_path: Path | str | None = None,
) -> AgentMemory | None:
    """更新记忆内容、状态或类型。"""
    existing = get_memory(memory_id, db_path)
    if existing is None:
        return None

    updates: list[str] = ["updated_at = datetime('now')"]
    params: list[Any] = []

    if content is not None:
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("内容不能为空")
        updates.append("content = ?")
        params.append(cleaned)

    if active is not None:
        updates.append("active = ?")
        params.append(1 if active else 0)

    if type is not None:
        if type not in MEMORY_TYPES:
            raise ValueError(f"非法记忆类型: {type}")
        updates.append("type = ?")
        params.append(type)

    params.append(memory_id)
    with get_connection(db_path) as conn:
        conn.execute(
            f"UPDATE agent_memories SET {', '.join(updates)} WHERE id = ?",
            params,
        )
    return get_memory(memory_id, db_path)


def delete_memory(
    memory_id: str,
    db_path: Path | str | None = None,
) -> bool:
    """删除记忆项。"""
    try:
        with get_connection(db_path) as conn:
            cur = conn.execute("DELETE FROM agent_memories WHERE id = ?", [memory_id])
            return cur.rowcount > 0
    except sqlite3.Error as exc:
        logger.warning("删除记忆异常: %s", exc)
        return False


def search_and_delete_memory(
    query: str | None = None,
    memory_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """根据关键词、最新记录或 ID 检索并删除长期记忆。

    1. 若指定 memory_id，直接删除对应记忆。
    2. 若 query 表示「最新/刚刚/最近」或为空，删除最新创建的一条记忆。
    3. 否则根据 query 关键词匹配 content，删除最匹配且最新的记忆。
    """
    if memory_id:
        target = get_memory(memory_id, db_path)
        if target is None:
            return {"ok": False, "deleted": [], "message": f"未找到 ID 为 {memory_id} 的记忆"}
        ok = delete_memory(memory_id, db_path)
        if ok:
            return {
                "ok": True,
                "deleted": [target.to_dict()],
                "message": f"已成功删除记忆：「{target.content}」",
            }
        return {"ok": False, "deleted": [], "message": f"删除记忆失败: {memory_id}"}

    all_mems = list_memories(db_path=db_path, active_only=False)
    if not all_mems:
        return {"ok": False, "deleted": [], "message": "当前没有保存任何长期记忆"}

    raw_q = (query or "").strip()
    q_lower = raw_q.lower()

    # 识别是否指代「刚刚/最新/上一条」
    latest_keywords = {
        "刚刚", "刚才", "最新", "最近", "上一条", "最后一条",
        "刚加的", "刚添加的", "刚刚添加的那条", "刚刚添加的",
        "latest", "last",
    }
    is_latest = not raw_q or any(k in q_lower for k in latest_keywords)

    if is_latest:
        target = all_mems[0]
        delete_memory(target.id, db_path)
        return {
            "ok": True,
            "deleted": [target.to_dict()],
            "message": f"已成功删除最新添加的记忆：「{target.content}」",
        }

    # 尝试子串包含匹配
    matches: list[AgentMemory] = []
    for m in all_mems:
        if q_lower in m.content.lower() or m.content.lower() in q_lower:
            matches.append(m)

    if not matches:
        # 去除口语停用词后进行多关键词模糊匹配
        stopwords = {
            "请", "帮我", "把", "关于", "那条", "这个", "那个", "记忆", "规则",
            "删除", "删掉", "撤销", "取消", "的", "和", "了", "一下", "刚刚", "刚才",
        }
        cleaned_q = raw_q
        for sw in sorted(stopwords, key=len, reverse=True):
            cleaned_q = cleaned_q.replace(sw, " ")
        tokens = [t.strip().lower() for t in cleaned_q.split() if len(t.strip()) >= 2]
        if not tokens:
            tokens = [t for t in re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9]+", raw_q) if t not in stopwords]

        if tokens:
            for m in all_mems:
                m_text = m.content.lower()
                matched_count = sum(1 for tok in tokens if tok in m_text)
                if matched_count > 0:
                    matches.append(m)

    if matches:
        target = matches[0]
        delete_memory(target.id, db_path)
        return {
            "ok": True,
            "deleted": [target.to_dict()],
            "message": f"已成功删除记忆：「{target.content}」",
        }

    existing_summaries = [f"[{m.type}] {m.content}" for m in all_mems[:5]]
    return {
        "ok": False,
        "deleted": [],
        "message": f"未找到匹配「{raw_q}」的记忆",
        "existing_memories": existing_summaries,
    }



def get_active_memory_prompt(
    db_path: Path | str | None = None,
    max_items: int = DEFAULT_MAX_PROMPT_ITEMS,
    max_chars: int = DEFAULT_MAX_PROMPT_CHARS,
) -> str:
    """获取格式化后的活跃记忆提示词分块（含 Top-K 与字符预算截断，fail-open）。"""
    try:
        memories = list_memories(db_path=db_path, active_only=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取活跃记忆失败，fail-open 降级: %s", exc)
        return ""

    if not memories:
        return ""

    selected = memories[:max_items]
    lines: list[str] = [
        "【用户个性化长期偏好与历史纠偏】（必须严格遵守以下规则）："
    ]
    for mem in selected:
        tag = _TYPE_TAG_MAP.get(mem.type, "偏好")
        line = f"- [{tag}] {mem.content}"
        lines.append(line)

    result = "\n".join(lines)
    if len(result) > max_chars:
        # 截断保护
        result = result[: max_chars - 3] + "..."
    return result


def extract_memory_intent(text: str) -> tuple[str, str] | None:
    """从对话文本中检测是否包含记忆沉淀意图。

    Returns:
        (type, content) 或 None。
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    # 常见明确前缀匹配
    patterns = [
        # 请记住：/ 记住：/ 请记住...
        r"^(?:请?记住[：:,，]?\s*)(.+)$",
        # 以后都不要/以后不要/以后请/以后都...
        r"^(?:以后(?:都)?(?:请|必须|要|尽量)?[：:,，]?\s*)(.+)$",
        # 偏好：/ 规则：/ 红线：
        r"^(?:(?:偏好|规则|红线|习惯)[：:,，]\s*)(.+)$",
        # 不要再... / 别再... / 严禁...
        r"^(?:(?:不要再?|别再?|严禁|切勿|禁止)\s*)(.+)$",
    ]

    matched_content: str | None = None

    for p in patterns:
        m = re.match(p, cleaned, re.IGNORECASE)
        if m:
            matched_content = m.group(1).strip()
            break

    # 特别支持句中包含："请记住以 STAR 原则..."
    if not matched_content and "请记住" in cleaned:
        parts = cleaned.split("请记住", 1)
        matched_content = parts[1].lstrip("：:,， ").strip()


    if not matched_content or len(matched_content) < 2:
        return None

    # 分类研判
    combined = (cleaned + " " + matched_content).lower()

    # 纠偏优先判定
    if any(neg in combined for neg in ("不要", "别", "严禁", "切勿", "禁止", "不能", "禁用", "纠偏")):
        return ("correction", matched_content)

    # 风格判定
    if any(sty in combined for sty in ("star", "风格", "句式", "口吻", "语气", "结构", "排版", "模版", "模板")):
        return ("style_sample", matched_content)

    # 其余归为通用偏好
    return ("preference", matched_content)


_MEMORY_EXTRACTOR_SYSTEM_PROMPT = """你是一个专业的简历对话意图分析官。
请分析用户给 AI 助手的最新一条发言，判断用户是否在表达个人长期偏好、纠偏红线、表达风格习惯或对 AI 行为的规则设定。

用户可能在自然表达中随口表达或夹杂这些看法（无需特定前缀），例如：
- 纠偏红线（correction）：禁用的词汇/内容/格式。例："我不喜欢写精通"、"别给我加薪资"、"不要写那些虚无缥缈的套话"、"刚才写的太水了，把精通去掉"
- 个人偏好（preference）：期望侧重的方向/能力/经历。例："我更倾向突出高并发和高可用"、"我主要是做后端架构的，多往这方面靠"、"突出我带团队的经历"
- 风格习惯（style_sample）：句式/语言风格/排版结构。例："我习惯用 STAR 原则写项目"、"语言尽量精简有力，多用动词"、"不要长篇大论，短句为主"

判定原则：
1. 仅当用户表达了具有【长期/跨会话适用性】的偏好、要求、习惯或禁忌时，才判定为规则。
2. 若用户只是在针对某次具体操作进行单次修改指令（如"帮我润色一下"、"第一段删掉"、"看看我的得分"、"这个错别字改一下"、"把手机号换成 138"），不属于长期记忆，has_memory 为 false。
3. 提炼出的规则内容（rule）必须简明扼要、客观独立，去除用户口语语气词（如"我想要..."提炼为"经历重点突出..."）。若一句话包含多项规则，请分别拆分提炼。

输出 JSON 格式：
{
  "has_memory": bool,
  "memories": [
    {
      "type": "preference" | "correction" | "style_sample",
      "rule": "提炼出的简短规则内容"
    }
  ]
}
"""


def _parse_json_safely(response: str) -> dict[str, Any]:
    """宽松解析 LLM 返回的 JSON。"""
    import json

    cleaned = (response or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            data = json.loads(cleaned[first : last + 1])
        else:
            return {}
    return data if isinstance(data, dict) else {}


async def extract_memories_smart(
    llm: Any | None,
    text: str,
) -> list[dict[str, str]]:
    """智能从自然语言对话中识别长期偏好与规则。

    - 优先使用 LLM 语义分析理解自然语言中夹带的偏好看法（无固定句式限制）；
    - 当 LLM 未配置或调用异常时，自动平滑降级使用正则/关键词兜底。

    Returns:
        [{"type": "preference"|"correction"|"style_sample", "content": "..."}]
    """
    cleaned = (text or "").strip()
    if not cleaned or len(cleaned) < 2:
        return []

    # 1. 尝试 LLM 智能语义理解
    if llm is not None and getattr(llm, "configured", False):
        try:
            resp = await llm.chat(
                system_prompt=_MEMORY_EXTRACTOR_SYSTEM_PROMPT,
                user_content=f"用户发言：\n{cleaned}",
                response_format_json=True,
            )
            data = _parse_json_safely(resp)
            if data.get("has_memory"):
                memories: list[dict[str, str]] = []
                raw_list = data.get("memories")
                if isinstance(raw_list, list):
                    for item in raw_list:
                        if isinstance(item, dict):
                            rule = str(item.get("rule", "")).strip()
                            t = str(item.get("type", "preference")).strip()
                            if rule and t in MEMORY_TYPES:
                                memories.append({"type": t, "content": rule})
                # 容错单对象格式
                if not memories and data.get("rule"):
                    rule = str(data["rule"]).strip()
                    t = str(data.get("type", "preference")).strip()
                    if rule and t in MEMORY_TYPES:
                        memories.append({"type": t, "content": rule})
                if memories:
                    return memories
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 智能记忆抽取异常，降级到规则匹配: %s", exc)

    # 2. 规则兜底
    fallback = extract_memory_intent(cleaned)
    if fallback:
        return [{"type": fallback[0], "content": fallback[1]}]

    return []

