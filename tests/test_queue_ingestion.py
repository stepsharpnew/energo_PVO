from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from executive_docs.domain import Artifact
from executive_docs.ingestion import (
    _build_segments,
    _pdf_text_reliability,
    build_compact_evidence,
    build_inventory,
    classify,
    read_indexed_source,
    select_visual_sources,
    validate_signature,
)
from executive_docs.pipeline import JobQueue
from executive_docs.storage import is_selected_filename


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


def test_cancel_and_wait_suppresses_rerun_and_waits_for_active_job() -> None:
    async def scenario() -> tuple[BlockingPipeline, bool]:
        pipeline = BlockingPipeline()
        queue = JobQueue(pipeline)  # type: ignore[arg-type]
        await queue.start()
        await queue.enqueue("same")
        assert await asyncio.to_thread(pipeline.started.wait, 1)
        await queue.enqueue("same")
        waiting = asyncio.create_task(queue.cancel_and_wait("same"))
        await asyncio.sleep(0)
        was_waiting = not waiting.done()
        pipeline.release.set()
        await waiting
        await queue.queue.join()
        await queue.stop()
        return pipeline, was_waiting

    pipeline, was_waiting = asyncio.run(scenario())
    assert was_waiting is True
    assert pipeline.calls == 1


def test_fake_ooxml_zip_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"PK-not-a-real-zip")
    with pytest.raises(ValueError, match="OOXML"):
        validate_signature(path)


def test_classification_uses_original_name_not_storage_prefix(tmp_path: Path) -> None:
    stored = tmp_path / "a1b2c3d4-safe.pdf"
    assert classify(stored, "чертёж", "АОСР 1-7 КЛ 6кВ.pdf") == "execution_scheme"


def test_unselected_optional_upload_is_not_a_file() -> None:
    assert not is_selected_filename(None)
    assert not is_selected_filename("")
    assert not is_selected_filename("   ")
    assert is_selected_filename("Фактические данные.xlsx")


def test_legacy_empty_file_placeholder_is_ignored(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "deadbeef-file").write_bytes(b"")
    artifact = Artifact(
        id="deadbeef",
        original_name="file",
        stored_name="deadbeef-file",
        media_type="application/octet-stream",
        size=0,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )

    updated, manifest = build_inventory(tmp_path, [artifact])

    assert updated == []
    assert manifest == "[]"


SIGNATURE_OVERLAY = (
    "ДОКУМЕНТ ПОДПИСАН ЭЛЕКТРОННОЙ ПОДПИСЬЮ Идентификатор: example\n"
    "ОТПРАВЛЕНО Организация\nСертификат 123456789\n"
    "УТВЕРЖДЕНО Организация\nСертификат 987654321\n"
    'Оператор ЭДО ООО "Оператор"\n'
)


@pytest.mark.parametrize(
    ("text", "reliable", "reason"),
    [
        ("", False, "no_text_layer"),
        ("КЛ-6 кВ, 120 м", True, None),
        ("Кабель ÖLFLEX 3×2,5 мм². " * 6, True, None),
        ("РАБОЧИЙ ПРОЕКТ\x15\x15\x17\x03\x18\x13", False, "broken_font_encoding"),
        ("ǚтǹоитǮлȅǺтǫо ǋǔИ ǚолǶǮȀǶогоǹǺǳиǲ район", False, "broken_font_encoding"),
        ("Строительство (cid:127)(cid:234)", False, "unmapped_font_glyphs"),
        (SIGNATURE_OVERLAY, False, "electronic_signature_overlay_only"),
        ("Наименование объекта: строительство воздушной линии. " * 4 + SIGNATURE_OVERLAY, True, None),
    ],
)
def test_pdf_text_reliability_detects_font_damage_and_signature_only_scans(
    text: str, reliable: bool, reason: str | None,
) -> None:
    assert _pdf_text_reliability(text) == (reliable, reason)


def test_unreliable_text_pages_remain_required_visual_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    texts = [
        "Проект кабельной линии КЛ-6 кВ с читаемым текстом. " * 5,
        "РАБОЧИЙ ПРОЕКТ\x15\x15\x17\x03\x18\x13 " * 10,
        SIGNATURE_OVERLAY,
        "",
    ]
    monkeypatch.setattr(
        "executive_docs.ingestion.PdfReader",
        lambda _: SimpleNamespace(
            is_encrypted=False,
            pages=[SimpleNamespace(extract_text=lambda text=text: text) for text in texts],
        ),
    )
    segments, pages = _build_segments(tmp_path / "project.pdf")
    assert [item["text_reliable"] for item in segments] == [True, False, False, False]
    assert [item["visual_required"] for item in segments] == [False, True, True, True]
    index = {"segments": segments, "pages": pages, "scope": "unknown"}
    monkeypatch.setattr("executive_docs.ingestion.source_index", lambda *_: index)
    artifact = Artifact(
        id="project",
        original_name="project.pdf",
        stored_name="project.pdf",
        media_type="application/pdf",
        size=100,
        sha256="0" * 64,
        category="project",
    )
    with pytest.raises(ValueError, match="3 страниц"):
        select_visual_sources(tmp_path, [artifact], max_pages=2, include_project=True)
    selected = select_visual_sources(tmp_path, [artifact], max_pages=4, include_project=True)
    assert selected[0]["pages"] == [1, 2, 3, 4]

    packet = build_compact_evidence(tmp_path, [artifact], max_chars=10_000)
    damaged = next(item for item in packet if item["locator"] == "page:2")
    assert damaged["text"] == texts[1]
    assert damaged["text_reliable"] is False
    assert damaged["text_reliability_reason"] == "broken_font_encoding"
    assert "page image" in damaged["evidence_instruction"]
    reread, _ = read_indexed_source(tmp_path, artifact, pages=[2])
    assert "UNRELIABLE TEXT LAYER" in reread
    assert texts[1] in reread


@pytest.mark.parametrize("category", ["execution_scheme", "filled_aosr"])
@pytest.mark.parametrize("text_reliable", [False, True])
def test_selected_template_keeps_vl_pdf_evidence_excluded_from_legacy_pilot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, category: str, text_reliable: bool,
) -> None:
    # Selected-template visual packets label even a full one-page PDF now.
    # Keep a real source behind the mocked routing index for that operation.
    from pypdf import PdfWriter

    source = tmp_path / "input" / "aosr-vl.pdf"
    source.parent.mkdir()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with source.open("wb") as stream:
        writer.write(stream)
    artifact = Artifact(
        id="aosr-vl",
        original_name="АОСР ВЛ.pdf",
        stored_name="aosr-vl.pdf",
        media_type="application/pdf",
        size=100,
        sha256="0" * 64,
        category=category,
    )
    index = {
        "pages": 1,
        "scope": "vl",
        "segments": [{
            "page": 1,
            "locator": "page:1",
            "text": "Строительство ВЛИ Солнечногорский район" if text_reliable else "ǚтǹоитǮлȅǺтǫо ǋǔИ ǚолǶǮȀǶогоǹǺǳиǲ район",
            "text_reliable": text_reliable,
            "text_reliability_reason": "broken_font_encoding",
            "visual_required": True,
            "score": 10,
        }],
    }
    monkeypatch.setattr("executive_docs.ingestion.source_index", lambda *_: index)
    assert build_compact_evidence(tmp_path, [artifact], 10_000) == []
    assert select_visual_sources(tmp_path, [artifact], max_pages=1, include_project=True) == []

    packet = build_compact_evidence(tmp_path, [artifact], 10_000, selected_template=True)
    # Broken font glyphs no longer consume text capacity. Their original page
    # is still mandatory visual input, regardless of legacy category/scope.
    assert [(item["file_id"], item["locator"]) for item in packet] == ([(artifact.id, "page:1")] if text_reliable else [])
    selected = select_visual_sources(
        tmp_path, [artifact], max_pages=1, include_project=False, selected_template=True,
    )
    assert selected[0]["pages"] == [1]
    with pytest.raises(ValueError, match="1 страниц"):
        select_visual_sources(
            tmp_path, [artifact], max_pages=0, include_project=True, selected_template=True,
        )
