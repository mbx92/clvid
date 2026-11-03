def test_motion_settings_round_trip_and_invalid_effects_do_not_create_revision(clients, ready_project):
    owner = clients[0]
    response = owner.post(f"/api/v1/projects/{ready_project['project_id']}/clips", json={
        'start_ms': 0, 'end_ms': 6000, 'cues': [{'start_ms': 0, 'end_ms': 6000, 'text': 'Momen lucu'}],
    })
    assert response.status_code == 201
    clip = response.json()
    assert clip['revision']['subtitle_style_json']['animation'] == 'none'
    path = f"/api/v1/clips/{clip['id']}"
    updated = owner.patch(path, json={'expected_revision': 1, 'subtitle_style_json': {
        'animation': 'rise', 'animation_ms': 220, 'background': False, 'bold': True,
    }})
    assert updated.status_code == 200
    style = owner.get(path).json()['revision']['subtitle_style_json']
    assert style['animation'] == 'rise' and style['animation_ms'] == 220
    for invalid in ({'animation': 'shake'}, {'animation_ms': 501}):
        assert owner.patch(path, json={'expected_revision': 2, 'subtitle_style_json': invalid}).status_code == 422
    assert owner.get(path).json()['revision']['revision'] == 2
