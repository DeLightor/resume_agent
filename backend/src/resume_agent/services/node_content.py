"""Atomic versioned node writes and bounded undo/redo history (US-32)."""
from __future__ import annotations

import json
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from resume_agent.db.connection import get_connection


def _content(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    value.pop('version', None)
    return value


def changed_paths(old: Any, new: Any, prefix: str = '') -> list[str]:
    if isinstance(old, dict) or isinstance(new, dict):
        old = old if isinstance(old, dict) else {}
        new = new if isinstance(new, dict) else {}
        result: list[str] = []
        for key in sorted(set(old) | set(new)):
            if key == 'version':
                continue
            child = changed_paths(old.get(key), new.get(key), f'{prefix}.{key}' if prefix else key)
            result.extend(child)
        return result
    return [] if old == new else [prefix]


def get_node_content(
    node_id: str, *, conn: sqlite3.Connection | None = None, db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    with nullcontext(conn) if conn is not None else get_connection(db_path) as connection:
        row = connection.execute(
            'SELECT content_json, version FROM resume_versions WHERE node_id=? AND deleted_at IS NULL',
            (node_id,),
        ).fetchone()
        if row is None:
            return None
        return {**_content(row['content_json']), 'version': row['version']}


def _check_version(row: dict[str, Any], expected_version: int | None) -> None:
    if expected_version is None:
        raise HTTPException(428, '保存需要节点版本，请重新加载后重试')
    if type(expected_version) is not int or expected_version != row['version']:
        raise HTTPException(409, {'message': '节点已更新，请重新加载后重试', 'version': row['version']})


def _begin(conn: sqlite3.Connection) -> None:
    if not conn.in_transaction:
        conn.execute('BEGIN IMMEDIATE')


def save_node_content(
    node_id: str, content: dict[str, Any], expected_version: int | None = None,
    *, conn: sqlite3.Connection | None = None, db_path: Path | str | None = None,
    title: str | None = None,
) -> bool:
    """CAS write; existing connection keeps caller's transaction atomic.

    The incoming dictionary is not mutated. Read again to obtain its new version.
    Missing or deleted nodes return False; absent/stale versions raise 428/409.
    """
    with nullcontext(conn) if conn is not None else get_connection(db_path) as connection:
        _begin(connection)
        row = connection.execute(
            'SELECT * FROM resume_versions WHERE node_id=? AND deleted_at IS NULL', (node_id,),
        ).fetchone()
        if row is None:
            return False
        expected = content.get('version') if expected_version is None else expected_version
        _check_version(row, expected)
        clean = {key: value for key, value in content.items() if key != 'version'}
        new_title = row['title'] if title is None else title
        before = _content(row['content_json'])
        if clean == before and new_title == row['title']:
            return True
        cursor_id = row['history_cursor']
        if cursor_id is None:
            cursor_id = connection.execute(
                'INSERT INTO node_history(node_id,content_json,title,summary) VALUES(?,?,?,?)',
                (node_id, json.dumps(before, ensure_ascii=False), row['title'], '初始版本'),
            ).lastrowid
        connection.execute('DELETE FROM node_history WHERE node_id=? AND id>?', (node_id, cursor_id))
        fields = changed_paths(before, clean)
        summary = '更新 ' + ('、'.join(fields) if fields else '标题')
        encoded = json.dumps(clean, ensure_ascii=False)
        history_id = connection.execute(
            'INSERT INTO node_history(node_id,content_json,title,summary) VALUES(?,?,?,?)',
            (node_id, encoded, new_title, summary[:240]),
        ).lastrowid
        connection.execute(
            "UPDATE resume_versions SET content_json=?,title=?,version=version+1,history_cursor=?,"
            "updated_at=datetime('now') WHERE node_id=? AND version=? AND deleted_at IS NULL",
            (encoded, new_title, history_id, node_id, expected),
        )
        connection.execute(
            'DELETE FROM node_history WHERE node_id=? AND id NOT IN '
            '(SELECT id FROM node_history WHERE node_id=? ORDER BY id DESC LIMIT 20)', (node_id, node_id),
        )
        return True


def get_node_history(node_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        # Consistent row/cursor/history snapshot, even while another caller saves.
        conn.execute('BEGIN')
        row = conn.execute(
            'SELECT version, history_cursor FROM resume_versions WHERE node_id=? AND deleted_at IS NULL',
            (node_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, '节点不存在')
        entries = conn.execute(
            'SELECT id,summary,created_at,content_json,title FROM node_history WHERE node_id=? ORDER BY id', (node_id,),
        ).fetchall()
        previous = None
        for entry in entries:
            if previous is not None:
                fields = changed_paths(_content(previous['content_json']), _content(entry['content_json']))
                if previous['title'] != entry['title']:
                    fields.append('标题')
                if fields:
                    entry['summary'] = '更新 ' + '、'.join(fields)
            previous = dict(entry)
            entry.pop('content_json', None)
            entry.pop('title', None)
        cursor = row['history_cursor']
        return {
            'version': row['version'], 'entries': entries,
            'can_undo': cursor is not None and any(item['id'] < cursor for item in entries),
            'can_redo': cursor is not None and any(item['id'] > cursor for item in entries),
        }


def move_node_history(node_id: str, expected_version: int | None, *, redo: bool = False) -> bool:
    """Move the history cursor and report whether personal information changed."""
    with get_connection() as conn:
        _begin(conn)
        row = conn.execute(
            'SELECT * FROM resume_versions WHERE node_id=? AND deleted_at IS NULL', (node_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, '节点不存在')
        _check_version(row, expected_version)
        compare, order = ('>', 'ASC') if redo else ('<', 'DESC')
        target = conn.execute(
            f'SELECT * FROM node_history WHERE node_id=? AND id{compare}? ORDER BY id {order} LIMIT 1',
            (node_id, row['history_cursor']),
        ).fetchone()
        if target is None:
            raise HTTPException(409, '没有可重做的历史' if redo else '没有可撤销的历史')
        conn.execute(
            "UPDATE resume_versions SET content_json=?, title=?,history_cursor=?,version=version+1,"
            "updated_at=datetime('now') WHERE node_id=?",
            (target['content_json'], target['title'], target['id'], node_id),
        )
        before, after = _content(row["content_json"]), _content(target["content_json"])
        return any(before.get(section) != after.get(section) for section in ("personal_info", "experience", "projects", "skills"))
