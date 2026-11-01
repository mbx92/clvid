"""Real HTTP/queue/media smoke. Requires an explicitly supplied test account.

CLIPPER_SMOKE_URL (default http://localhost:8080), CLIPPER_SMOKE_EMAIL,
CLIPPER_SMOKE_PASSWORD. Creates one named test project; retains it for UI review.
"""
import json
import os
from pathlib import Path
import time

import httpx

root = Path(__file__).resolve().parents[1]
base = os.environ.get("CLIPPER_SMOKE_URL", "http://localhost:8080")
email = os.environ["CLIPPER_SMOKE_EMAIL"]
password = os.environ["CLIPPER_SMOKE_PASSWORD"]
fixture = root / ".artifacts/fixture-source.mp4"
if not fixture.exists():
    raise SystemExit("Buat fixture dengan python scripts/make_fixture.py dahulu.")


def wait_job(client, job_id, timeout=300):
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        state = (job["status"], job["stage"])
        if state != previous:
            print("Job", job["stage"], job["status"], flush=True)
            previous = state
        if job["status"] == "succeeded":
            return job
        if job["status"] in ("failed", "cancelled"):
            raise AssertionError(f"{job['error_code']}: {job['error_message']}")
        time.sleep(1)
    raise TimeoutError(f"Job tidak selesai dalam {timeout} detik")


with httpx.Client(base_url=base, timeout=60) as client:
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers={"X-CSRF-Token": csrf})
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    project = client.post("/api/v1/projects", json={"name": "Uji pipeline nyata — pola sintetis"})
    project.raise_for_status()
    pid = project.json()["id"]
    with fixture.open("rb") as stream:
        response = client.post(f"/api/v1/projects/{pid}/source", content=stream, headers={"Content-Type": "video/mp4", "X-Filename": fixture.name})
    response.raise_for_status()
    wait_job(client, response.json()["id"])
    clip_response = client.post(f"/api/v1/projects/{pid}/clips", json={
        "title": "Crop kanan dan subtitle koreksi", "start_ms": 1123, "end_ms": 8123,
        "crop_json": {"mode": "fill", "x": 0.8, "y": 0.5},
        "cues": [
            {"start_ms": 0, "end_ms": 3000, "text": "Subtitle koreksi — hasil ekspor nyata."},
            {"start_ms": 3000, "end_ms": 7000, "text": "Teks {aman} dan garis \\ bukan instruksi."},
        ],
    })
    clip_response.raise_for_status()
    clip = clip_response.json()
    export_url = f"/api/v1/clips/{clip['id']}/exports"
    export = client.post(export_url, json={"revision": 1, "resolution": 720}, headers={"Idempotency-Key": "smoke-render"})
    export.raise_for_status()
    duplicate = client.post(export_url, json={"revision": 1, "resolution": 720}, headers={"Idempotency-Key": "smoke-render"})
    assert duplicate.json()["id"] == export.json()["id"]
    edit = client.patch(f"/api/v1/clips/{clip['id']}", json={"expected_revision": 1, "title": "Revisi 2 setelah ekspor dimulai"})
    edit.raise_for_status()
    wait_job(client, export.json()["id"])
    exported = client.get(f"/api/v1/projects/{pid}/exports").json()["items"][0]
    assert exported["revision"] == 1 and exported["status"] == "ready"
    paths = {}
    for extension, field in (("mp4", "mp4_asset"), ("srt", "srt_asset")):
        data = client.get(exported[field]["content_url"])
        data.raise_for_status()
        target = root / f".artifacts/acceptance.{extension}"
        target.write_bytes(data.content)
        paths[extension] = str(target)
    assert "Subtitle koreksi" in (root / ".artifacts/acceptance.srt").read_text(encoding="utf8")
    range_response = client.get(exported["mp4_asset"]["content_url"], headers={"Range": "bytes=0-99"})
    assert range_response.status_code == 206 and len(range_response.content) == 100
    report = {"project_id": pid, "clip_id": clip["id"], "export_id": exported["id"], "job_id": export.json()["id"], "paths": paths}
    (root / ".artifacts/smoke-report.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print("PASS: upload -> validation -> manual clip -> immutable render -> MP4/SRT -> HTTP Range")
    print("Project:", pid)
