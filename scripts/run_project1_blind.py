#!/usr/bin/env python3
"""Create and synchronously analyze the project1 blind-test job without its filled XLSX files."""

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
from executive_docs.storage import Storage  # noqa: E402
from executive_docs.usage import job_estimated_cost  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["heuristic", "openai"], default="heuristic")
    parser.add_argument("--branch", choices=["khimki", "solnechnogorsk"], default="khimki")
    parser.add_argument("--profile", choices=["economy", "balanced", "quality"], default="balanced")
    parser.add_argument("--first-number", type=int, default=1)
    parser.add_argument("--operator", default="Слепой тест project1")
    args = parser.parse_args()
    settings = replace(base_settings, agent_mode=args.mode)
    if args.mode == "openai" and not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is required for --mode openai")
    settings.ensure_directories()
    repository = Repository(settings.db_path)
    repository.initialize()
    storage = Storage(settings)
    job_id = str(uuid.uuid4())
    storage.initialize_job(job_id)
    sources = sorted((ROOT / "project1").glob("*.pdf"))
    if not sources:
        raise SystemExit("project1 PDF files were not found")
    artifacts = []
    for source in sources:
        with source.open("rb") as stream:
            artifacts.append(
                storage.save_upload(
                    job_id,
                    source.name,
                    stream,
                    mimetypes.guess_type(source.name)[0] or "application/pdf",
                )
            )
    state = ProjectState(
        job_id=job_id,
        branch_id=args.branch,
        first_aosr_number=args.first_number,
        operator_name=args.operator,
        processing_profile=args.profile,
        status=JobStatus.FILES_UPLOADED,
        artifacts=artifacts,
    )
    repository.create(state)
    Pipeline(settings, repository, storage).process(job_id)
    result = repository.get(job_id)
    if result is None:
        raise SystemExit("Job disappeared from the repository")
    print(f"job_id={job_id}")
    print(f"status={result.status}")
    print(f"uploaded_pdf_count={len(artifacts)}")
    print("filled_xlsx_count=0")
    print(f"processing_profile={result.processing_profile}")
    print(f"model_input_tokens={sum(item.input_tokens for item in result.model_usage)}")
    estimated_cost = job_estimated_cost(result)
    print(f"estimated_cost_usd={estimated_cost:.4f}" if estimated_cost is not None else "estimated_cost_usd=unavailable")
    print(f"job_path={storage.job_dir(job_id)}")
    for question in result.questions:
        print(f"question[{question.field_key}]={question.prompt}")
    return 0 if result.status == JobStatus.NEEDS_INPUT else 2


if __name__ == "__main__":
    raise SystemExit(main())
