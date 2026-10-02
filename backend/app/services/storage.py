"""Where uploaded files live.

Routes depend on the `FileStorage` protocol, not on a disk path, so moving to
S3 later means adding an `S3FileStorage` and changing `get_storage` — nothing
that saves a file has to change. Tests override `get_storage` with a
temporary directory.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings


class FileStorage(Protocol):
    async def save(self, key: str, data: bytes) -> str:
        """Store `data` under `key` and return a URI that identifies it."""
        ...


class LocalFileStorage:
    """Files on local disk under `root`. URIs look like `local://resumes/…`."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    async def save(self, key: str, data: bytes) -> str:
        path = (self.root / key).resolve()
        # Keys are built by our own code from UUIDs, but refuse to write
        # outside the root anyway — cheap insurance against a future caller.
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"storage key escapes the root: {key}")
        await asyncio.to_thread(self._write, path, data)
        return f"local://{key}"

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


@lru_cache
def get_storage() -> FileStorage:
    return LocalFileStorage(settings.UPLOAD_DIR)
