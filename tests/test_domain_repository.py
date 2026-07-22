from pathlib import Path

import pytest

from executive_docs.domain import CorrectionPayload, JobStatus, ModelUsageRecord, ProjectState
from executive_docs.repository import Repository


def test_repository_persists_full_project_state(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "app.db")
    repository.initialize()
    state = ProjectState(
        job_id="11111111-1111-1111-1111-111111111111",
        branch_id="khimki",
        first_aosr_number=7,
        operator_name="Специалист",
        status=JobStatus.NEEDS_INPUT,
    )
    repository.create(state)
    loaded = repository.get(state.job_id)
    assert loaded is not None
    assert loaded.status == JobStatus.NEEDS_INPUT
    assert loaded.first_aosr_number == 7
    assert repository.recoverable_jobs() == []


def test_active_job_is_recoverable(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "app.db")
    repository.initialize()
    state = ProjectState(
        job_id="22222222-2222-2222-2222-222222222222",
        branch_id="solnechnogorsk",
        first_aosr_number=1,
        operator_name="Оператор",
        status=JobStatus.GENERATING,
    )
    repository.create(state)
    assert repository.recoverable_jobs() == [state.job_id]


def test_usage_progress_does_not_revive_cancelled_job(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "app.db")
    repository.initialize()
    state = ProjectState(
        job_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Оператор",
        status=JobStatus.ANALYZING,
    )
    repository.create(state)
    cancelled = state.model_copy(update={"status": JobStatus.CANCELLED})
    repository.save(cancelled)
    state.model_usage.append(
        ModelUsageRecord(
            stage="analysis",
            revision=1,
            response_id="paid-after-cancel",
            model="gpt-5.6-luna",
            input_tokens=10,
            cached_tokens=0,
            cache_write_tokens=0,
            output_tokens=2,
            reasoning_tokens=0,
            estimated_cost_usd=0.000022,
        )
    )
    assert repository.save_progress(state) is False
    loaded = repository.get(state.job_id)
    assert loaded.status == JobStatus.CANCELLED
    assert loaded.model_usage[0].response_id == "paid-after-cancel"


def test_customer_correction_requires_regression_before_approval(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "app.db")
    repository.initialize()
    state = ProjectState(
        job_id="55555555-5555-5555-5555-555555555555",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
    )
    repository.create(state)
    repository.add_corrections(
        state.job_id,
        1,
        [
            CorrectionPayload(
                artifact="АОСР КЛ-6кВ",
                location="подписант",
                current_value="А",
                expected_value="Б",
                reason="Правило филиала",
                scope="customer",
            )
        ],
    )
    proposal = repository.list_corrections(state.job_id)[0]
    assert proposal["category"] == "customer_or_branch_rule"
    assert proposal["status"] == "PROPOSED"
    with pytest.raises(ValueError, match="регрессионный"):
        repository.review_correction(
            proposal["id"],
            status="APPROVED",
            reviewed_by="Эксперт",
            comment="Проверено",
            regression_passed=False,
        )
    approved = repository.review_correction(
        proposal["id"],
        status="APPROVED",
        reviewed_by="Эксперт",
        comment="Регрессия пройдена",
        regression_passed=True,
    )
    assert approved and approved["status"] == "APPROVED"
