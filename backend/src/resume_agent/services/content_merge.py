"""Three-way content differences used by the upstream merge flow (US-33).

The service deliberately produces decisions, never an automatic merge.  A
decision includes enough stable locator data to apply the user's choice to the
current child content later in the same database transaction.
"""
from __future__ import annotations

import copy
import json
from difflib import SequenceMatcher
from typing import Any

_MISSING = object()
_SECTIONS = ("personal_info", "experience", "projects", "skills")
_LABELS = {
    "personal_info": "个人信息", "experience": "工作经历", "projects": "项目经历", "skills": "技能",
    "contact": "联系方式", "education": "教育背景", "summary": "自我评价", "bullets": "工作成果",
}


def _same(left: Any, right: Any) -> bool:
    if left is _MISSING or right is _MISSING:
        return left is right
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(right, ensure_ascii=False, sort_keys=True)


def _label(parts: list[str]) -> str:
    return " / ".join(_LABELS.get(part, part) for part in parts)


def _change(
    key: str, section: str, label: str, base: Any, upstream: Any, local: Any, locator: dict[str, Any],
    *, base_missing: bool = False, upstream_missing: bool = False, local_missing: bool = False,
) -> tuple[str, dict[str, Any]]:
    return key, {
        "section": section, "label": label, "base": None if base_missing else copy.deepcopy(base),
        "old": None if local_missing else copy.deepcopy(local), "new": None if upstream_missing else copy.deepcopy(upstream),
        "conflict": not _same(local, base) and not _same(local, upstream), "_locator": locator,
        "_base_missing": base_missing, "_new_missing": upstream_missing, "_old_missing": local_missing,
    }


def _dict_changes(section: str, base: Any, upstream: Any, local: Any, path: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """Diff dictionaries recursively; lists are intentionally atomic here."""
    if isinstance(base, dict) or isinstance(upstream, dict):
        base_dict = base if isinstance(base, dict) else {}
        upstream_dict = upstream if isinstance(upstream, dict) else {}
        local_dict = local if isinstance(local, dict) else {}
        result: list[tuple[str, dict[str, Any]]] = []
        for name in sorted(set(base_dict) | set(upstream_dict)):
            before = base_dict.get(name, _MISSING)
            after = upstream_dict.get(name, _MISSING)
            current = local_dict.get(name, _MISSING)
            if _same(before, after):
                continue
            result.extend(_dict_changes(section, before, after, current, path + [name]))
        return result
    if _same(base, upstream) or _same(local, upstream):
        return []
    key = ".".join(path)
    return [_change(key, section, _label(path), base, upstream, local, {"kind": "path", "path": path},
                    base_missing=base is _MISSING, upstream_missing=upstream is _MISSING, local_missing=local is _MISSING)]


def _find_slice(values: list[Any], target: list[Any]) -> int | None:
    if not target:
        return None
    for index in range(len(values) - len(target) + 1):
        if _same(values[index:index + len(target)], target):
            return index
    return None


def _sequence_changes(section: str, base: list[Any], upstream: list[Any], local: list[Any], locator: dict[str, Any], label: str) -> list[tuple[str, dict[str, Any]]]:
    """Produce independently applicable sequence patches.

    We align parent values to the common baseline.  A patch searches the child
    for its baseline slice at apply time, so a local insertion does not shift a
    later bullet or skill decision.
    """
    matcher = SequenceMatcher(a=[json.dumps(v, ensure_ascii=False, sort_keys=True) for v in base], b=[json.dumps(v, ensure_ascii=False, sort_keys=True) for v in upstream], autojunk=False)
    result: list[tuple[str, dict[str, Any]]] = []
    for ordinal, (tag, left_start, left_end, right_start, right_end) in enumerate(matcher.get_opcodes()):
        if tag == "equal":
            continue
        old, new = base[left_start:left_end], upstream[right_start:right_end]
        before = base[left_start - 1] if left_start else _MISSING
        after = base[left_end] if left_end < len(base) else _MISSING
        seq_locator = {**locator, "kind": "sequence", "old": old, "before": None if before is _MISSING else before,
                       "after": None if after is _MISSING else after, "_before_missing": before is _MISSING,
                       "_after_missing": after is _MISSING}
        # Parent additions cannot conflict with an unrelated local insertion.
        if old:
            local_piece_index = _find_slice(local, old)
            current: Any = old if local_piece_index is not None else local
            local_missing = local_piece_index is None
        else:
            # The child may have independently added the exact parent item.
            # It already converged, so presenting that addition is redundant.
            current = new if _find_slice(local, new) is not None else []
            local_missing = False
        key = f"{section}:{label}:{ordinal}"
        item = dict(_change(key, section, label, old, new, current, seq_locator, local_missing=local_missing)[1])
        item["_locator"]["new"] = copy.deepcopy(new)
        result.append((key, item))
    return result


def _entry_key(item: Any, fields: tuple[str, ...]) -> tuple[Any, ...] | None:
    if not isinstance(item, dict):
        return None
    values = tuple(item.get(field, _MISSING) for field in fields)
    # These fields are user-facing identifiers.  Treat malformed LLM or API
    # data as unmatchable so we present one safe whole-section decision instead
    # of hashing an arbitrary list/dict or pairing the wrong entries.
    if any(not isinstance(value, str) or not value.strip() for value in values):
        return None
    return values


def _keyed_changes(section: str, fields: tuple[str, ...], base: Any, upstream: Any, local: Any) -> list[tuple[str, dict[str, Any]]]:
    base_items = base if isinstance(base, list) else []
    upstream_items = upstream if isinstance(upstream, list) else []
    local_items = local if isinstance(local, list) else []
    b_keys = [_entry_key(item, fields) for item in base_items]
    u_keys = [_entry_key(item, fields) for item in upstream_items]
    # Duplicate/missing identity is unsafe to pair: expose a single whole-section decision.
    if None in b_keys or None in u_keys or len(set(b_keys)) != len(b_keys) or len(set(u_keys)) != len(u_keys):
        if _same(base_items, upstream_items):
            return []
        return [_change(section, section, _LABELS[section], base_items, upstream_items, local_items, {"kind": "section", "section": section})]
    b_map = dict(zip(b_keys, base_items, strict=True))
    u_map = dict(zip(u_keys, upstream_items, strict=True))
    l_map = {key: value for value in local_items if (key := _entry_key(value, fields)) is not None}
    result: list[tuple[str, dict[str, Any]]] = []
    for key in sorted(set(b_map) | set(u_map), key=repr):
        before, after, current = b_map.get(key, _MISSING), u_map.get(key, _MISSING), l_map.get(key, _MISSING)
        identity = {"kind": "entry", "section": section, "fields": list(fields), "key": list(key)}
        if before is _MISSING or after is _MISSING:
            if _same(before, after):
                continue
            result.append(_change(f"{section}:{key}", section, _LABELS[section], before, after, current, identity,
                                  base_missing=before is _MISSING, upstream_missing=after is _MISSING, local_missing=current is _MISSING))
            continue
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        for field in sorted(set(before) | set(after)):
            old, new, child = before.get(field, _MISSING), after.get(field, _MISSING), (current.get(field, _MISSING) if isinstance(current, dict) else _MISSING)
            if _same(old, new) or field in fields:
                continue
            field_label = _label([section, str(key[0]), field])
            field_locator = {**identity, "field": field}
            if isinstance(old, list) and isinstance(new, list) and field in ("bullets", "highlights"):
                result.extend(_sequence_changes(section, old, new, child if isinstance(child, list) else [], field_locator, field_label))
            else:
                result.append(_change(f"{section}:{key}:{field}", section, field_label, old, new, child, field_locator,
                                      base_missing=old is _MISSING, upstream_missing=new is _MISSING, local_missing=child is _MISSING))
    return result


def build_changes(base: dict[str, Any], upstream: dict[str, Any], local: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return parent-only updates and explicit three-way conflicts for US-33."""
    result: list[tuple[str, dict[str, Any]]] = []
    # Keep personal information at the existing form-field granularity.  It
    # avoids turning a contact-card update into ten separate prompts while the
    # resumé sections below remain item/bullet level.
    b_pi = base.get("personal_info", {}) if isinstance(base.get("personal_info", {}), dict) else {}
    u_pi = upstream.get("personal_info", {}) if isinstance(upstream.get("personal_info", {}), dict) else {}
    l_pi = local.get("personal_info", {}) if isinstance(local.get("personal_info", {}), dict) else {}
    for field in sorted(set(b_pi) | set(u_pi)):
        before, after, current = b_pi.get(field, _MISSING), u_pi.get(field, _MISSING), l_pi.get(field, _MISSING)
        if _same(before, after) or _same(current, after):
            continue
        result.append(_change(field, "personal_info", _label(["personal_info", field]), before, after, current,
                              {"kind": "path", "path": ["personal_info", field]}, base_missing=before is _MISSING,
                              upstream_missing=after is _MISSING, local_missing=current is _MISSING))
    result.extend(_keyed_changes("experience", ("company", "role"), base.get("experience"), upstream.get("experience"), local.get("experience")))
    result.extend(_keyed_changes("projects", ("name",), base.get("projects"), upstream.get("projects"), local.get("projects")))
    base_skills = base.get("skills", [])
    upstream_skills = upstream.get("skills", [])
    local_skills = local.get("skills", [])
    if isinstance(base_skills, list) and isinstance(upstream_skills, list) and isinstance(local_skills, list):
        result.extend(_sequence_changes("skills", base_skills, upstream_skills, local_skills, {"section": "skills"}, _LABELS["skills"]))
    else:
        result.extend(_dict_changes("skills", base_skills, upstream_skills, local_skills, ["skills"]))
    # A child that already has the new parent value needs no review.  This also
    # keeps a retry after a successfully applied decision idempotent.
    return {key: change for key, change in result if not _same(change["old"], change["new"])
            or change.get("_old_missing") != change.get("_new_missing")}


def _entry_index(items: list[Any], fields: list[str], values: list[Any]) -> int | None:
    for index, item in enumerate(items):
        if isinstance(item, dict) and all(_same(item.get(field, _MISSING), value) for field, value in zip(fields, values, strict=True)):
            return index
    return None


def _overlay_parent_delta(base: Any, newer: Any, current: Any) -> Any:
    """Apply only parent-changed dictionary leaves, retaining child-only keys."""
    if isinstance(base, dict) and isinstance(newer, dict):
        result = copy.deepcopy(current) if isinstance(current, dict) else {}
        for key in set(base) | set(newer):
            before, after = base.get(key, _MISSING), newer.get(key, _MISSING)
            if _same(before, after):
                continue
            if after is _MISSING:
                result.pop(key, None)
            else:
                result[key] = _overlay_parent_delta(before, after, result.get(key, _MISSING))
        return result
    return copy.deepcopy(newer)


def apply_change(content: dict[str, Any], change: dict[str, Any], *, source: str = "new") -> dict[str, Any]:
    """Apply one user decision to a copy of ``content`` without touching other edits."""
    result = copy.deepcopy(content)
    value, missing = (change["new"], change.get("_new_missing", False)) if source == "new" else (change["old"], change.get("_old_missing", False))
    loc = change["_locator"]
    if loc["kind"] == "section":
        if missing:
            result.pop(loc["section"], None)
        else:
            result[loc["section"]] = copy.deepcopy(value)
        return result
    if loc["kind"] == "path":
        target: dict[str, Any] = result
        for part in loc["path"][:-1]:
            target = target.setdefault(part, {})
        if missing:
            target.pop(loc["path"][-1], None)
        else:
            target[loc["path"][-1]] = _overlay_parent_delta(change.get("base"), value, target.get(loc["path"][-1], _MISSING))
        return result
    section_items = result.setdefault(loc["section"], [])
    if not isinstance(section_items, list):
        return result
    if loc["kind"] == "entry":
        index = _entry_index(section_items, loc["fields"], loc["key"])
        if index is None:
            if not missing:
                section_items.append(copy.deepcopy(value))
        elif missing:
            section_items.pop(index)
        else:
            section_items[index] = copy.deepcopy(value)
        return result
    if loc["kind"] == "sequence":
        target = section_items
        if "fields" in loc:
            index = _entry_index(section_items, loc["fields"], loc["key"])
            if index is None or not isinstance(section_items[index], dict):
                return result
            target = section_items[index].setdefault(loc["field"], [])
        if not isinstance(target, list):
            return result
        old = loc["old"]
        start = _find_slice(target, old) if old else None
        replacement = copy.deepcopy(value)
        if old and start is not None:
            target[start:start + len(old)] = replacement
        elif not old:
            anchor = len(target)
            if not loc.get("_before_missing", False):
                index = _find_slice(target, [loc["before"]])
                if index is not None:
                    anchor = index + 1
            elif not loc.get("_after_missing", False):
                index = _find_slice(target, [loc["after"]])
                if index is not None:
                    anchor = index
            target[anchor:anchor] = replacement
        return result
    # A scalar field in a keyed entry.
    index = _entry_index(section_items, loc["fields"], loc["key"])
    if index is None or not isinstance(section_items[index], dict):
        return result
    if missing:
        section_items[index].pop(loc["field"], None)
    else:
        section_items[index][loc["field"]] = copy.deepcopy(value)
    return result
