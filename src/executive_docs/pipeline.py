from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from pathlib import Path

from .agent import make_agent
from .config import Settings
from .domain import JobStatus, ProjectState, ValidationIssue
from .excel import ExcelGenerator
from .knowledge import KnowledgeBase
from .packaging import build_result_zip, merge_pdfs, render_selected_sheets, revision_paths, write_report
from .profiles import ProfileStore
from .repository import Repository
from .review import IndependentReviewer
from .storage import Storage
from .validation import validate_semantics, validate_workbook


class Pipeline:
    def __init__(self, settings: Settings, repository: Repository, storage: Storage):
        self.settings = settings
        self.repository = repository
        self.storage = storage
        self.knowledge = KnowledgeBase(settings.skill_dir)
        self.agent = make_agent(settings, self.knowledge)
        self.reviewer = IndependentReviewer(settings, self.knowledge)
        self.excel = ExcelGenerator(settings.root, settings.contracts_dir, settings.approved_templates_dir)
        self.profiles = ProfileStore(settings.profiles_dir)

    def _set_failure(self, state: ProjectState, status: JobStatus, exc: Exception) -> None:
        latest = self.repository.get(state.job_id)
        if latest is None or latest.status == JobStatus.CANCELLED:
            return
        state.status = status
        state.error = str(exc)
        state.summary = str(exc)
        self.repository.save(state)

    def process(self, job_id: str) -> None:
        state = self.repository.get(job_id)
        if not state or state.status in {JobStatus.CANCELLED, JobStatus.APPROVED_FINAL}:
            return
        root = self.storage.job_dir(job_id)
        try:
            state.status = JobStatus.ANALYZING
            state.error = None
            state.model = self.settings.openai_model if self.settings.agent_mode == "openai" else "heuristic"
            state.skill_version = self.knowledge.skill_version()
            state.knowledge_version = self.knowledge.version()
            state.claims = [claim for claim in state.claims if claim.source_kind != "approved_profile"]
            state.claims.extend(self.profiles.claims(state.branch_id))
            self.repository.save(state)
            analysis = self.agent.analyze(state, root)
            latest = self.repository.get(job_id)
            if latest is None or latest.status == JobStatus.CANCELLED:
                return
            state.claims = state.claims + analysis.claims + state.answered_claims()
            unique_claims = {}
            for claim in state.claims:
                unique_claims[(claim.key, claim.locator)] = claim
            state.claims = list(unique_claims.values())
            state.work_items = analysis.work_items
            state.document_plans = analysis.document_plans
            state.questions = analysis.questions
            state.summary = analysis.summary
            if analysis.status == "NEEDS_INPUT":
                state.status = JobStatus.NEEDS_INPUT
                self.repository.save(state)
                write_report(state, root)
                return
        except Exception as exc:
            self._set_failure(state, JobStatus.FAILED_ANALYSIS, exc)
            return
        try:
            state.status = JobStatus.GENERATING
            self.repository.save(state)
            revision_root, preview_dir, _ = revision_paths(root, state.revision)
            expected_outputs = {plan.output_filename for plan in state.document_plans}
            if len(expected_outputs) != len(state.document_plans):
                raise RuntimeError("Планы содержат повторяющиеся имена выходных файлов")
            generation_payload = {
                "claims": [item.model_dump(mode="json") for item in state.claims],
                "work_items": [item.model_dump(mode="json") for item in state.work_items],
                "document_plans": [item.model_dump(mode="json") for item in state.document_plans],
            }
            analysis_hash = hashlib.sha256(
                json.dumps(generation_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            existing_outputs = set()
            if (revision_root / "xlsx").exists():
                existing_outputs = {path.name for path in (revision_root / "xlsx").glob("*.xlsx")}
            preview_dir.mkdir(parents=True, exist_ok=True)
            generated: list[tuple[Path, object, object, Path]] = []
            generation_record = revision_root / "generation.json"
            recorded_hash = None
            if generation_record.exists():
                recorded_hash = json.loads(generation_record.read_text(encoding="utf-8")).get("analysis_sha256")
            if existing_outputs == expected_outputs and expected_outputs and recorded_hash == analysis_hash:
                for plan in state.document_plans:
                    contract = self.excel.contract(plan.template_id)
                    source = self.excel.template_path(contract)
                    state.template_versions[contract.template_id] = contract.version
                    generated.append((revision_root / "xlsx" / plan.output_filename, contract, plan, source))
            else:
                if revision_root.exists():
                    raise RuntimeError(f"Ревизия r{state.revision} уже закреплена другим планом или содержит неполный набор")
                staging = root / "state" / f"generation-r{state.revision}"
                if staging.exists():
                    shutil.rmtree(staging)
                xlsx_dir = staging / "xlsx"
                xlsx_dir.mkdir(parents=True, exist_ok=True)
                for plan in state.document_plans:
                    output, contract = self.excel.generate(plan, state.work_items, state.claims, xlsx_dir)
                    source = self.excel.template_path(contract)
                    state.template_versions[contract.template_id] = contract.version
                    generated.append((output, contract, plan, source))
                attachment_dir = staging / "attachments"
                attachment_dir.mkdir(parents=True, exist_ok=True)
                attachment_ids = {
                    artifact_id
                    for plan in state.document_plans
                    for artifact_id in plan.attachments
                }
                attachment_ids.update(
                    material.source_file_id
                    for work_item in state.work_items
                    for material in work_item.materials
                    if material.source_file_id
                )
                for artifact in state.artifacts:
                    if artifact.id in attachment_ids:
                        safe_name = self.storage.safe_filename(artifact.original_name)
                        destination = attachment_dir / safe_name
                        if destination.exists():
                            destination = attachment_dir / f"{artifact.id}-{safe_name}"
                        shutil.copy2(root / "input" / artifact.stored_name, destination)
                (staging / "generation.json").write_text(
                    json.dumps(
                        {"analysis_sha256": analysis_hash, **generation_payload},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                staging.rename(revision_root)
                generated = [
                    (revision_root / "xlsx" / output.name, contract, plan, source)
                    for output, contract, plan, source in generated
                ]
            latest = self.repository.get(job_id)
            if latest is None or latest.status == JobStatus.CANCELLED:
                return
        except Exception as exc:
            self._set_failure(state, JobStatus.FAILED_GENERATION, exc)
            return
        try:
            state.status = JobStatus.VALIDATING
            state.validation_issues = validate_semantics(
                state.work_items,
                state.claims,
                state.document_plans,
                first_aosr_number=state.first_aosr_number,
                branch_id=state.branch_id,
                artifact_categories={item.id: item.category for item in state.artifacts},
            )
            all_previews: list[Path] = []
            for output, contract, plan, source in generated:
                state.validation_issues.extend(validate_workbook(output, source, contract, plan, state.claims))
                previews, render_issues = render_selected_sheets(
                    output,
                    plan.selected_sheets,
                    preview_dir,
                    self.settings.soffice_path,
                )
                all_previews.extend(previews)
                state.validation_issues.extend(render_issues)
            scheme_pdfs = sorted((revision_root / "attachments").glob("*.pdf"))
            if all_previews:
                merge_pdfs([*all_previews, *scheme_pdfs], preview_dir / "final-package.pdf")
            deterministic_errors = [issue for issue in state.validation_issues if issue.severity == "error"]
            if not deterministic_errors:
                state.validation_issues.extend(self.reviewer.review(state, all_previews))
            else:
                state.validation_issues.append(
                    ValidationIssue(
                        code="MODEL_REVIEW_SKIPPED",
                        severity="info",
                        message="Модельная проверка не запускалась из-за детерминированных блокирующих ошибок",
                    )
                )
            errors = [issue for issue in state.validation_issues if issue.severity == "error"]
            latest = self.repository.get(job_id)
            if latest is None or latest.status == JobStatus.CANCELLED:
                return
            state.status = JobStatus.FAILED_VALIDATION if errors else JobStatus.READY_FOR_REVIEW
            state.summary = (
                f"Найдено критических ошибок: {len(errors)}"
                if errors
                else "Комплект сформирован и готов к проверке специалистом"
            )
            self.repository.save(state)
            write_report(state, root)
            if not errors:
                result = build_result_zip(state, root)
                state.result_zip = str(result.relative_to(root))
                self.repository.save(state)
        except Exception as exc:
            self._set_failure(state, JobStatus.FAILED_VALIDATION, exc)


class JobQueue:
    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.worker: asyncio.Task | None = None
        self.queued: set[str] = set()
        self.active: set[str] = set()
        self.rerun: set[str] = set()
        self.stopping = False

    async def start(self) -> None:
        if self.worker is None:
            self.stopping = False
            self.worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self.worker:
            self.stopping = True
            await self.queue.put(None)
            await self.worker
            self.worker = None

    async def enqueue(self, job_id: str) -> None:
        if self.stopping:
            return
        if job_id in self.active:
            self.rerun.add(job_id)
            return
        if job_id in self.queued:
            return
        self.queued.add(job_id)
        await self.queue.put(job_id)

    async def _run(self) -> None:
        while True:
            job_id = await self.queue.get()
            if job_id is None:
                self.queue.task_done()
                return
            self.queued.discard(job_id)
            self.active.add(job_id)
            try:
                await asyncio.to_thread(self.pipeline.process, job_id)
            finally:
                self.active.discard(job_id)
                if job_id in self.rerun and not self.stopping:
                    self.rerun.discard(job_id)
                    self.queued.add(job_id)
                    await self.queue.put(job_id)
                self.queue.task_done()
