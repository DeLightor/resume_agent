"""US-31 recovery and confirmed-data regression tests."""

import pytest

from resume_agent.api import resumes
from resume_agent.db.connection import get_connection
from resume_agent.db.init_db import init_database


@pytest.fixture
def task(monkeypatch):
    # The config singleton is reset by conftest for every test.
    from resume_agent import config

    init_database(config.settings.sqlite_path)
    monkeypatch.setattr(resumes, "_tasks", {})
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO upload_records (id,file_name,file_type,file_path,parse_status) VALUES ('upload','r.pdf','pdf','r.pdf','parsing')"
        )
        conn.execute(
            "INSERT INTO parse_tasks (id,upload_id,status,raw_text) VALUES ('task','upload','extracting','WRONG ORIGINAL')"
        )
    return "task"


@pytest.mark.asyncio
async def test_slow_active_task_stream_does_not_timeout_or_remove_worker(task, monkeypatch):
    state = resumes._TaskState()
    resumes._tasks[task] = state
    ticks = 0

    async def tick(_):
        nonlocal ticks
        ticks += 1
        if ticks == 65:
            with get_connection() as conn:
                conn.execute("UPDATE parse_tasks SET status='awaiting_confirm' WHERE id=?", (task,))
            state.emit({"type": "done", "task_id": task})

    monkeypatch.setattr(resumes.asyncio, "sleep", tick)
    frames = [frame async for frame in resumes._parse_event_stream(task)]
    assert ticks >= 65
    assert "event: done" in "".join(frames)
    assert "event: error" not in "".join(frames)


@pytest.mark.asyncio
async def test_orphan_detail_persists_failure_and_start_can_retry(task, monkeypatch):
    assert resumes.get_parse_task(task)["data"]["status"] == "failed"
    with get_connection() as conn:
        row = conn.execute("SELECT status FROM parse_tasks WHERE id=?", (task,)).fetchone()
        upload = conn.execute(
            "SELECT parse_status FROM upload_records WHERE id='upload'"
        ).fetchone()
    assert row["status"] == "failed"
    assert upload["parse_status"] == "needs_review"
    monkeypatch.setattr(resumes.LLMClient, "configured", property(lambda self: True))
    monkeypatch.setattr(resumes.threading.Thread, "start", lambda self: None)
    result = await resumes.start_parse(resumes.ParseRequest(upload_id="upload"))
    assert result["data"]["task_id"] != task


@pytest.mark.asyncio
async def test_orphan_start_retries_without_polling_first(task, monkeypatch):
    monkeypatch.setattr(resumes.LLMClient, "configured", property(lambda self: True))
    monkeypatch.setattr(resumes.threading.Thread, "start", lambda self: None)
    result = await resumes.start_parse(resumes.ParseRequest(upload_id="upload"))
    assert result["data"]["task_id"] != task


@pytest.mark.asyncio
async def test_confirm_indexes_corrected_data_and_persists_it(task, monkeypatch):
    with get_connection() as conn:
        conn.execute("UPDATE parse_tasks SET status='awaiting_confirm' WHERE id=?", (task,))
    indexed = []
    monkeypatch.setattr(
        resumes, "_index_resume_to_knowledge", lambda text, *args: indexed.append(text) or 1
    )
    result = await resumes.confirm_parse(
        task, resumes.ConfirmRequest(structured_resume={"basic": {"name": "CORRECTED"}})
    )
    assert result["ok"] is True
    assert "CORRECTED" in indexed[0]
    assert "WRONG ORIGINAL" not in indexed[0]
    assert resumes.get_parse_task(task)["data"]["structured_resume"]["basic"]["name"] == "CORRECTED"
    again = await resumes.confirm_parse(task, resumes.ConfirmRequest(structured_resume={}))
    assert again["error"]["code"] == "TASK_ALREADY_CONFIRMED"
    assert len(indexed) == 1


@pytest.mark.asyncio
async def test_confirm_index_failure_is_visible_and_does_not_repeat_tree_write(task, monkeypatch):
    with get_connection() as conn:
        conn.execute("UPDATE parse_tasks SET status='awaiting_confirm' WHERE id=?", (task,))

    def fail_index(*args):
        raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(resumes, "_index_resume_to_knowledge", fail_index)
    result = await resumes.confirm_parse(task, resumes.ConfirmRequest(structured_resume={}))
    assert result["ok"] is True
    assert result["data"]["knowledge_warning"]
    assert result["data"]["knowledge_chunks"] == 0
    assert resumes.get_parse_task(task)["data"]["status"] == "confirmed"


def test_worker_releases_registry_without_sse_subscriber(task, monkeypatch):
    resumes._tasks[task] = resumes._TaskState()
    monkeypatch.setattr(resumes.LLMClient, "configured", property(lambda self: False))
    resumes._run_parse_task(task, "upload", {})
    assert task not in resumes._tasks
    assert resumes.get_parse_task(task)["data"]["status"] == "failed"


@pytest.mark.asyncio
async def test_invalid_knowledge_override_is_rejected_without_tree_write(task):
    with get_connection() as conn:
        conn.execute(
            "UPDATE parse_tasks SET status='awaiting_confirm', knowledge_personal_json=? WHERE id=?",
            ('{"contact":{"phone":["invalid"]}}', task),
        )
    result = await resumes.confirm_parse(
        task,
        resumes.ConfirmRequest(
            structured_resume={},
            apply_knowledge_personal_info=True,
        ),
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_KNOWLEDGE_PERSONAL_INFO"
    with get_connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM resume_versions WHERE node_type='branch'"
            ).fetchone()["n"]
            == 0
        )


@pytest.mark.asyncio
async def test_tree_failure_preserves_confirmable_task_and_skips_index(task, monkeypatch):
    with get_connection() as conn:
        conn.execute("UPDATE parse_tasks SET status='awaiting_confirm' WHERE id=?", (task,))

    def fail_tree(*args):
        raise RuntimeError("tree failure")

    monkeypatch.setattr(resumes.TreeBuilder, "build_from_resume", fail_tree)
    result = await resumes.confirm_parse(task, resumes.ConfirmRequest(structured_resume={}))
    assert result["error"]["code"] == "TREE_BUILD_FAILED"
    assert resumes.get_parse_task(task)["data"]["status"] == "awaiting_confirm"
    with get_connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM knowledge_chunks").fetchone()["n"] == 0


@pytest.mark.asyncio
async def test_stream_handles_worker_finishing_between_db_read_and_state_lookup(task, monkeypatch):
    resumes._tasks[task] = resumes._TaskState()
    read_row = resumes._get_task_row
    first = True

    def finish_after_read(task_id):
        nonlocal first
        row = read_row(task_id)
        if first:
            first = False
            with get_connection() as conn:
                conn.execute("UPDATE parse_tasks SET status='awaiting_confirm' WHERE id=?", (task,))
            resumes._tasks.pop(task)
        return row

    monkeypatch.setattr(resumes, "_get_task_row", finish_after_read)
    frames = [frame async for frame in resumes._parse_event_stream(task)]
    assert "event: done" in "".join(frames)
    assert "event: error" not in "".join(frames)


@pytest.mark.parametrize("payload", [
    '[]', '"text"', '{"education":"bad"}', '{"education":["bad"]}',
    '{"contact":{"name":{"nested":"bad"}}}', '{"contact":[]}', 'invalid json',
])
def test_detail_discards_malformed_legacy_knowledge_suggestions(task, payload):
    with get_connection() as conn:
        conn.execute("UPDATE parse_tasks SET status='awaiting_confirm', knowledge_personal_json=? WHERE id=?", (payload, task))
    assert resumes.get_parse_task(task)["data"]["knowledge_personal_info"] is None


def test_detail_normalizes_missing_knowledge_fields(task):
    with get_connection() as conn:
        conn.execute("UPDATE parse_tasks SET status='awaiting_confirm', knowledge_personal_json=? WHERE id=?", ('{"contact":{"name":"Alice"}}', task))
    info = resumes.get_parse_task(task)["data"]["knowledge_personal_info"]
    assert info["contact"]["name"] == "Alice"
    assert info["contact"]["phone"] is None
    assert info["education"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ['[]', '{"contact":{"name":{}}}', '{"education":"bad"}'])
async def test_extractor_discards_malformed_optional_knowledge(payload, monkeypatch):
    from resume_agent.rag import chroma_client

    class Collection:
        def query(self, **kwargs):
            return {"ids": [["chunk"]], "documents": [["Alice resume"]]}

    async def chat(self, **kwargs):
        return payload

    monkeypatch.setattr(chroma_client, "get_knowledge_collection", lambda: Collection())
    monkeypatch.setattr(resumes.LLMClient, "configured", property(lambda self: True))
    monkeypatch.setattr(resumes.LLMClient, "chat", chat)
    assert await resumes._extract_personal_info_from_knowledge() is None


def test_empty_mineru_token_is_not_degraded(monkeypatch, tmp_path):
    from resume_agent import config
    monkeypatch.setattr(config.settings, "mineru_api_token", "")
    monkeypatch.setattr(resumes, "extract_text_from_pdf", lambda path: "resume")
    assert resumes._extract_text(tmp_path / "test.pdf", "pdf") == ("resume", "local", False)

@pytest.mark.asyncio
async def test_custom_direction_survives_confirmation_and_list(task, monkeypatch):
    with get_connection() as conn:
        conn.execute("UPDATE upload_records SET file_path='resumes/r.pdf' WHERE id='upload'")
        conn.execute("UPDATE parse_tasks SET status='awaiting_confirm' WHERE id=?", (task,))
    monkeypatch.setattr(resumes, '_index_resume_to_knowledge', lambda *args: 1)
    result = await resumes.confirm_parse(task, resumes.ConfirmRequest(structured_resume={'primary_direction': '其他'}, custom_direction='  云安全  '))
    assert result['data']['tree_node']['direction'] == '云安全'
    assert resumes.list_resumes()['data'][0]['direction'] == '云安全'


def test_delete_resume_preserves_tree_and_cleans_record(task, monkeypatch):
    from resume_agent import config
    from resume_agent.rag import chroma_client
    path = config.settings.files_root / 'resumes/r.pdf'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x')
    with get_connection() as conn:
        conn.execute("UPDATE upload_records SET file_path='resumes/r.pdf', parse_status='success' WHERE id='upload'")
        conn.execute("INSERT INTO knowledge_chunks(id,source_file,chunk_text,embedding_id,metadata_json) VALUES('c','r.pdf','text','e','{\"upload_id\":\"upload\"}')")
        count = conn.execute('SELECT count(*) n FROM resume_versions').fetchone()['n']
    class Collection:
        def delete(self, ids): pass
    monkeypatch.setattr(chroma_client, 'get_knowledge_collection', lambda: Collection())
    assert resumes.delete_uploaded_resume('upload')['ok']
    with get_connection() as conn:
        assert not conn.execute("SELECT id FROM upload_records WHERE id='upload'").fetchone()
        assert conn.execute('SELECT count(*) n FROM resume_versions').fetchone()['n'] == count
