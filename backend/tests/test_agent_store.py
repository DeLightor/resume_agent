"""Agent 会话与 trace 持久化测试（agent-runtime US-27 Task 1）。

覆盖：
- schema 建表幂等
- session 生命周期（创建/读取/状态迁移/消息持久化）
- trace 写入与按 session 查询
"""

from __future__ import annotations

from typing import Any

from resume_agent.db.init_db import list_tables


def test_agent_tables_created(initialized_db: Any) -> None:
    """建表后 agent_sessions / agent_traces 存在。"""
    tables = list_tables(initialized_db)
    assert "agent_sessions" in tables
    assert "agent_traces" in tables


def test_agent_tables_idempotent(initialized_db: Any) -> None:
    """重复 init 不报错、不产生重复表。"""
    from resume_agent.db.init_db import init_database

    init_database(initialized_db)  # 二次执行应幂等
    tables = list_tables(initialized_db)
    assert tables.count("agent_sessions") == 1
    assert tables.count("agent_traces") == 1


def test_create_and_get_session(initialized_db: Any) -> None:
    """创建 session 后可按 id 读取，字段完整。"""
    from resume_agent.agents import store

    s = store.create_session(
        db_path=initialized_db, context={"current_node_id": "master"}
    )
    assert s.id
    assert s.status == "running"
    assert s.context == {"current_node_id": "master"}
    assert s.messages == []

    fetched = store.get_session(s.id, initialized_db)
    assert fetched is not None
    assert fetched.id == s.id
    assert fetched.status == "running"


def test_get_session_not_found(initialized_db: Any) -> None:
    """不存在的 session 返回 None。"""
    from resume_agent.agents import store

    assert store.get_session("no-such-id", initialized_db) is None


def test_save_session_status_transition(initialized_db: Any) -> None:
    """session 状态迁移与消息持久化往返。"""
    from resume_agent.agents import store

    s = store.create_session(db_path=initialized_db)
    s.status = "awaiting_user"
    s.pending_question = "你的电话是多少？"
    s.messages = [
        {"role": "user", "content": "帮我优化简历"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "tc1", "type": "function",
             "function": {"name": "ask_user", "arguments": "{}"}}
        ]},
    ]
    store.save_session(s, initialized_db)

    fetched = store.get_session(s.id, initialized_db)
    assert fetched is not None
    assert fetched.status == "awaiting_user"
    assert fetched.pending_question == "你的电话是多少？"
    assert fetched.messages[1]["tool_calls"][0]["id"] == "tc1"


def test_list_sessions_excludes_messages(initialized_db: Any) -> None:
    """列表返回摘要（id/status/时间），不含消息体。"""
    from resume_agent.agents import store

    store.create_session(db_path=initialized_db)
    store.create_session(db_path=initialized_db)

    items = store.list_sessions(initialized_db)
    assert len(items) == 2
    for item in items:
        assert "messages" not in item
        assert item["status"] == "running"
        assert item["id"]


def test_append_and_list_traces(initialized_db: Any) -> None:
    """trace 写入后按 session 查询，含轮次与输入输出。"""
    from resume_agent.agents import store

    s = store.create_session(db_path=initialized_db)
    store.append_trace(
        session_id=s.id,
        round=1,
        tool_name="retrieve_knowledge",
        input_data={"query": "K8s 运维"},
        output_data=[{"chunk_text": "...", "score": 0.9}],
        db_path=initialized_db,
    )
    store.append_trace(
        session_id=s.id,
        round=2,
        tool_name="read_node",
        input_data={"node_id": "master"},
        output_data={"experience": []},
        db_path=initialized_db,
    )

    traces = store.list_traces(s.id, initialized_db)
    assert len(traces) == 2
    assert traces[0]["tool_name"] == "retrieve_knowledge"
    assert traces[0]["round"] == 1
    assert traces[1]["tool_name"] == "read_node"


# === pending_write 持久化（agent-write-guard）===


def test_pending_write_roundtrip(initialized_db: Any) -> None:
    """pending_write 序列化往返：保存/读取/清空。"""
    from resume_agent.agents import store

    s = store.create_session(db_path=initialized_db)
    s.status = "awaiting_user"
    s.pending_question = "确认写入节点 master？"
    s.pending_write = {
        "tool_call_id": "tc1",
        "node_id": "master",
        "content": {"skills": [{"name": "Python"}]},
    }
    store.save_session(s, initialized_db)

    fetched = store.get_session(s.id, initialized_db)
    assert fetched is not None
    assert fetched.status == "awaiting_user"
    assert fetched.pending_write == {
        "tool_call_id": "tc1",
        "node_id": "master",
        "content": {"skills": [{"name": "Python"}]},
    }

    # 清空后保存
    fetched.pending_write = None
    fetched.pending_question = None
    store.save_session(fetched, initialized_db)
    again = store.get_session(s.id, initialized_db)
    assert again is not None
    assert again.pending_write is None


def test_pending_write_column_migrated(tmp_db_path: Any) -> None:
    """老库（无 pending_write_json 列）经 init_database 幂等补列。"""
    import sqlite3

    from resume_agent.db.init_db import init_database

    # 模拟旧版 schema 建表（不含新列）
    conn = sqlite3.connect(tmp_db_path)
    conn.execute(
        "CREATE TABLE agent_sessions ("
        " id TEXT PRIMARY KEY,"
        " status TEXT NOT NULL DEFAULT 'running',"
        " context_json TEXT,"
        " messages_json TEXT NOT NULL DEFAULT '[]',"
        " pending_question TEXT,"
        " created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        " updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()
    conn.close()

    init_database(tmp_db_path)  # 幂等迁移补列

    conn = sqlite3.connect(tmp_db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_sessions)")}
    conn.close()
    assert "pending_write_json" in cols

    # 再次 init 幂等（不因列已存在报错）
    init_database(tmp_db_path)


def test_append_trace_output_truncated(initialized_db: Any) -> None:
    """超过 4KB 的输出被截断存储。"""
    from resume_agent.agents import store

    s = store.create_session(db_path=initialized_db)
    big_output = {"text": "x" * 10_000}
    store.append_trace(
        session_id=s.id,
        round=1,
        tool_name="retrieve_knowledge",
        input_data={"query": "q"},
        output_data=big_output,
        db_path=initialized_db,
    )
    traces = store.list_traces(s.id, initialized_db)
    assert len(traces) == 1
    raw = traces[0]["output"]
    assert len(raw) <= 4096 + 64  # 截断标记允许少量超出
