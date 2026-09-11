from resume_agent.services.content_merge import apply_change, build_changes


def test_fields_three_way_and_missing_null():
    base = {'personal_info': {'contact': {'name': 'A', 'phone': '1'}}}
    up = {'personal_info': {'contact': {'name': 'B', 'phone': None}}}
    local = {'personal_info': {'contact': {'name': 'C', 'phone': '1', 'city': 'X'}}}
    changes = build_changes(base, up, local)
    assert len(changes) == 1
    assert sum(c['conflict'] for c in changes.values()) == 1
    for c in changes.values():
        local = apply_change(local, c)
    assert local['personal_info']['contact'] == {'name': 'B', 'phone': None, 'city': 'X'}
    assert not build_changes(up, up, local)
    assert not build_changes(base, up, up)


def test_keyed_entries_and_selective_bullets_preserve_local():
    base = {'experience': [{'company': 'A', 'role': 'R', 'bullets': ['a', 'b', 'c']}]}
    up = {'experience': [{'company': 'A', 'role': 'R', 'bullets': ['A', 'b', 'C']}]}
    local = {'experience': [{'company': 'A', 'role': 'R', 'bullets': ['a', 'local', 'b', 'c']}]}
    changes = list(build_changes(base, up, local).values())
    assert len(changes) == 2
    assert not any(c['conflict'] for c in changes)
    for c in reversed(changes):
        local = apply_change(local, c)
    assert local['experience'][0]['bullets'] == ['A', 'local', 'b', 'C']


def test_skills_selective_delete_and_append():
    base = {'skills': ['a', 'b', 'c']}
    up = {'skills': ['a', 'd', 'e']}
    local = {'skills': ['a', 'b', 'c', 'local']}
    changes = build_changes(base, up, local)
    for c in changes.values():
        local = apply_change(local, c)
    assert local['skills'] == ['a', 'd', 'e', 'local']


def test_project_add_delete_and_duplicate_safe_group():
    base = {'projects': [{'name': 'A', 'description': 'x'}]}
    up = {'projects': [{'name': 'B', 'description': 'y'}]}
    changes = build_changes(base, up, base)
    assert len(changes) == 2
    current = base
    for c in changes.values():
        current = apply_change(current, c)
    assert current == up
    dup = {'projects': [{'name': 'A'}, {'name': 'A'}]}
    assert len(build_changes(base, dup, base)) == 1


def test_invalid_entry_identity_falls_back_to_a_whole_section_decision():
    base = {'experience': [{'company': 'A', 'role': 'R'}]}
    upstream = {'experience': [{'company': ['not', 'a', 'string'], 'role': 'R'}]}
    changes = build_changes(base, upstream, base)
    assert list(changes) == ['experience']


def test_reject_advance_baseline_does_not_repeat():
    base = {'skills': ['a', 'b']}
    up = {'skills': ['A', 'b']}
    local = {'skills': ['local', 'b']}
    change = next(iter(build_changes(base, up, local).values()))
    assert change['conflict']
    advanced = apply_change(base, change)
    assert not build_changes(advanced, up, local)
