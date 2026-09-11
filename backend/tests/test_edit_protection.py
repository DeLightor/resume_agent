"""US-32: real SQLite/API regression tests for edit protection."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from resume_agent.db.connection import get_connection
from resume_agent.db.init_db import init_database
from resume_agent.services.node_content import get_node_content, save_node_content


@pytest.fixture
def client():
    from resume_agent.config import settings
    from resume_agent.main import app
    init_database(settings.sqlite_path)
    return TestClient(app)


def test_read_exposes_version_and_write_requires_version(client):
    assert get_node_content('master') == {'version': 0}
    with pytest.raises(HTTPException) as exc:
        save_node_content('master', {'name': 'first'})
    assert exc.value.status_code == 428


def test_cas_rejects_stale_write_and_keeps_winner(client):
    assert save_node_content('master', {'name': 'first', 'version': 0})
    with pytest.raises(HTTPException) as exc:
        save_node_content('master', {'name': 'stale', 'version': 0})
    assert exc.value.status_code == 409
    assert get_node_content('master') == {'name': 'first', 'version': 1}


def test_concurrent_cas_only_one_winner(client):
    def write(name):
        try:
            save_node_content('master', {'name': name, 'version': 0})
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ['one', 'two'])) == [200, 409]


def test_history_baseline_undo_redo_branch_and_limit(client):
    for i in range(23):
        assert save_node_content('master', {'name': str(i), 'version': i})
    path = '/api/tree/node/master'
    history = client.get(path + '/history').json()['data']
    assert len(history['entries']) == 20
    assert history['can_undo'] and not history['can_redo']
    # A duplicate save must not create history or increase version.
    save_node_content('master', {'name': '22', 'version': 23})
    assert get_node_content('master')['version'] == 23
    undo = client.post(path + '/undo', json={'expected_version': 23}).json()['data']
    assert undo['content_json'] == {'name': '21', 'version': 24}
    assert client.post(path + '/redo', json={'expected_version': 23}).status_code == 409
    redo = client.post(path + '/redo', json={'expected_version': 24}).json()['data']
    assert redo['content_json'] == {'name': '22', 'version': 25}
    client.post(path + '/undo', json={'expected_version': 25})
    save_node_content('master', {'name': 'new', 'version': 26})
    assert not client.get(path + '/history').json()['data']['can_redo']
    assert client.post(path + '/redo', json={'expected_version': 27}).status_code == 409


def test_undo_first_write_restores_empty_baseline(client):
    save_node_content('master', {'name': 'first', 'version': 0})
    response = client.post('/api/tree/node/master/undo', json={'expected_version': 1})
    assert response.json()['data']['content_json'] == {'version': 2}


def test_tree_update_cas_including_title(client):
    path = '/api/tree/node/master'
    assert client.put(path, json={'title': 'Oops'}).status_code == 428
    response = client.put(path, json={'title': 'Edited', 'expected_version': 0})
    assert response.json()['data']['version'] == 1
    assert client.put(path, json={'title': 'Stale', 'expected_version': 0}).status_code == 409
    assert client.get('/api/tree/master').json()['data']['title'] == 'Edited'


def branch_and_child(client):
    branch = client.post('/api/tree/node', json={
        'parent_id': 'master', 'node_type': 'branch', 'title': 'Safety', 'direction': '安全',
    }).json()['data']['node_id']
    child = client.post('/api/tree/node', json={
        'parent_id': branch, 'node_type': 'company', 'title': 'Company', 'company': 'Acme',
    }).json()['data']['node_id']
    return branch, child


def test_soft_delete_restore_batch_preserves_content(client):
    branch, child = branch_and_child(client)
    save_node_content(child, {'name': 'kept', 'version': 0})
    assert client.delete('/api/tree/node/' + branch).json()['data']['deleted_count'] == 2
    assert get_node_content(child) is None
    assert not save_node_content(child, {'version': 1})
    assert client.get('/api/tree/' + child).status_code == 404
    assert len(client.get('/api/tree').json()['data']['nodes']) == 1
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) AS n FROM resume_versions').fetchone()['n'] == 3
    trash = client.get('/api/tree/trash').json()['data']['items']
    assert len(trash) == 1 and trash[0]['node_id'] == branch
    assert client.post('/api/tree/node/' + branch + '/restore').status_code == 200
    assert get_node_content(child)['name'] == 'kept'


def test_restore_does_not_revive_previously_deleted_child(client):
    branch, child = branch_and_child(client)
    client.delete('/api/tree/node/' + child)
    client.delete('/api/tree/node/' + branch)
    assert client.post('/api/tree/node/' + child + '/restore').status_code == 409
    client.post('/api/tree/node/' + branch + '/restore')
    assert get_node_content(child) is None
    assert client.post('/api/tree/node/' + child + '/restore').status_code == 200


def test_expired_trash_cannot_restore_or_write(client):
    branch, _ = branch_and_child(client)
    client.delete('/api/tree/node/' + branch)
    with get_connection() as conn:
        conn.execute("UPDATE resume_versions SET deleted_at=datetime('now', '-31 days') WHERE deleted_at IS NOT NULL")
    assert client.post('/api/tree/node/' + branch + '/restore').status_code == 410
    assert client.get('/api/tree/trash').json()['data']['items'] == []
    assert get_node_content(branch) is None

def test_history_summary_includes_nested_field_paths(client):
    assert save_node_content('master', {'personal_info': {'contact': {'name': 'A'}}, 'version': 0})
    assert save_node_content('master', {'personal_info': {'contact': {'name': 'B'}}, 'version': 1})
    entries = client.get('/api/tree/node/master/history').json()['data']['entries']
    assert entries[-1]['summary'] == '更新 personal_info.contact.name'

def test_legacy_history_reconstructs_specific_fields(client):
    save_node_content('master', {'personal_info': {'contact': {'name': 'A'}}, 'version': 0})
    save_node_content('master', {'personal_info': {'contact': {'name': 'B'}}, 'version': 1})
    with get_connection() as conn:
        conn.execute("UPDATE node_history SET summary='更新 personal_info' WHERE summary != '初始版本'")
    entries = client.get('/api/tree/node/master/history').json()['data']['entries']
    assert entries[-1]['summary'] == '更新 personal_info.contact.name'
