"""版本 Diff 对比端点（US-10）。

对比两个版本树节点的 content_json，逐字段高亮差异。

仅对比 ``experience`` / ``projects`` / ``skills`` 三段：
- experience: 按 ``company`` + ``role`` 匹配，对比 ``highlights``。
- projects:   按 ``name`` 匹配，对比 ``description`` / ``tech_stack``。
- skills:     按 ``category`` + ``name`` 匹配，对比 ``context``。

content_json 为 ``null`` 时视为空 dict ``{}``，缺失的段落视为空集合。
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from resume_agent.api.response import error, success
from resume_agent.db.connection import get_connection

router = APIRouter(prefix="/diff", tags=["diff"])


class DiffRequest(BaseModel):
    """版本 Diff 请求体。"""

    node_a_id: str
    node_b_id: str


# === 读取节点 ===


def _fetch_node(node_id: str) -> dict[str, Any] | None:
    """从 ``resume_versions`` 表读取单个节点行。

    Args:
        node_id: 业务节点 ID。

    Returns:
        节点行字典（含 ``content_json`` 原始字符串）；节点不存在时返回 ``None``。
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT node_id, title, content_json
            FROM resume_versions
            WHERE node_id = ?
            """,
            (node_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def _parse_content_json(raw: Any) -> dict[str, Any]:
    """解析 ``content_json`` 字段为 dict。

    - ``None`` → 空 dict ``{}``
    - JSON 字符串 → 解析为 dict；解析失败时退化为空 dict
    - 已是 dict → 原样返回
    - 其他类型 → 空 dict

    Args:
        raw: 数据库中 ``content_json`` 列的原始值。

    Returns:
        解析后的字典。
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
    return {}


# === 通用辅助 ===


def _as_list(value: Any) -> list[Any]:
    """将任意值转为 list；非 list 视为空列表。"""
    if isinstance(value, list):
        return value
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    """将任意值转为 dict；非 dict 视为空 dict。"""
    if isinstance(value, dict):
        return value
    return {}


# === experience 对比 ===


def _exp_key(item: Any) -> tuple[str, str]:
    """提取 experience 条目的匹配键 ``(company, role)``。"""
    if not isinstance(item, dict):
        return ("", "")
    return (
        str(item.get("company") or ""),
        str(item.get("role") or ""),
    )


def _diff_highlights(old_hl: list[Any], new_hl: list[Any]) -> list[dict[str, Any]]:
    """逐条对比 highlights 列表，返回子项差异。

    策略（基于字符串集合，保序输出）：
    - 在 new 但不在 old → added
    - 在 old 但不在 new → removed

    Args:
        old_hl: 旧 highlights 列表。
        new_hl: 新 highlights 列表。

    Returns:
        子项差异列表。
    """
    details: list[dict[str, Any]] = []
    old_set = [str(h) for h in old_hl if h is not None]
    new_set = [str(h) for h in new_hl if h is not None]

    # added：遍历新列表，保留出现顺序
    for idx, h in enumerate(new_set):
        if h not in old_set:
            details.append(
                {
                    "type": "added",
                    "field": f"highlights[{idx}]",
                    "value": h,
                }
            )
    # removed：遍历旧列表，保留出现顺序
    for idx, h in enumerate(old_set):
        if h not in new_set:
            details.append(
                {
                    "type": "removed",
                    "field": f"highlights[{idx}]",
                    "value": h,
                }
            )
    return details


def _diff_experience(list_a: list[Any], list_b: list[Any]) -> list[dict[str, Any]]:
    """按 ``company`` + ``role`` 匹配，返回差异列表。

    匹配规则：``company`` 和 ``role`` 都相同视为同一条经历。
    - 在 B 但不在 A → added
    - 在 A 但不在 B → removed
    - 都在但 highlights 不同 → modified（逐条对比 highlights）

    Args:
        list_a: A 节点的 experience 列表。
        list_b: B 节点的 experience 列表。

    Returns:
        差异项列表，每项含 ``type`` / ``field`` / ``value`` 或
        ``old_value`` / ``new_value`` / ``details``。
    """
    diffs: list[dict[str, Any]] = []

    # 以 (company, role) 为键建立索引
    index_a: dict[tuple[str, str], int] = {}
    for idx, item in enumerate(list_a):
        index_a.setdefault(_exp_key(item), idx)

    matched_a_keys: set[tuple[str, str]] = set()

    for idx_b, item_b in enumerate(list_b):
        key_b = _exp_key(item_b)
        if key_b in index_a:
            matched_a_keys.add(key_b)
            idx_a = index_a[key_b]
            item_a = list_a[idx_a]
            hl_a = _as_list(item_a.get("highlights")) if isinstance(item_a, dict) else []
            hl_b = _as_list(item_b.get("highlights")) if isinstance(item_b, dict) else []
            hl_details = _diff_highlights(hl_a, hl_b)
            if hl_details:
                diffs.append(
                    {
                        "type": "modified",
                        "field": f"experience[{idx_a}]",
                        "old_value": item_a,
                        "new_value": item_b,
                        "details": hl_details,
                    }
                )
        else:
            diffs.append(
                {
                    "type": "added",
                    "field": f"experience[{idx_b}]",
                    "value": item_b,
                }
            )

    # removed：在 A 但不在 B
    for idx_a, item_a in enumerate(list_a):
        if _exp_key(item_a) not in matched_a_keys:
            diffs.append(
                {
                    "type": "removed",
                    "field": f"experience[{idx_a}]",
                    "value": item_a,
                }
            )

    return diffs


# === projects 对比 ===


def _proj_key(item: Any) -> str:
    """提取 project 条目的匹配键 ``name``。"""
    if isinstance(item, dict):
        return str(item.get("name") or "")
    return ""


def _diff_projects(list_a: list[Any], list_b: list[Any]) -> list[dict[str, Any]]:
    """按 ``name`` 匹配，返回差异列表。

    - 在 B 但不在 A → added
    - 在 A 但不在 B → removed
    - 都在但 ``description`` / ``tech_stack`` 不同 → modified

    Args:
        list_a: A 节点的 projects 列表。
        list_b: B 节点的 projects 列表。

    Returns:
        差异项列表。
    """
    diffs: list[dict[str, Any]] = []

    index_a: dict[str, int] = {}
    for idx, item in enumerate(list_a):
        index_a.setdefault(_proj_key(item), idx)

    matched_a_keys: set[str] = set()

    for idx_b, item_b in enumerate(list_b):
        key_b = _proj_key(item_b)
        if key_b in index_a and key_b != "":
            matched_a_keys.add(key_b)
            idx_a = index_a[key_b]
            item_a = list_a[idx_a]
            details = _diff_project_fields(item_a, item_b)
            if details:
                diffs.append(
                    {
                        "type": "modified",
                        "field": f"projects[{idx_a}]",
                        "old_value": item_a,
                        "new_value": item_b,
                        "details": details,
                    }
                )
        else:
            diffs.append(
                {
                    "type": "added",
                    "field": f"projects[{idx_b}]",
                    "value": item_b,
                }
            )

    for idx_a, item_a in enumerate(list_a):
        key_a = _proj_key(item_a)
        if key_a not in matched_a_keys and key_a != "":
            diffs.append(
                {
                    "type": "removed",
                    "field": f"projects[{idx_a}]",
                    "value": item_a,
                }
            )

    return diffs


def _diff_project_fields(
    item_a: Any, item_b: Any
) -> list[dict[str, Any]]:
    """对比单个 project 的 ``description`` / ``tech_stack`` 字段。

    Args:
        item_a: 旧 project 对象。
        item_b: 新 project 对象。

    Returns:
        字段级差异列表；为空表示无差异。
    """
    details: list[dict[str, Any]] = []
    if not isinstance(item_a, dict):
        item_a = {}
    if not isinstance(item_b, dict):
        item_b = {}

    desc_a = item_a.get("description")
    desc_b = item_b.get("description")
    if desc_a != desc_b:
        details.append(
            {
                "type": "modified",
                "field": "description",
                "old_value": desc_a,
                "new_value": desc_b,
            }
        )

    ts_a = item_a.get("tech_stack")
    ts_b = item_b.get("tech_stack")
    if ts_a != ts_b:
        details.append(
            {
                "type": "modified",
                "field": "tech_stack",
                "old_value": ts_a,
                "new_value": ts_b,
            }
        )
    return details


# === skills 对比 ===


_SKILL_CATEGORIES: tuple[str, ...] = ("tech_stack", "hard_skills", "soft_skills")


def _skill_key(category: str, item: Any) -> tuple[str, str]:
    """提取 skill 条目的匹配键 ``(category, name)``。"""
    name = ""
    if isinstance(item, dict):
        name = str(item.get("name") or "")
    return (category, name)


def _diff_skills(skills_a: Any, skills_b: Any) -> list[dict[str, Any]]:
    """按 ``category`` + ``name`` 匹配，返回差异列表。

    遍历 ``tech_stack`` / ``hard_skills`` / ``soft_skills`` 三个类别，
    按 ``name`` 匹配，对比 ``context``。

    - 在 B 但不在 A → added
    - 在 A 但不在 B → removed
    - 都在但 ``context`` 不同 → modified

    Args:
        skills_a: A 节点的 skills 对象（dict，键为类别名）。
        skills_b: B 节点的 skills 对象。

    Returns:
        差异项列表。
    """
    skills_a = _as_dict(skills_a)
    skills_b = _as_dict(skills_b)
    diffs: list[dict[str, Any]] = []

    for category in _SKILL_CATEGORIES:
        list_a = _as_list(skills_a.get(category))
        list_b = _as_list(skills_b.get(category))

        index_a: dict[tuple[str, str], int] = {}
        for idx, item in enumerate(list_a):
            index_a.setdefault(_skill_key(category, item), idx)

        matched_a_keys: set[tuple[str, str]] = set()

        for idx_b, item_b in enumerate(list_b):
            key_b = _skill_key(category, item_b)
            if key_b in index_a and key_b[1] != "":
                matched_a_keys.add(key_b)
                idx_a = index_a[key_b]
                item_a = list_a[idx_a]
                ctx_a = item_a.get("context") if isinstance(item_a, dict) else None
                ctx_b = item_b.get("context") if isinstance(item_b, dict) else None
                if ctx_a != ctx_b:
                    diffs.append(
                        {
                            "type": "modified",
                            "field": f"skills.{category}[{idx_a}]",
                            "old_value": item_a,
                            "new_value": item_b,
                            "details": [
                                {
                                    "type": "modified",
                                    "field": "context",
                                    "old_value": ctx_a,
                                    "new_value": ctx_b,
                                }
                            ],
                        }
                    )
            else:
                diffs.append(
                    {
                        "type": "added",
                        "field": f"skills.{category}[{idx_b}]",
                        "value": item_b,
                    }
                )

        for idx_a, item_a in enumerate(list_a):
            key_a = _skill_key(category, item_a)
            if key_a not in matched_a_keys and key_a[1] != "":
                diffs.append(
                    {
                        "type": "removed",
                        "field": f"skills.{category}[{idx_a}]",
                        "value": item_a,
                    }
                )

    return diffs


# === 汇总 ===


def _compute_diff(content_a: dict[str, Any], content_b: dict[str, Any]) -> dict[str, Any]:
    """汇总三段 diff + 统计。

    对比方向：以 B 为基准，查看 A 相对 B 的变化。
    - A 有 B 没有 → added（A 新增了）
    - B 有 A 没有 → removed（A 移除了）
    - 两者都有但不同 → modified（A 修改了），old_value=B 的值，new_value=A 的值

    Args:
        content_a: A 节点解析后的 content_json dict（对比目标，"新版本"）。
        content_b: B 节点解析后的 content_json dict（对比基准，"旧版本"）。

    Returns:
        包含 ``experience`` / ``projects`` / ``skills`` 差异列表与
        ``summary`` 统计（added / removed / modified 计数）的字典。
    """
    # 以 B 为旧版本（list_a 参数），A 为新版本（list_b 参数）
    # _diff_* 函数逻辑：在 list_b(A) 但不在 list_a(B) → added；在 list_a(B) 但不在 list_b(A) → removed
    exp_diffs = _diff_experience(
        _as_list(content_b.get("experience")),
        _as_list(content_a.get("experience")),
    )
    proj_diffs = _diff_projects(
        _as_list(content_b.get("projects")),
        _as_list(content_a.get("projects")),
    )
    skill_diffs = _diff_skills(
        content_b.get("skills"),
        content_a.get("skills"),
    )

    all_diffs = exp_diffs + proj_diffs + skill_diffs
    summary = {
        "added": sum(1 for d in all_diffs if d["type"] == "added"),
        "removed": sum(1 for d in all_diffs if d["type"] == "removed"),
        "modified": sum(1 for d in all_diffs if d["type"] == "modified"),
    }

    return {
        "experience": exp_diffs,
        "projects": proj_diffs,
        "skills": skill_diffs,
        "summary": summary,
    }


# === 端点 ===


@router.post("")
async def compare_nodes(req: DiffRequest) -> dict[str, Any]:
    """对比两个节点的 content_json。

    读取两个节点的 content_json，逐字段对比差异。

    Args:
        req: 包含 ``node_a_id`` / ``node_b_id`` 的请求体。

    Returns:
        统一响应 envelope。``data`` 含 ``node_a`` / ``node_b`` 元信息、
        ``diffs``（experience / projects / skills）与 ``summary``。
        任一节点不存在时返回 HTTP 404 + error envelope。
    """
    # 1. 读取节点
    node_a = _fetch_node(req.node_a_id)
    if node_a is None:
        return JSONResponse(
            status_code=404,
            content=error("NODE_NOT_FOUND", f"节点不存在: {req.node_a_id}"),
        )
    node_b = _fetch_node(req.node_b_id)
    if node_b is None:
        return JSONResponse(
            status_code=404,
            content=error("NODE_NOT_FOUND", f"节点不存在: {req.node_b_id}"),
        )

    # 2. 解析 content_json
    content_a = _parse_content_json(node_a.get("content_json"))
    content_b = _parse_content_json(node_b.get("content_json"))

    # 3. 计算差异
    diffs = _compute_diff(content_a, content_b)

    # 4. 返回
    return success(
        {
            "node_a": {
                "node_id": node_a.get("node_id"),
                "title": node_a.get("title"),
            },
            "node_b": {
                "node_id": node_b.get("node_id"),
                "title": node_b.get("title"),
            },
            "diffs": {
                "experience": diffs["experience"],
                "projects": diffs["projects"],
                "skills": diffs["skills"],
            },
            "summary": diffs["summary"],
        }
    )


__all__ = ["DiffRequest", "compare_nodes", "router"]
