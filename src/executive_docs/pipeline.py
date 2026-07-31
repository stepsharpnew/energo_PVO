from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .agent import make_agent
from .approved_examples import approved_project1_draft_plan
from .config import Settings
from .domain import (
    Artifact,
    Claim,
    ClaimStatus,
    JobStatus,
    ProjectState,
    TemplateFillAnalysis,
    ValidationIssue,
)
from .excel import ExcelGenerator
from .knowledge import KnowledgeBase
from .packaging import build_result_zip, merge_pdfs, render_selected_sheets, revision_paths, write_report
from .profiles import ProfileStore
from .questions import is_delegated_value
from .repository import Repository
from .review import IndependentReviewer
from .selected_templates import (
    SelectedTemplateGenerator,
    TemplateCatalog,
    validate_selected_template_output,
)
from .storage import Storage
from .validation import validate_semantics, validate_workbook


class Pipeline:
    def __init__(self, settings: Settings, repository: Repository, storage: Storage):
        self.settings = settings
        self.repository = repository
        self.storage = storage
        self.knowledge = KnowledgeBase(settings.skill_dir)
        self.agent = make_agent(settings, self.knowledge, persist_usage=self.repository.save_progress)
        self.reviewer = IndependentReviewer(settings, self.knowledge, persist_usage=self.repository.save_progress)
        self.excel = ExcelGenerator(settings.root, settings.contracts_dir, settings.approved_templates_dir)
        self.template_catalog = TemplateCatalog(
            settings.root,
            settings.fill_contracts_dir,
            settings.approved_templates_dir,
        )
        self.selected_template_generator = SelectedTemplateGenerator(self.template_catalog)
        self.profiles = ProfileStore(settings.profiles_dir)

    def _set_failure(self, state: ProjectState, status: JobStatus, exc: Exception) -> None:
        state.status = status
        state.error = str(exc)
        state.summary = str(exc)
        self.repository.save_progress(state)

    @staticmethod
    def _selected_template_claims(
        contract,
        pdf_artifact: Artifact,
        analysis: TemplateFillAnalysis,
    ) -> list[Claim]:
        claims = [
            Claim(
                key=(
                    f"template.{contract.template_id}."
                    f"{item.sheet}.{item.cell}"
                ),
                raw_value=item.value,
                normalized_value=item.value,
                source_kind="project_pdf",
                source_file_id=item.source_file_id,
                locator=item.locator,
                evidence_fragment=item.evidence_fragment,
                status=ClaimStatus.OBSERVED,
                affected_documents=[contract.template_id],
            )
            for item in analysis.assignments
        ]
        for finding in analysis.unresolved:
            claim_status = (
                ClaimStatus.CONFLICT
                if finding.category in {"conflict", "ambiguous"}
                else ClaimStatus.REJECTED
            )
            for index, (value, locator, fragment) in enumerate(
                zip(
                    finding.source_values,
                    finding.source_locators,
                    finding.evidence_fragments,
                ),
                1,
            ):
                claims.append(
                    Claim(
                        key=(
                            f"template.{contract.template_id}."
                            f"{finding.sheet}.{finding.cell}."
                            f"unresolved.{index}"
                        ),
                        raw_value=value,
                        normalized_value=value,
                        source_kind="project_pdf",
                        source_file_id=pdf_artifact.id,
                        locator=locator,
                        evidence_fragment=fragment,
                        status=claim_status,
                        affected_documents=[contract.template_id],
                    )
                )
        return claims

    def _generate_draft_excel(self, state: ProjectState, root: Path) -> list[str]:
        if not state.document_plans:
            raise RuntimeError(
                "Не удалось определить состав Excel-листов. Нужен повторный анализ состава работ."
            )
        plan_issues = validate_semantics(
            state.work_items,
            state.claims,
            state.document_plans,
            first_aosr_number=state.first_aosr_number,
            branch_id=state.branch_id,
            artifact_categories={item.id: item.category for item in state.artifacts},
        )
        blocking_plan_codes = {
            "EMPTY_DOCUMENT_SET",
            "DUPLICATE_WORK",
            "INVALID_WORK_SEQUENCE",
            "WORK_COVERAGE",
            "DUPLICATE_NUMBER",
            "NUMBER_GAP",
            "INVALID_NUMBER_SEQUENCE",
            "DUPLICATE_OUTPUT",
            "DUPLICATE_ATTACHMENT",
            "INVALID_ATTACHMENT",
        }
        plan_errors = [issue for issue in plan_issues if issue.code in blocking_plan_codes]
        if plan_errors:
            details = "; ".join(issue.message for issue in plan_errors[:3])
            raise RuntimeError(f"План чернового Excel некорректен: {details}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        draft_dir = root / "output" / "drafts" / f"r{state.revision}-{stamp}" / "xlsx"
        draft_dir.mkdir(parents=True, exist_ok=False)
        draft_claims = [*state.claims, *state.answered_claims()]
        answer_map = {
            question.field_key: question.answer
            for question in state.questions
            if question.answer
        }
        draft_items = []
        for item in state.work_items:
            updates = {}
            if answer_map.get("actual.start"):
                updates["actual_start"] = answer_map["actual.start"]
            if answer_map.get("actual.end"):
                updates["actual_end"] = answer_map["actual.end"]
            if answer_map.get("changes.state") in {"YES", "NO"}:
                updates["change_state"] = answer_map["changes.state"]
            draft_items.append(item.model_copy(update=updates))
        files: list[str] = []
        for plan in state.document_plans:
            output, contract = self.excel.generate_draft(
                plan,
                draft_items,
                draft_claims,
                state.questions,
                draft_dir,
            )
            issues = validate_workbook(
                output,
                self.excel.template_path(contract),
                contract,
                plan,
                draft_claims,
            )
            errors = [issue for issue in issues if issue.severity == "error"]
            if errors:
                details = "; ".join(issue.message for issue in errors[:3])
                raise RuntimeError(f"Черновой Excel не прошёл техническую проверку: {details}")
            files.append(output.relative_to(root).as_posix())
        return files

    def _process_selected_template(self, state: ProjectState, root: Path) -> None:
        if not state.selected_template_id:
            raise ValueError("В задании не выбран шаблон")
        failure_status = JobStatus.FAILED_ANALYSIS
        if not all(
            (
                state.selected_template_version,
                state.selected_template_sha256,
                state.selected_template_contract_sha256,
            )
        ):
            self._set_failure(
                state,
                JobStatus.FAILED_ANALYSIS,
                ValueError(
                    "В задании отсутствует закреплённая версия или SHA выбранного шаблона"
                ),
            )
            return
        try:
            contract = self.template_catalog.get(state.selected_template_id)
        except (KeyError, ValueError) as exc:
            self._set_failure(
                state,
                JobStatus.FAILED_ANALYSIS,
                ValueError(f"Выбранный шаблон недоступен в серверном каталоге: {exc}"),
            )
            return
        contract_sha256 = contract.contract_sha256
        pinned_version = state.selected_template_version
        if (
            state.selected_template_sha256 != contract.candidate_sha256
        ) or (
            state.selected_template_contract_sha256 != contract_sha256
        ) or pinned_version != contract.version:
            self._set_failure(
                state,
                JobStatus.FAILED_ANALYSIS,
                ValueError("Версия выбранного шаблона изменилась после создания задания"),
            )
            return
        state.selected_template_name = contract.display_name
        state.selected_template_status = contract.status
        state.selected_template_version = contract.version
        state.selected_template_sha256 = contract.candidate_sha256
        state.selected_template_contract_sha256 = contract_sha256
        state.template_versions[contract.template_id] = (
            f"{contract.version}@{contract.candidate_sha256}@{contract_sha256}"
        )
        state.skill_version = self.knowledge.skill_version()
        state.knowledge_version = self.knowledge.version()
        state.model = (
            f"analysis={self.settings.policy(state.processing_profile).analysis_model}"
            if self.settings.agent_mode == "openai"
            else "heuristic"
        )
        try:
            def persist() -> bool:
                return self.repository.save_progress(state)

            if not state.template_analysis_complete:
                state.status = JobStatus.ANALYZING
                state.error = None
                state.draft_report_ready = False
                state.draft_excel_files = []
                state.validation_issues = []
                state.summary = f"Переносим подтверждённые сведения в «{contract.display_name}»."
                if not persist():
                    return
                analysis = self.agent.fill_template(state, root, contract)
                latest = self.repository.get(state.job_id)
                if latest is None or latest.status == JobStatus.CANCELLED:
                    return
                rejection = getattr(self.agent, "_template_fill_rejection", lambda *_: None)(
                    state,
                    contract,
                    analysis,
                    root,
                )
                if rejection:
                    raise ValueError(rejection)
                state.template_assignments = analysis.assignments
                state.template_unresolved_findings = analysis.unresolved
                state.claims = [
                    claim
                    for claim in state.claims
                    if not claim.key.startswith(f"template.{contract.template_id}.")
                ]
                state.claims.extend(
                    self._selected_template_claims(
                        contract,
                        state.artifacts[0],
                        analysis,
                    )
                )
                state.template_analysis_complete = True
                state.summary = analysis.summary
                if not persist():
                    return

            failure_status = JobStatus.FAILED_GENERATION
            state.status = JobStatus.GENERATING
            state.summary = f"Заполняем один выбранный файл: «{contract.display_name}»."
            if not persist():
                return
            generation_payload = {
                "template_id": contract.template_id,
                "candidate_sha256": contract.candidate_sha256,
                "contract_sha256": contract_sha256,
                "assignments": [
                    item.model_dump(mode="json")
                    for item in state.template_assignments
                ],
                "unresolved": [
                    item.model_dump(mode="json")
                    for item in state.template_unresolved_findings
                ],
            }
            analysis_hash = hashlib.sha256(
                json.dumps(
                    generation_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            revision_root = root / "output" / "selected" / f"r{state.revision}"
            generation_record = revision_root / "generation.json"
            expected_name = f"ЧЕРНОВИК - {contract.output_filename}"
            output = revision_root / "xlsx" / expected_name
            source_snapshot = revision_root / "source" / "template.xlsx"
            recorded_hash = None
            if generation_record.is_file():
                recorded_hash = json.loads(
                    generation_record.read_text(encoding="utf-8")
                ).get("analysis_sha256")
            if (
                output.is_file()
                and source_snapshot.is_file()
                and recorded_hash == analysis_hash
            ):
                unresolved = self.selected_template_generator.unresolved_cells(
                    contract,
                    state.template_assignments,
                    state.template_unresolved_findings,
                )
            else:
                if revision_root.exists():
                    raise RuntimeError(
                        f"Ревизия r{state.revision} уже закреплена другим выбранным шаблоном или планом"
                    )
                staging = root / "state" / f"selected-template-r{state.revision}"
                if staging.exists():
                    shutil.rmtree(staging)
                generated, unresolved = self.selected_template_generator.generate(
                    contract,
                    state.template_assignments,
                    staging / "xlsx",
                    findings=state.template_unresolved_findings,
                    source_snapshot=staging / "source" / "template.xlsx",
                )
                (staging / "generation.json").write_text(
                    json.dumps(
                        {
                            "analysis_sha256": analysis_hash,
                            **generation_payload,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                revision_root.parent.mkdir(parents=True, exist_ok=True)
                staging.rename(revision_root)
                output = revision_root / "xlsx" / generated.name
                source_snapshot = revision_root / "source" / "template.xlsx"

            state.unresolved_template_cells = unresolved
            failure_status = JobStatus.FAILED_VALIDATION
            state.status = JobStatus.VALIDATING
            state.summary = "Проверяем структуру книги и предупреждающую заливку."
            if not persist():
                return
            state.validation_issues = validate_selected_template_output(
                output,
                source_snapshot,
                contract,
                state.template_assignments,
                unresolved,
            )
            errors = [
                issue
                for issue in state.validation_issues
                if issue.severity == "error"
            ]
            state.draft_excel_files = [output.relative_to(root).as_posix()]
            state.draft_excel_error = None
            state.draft_report_ready = True
            state.draft_excel_requested = False
            if errors:
                state.status = JobStatus.FAILED_VALIDATION
                state.summary = (
                    f"Черновик создан, но техническая проверка нашла ошибок: {len(errors)}."
                )
            else:
                state.status = JobStatus.NEEDS_INPUT
                state.summary = (
                    f"Сформирован один черновой Excel-файл. Перенесено полей: "
                    f"{len(state.template_assignments)}; пустых выделенных полей: {len(unresolved)}. "
                    f"Статус шаблона: {contract.status}."
                )
            if not persist():
                return
            write_report(state, root)
        except Exception as exc:
            self._set_failure(state, failure_status, exc)

    def process(self, job_id: str) -> None:
        state = self.repository.get(job_id)
        if not state or state.status in {JobStatus.CANCELLED, JobStatus.APPROVED_FINAL}:
            return
        root = self.storage.job_dir(job_id)
        if state.flow_version == "selected-template-v2" or state.selected_template_id:
            self._process_selected_template(state, root)
            return
        if state.draft_excel_requested and not state.document_plans:
            approved_plan = approved_project1_draft_plan(state)
            if approved_plan is not None:
                composition, work_items, document_plans = approved_plan
                state.claims = [
                    claim
                    for claim in state.claims
                    if claim.key != composition.key
                ]
                state.claims.append(composition)
                state.work_items = work_items
                state.document_plans = document_plans
                state.error = None
                self.repository.save(state)
        if state.draft_excel_requested and state.document_plans:
            state.status = JobStatus.GENERATING
            state.draft_report_ready = False
            state.draft_excel_error = None
            state.summary = "Заполняем Excel-файлы и наносим предупреждения."
            self.repository.save(state)
            try:
                state.draft_excel_files = self._generate_draft_excel(state, root)
                state.draft_excel_error = None
                state.summary = (
                    f"Сформировано Excel-файлов: {len(state.draft_excel_files)}. "
                    f"Предупреждений: {len([q for q in state.questions if not q.answer])}. "
                    "Пропуски отмечены непосредственно в книгах."
                )
            except Exception as exc:
                state.draft_excel_files = []
                state.draft_excel_error = str(exc)
                state.summary = f"Не удалось сформировать черновой Excel: {exc}"
            finally:
                state.status = JobStatus.NEEDS_INPUT
                state.draft_excel_requested = False
                state.draft_report_ready = True
                self.repository.save(state)
                write_report(state, root)
            return
        try:
            state.status = JobStatus.ANALYZING
            state.draft_report_ready = False
            if state.draft_excel_requested:
                state.draft_excel_error = None
            state.error = None
            policy = self.settings.policy(state.processing_profile)
            state.model = (
                f"analysis={policy.analysis_model}; review={policy.review_model}"
                if self.settings.agent_mode == "openai"
                else "heuristic"
            )
            state.skill_version = self.knowledge.skill_version()
            state.knowledge_version = self.knowledge.version()
            state.claims = [
                claim
                for claim in state.claims
                if claim.source_kind != "approved_profile"
                and not (claim.source_kind == "human_answer" and is_delegated_value(claim.normalized_value))
            ]
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
                if state.draft_excel_requested:
                    try:
                        state.draft_excel_files = self._generate_draft_excel(state, root)
                        state.draft_excel_error = None
                        state.summary = (
                            f"Сформировано Excel-файлов: {len(state.draft_excel_files)}. "
                            f"Предупреждений: {len(state.questions)}. "
                            "Пропуски отмечены непосредственно в книгах."
                        )
                    except Exception as exc:
                        state.draft_excel_files = []
                        state.draft_excel_error = str(exc)
                        state.summary = f"Не удалось сформировать черновой Excel: {exc}"
                    finally:
                        state.draft_excel_requested = False
                        state.draft_report_ready = True
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
        self.idle_events: dict[str, asyncio.Event] = {}
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

    async def cancel_and_wait(self, job_id: str) -> None:
        """Suppress reruns and wait until an active worker releases the job."""

        self.rerun.discard(job_id)
        if job_id not in self.active:
            return
        event = self.idle_events.setdefault(job_id, asyncio.Event())
        await event.wait()

    async def _run(self) -> None:
        while True:
            job_id = await self.queue.get()
            if job_id is None:
                self.queue.task_done()
                return
            self.queued.discard(job_id)
            self.active.add(job_id)
            event = self.idle_events.setdefault(job_id, asyncio.Event())
            event.clear()
            try:
                await asyncio.to_thread(self.pipeline.process, job_id)
            finally:
                self.active.discard(job_id)
                if job_id in self.rerun and not self.stopping:
                    self.rerun.discard(job_id)
                    self.queued.add(job_id)
                    await self.queue.put(job_id)
                event.set()
                self.queue.task_done()
