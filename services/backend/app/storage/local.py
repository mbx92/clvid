import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from app.config import get_settings


class Storage(Protocol):
    def path(self, key: str) -> Path: ...
    def remove(self, key: str) -> None: ...


class LocalStorage:
    """Private filesystem adapter. Keys are server generated and relative to MEDIA_ROOT."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root if root is not None else get_settings().media_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        parts = PurePosixPath(key).parts
        if not key or "\\" in key or ":" in key or key.startswith("/") or any(x in (".", "..") for x in parts):
            raise ValueError("Kunci penyimpanan tidak valid.")
        candidate = self.root.joinpath(*parts)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root) or resolved == self.root:
            raise ValueError("Akses penyimpanan di luar direktori media ditolak.")
        # Reject all symlinks, including links that happen to remain within the root.
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Akses symlink ditolak.")
        return candidate

    def new_key(self, project_id: str, suffix: str) -> str:
        return f"projects/{project_id}/{uuid4().hex}{suffix}"

    def prepare(self, key: str) -> Path:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def remove(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def free_bytes(self) -> int:
        return shutil.disk_usage(self.root).free

    def publish(self, temporary: Path, key: str) -> Path:
        if not temporary.resolve().is_relative_to(self.root):
            raise ValueError("File sementara di luar penyimpanan.")
        final = self.prepare(key)
        os.replace(temporary, final)
        return final
