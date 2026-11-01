"""Live speech upload -> Whisper -> manual transcript clip -> MP4/SRT.

Use a short licensed MP4 (5-180s) and an explicitly supplied smoke account.
Does not call the external selector or silently mock transcription.
"""
import argparse
import json
import os
from pathlib import Path
import time

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("input", type=Path)
parser.add_argument("--language", choices=["auto", "id", "en"], default="auto")
parser.add_argument("--expect-empty", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = root / ".artifacts/transcription-pipeline"
output.mkdir(parents=True, exist_ok=True)


def wait(client, job_id, timeout=600):
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout:
        response = client.get(f"/api/v1/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        if last != job["status"]:
            print(job["stage"], job["status"], flush=True)
            last = job["status"]
        if job["status"] in ("succeeded", "failed", "cancelled"):
            assert job["status"] == "succeeded", job["error_message"]
            return job
        time.sleep(1)
    raise TimeoutError("Live transcription smoke timed out")


with httpx.Client(base_url=os.environ.get("CLIPPER_SMOKE_URL", "http://localhost:8080"), timeout=60) as client:
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post("/api/v1/auth/login", json={"email": os.environ["CLIPPER_SMOKE_EMAIL"], "password": os.environ["CLIPPER_SMOKE_PASSWORD"]}, headers={"X-CSRF-Token": csrf})
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    project = client.post("/api/v1/projects", json={"name": f"Uji transkripsi nyata - {args.language} - {args.input.stem}"})
    project.raise_for_status()
    pid = project.json()["id"]
    with args.input.open("rb") as stream:
        upload = client.post(f"/api/v1/projects/{pid}/source", content=stream, headers={"Content-Type": "video/mp4"})
    upload.raise_for_status()
    wait(client, upload.json()["id"])
    started = time.monotonic()
    process = client.post(f"/api/v1/projects/{pid}/process", json={"language": args.language, "analyze": args.expect_empty})
    process.raise_for_status()
    wait(client, process.json()["id"])
    transcript = client.get(f"/api/v1/projects/{pid}/transcripts/latest").json()
    report = {"project_id": pid, "language": transcript["language"], "segments": len(transcript["segments"]), "transcription_with_queue_seconds": round(time.monotonic() - started, 2)}
    if args.expect_empty:
        project = client.get(f"/api/v1/projects/{pid}").json()
        assert project["status"] == "no_speech"
        assert not transcript["segments"]
        assert not any(job["kind"] == "analyze" for job in project["jobs"])
        print("PASS: no speech, no selector job")
    else:
        assert transcript["segments"]
        project = client.get(f"/api/v1/projects/{pid}").json()
        duration = project["source_asset"]["metadata"]["duration_ms"]
        assert 5000 <= duration <= 180000, "Use a 5-180 second speech fixture"
        clip = client.post(f"/api/v1/projects/{pid}/clips", json={"title": "Ucapan asli dengan subtitle", "start_ms": 0, "end_ms": duration, "transcript_id": transcript["id"], "crop_json": {"mode": "fit", "x": 0.5, "y": 0.5}})
        clip.raise_for_status()
        assert clip.json()["revision"]["cues"]
        export = client.post(f"/api/v1/clips/{clip.json()['id']}/exports", json={"revision": 1, "resolution": 720})
        export.raise_for_status()
        wait(client, export.json()["id"])
        result = client.get(f"/api/v1/projects/{pid}/exports").json()["items"][0]
        for extension in ("mp4", "srt"):
            file = client.get(result[f"{extension}_asset"]["content_url"])
            file.raise_for_status()
            (output / f"speech-{args.language}.{extension}").write_bytes(file.content)
        report["clip_id"] = clip.json()["id"]
        print("PASS: real speech -> versioned transcript -> source cues -> MP4/SRT")
    (output / f"report-{'silence' if args.expect_empty else args.language}.json").write_text(json.dumps(report, indent=2), encoding="utf8")
