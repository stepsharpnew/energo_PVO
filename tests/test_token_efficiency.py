from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from pypdf import PdfWriter

from executive_docs.config import Settings
from executive_docs.domain import Artifact, ProjectState
from executive_docs.ingestion import _selected_pdf_pages, build_inventory, select_visual_sources, source_index
from executive_docs.usage import TokenBudgetExceeded, ensure_budget, usage_record


def _pdf_artifact(root: Path, name: str, page_count: int = 1) -> Artifact:
    path = root / "input" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=595, height=842)
    with path.open("wb") as stream:
        writer.write(stream)
    payload = path.read_bytes()
    return Artifact(
        id=sha256(name.encode()).hexdigest()[:8],
        original_name=name,
        stored_name=name,
        media_type="application/pdf",
        size=len(payload),
        sha256=sha256(payload).hexdigest(),
    )


def test_sha_index_is_reused_and_out_of_pilot_visuals_are_filtered(tmp_path: Path) -> None:
    kl6 = _pdf_artifact(tmp_path, "АОСР 1-7 КЛ 6кВ.pdf")
    ktp = _pdf_artifact(tmp_path, "АОСР 1 КТП.pdf")
    artifacts, _ = build_inventory(tmp_path, [kl6, ktp])
    cached_path = tmp_path / "extracted" / f"{kl6.sha256}-2.json"
    assert cached_path.exists()
    first_mtime = cached_path.stat().st_mtime_ns
    source_index(tmp_path, artifacts[0])
    assert cached_path.stat().st_mtime_ns == first_mtime

    selected = select_visual_sources(tmp_path, artifacts, max_pages=10, include_project=False)
    selected_names = {item["artifact"].original_name for item in selected}
    assert "АОСР 1-7 КЛ 6кВ.pdf" in selected_names
    assert "АОСР 1 КТП.pdf" not in selected_names


def test_sha_index_rejects_source_changed_after_cache_creation(tmp_path: Path) -> None:
    artifact = _pdf_artifact(tmp_path, "Рабочий проект.pdf")
    source_index(tmp_path, artifact)
    (tmp_path / "input" / artifact.stored_name).write_bytes(b"%PDF-changed")
    with pytest.raises(ValueError, match="изменился после загрузки"):
        source_index(tmp_path, artifact)


def test_visual_selection_is_upload_order_independent_and_keeps_project_scans(tmp_path: Path) -> None:
    project = _pdf_artifact(tmp_path, "Рабочий проект.pdf")
    scheme = _pdf_artifact(tmp_path, "Исполнительная схема КЛ 6кВ.pdf")
    ktp = _pdf_artifact(tmp_path, "АОСР 1 КТП.pdf")
    artifacts, _ = build_inventory(tmp_path, [project, scheme, ktp])
    forward = select_visual_sources(tmp_path, artifacts, max_pages=2, include_project=True)
    reverse = select_visual_sources(tmp_path, list(reversed(artifacts)), max_pages=2, include_project=True)
    signature = lambda items: {(item["artifact"].original_name, tuple(item["pages"])) for item in items}
    assert signature(forward) == signature(reverse)
    assert signature(forward) == {
        ("Рабочий проект.pdf", (1,)),
        ("Исполнительная схема КЛ 6кВ.pdf", (1,)),
    }


def test_project_page_selector_is_not_hard_capped_at_sixteen_pages() -> None:
    segments = [
        {
            "page": page,
            "locator": f"page:{page}",
            "text": "КЛ-6 кВ кабельная линия" if page == 33 else f"generic page {page}",
            "visual_required": page in {3, 4, 5, 6, 45, 46},
            "score": 1,
        }
        for page in range(1, 47)
    ]
    pages = _selected_pdf_pages({"segments": segments}, project=True, limit=24)
    assert 33 in pages
    assert {3, 4, 5, 6, 45, 46}.issubset(pages)


def test_visual_budget_fails_closed_instead_of_dropping_required_source(tmp_path: Path) -> None:
    project = _pdf_artifact(tmp_path, "Рабочий проект.pdf", page_count=30)
    scheme = _pdf_artifact(tmp_path, "Исполнительная схема КЛ 6кВ.pdf")
    artifacts, _ = build_inventory(tmp_path, [project, scheme])
    with pytest.raises(ValueError, match="31 страниц"):
        select_visual_sources(tmp_path, artifacts, max_pages=24, include_project=True)
    selected = select_visual_sources(tmp_path, artifacts, max_pages=31, include_project=True)
    assert {item["artifact"].original_name for item in selected} == {
        "Рабочий проект.pdf",
        "Исполнительная схема КЛ 6кВ.pdf",
    }


def test_usage_ledger_prices_cache_and_budget() -> None:
    record = usage_record(
        stage="analysis",
        revision=1,
        response_id="resp-1",
        model="gpt-5.6-terra",
        usage={
            "input_tokens": 100_000,
            "input_tokens_details": {"cached_tokens": 80_000, "cache_write_tokens": 10_000},
            "output_tokens": 2_000,
            "output_tokens_details": {"reasoning_tokens": 500},
        },
    )
    assert record.cached_tokens == 80_000
    assert record.reasoning_tokens == 500
    assert record.estimated_cost_usd == pytest.approx(0.10625)

    state = ProjectState(
        job_id="88888888-8888-8888-8888-888888888888",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        model_usage=[record],
    )
    with pytest.raises(TokenBudgetExceeded, match="лимит"):
        ensure_budget(
            state,
            next_input_tokens=350_000,
            max_input_tokens_per_call=400_000,
            max_job_input_tokens=400_000,
            max_job_cost_usd=2.0,
            max_model_calls_per_job=8,
            model="gpt-5.6-terra",
        )


def test_budget_reserves_output_and_cache_write_rates() -> None:
    state = ProjectState(
        job_id="99999999-9999-9999-9999-999999999999",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
    )
    with pytest.raises(TokenBudgetExceeded, match="стоимости"):
        ensure_budget(
            state,
            next_input_tokens=90_000,
            next_output_tokens=12_000,
            max_input_tokens_per_call=100_000,
            max_job_input_tokens=400_000,
            max_job_cost_usd=0.40,
            max_model_calls_per_job=8,
            model="gpt-5.6-terra",
        )


def test_budget_is_whole_job_and_unknown_model_fails_closed() -> None:
    prior = usage_record(
        stage="analysis",
        revision=1,
        response_id="resp-prior",
        model="gpt-5.6-luna",
        usage={"input_tokens": 80_000, "output_tokens": 1_000},
    )
    state = ProjectState(
        job_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        revision=2,
        model_usage=[prior],
    )
    with pytest.raises(TokenBudgetExceeded, match="задании"):
        ensure_budget(
            state,
            next_input_tokens=30_000,
            max_input_tokens_per_call=100_000,
            max_job_input_tokens=100_000,
            max_job_cost_usd=2.0,
            max_model_calls_per_job=8,
            model="gpt-5.6-luna",
        )
    with pytest.raises(TokenBudgetExceeded, match="нет тарифа"):
        ensure_budget(
            ProjectState(
                job_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                branch_id="khimki",
                first_aosr_number=1,
                operator_name="Специалист",
            ),
            next_input_tokens=10,
            max_input_tokens_per_call=100_000,
            max_job_input_tokens=100_000,
            max_job_cost_usd=2.0,
            max_model_calls_per_job=8,
            model="typo-model",
        )


def test_quality_profile_never_overrides_global_step_cap() -> None:
    settings = Settings(max_agent_steps=3)
    assert settings.policy("quality").max_agent_steps == 3


def test_model_call_limit_is_whole_job() -> None:
    records = [
        usage_record(
            stage="analysis",
            revision=revision,
            response_id=f"response-{revision}",
            model="gpt-5.6-luna",
            usage={"input_tokens": 1, "output_tokens": 1},
        )
        for revision in (1, 2)
    ]
    state = ProjectState(
        job_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        revision=3,
        model_usage=records,
    )
    with pytest.raises(TokenBudgetExceeded, match="вызовов для задания"):
        ensure_budget(
            state,
            next_input_tokens=1,
            max_input_tokens_per_call=100,
            max_job_input_tokens=100,
            max_job_cost_usd=2.0,
            max_model_calls_per_job=2,
            model="gpt-5.6-luna",
        )
