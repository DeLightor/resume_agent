"""Committed tree notifications, reconnect snapshots, and disconnect behavior."""

import asyncio
import json

import pytest

from resume_agent.db.connection import get_connection


@pytest.fixture
def event_db():
    with get_connection() as conn:
        conn.execute("CREATE TABLE tree_events (id INTEGER PRIMARY KEY AUTOINCREMENT, node_ids TEXT NOT NULL)")


class Request:
    disconnected = False

    async def is_disconnected(self):
        return self.disconnected


def insert_event(node_ids):
    with get_connection() as conn:
        conn.execute("INSERT INTO tree_events(node_ids) VALUES (?)", (json.dumps(node_ids),))


def test_initial_snapshot_then_only_committed_events(event_db):
    from resume_agent.api.tree_events import stream_tree_events

    async def run():
        insert_event(["older"])
        request = Request()
        stream = stream_tree_events(request, poll_interval=0, heartbeat_interval=0)
        first = await anext(stream)
        assert '"node_ids": []' in first
        assert "id: 1\n" in first
        with pytest.raises(RuntimeError), get_connection() as conn:
            conn.execute("INSERT INTO tree_events(node_ids) VALUES (?)", ('["rolled-back"]',))
            raise RuntimeError("abort")
        assert await anext(stream) == ": heartbeat\n\n"
        insert_event(["parent", "child"])
        event = await anext(stream)
        assert "event: tree_update\n" in event
        assert '"node_ids": ["parent", "child"]' in event
        request.disconnected = True
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        # Reconnect must reload all state, even when old events already exist.
        reconnect = stream_tree_events(Request())
        assert '"node_ids": []' in await anext(reconnect)
        await reconnect.aclose()

    asyncio.run(run())


def test_events_arriving_after_snapshot_are_not_lost(event_db):
    from resume_agent.api.tree_events import stream_tree_events

    async def run():
        stream = stream_tree_events(Request(), poll_interval=0)
        assert "id: 0\n" in await anext(stream)
        for index in range(105):
            insert_event([str(index)])
        received = [await anext(stream) for _ in range(105)]
        assert "id: 1\n" in received[0]
        assert "id: 105\n" in received[-1]
        await stream.aclose()

    asyncio.run(run())


def test_reconnect_replays_committed_events_after_last_event_id(event_db):
    from resume_agent.api.tree_events import stream_tree_events

    async def run():
        insert_event(["first"])
        insert_event(["second"])
        stream = stream_tree_events(Request(), after_id=1, poll_interval=0)
        assert "id: 1\n" in await anext(stream)
        replayed = await anext(stream)
        assert "id: 2\n" in replayed
        assert '"node_ids": ["second"]' in replayed
        await stream.aclose()

    asyncio.run(run())
