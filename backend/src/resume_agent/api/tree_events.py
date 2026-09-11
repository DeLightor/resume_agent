"""Small, database-backed SSE feed for version-tree freshness (US-33)."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from resume_agent.db.connection import get_connection

router = APIRouter(prefix="/tree", tags=["tree"])


def record_tree_update(conn: object, node_ids: list[str]) -> None:
    """Add an event in the caller's transaction; rollback therefore emits nothing."""
    conn.execute("INSERT INTO tree_events(node_ids) VALUES (?)", (json.dumps(sorted(set(node_ids))),))  # type: ignore[attr-defined]


def _read_events(after_id: int) -> list[dict[str, object]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id,node_ids FROM tree_events WHERE id>? ORDER BY id LIMIT 100", (after_id,),
        ).fetchall()
    return rows


def _last_event_id() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS id FROM tree_events").fetchone()
    return int(row["id"])


async def stream_tree_events(
    request: Request,
    *,
    after_id: int | None = None,
    poll_interval: float = 1.0,
    heartbeat_interval: float = 15.0,
) -> AsyncIterator[str]:
    """Send an initial snapshot signal then durable committed updates.

    The initial signal deliberately asks clients to fetch current state.  It
    makes reconnect correctness independent of event retention and avoids a
    stale event overwriting an in-memory unsaved draft.
    """
    cursor = await asyncio.to_thread(_last_event_id) if after_id is None else after_id
    yield f"id: {cursor}\nevent: tree_update\ndata: {json.dumps({'node_ids': []})}\n\n"
    idle = 0.0
    while not await request.is_disconnected():
        events = await asyncio.to_thread(_read_events, cursor)
        if events:
            for event in events:
                cursor = int(event["id"])
                try:
                    nodes = json.loads(str(event["node_ids"]))
                except json.JSONDecodeError:
                    nodes = []
                yield f"id: {cursor}\nevent: tree_update\ndata: {json.dumps({'node_ids': nodes})}\n\n"
            idle = 0.0
            continue
        if idle >= heartbeat_interval:
            yield ": heartbeat\n\n"
            idle = 0.0
        await asyncio.sleep(poll_interval)
        idle += poll_interval


@router.get("/events")
async def tree_events(request: Request) -> StreamingResponse:
    try:
        after_id = max(0, int(request.headers.get("last-event-id", "")))
    except ValueError:
        after_id = None
    return StreamingResponse(
        stream_tree_events(request, after_id=after_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
