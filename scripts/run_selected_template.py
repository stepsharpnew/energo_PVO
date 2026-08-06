#!/usr/bin/env python3
"""Run one selected-template job synchronously against one PDF."""

from __future__ import annotations

import argparse
import mimetypes
import sys
import uuid
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from executive_docs.config import settings as base_settings  # noqa: E402
from executive_docs.domain import JobStatus, ProjectState  # noqa: E402
from executive_docs.pipeline import Pipeline  # noqa: E402
from executive_docs.repository import Repository  # noqa: E402
from executive_docs.selected_templates import TemplateCatalog  # noqa: E402
from executive_docs.storage import Storage  # noqa: E402
from executive_docs.usage import job_estimated_cost  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--template-id", default="aosr_vl")
    parser.add_argument("--mode", choices=["heuristic", "openai"], default="openai")
    parser.add_argument(
        "--profile",
        choices=["economy", "balanced", "quality"],
        default="quality",
    )
    parser.add_argument("--operator", default="Регрессионный запуск selected-template")
    args = parser.parse_args()

    source = args.pdf.resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise SystemExit(f"PDF не найден: {source}")
    settings = replace(base_settings, agent_mode=args.mode)
    if args.mode == "openai" and not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is required for --mode openai")
    settings.ensure_directories()
    catalog = TemplateCatalog(
        settings.root,
        settings.fill_contracts_dir,
        settings.approved_templates_dir,
    )
    try:
        contract = catalog.get(args.template_id)
    except (KeyError, ValueError) as exc:
        raise SystemExit(f"Шаблон недоступен: {exc}") from exc

    repository = Repository(settings.db_path)
    repository.initialize()
    storage = Storage(settings)
    job_id = str(uuid.uuid4())
    storage.initialize_job(job_id)
    with source.open("rb") as stream:
        artifact = storage.save_upload(
            job_id,
            source.name,
            stream,
            mimetypes.guess_type(source.name)[0] or "application/pdf",
        )
    state = ProjectState(
        job_id=job_id,
        operator_name=args.operator,
        flow_version="selected-template-v2",
        selected_template_id=contract.template_id,
        selected_template_name=contract.display_name,
        selected_template_status=contract.status,
        selected_template_version=contract.version,
        selected_template_sha256=contract.candidate_sha256,
        selected_template_contract_sha256=contract.contract_sha256,
        processing_profile=args.profile,
        status=JobStatus.FILES_UPLOADED,
        artifacts=[artifact],
    )
    repository.create(state)
    Pipeline(settings, repository, storage).process(job_id)
    result = repository.get(job_id)
    if result is None:
        raise SystemExit("Job disappeared from the repository")

    estimated_cost = job_estimated_cost(result)
    print(f"job_id={job_id}")
    print(f"status={result.status}")
    print(f"template_id={contract.template_id}")
    print(f"template_version={contract.version}")
    print(f"processing_profile={result.processing_profile}")
    print(f"assigned_fields={len(result.template_assignments)}")
    print(f"unresolved_fields={len(result.unresolved_template_cells)}")
    print(f"validation_errors={sum(item.severity == 'error' for item in result.validation_issues)}")
    print(f"model_calls={len(result.model_usage)}")
    print(f"model_input_tokens={sum(item.input_tokens for item in result.model_usage)}")
    print(f"model_output_tokens={sum(item.output_tokens for item in result.model_usage)}")
    print(
        f"estimated_cost_usd={estimated_cost:.4f}"
        if estimated_cost is not None
        else "estimated_cost_usd=unavailable"
    )
    print(f"job_path={storage.job_dir(job_id)}")
    for assignment in result.template_assignments:
        print(
            f"assignment[{assignment.sheet}!{assignment.cell}]="
            f"{assignment.value} ({assignment.locator})"
        )
    for issue in result.validation_issues:
        print(f"validation[{issue.severity}:{issue.code}]={issue.message}")
    return 0 if result.status == JobStatus.NEEDS_INPUT else 2


if __name__ == "__main__":
    raise SystemExit(main())
