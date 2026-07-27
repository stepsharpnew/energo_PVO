from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from .config import Settings
from .domain import Artifact


SAFE_NAME = re.compile(r"[^0-9A-Za-zА-Яа-яЁё._()\- ]+")


def is_selected_filename(name: str | None) -> bool:
    """Distinguish a selected upload from an empty multipart file field."""
    return bool(name and name.strip())


class Storage:
    def __init__(self, settings: Settings):
        self.settings = settings

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f-]{36}", job_id):
            raise ValueError("Invalid job id")
        return self.settings.runs_dir / job_id

    def initialize_job(self, job_id: str) -> Path:
        root = self.job_dir(job_id)
        for name in ("input", "extracted", "state", "output/revisions", "preview", "report"):
            (root / name).mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def safe_filename(name: str) -> str:
        cleaned = SAFE_NAME.sub("_", Path(name).name).strip(" .")
        return cleaned[:180] or "file"

    def save_upload(self, job_id: str, original_name: str, stream: BinaryIO, media_type: str) -> Artifact:
        safe = self.safe_filename(original_name)
        prefix = uuid.uuid4().hex[:8]
        stored = f"{prefix}-{safe}"
        destination = self.job_dir(job_id) / "input" / stored
        digest = hashlib.sha256()
        size = 0
        with destination.open("wb") as target:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > self.settings.max_file_bytes:
                    target.close()
                    destination.unlink(missing_ok=True)
                    raise ValueError(f"Файл {original_name} превышает лимит")
                digest.update(chunk)
                target.write(chunk)
        return Artifact(
            id=prefix,
            original_name=original_name,
            stored_name=stored,
            media_type=media_type or "application/octet-stream",
            size=size,
            sha256=digest.hexdigest(),
        )

    def remove_job(self, job_id: str) -> None:
        root = self.job_dir(job_id)
        if root.exists():
            shutil.rmtree(root)
