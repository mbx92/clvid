"""Isolated test database. PostgreSQL runs require an explicitly named *_test DB."""
import os
from pathlib import Path
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "backend"))
TEST_ROOT = Path(tempfile.mkdtemp(prefix="clipper-tests-"))
database_url = os.environ.get("CLIPPER_TEST_DATABASE_URL", f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}")
if not database_url.startswith("sqlite") and not database_url.split("?", 1)[0].endswith("_test"):
    raise RuntimeError("CLIPPER_TEST_DATABASE_URL must use a dedicated database ending in _test")
os.environ["DATABASE_URL"] = database_url
os.environ["MEDIA_ROOT"] = str(TEST_ROOT / "media")
os.environ["APP_ORIGIN"] = "http://testserver"
os.environ["MIN_FREE_DISK_BYTES"] = "0"
os.environ["REDIS_URL"] = os.environ.get("CLIPPER_TEST_REDIS_URL", "redis://127.0.0.1:6387/15")
os.environ["SUBTITLE_FONT_PATH"] = str(ROOT / "services/backend/fonts/NotoSans-Regular.ttf")
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["STORY_LOCAL_ENABLED"] = "false"


@pytest.fixture
def database(tmp_path):
    from sqlalchemy import text
    from app.config import get_settings
    from app.db import Base, engine, SessionLocal
    from app.domain import models  # Register all tables before creating them.
    Base.metadata.create_all(engine)
    names = list(Base.metadata.tables)
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            for name in names:
                connection.exec_driver_sql(f'DELETE FROM "{name}"')
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        else:
            connection.execute(text("TRUNCATE " + ", ".join(f'"{name}"' for name in names) + " CASCADE"))
            connection.commit()
    get_settings().media_root = tmp_path / "media"
    get_settings().media_root.mkdir()
    yield SessionLocal


@pytest.fixture
def clients(database):
    from fastapi.testclient import TestClient
    from app.api.auth import hasher
    from app.domain.models import User
    from app.main import app
    # Test-only credentials. The deployed application has no default account.
    with database() as db:
        db.add_all([User(email=email, password_hash=hasher.hash("test-only-password"))
                    for email in ("a@example.test", "b@example.test")])
        db.commit()
    result = []
    for email in ("a@example.test", "b@example.test"):
        client = TestClient(app)
        token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        response = client.post("/api/v1/auth/login", json={"email": email, "password": "test-only-password"}, headers={"X-CSRF-Token": token})
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        result.append(client)
    yield result
    for client in result:
        client.close()


@pytest.fixture
def ready_project(clients, database):
    from app.domain.models import Asset, Project
    from app.storage.local import LocalStorage
    response = clients[0].post("/api/v1/projects", json={"name": "Uji editorial"})
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    storage = LocalStorage()
    key = storage.new_key(project_id, ".mp4")
    storage.prepare(key).write_bytes(b"0123456789abcdef")
    with database() as db:
        asset = Asset(project_id=project_id, storage_key=key, kind="source", bytes=16, state="ready", mime="video/mp4", meta_json={"duration_ms": 12000, "width": 640, "height": 360})
        db.add(asset)
        db.flush()
        project = db.get(Project, project_id)
        project.source_asset_id, project.status = asset.id, "ready"
        db.commit()
        return {"project_id": project_id, "asset_id": asset.id}
