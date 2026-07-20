from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from executive_docs.ingestion import classify, validate_signature
from executive_docs.pipeline import JobQueue


class RecordingPipeline:
    def __init__(self) -> None:
        self.active = 0
        self.maximum_active = 0
        self.completed: list[str] = []
        self.lock = threading.Lock()

    def process(self, job_id: str) -> None:
        with self.lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        time.sleep(0.02)
        with self.lock:
            self.completed.append(job_id)
            self.active -= 1


class BlockingPipeline:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def process(self, _: str) -> None:
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            self.release.wait(timeout=1)


def test_queue_runs_only_one_job_at_a_time() -> None:
    async def scenario() -> RecordingPipeline:
        pipeline = RecordingPipeline()
        queue = JobQueue(pipeline)  # type: ignore[arg-type]
        await queue.start()
        await queue.enqueue("first")
        await queue.enqueue("second")
        await queue.queue.join()
        await queue.stop()
        return pipeline

    pipeline = asyncio.run(scenario())
    assert pipeline.maximum_active == 1
    assert pipeline.completed == ["first", "second"]


def test_enqueue_during_active_job_schedules_resume() -> None:
    async def scenario() -> BlockingPipeline:
        pipeline = BlockingPipeline()
        queue = JobQueue(pipeline)  # type: ignore[arg-type]
        await queue.start()
        await queue.enqueue("same")
        assert await asyncio.to_thread(pipeline.started.wait, 1)
        await queue.enqueue("same")
        pipeline.release.set()
        await queue.queue.join()
        await queue.stop()
        return pipeline

    pipeline = asyncio.run(scenario())
    assert pipeline.calls == 2


def test_fake_ooxml_zip_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"PK-not-a-real-zip")
    with pytest.raises(ValueError, match="OOXML"):
        validate_signature(path)


def test_classification_uses_original_name_not_storage_prefix(tmp_path: Path) -> None:
    stored = tmp_path / "a1b2c3d4-safe.pdf"
    assert classify(stored, "чертёж", "АОСР 1-7 КЛ 6кВ.pdf") == "execution_scheme"
