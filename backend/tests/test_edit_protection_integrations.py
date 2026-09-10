"""US-32: all write entrypoints preserve optimistic concurrency."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from resume_agent.config import settings
    from resume_agent.db.init_db import init_database
    from resume_agent.main import app
    init_database(settings.sqlite_path)
    return TestClient(app)


@pytest.mark.parametrize(('path', 'payload'), [
    ('personal-info', {'contact': {'name': 'First'}}),
    ('section-order', {'sections': [{'key': 'skills', 'title': 'Skills'}]}),
    ('section', {'section': 'summary', 'data': 'First'}),
])
def test_partial_writes_require_version_and_reject_stale(client, path, payload):
    url = f'/api/tree/node/master/{path}'
    assert client.put(url, json=payload).status_code == 428
    result = client.put(url, json=payload, headers={'If-Match': '0'})
    assert result.status_code == 200
    assert result.json()['data']['version'] == 1
    assert client.put(url, json=payload, headers={'If-Match': '0'}).status_code == 409


@pytest.mark.parametrize('path', ['personal-info', 'section-order', 'upstream-changes'])
def test_partial_reads_include_version(client, path):
    response = client.get(f'/api/tree/node/master/{path}')
    assert response.json()['data']['version'] == 0


@pytest.mark.parametrize('endpoint', ['full', 'section'])
def test_generation_is_a_versioned_draft(client, monkeypatch, endpoint):
    from resume_agent.api import generate
    async def fake_generate(section, *args):
        return {'content': {section: 'Draft' if section == 'summary' else []}}
    async def no_info():
        return {}
    monkeypatch.setattr(generate, '_generate_one_section', fake_generate)
    monkeypatch.setattr(generate, '_extract_personal_info_from_knowledge', no_info)
    response = client.post(f'/api/generate/{endpoint}', json={'node_id': 'master', 'section': 'summary'})
    assert response.status_code == 200
    data = response.json()['data']
    assert data['base_version'] == 0
    assert data['base_content'] == {'version': 0}
    assert data['content']['summary'] == 'Draft'
    from resume_agent.services.node_content import get_node_content
    saved = get_node_content('master')
    assert saved.get('summary') != 'Draft'
    assert saved['version'] == 0


def test_agent_write_requires_read_version(client):
    import asyncio

    from resume_agent.tools.agent_tools import _write_node
    result = asyncio.run(_write_node({'node_id': 'master', 'content': {'summary': 'AI'}}))
    assert 'error' in result


@pytest.mark.parametrize(('path', 'payload'), [('merge', {'field': 'summary'}), ('merge/all', {}), ('reject', {'field': 'summary'})])
def test_upstream_requires_version_and_preserves_manual_edits(client, path, payload):
    import json

    from resume_agent.db.connection import get_connection
    with get_connection() as conn:
        conn.execute('UPDATE resume_versions SET upstream_changes=?,has_upstream_update=1 WHERE node_id=?',
                     (json.dumps({'summary': {'old': '', 'new': 'Upstream'}}), 'master'))
    url = f'/api/tree/node/master/{path}'
    assert client.post(url, json=payload).status_code == 428
    response = client.post(url, json=payload, headers={'If-Match': '0'})
    assert response.status_code == 200
    assert response.json()['data']['version'] == 1
    assert client.post(url, json=payload, headers={'If-Match': '0'}).status_code == 409


def test_import_does_not_revive_deleted_direction(client):
    from resume_agent.parsers.extractor import StructuredResume
    from resume_agent.services.tree_builder import TreeBuilder
    first = TreeBuilder().build_from_resume(StructuredResume(primary_direction='后端'))
    node_id = first['node']['node_id']
    client.delete(f'/api/tree/node/{node_id}')
    second = TreeBuilder().build_from_resume(StructuredResume(primary_direction='后端'))
    assert second['node']['node_id'] != node_id
    assert second['node']['deleted_at'] is None
    assert second['deduplicated'] is False


def test_import_initializes_version_zero_and_updates_existing_with_history(client):
    from resume_agent.parsers.extractor import BasicInfo, StructuredResume
    from resume_agent.services.tree_builder import TreeBuilder
    first = TreeBuilder().build_from_resume(StructuredResume(primary_direction='后端'))
    assert first['node']['version'] == 0
    second = TreeBuilder().build_from_resume(StructuredResume(primary_direction='后端', basic=BasicInfo(name='Changed')))
    assert second['node']['node_id'] == first['node']['node_id']
    assert second['node']['version'] == 1
    from resume_agent.services.node_content import get_node_history
    assert len(get_node_history(second['node']['node_id'])['entries']) == 2


def test_agent_pending_write_cannot_overwrite_new_manual_edit(client):
    import asyncio

    from resume_agent.services.node_content import get_node_content, save_node_content
    from resume_agent.tools.agent_tools import _write_node
    pending = get_node_content('master')
    pending['summary'] = 'AI draft'
    save_node_content('master', {'summary': 'User edit', 'version': 0})
    result = asyncio.run(_write_node({'node_id': 'master', 'content': pending}))
    assert result['status'] == 409
    assert get_node_content('master')['summary'] == 'User edit'


def test_full_content_save_propagates_personal_info_changes(client):
    child = client.post('/api/tree/node', json={'parent_id': 'master', 'node_type': 'branch', 'title': 'Child'}).json()['data']['node_id']
    content = {'personal_info': {'contact': {'name': 'Updated'}}}
    result = client.put('/api/tree/node/master', json={'content_json': content, 'expected_version': 0})
    assert result.status_code == 200
    upstream = client.get(f'/api/tree/node/{child}/upstream-changes').json()['data']
    assert upstream['has_upstream_update'] is True
    assert upstream['changes']['contact']['new']['name'] == 'Updated'
    version = upstream['version']
    # Re-saving identical information must not produce more metadata versions.
    client.put('/api/tree/node/master', json={'content_json': content, 'expected_version': 1})
    assert client.get(f'/api/tree/node/{child}/upstream-changes').json()['data']['version'] == version


@pytest.mark.parametrize('deleted_side', ['node_a_id', 'node_b_id'])
def test_diff_rejects_soft_deleted_nodes(client, deleted_side):
    child = client.post('/api/tree/node', json={'parent_id': 'master', 'node_type': 'branch', 'title': 'Deleted'}).json()['data']['node_id']
    client.delete(f'/api/tree/node/{child}')
    payload = {'node_a_id': 'master', 'node_b_id': 'master', deleted_side: child}
    response = client.post('/api/diff', json=payload)
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'NODE_NOT_FOUND'


def test_undo_redo_propagates_restored_personal_info(client):
    old_content = {'personal_info': {'contact': {'name': 'Old'}}}
    new_content = {'personal_info': {'contact': {'name': 'New'}}}
    client.put('/api/tree/node/master', json={'content_json': old_content, 'expected_version': 0})
    child = client.post('/api/tree/node', json={'parent_id': 'master', 'node_type': 'branch', 'title': 'Inherited'}).json()['data']['node_id']
    client.put('/api/tree/node/master', json={'content_json': new_content, 'expected_version': 1})
    upstream_url = f'/api/tree/node/{child}/upstream-changes'
    assert client.get(upstream_url).json()['data']['changes']['contact']['new']['name'] == 'New'
    undone = client.post('/api/tree/node/master/undo', json={'expected_version': 2})
    assert undone.status_code == 200
    assert client.get(upstream_url).json()['data']['has_upstream_update'] is False
    redone = client.post('/api/tree/node/master/redo', json={'expected_version': 3})
    assert redone.status_code == 200
    assert client.get(upstream_url).json()['data']['changes']['contact']['new']['name'] == 'New'


def test_create_cannot_leave_live_child_under_concurrently_deleted_parent(client, monkeypatch):
    import sqlite3
    from contextlib import contextmanager

    from resume_agent.api import tree
    from resume_agent.config import settings
    from resume_agent.db.connection import get_connection

    parent = client.post('/api/tree/node', json={'parent_id': 'master', 'node_type': 'branch', 'title': 'Concurrent parent'}).json()['data']['node_id']

    class CursorAtParentRead:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchone(self):
            row = self.cursor.fetchone()
            # Force the competing delete into the former SELECT/INSERT gap.
            competitor = sqlite3.connect(str(settings.sqlite_path), timeout=0)
            try:
                competitor.execute("UPDATE resume_versions SET deleted_at=datetime('now') WHERE node_id=?", (parent,))
                competitor.commit()
            except sqlite3.OperationalError as exc:
                assert 'locked' in str(exc)
            finally:
                competitor.close()
            return row

    class ConnectionAtParentRead:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, parameters=()):
            cursor = self.connection.execute(sql, parameters)
            if sql.startswith('SELECT * FROM resume_versions WHERE node_id = ?') and parameters == (parent,):
                return CursorAtParentRead(cursor)
            return cursor

    @contextmanager
    def competing_connection():
        with get_connection() as connection:
            yield ConnectionAtParentRead(connection)

    monkeypatch.setattr(tree, 'get_connection', competing_connection)
    client.post('/api/tree/node', json={'parent_id': parent, 'node_type': 'company', 'title': 'Company', 'company': 'Race'})
    with get_connection() as connection:
        orphan = connection.execute('SELECT child.node_id FROM resume_versions child JOIN resume_versions parent ON child.parent_id=parent.node_id WHERE child.deleted_at IS NULL AND parent.deleted_at IS NOT NULL').fetchone()
    assert orphan is None


def test_history_on_unrelated_field_keeps_rejected_upstream_changes(client):
    child = client.post('/api/tree/node', json={'parent_id': 'master', 'node_type': 'branch', 'title': 'Reject child'}).json()['data']['node_id']
    content = {'personal_info': {'contact': {'name': 'New'}}}
    client.put('/api/tree/node/master', json={'content_json': content, 'expected_version': 0})
    upstream_url = f'/api/tree/node/{child}/upstream-changes'
    upstream = client.get(upstream_url).json()['data']
    for field in upstream['changes']:
        response = client.post(f'/api/tree/node/{child}/reject', json={'field': field}, headers={'If-Match': str(upstream['version'])})
        upstream['version'] = response.json()['data']['version']
    content['skills'] = ['Python']
    client.put('/api/tree/node/master', json={'content_json': content, 'expected_version': 1})
    client.post('/api/tree/node/master/undo', json={'expected_version': 2})
    assert client.get(upstream_url).json()['data']['has_upstream_update'] is False
    client.post('/api/tree/node/master/redo', json={'expected_version': 3})
    assert client.get(upstream_url).json()['data']['has_upstream_update'] is False
