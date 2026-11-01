from app.domain.models import Asset, Project


def test_media_library_is_private_and_reports_project_storage(clients, ready_project, database):
    owner, other = clients
    project_id = ready_project["project_id"]
    with database() as db:
        project = db.get(Project, project_id)
        source = db.get(Asset, project.source_asset_id)
        source.meta_json = {**source.meta_json, "filename": "wawancara.mp4"}
        db.add_all([
            Asset(project_id=project_id, storage_key=f"projects/{project_id}/preview.mp4", kind="preview", bytes=7, state="ready", mime="video/mp4"),
            Asset(project_id=project_id, storage_key=f"projects/{project_id}/export.mp4", kind="export_mp4", bytes=11, state="ready", mime="video/mp4"),
            Asset(project_id=project_id, storage_key=f"projects/{project_id}/export.srt", kind="export_srt", bytes=3, state="ready", mime="application/x-subrip"),
        ])
        db.commit()

    response = owner.get("/api/v1/media")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["summary"] == {
        "project_count": 1,
        "video_count": 3,
        "source_bytes": 16,
        "preview_bytes": 7,
        "export_bytes": 11,
        "subtitle_bytes": 3,
        "total_bytes": 37,
    }
    item = body["items"][0]
    assert item["project_id"] == project_id
    assert item["source_asset"]["metadata"]["filename"] == "wawancara.mp4"
    assert item["file_count"] == 4
    assert item["video_count"] == 3
    assert item["total_bytes"] == 37

    assert other.get("/api/v1/media").json()["items"] == []


def test_media_library_search_and_pagination(clients, ready_project):
    owner = clients[0]
    assert owner.get("/api/v1/media", params={"search": "tidak ada"}).json()["total"] == 0
    page = owner.get("/api/v1/media", params={"search": "editorial", "page": 1, "page_size": 1}).json()
    assert page["total"] == 1
    assert page["page"] == 1
    assert page["page_size"] == 1
