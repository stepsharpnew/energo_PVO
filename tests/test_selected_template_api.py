from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from pypdf import PdfWriter
from starlette.datastructures import Headers

from executive_docs.config import Settings
from executive_docs.domain import JobStatus, ProjectState
from executive_docs.main import create_job, delete_job, job_file
from executive_docs.storage import Storage


class RecordingRepository:
    def __init__(self):
        self.created = []

    def create(self, state) -> None:
        self.created.append(state)


class RecordingQueue:
    def __init__(self):
        self.enqueued: list[str] = []

    async def enqueue(self, job_id: str) -> None:
        self.enqueued.append(job_id)


def pdf_upload(name: str = "project.pdf") -> UploadFile:
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(stream)
    stream.seek(0)
    return UploadFile(
        filename=name,
        file=stream,
        headers=Headers({"content-type": "application/pdf"}),
    )


def configured_storage(tmp_path) -> Storage:
    settings = Settings(
        root=tmp_path,
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "data" / "runs",
        db_path=tmp_path / "data" / "app.db",
    )
    settings.ensure_directories()
    return Storage(settings)


def test_create_job_pins_one_selected_template_and_one_pdf(tmp_path, monkeypatch) -> None:
    repository = RecordingRepository()
    queue = RecordingQueue()
    monkeypatch.setattr("executive_docs.main.repository", repository)
    monkeypatch.setattr("executive_docs.main.queue", queue)
    monkeypatch.setattr(
        "executive_docs.main.storage",
        configured_storage(tmp_path),
    )
    request = SimpleNamespace(headers={"accept": "application/json"})

    response = asyncio.run(
        create_job(
            request,
            template_id="ojr",
            operator_name="Специалист",
            processing_profile="balanced",
            files=[pdf_upload()],
        )
    )

    assert response.status_code == 202
    payload = json.loads(response.body)
    assert payload["flow_version"] == "selected-template-v2"
    assert payload["selected_template_id"] == "ojr"
    assert "selected_template_sha256" not in payload
    assert "selected_template_contract_sha256" not in payload
    assert len(repository.created) == 1
    state = repository.created[0]
    assert state.selected_template_sha256
    assert state.selected_template_contract_sha256
    assert len(state.artifacts) == 1
    assert state.artifacts[0].original_name == "project.pdf"
    assert queue.enqueued == [state.job_id]


@pytest.mark.parametrize(
    "template_id,files",
    [
        ("missing", [pdf_upload()]),
        ("ojr", [pdf_upload("one.pdf"), pdf_upload("two.pdf")]),
        (
            "ojr",
            [
                UploadFile(
                    filename="facts.xlsx",
                    file=io.BytesIO(b"PK-not-a-workbook"),
                )
            ],
        ),
        (
            "ojr",
            [
                pdf_upload(),
                UploadFile(
                    filename="facts.xlsx",
                    file=io.BytesIO(b"PK-not-a-workbook"),
                ),
            ],
        ),
    ],
)
def test_create_job_rejects_unknown_template_multiple_pdfs_and_xlsx(
    template_id,
    files,
) -> None:
    request = SimpleNamespace(headers={"accept": "application/json"})
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            create_job(
                request,
                template_id=template_id,
                operator_name="Специалист",
                processing_profile="balanced",
                files=files,
            )
        )
    assert error.value.status_code == 422


def test_create_job_rejects_false_pdf_signature(tmp_path, monkeypatch) -> None:
    repository = RecordingRepository()
    queue = RecordingQueue()
    monkeypatch.setattr("executive_docs.main.repository", repository)
    monkeypatch.setattr("executive_docs.main.queue", queue)
    monkeypatch.setattr(
        "executive_docs.main.storage",
        configured_storage(tmp_path),
    )
    upload = UploadFile(
        filename="project.pdf",
        file=io.BytesIO(b"not a pdf"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    request = SimpleNamespace(headers={"accept": "application/json"})

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            create_job(
                request,
                template_id="ojr",
                operator_name="Специалист",
                processing_profile="balanced",
                files=[upload],
            )
        )

    assert error.value.status_code == 400
    assert repository.created == []
    assert queue.enqueued == []


def test_create_job_reports_hot_changed_template_as_unavailable(monkeypatch) -> None:
    class ChangedCatalog:
        @staticmethod
        def get(_: str):
            raise ValueError("Контракт шаблона изменился")

    monkeypatch.setattr("executive_docs.main.template_catalog", ChangedCatalog())
    request = SimpleNamespace(headers={"accept": "application/json"})

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            create_job(
                request,
                template_id="ojr",
                operator_name="Специалист",
                processing_profile="balanced",
                files=[pdf_upload()],
            )
        )

    assert error.value.status_code == 422
    assert "Шаблон недоступен" in error.value.detail


def test_generic_file_route_exposes_only_current_preview_pdf(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configured = configured_storage(tmp_path)
    state = ProjectState(
        job_id="77777777-7777-7777-7777-777777777777",
        operator_name="Специалист",
        revision=2,
    )
    configured.initialize_job(state.job_id)
    root = configured.job_dir(state.job_id)
    preview_path = root / "preview" / "r2" / "preview.pdf"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"%PDF-preview")
    input_path = root / "input" / "project.pdf"
    input_path.write_bytes(b"%PDF-private-input")

    class SingleRepository:
        @staticmethod
        def get(job_id: str):
            return state if job_id == state.job_id else None

        @staticmethod
        def list(_: int = 100):
            return [state]

    monkeypatch.setattr("executive_docs.main.repository", SingleRepository())
    monkeypatch.setattr("executive_docs.main.storage", configured)

    response = asyncio.run(
        job_file(state.public_ref, "preview/r2/preview.pdf")
    )
    assert Path(response.path) == preview_path

    with pytest.raises(HTTPException) as error:
        asyncio.run(job_file(state.public_ref, "input/project.pdf"))
    assert error.value.status_code == 404


def test_delete_waits_for_worker_before_removing_job_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configured = configured_storage(tmp_path)
    state = ProjectState(
        job_id="88888888-8888-8888-8888-888888888888",
        operator_name="Специалист",
    )
    configured.initialize_job(state.job_id)
    root = configured.job_dir(state.job_id)
    (root / "input" / "project.pdf").write_bytes(b"%PDF-private-input")

    class DeletingRepository:
        def __init__(self):
            self.current = state
            self.saved_statuses: list[JobStatus] = []

        def get(self, job_id: str):
            return self.current if self.current and job_id == state.job_id else None

        def list(self, _: int = 100):
            return [self.current] if self.current else []

        def save(self, saved: ProjectState):
            self.saved_statuses.append(saved.status)
            self.current = saved

        def delete(self, job_id: str):
            if job_id == state.job_id:
                self.current = None

    class WaitingQueue:
        def __init__(self):
            self.waited: list[str] = []

        async def cancel_and_wait(self, job_id: str):
            self.waited.append(job_id)

    repository = DeletingRepository()
    queue = WaitingQueue()
    monkeypatch.setattr("executive_docs.main.repository", repository)
    monkeypatch.setattr("executive_docs.main.queue", queue)
    monkeypatch.setattr("executive_docs.main.storage", configured)

    response = asyncio.run(delete_job(state.public_ref))

    assert response.status_code == 200
    assert repository.saved_statuses == [JobStatus.CANCELLED]
    assert queue.waited == [state.job_id]
    assert repository.current is None
    assert not root.exists()
