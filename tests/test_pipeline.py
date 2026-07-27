from __future__ import annotations

import io
from pathlib import Path

from executive_docs.config import Settings
from executive_docs.domain import JobStatus, ProjectState
from executive_docs.excel import sha256
from executive_docs.pipeline import Pipeline
from executive_docs.repository import Repository
from executive_docs.storage import Storage


ROOT = Path(__file__).resolve().parents[1]
JOB_ID = "44444444-4444-4444-4444-444444444444"


def local_settings(tmp_path: Path) -> Settings:
    return Settings(
        root=ROOT,
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "data" / "runs",
        db_path=tmp_path / "data" / "app.db",
        skill_dir=ROOT / "agent-skill" / "prepare-executive-docs",
        contracts_dir=ROOT / "templates" / "contracts",
        approved_templates_dir=ROOT / "templates" / "approved",
        source_templates_dir=ROOT / "template",
        agent_mode="heuristic",
        soffice_path="missing-soffice",
    )


def test_pipeline_resumes_after_needs_input_without_overwriting_revision(tmp_path: Path, monkeypatch) -> None:
    settings = local_settings(tmp_path)
    settings.ensure_directories()
    repository = Repository(settings.db_path)
    repository.initialize()
    storage = Storage(settings)
    storage.initialize_job(JOB_ID)
    artifact = storage.save_upload(
        JOB_ID,
        "АОСР 1-7 КЛ 6кВ.txt",
        io.BytesIO("Исполнительная схема КЛ 6 кВ".encode()),
        "text/plain",
    )
    state = ProjectState(
        job_id=JOB_ID,
        branch_id="khimki",
        first_aosr_number=20,
        operator_name="Специалист",
        status=JobStatus.FILES_UPLOADED,
        artifacts=[artifact],
    )
    repository.create(state)
    pipeline = Pipeline(settings, repository, storage)
    pipeline.process(JOB_ID)
    state = repository.get(JOB_ID)
    assert state is not None and state.status == JobStatus.NEEDS_INPUT
    answers = {
        "actual.start": "01.06.2026",
        "actual.end": "08.06.2026",
        "materials.quality_documents": "Сертификат № 42 от 01.05.2026",
        "changes.state": "НЕТ",
        "customer.profile_confirmation": "Подтверждено специалистом",
    }
    for question in state.questions:
        question.answer = answers[question.field_key]
        question.confirmed_by = "Специалист"
    state.status = JobStatus.FILES_UPLOADED
    repository.save(state)
    monkeypatch.setattr("executive_docs.pipeline.render_selected_sheets", lambda *args, **kwargs: ([], []))
    pipeline.process(JOB_ID)
    state = repository.get(JOB_ID)
    assert state is not None and state.status == JobStatus.FAILED_VALIDATION
    codes = {issue.code for issue in state.validation_issues}
    assert "TEMPLATE_NOT_APPROVED" not in codes
    assert "MODEL_REVIEW_SKIPPED" in codes
    output = storage.job_dir(JOB_ID) / "output" / "revisions" / "r1" / "xlsx" / "АОСР КЛ-6кВ.xlsx"
    assert output.exists()
    first_hash = sha256(output)
    pipeline.process(JOB_ID)
    assert sha256(output) == first_hash
    assert len(list(output.parent.glob("*.xlsx"))) == 1
    state = repository.get(JOB_ID)
    assert state is not None
    state.revision = 2
    state.status = JobStatus.FILES_UPLOADED
    state.validation_issues = []
    repository.save(state)
    pipeline.process(JOB_ID)
    revision_two = storage.job_dir(JOB_ID) / "output" / "revisions" / "r2" / "xlsx" / "АОСР КЛ-6кВ.xlsx"
    assert revision_two.exists()
    assert output.exists() and sha256(output) == first_hash
