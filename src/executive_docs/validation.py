from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

from .domain import Claim, DocumentPlan, ValidationIssue, WorkItem
from .excel import TemplateContract, workbook_snapshot


REQUIRED_DOCUMENT_CLAIMS = {
    "project.name",
    "project.address",
    "project.code",
    "project.installation",
    "contractor.name",
    "contractor.registration",
    "contractor.address",
    "contractor.construction_control.position",
    "contractor.construction_control.name",
    "contractor.construction_control.authority",
    "contractor.work_supervisor.position",
    "contractor.work_supervisor.name",
    "contractor.work_supervisor.authority",
    "customer.name",
    "customer.registration",
    "customer.address",
    "customer.construction_control.position",
    "customer.construction_control.name",
    "customer.construction_control.authority",
    "customer.site_representative.position",
    "customer.site_representative.name",
    "customer.site_representative.authority",
    "designer.name",
    "designer.registration",
    "designer.address",
    "designer.issue_city",
}


def validate_workbook(
    output: Path,
    source: Path,
    contract: TemplateContract,
    plan: DocumentPlan,
    claims: list[Claim] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        with zipfile.ZipFile(output) as archive:
            bad = archive.testzip()
            if bad:
                issues.append(ValidationIssue(code="OOXML_CORRUPT", severity="error", message=f"Повреждена часть {bad}", artifact=output.name))
    except Exception as exc:
        return [ValidationIssue(code="OOXML_OPEN", severity="error", message=str(exc), artifact=output.name)]
    baseline = workbook_snapshot(source)
    current = workbook_snapshot(output)
    if not contract.approved:
        issues.append(
            ValidationIssue(
                code="TEMPLATE_NOT_APPROVED",
                severity="error",
                message="Шаблон не утверждён специалистом после очистки",
                artifact=output.name,
            )
        )
    if [item["name"] for item in baseline["sheets"]] != [item["name"] for item in current["sheets"]]:
        issues.append(ValidationIssue(code="SHEET_STRUCTURE", severity="error", message="Изменён состав или порядок листов", artifact=output.name))
    if current["external_links"] > baseline["external_links"]:
        issues.append(ValidationIssue(code="NEW_EXTERNAL_LINK", severity="error", message="Появились новые внешние ссылки", artifact=output.name))
    if current["external_links"]:
        issues.append(ValidationIssue(code="EXTERNAL_LINK", severity="error", message=f"В книге остались внешние ссылки: {current['external_links']}", artifact=output.name))
    writable = contract.writable_cells()
    for location in sorted(set(baseline["formulas"]) | set(current["formulas"])):
        if location not in writable and baseline["formulas"].get(location) != current["formulas"].get(location):
            issues.append(ValidationIssue(code="FORMULA_CHANGED", severity="error", message=f"Изменена формула вне whitelist: {location}", artifact=output.name, locator=location))
    if baseline["defined_names"] != current["defined_names"]:
        issues.append(ValidationIssue(code="DEFINED_NAMES_CHANGED", severity="error", message="Изменены именованные диапазоны", artifact=output.name))
    for error in current["defined_name_errors"]:
        issues.append(ValidationIssue(code="DEFINED_NAME_ERROR", severity="error", message=error, artifact=output.name))
    selected = set(plan.selected_sheets)
    baseline_sheets = {sheet["name"]: sheet for sheet in baseline["sheets"]}
    for sheet in current["sheets"]:
        if sheet["name"] in contract.candidate_sheets:
            expected = "visible" if sheet["name"] in selected else "hidden"
            if sheet["state"] != expected:
                issues.append(ValidationIssue(code="SHEET_VISIBILITY", severity="error", message=f"Неверная видимость {sheet['name']}", artifact=output.name))
        base_sheet = baseline_sheets.get(sheet["name"])
        if base_sheet:
            for key, code, message in (
                ("merged", "MERGES_CHANGED", "Изменены объединённые ячейки"),
                ("styles", "STYLES_CHANGED", "Изменены стили ячеек"),
                ("print_area", "PRINT_AREA_CHANGED", "Изменена печатная область"),
                ("page_orientation", "PAGE_SETUP_CHANGED", "Изменена ориентация страницы"),
                ("paper_size", "PAGE_SETUP_CHANGED", "Изменён формат бумаги"),
            ):
                if base_sheet[key] != sheet[key]:
                    issues.append(ValidationIssue(code=code, severity="error", message=f"{message}: {sheet['name']}", artifact=output.name, locator=sheet["name"]))
        for error in sheet["errors"]:
            issues.append(ValidationIssue(code="FORMULA_ERROR", severity="error", message=error, artifact=output.name))
    with zipfile.ZipFile(output) as archive:
        raw = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist()
            if name.endswith((".xml", ".rels"))
        )
    accepted_values = {claim.normalized_value for claim in (claims or []) if claim.status.value in {"observed", "derived", "human_confirmed"}}
    for token in contract.forbidden_tokens:
        if token and token in raw and not any(token in value for value in accepted_values):
            issues.append(ValidationIssue(code="STALE_TOKEN", severity="error", message=f"Найдены остаточные данные: {token}", artifact=output.name))
    return issues


def validate_semantics(
    work_items: list[WorkItem],
    claims: list[Claim],
    plans: list[DocumentPlan],
    *,
    first_aosr_number: int | None = None,
    branch_id: str | None = None,
    artifact_categories: dict[str, str] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not work_items or not plans:
        issues.append(ValidationIssue(code="EMPTY_DOCUMENT_SET", severity="error", message="Не определён ни один поддерживаемый АОСР"))
    if len({item.id for item in work_items}) != len(work_items):
        issues.append(ValidationIssue(code="DUPLICATE_WORK", severity="error", message="Повторяющиеся идентификаторы работ"))
    sequence = [item.sequence_index for item in work_items]
    if sequence and sorted(sequence) != list(range(1, len(sequence) + 1)):
        issues.append(ValidationIssue(code="INVALID_WORK_SEQUENCE", severity="error", message="Нарушена последовательность работ"))
    planned = [work_id for plan in plans for work_id in plan.work_item_ids]
    if sorted(planned) != sorted(item.id for item in work_items):
        issues.append(ValidationIssue(code="WORK_COVERAGE", severity="error", message="Не каждая работа сопоставлена ровно одному акту"))
    numbers = [number for plan in plans for number in range(plan.first_number, plan.first_number + len(plan.selected_sheets))]
    if len(numbers) != len(set(numbers)):
        issues.append(ValidationIssue(code="DUPLICATE_NUMBER", severity="error", message="Дублируются номера АОСР"))
    if numbers and sorted(numbers) != list(range(min(numbers), max(numbers) + 1)):
        issues.append(ValidationIssue(code="NUMBER_GAP", severity="error", message="В последовательности АОСР есть пропуски"))
    if first_aosr_number is not None and numbers != list(range(first_aosr_number, first_aosr_number + len(numbers))):
        issues.append(ValidationIssue(code="INVALID_NUMBER_SEQUENCE", severity="error", message="Нумерация не начинается с заданного номера или нарушен порядок"))
    output_names = [plan.output_filename for plan in plans]
    if len(output_names) != len(set(output_names)):
        issues.append(ValidationIssue(code="DUPLICATE_OUTPUT", severity="error", message="Несколько планов записываются в один файл"))
    if artifact_categories is not None:
        for plan in plans:
            if len(plan.attachments) != len(set(plan.attachments)):
                issues.append(ValidationIssue(code="DUPLICATE_ATTACHMENT", severity="error", message=f"Повторяются приложения: {plan.output_filename}"))
            for artifact_id in plan.attachments:
                if artifact_categories.get(artifact_id) not in {"execution_scheme", "passport", "certificate", "attestation"}:
                    issues.append(ValidationIssue(code="INVALID_ATTACHMENT", severity="error", message=f"Недопустимое приложение {artifact_id}: {plan.output_filename}"))
    admissible: set[str] = set()
    for claim in claims:
        if not claim.locator.strip() or not claim.evidence_fragment.strip():
            issues.append(ValidationIssue(code="INCOMPLETE_PROVENANCE", severity="error", message=f"Неполный источник значения {claim.key}", locator=claim.locator))
            continue
        if claim.status.value == "observed" and not claim.source_file_id:
            issues.append(ValidationIssue(code="MISSING_SOURCE_FILE", severity="error", message=f"Для найденного значения нет файла-источника: {claim.key}", locator=claim.locator))
            continue
        if claim.status.value == "derived" and not claim.rule_id:
            issues.append(ValidationIssue(code="MISSING_RULE_ID", severity="error", message=f"Для выведенного значения нет утверждённого правила: {claim.key}", locator=claim.locator))
            continue
        if claim.status.value in {"observed", "derived", "human_confirmed"}:
            admissible.add(claim.key)
    if branch_id and not ({"customer.profile_confirmation", "customer.profile.version"} & admissible):
        issues.append(ValidationIssue(code="UNAPPROVED_CUSTOMER_PROFILE", severity="error", message=f"Не подтверждён профиль заказчика: {branch_id}"))
    if branch_id:
        for key in sorted(REQUIRED_DOCUMENT_CLAIMS - admissible):
            issues.append(ValidationIssue(code="MISSING_DOCUMENT_CLAIM", severity="error", message=f"Нет подтверждённого обязательного поля: {key}"))

    def parse_date(value: str) -> datetime | None:
        for pattern in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
            try:
                return datetime.strptime(value.strip(), pattern)
            except ValueError:
                continue
        return None

    claim_values = {claim.key: claim.normalized_value for claim in claims if claim.key in admissible}
    for profile_id in ("organization", branch_id):
        if not profile_id or f"{profile_id}.profile.effective_from" not in claim_values:
            continue
        valid_from = parse_date(claim_values[f"{profile_id}.profile.effective_from"])
        valid_to = parse_date(claim_values.get(f"{profile_id}.profile.effective_to", ""))
        for item in work_items:
            actual_start = parse_date(item.actual_start or "")
            actual_end = parse_date(item.actual_end or "")
            if not valid_from or not valid_to or not actual_start or not actual_end or actual_start < valid_from or actual_end > valid_to:
                issues.append(ValidationIssue(code="PROFILE_OUTSIDE_VALIDITY", severity="error", message=f"Профиль {profile_id} не действует на даты работы: {item.work_type}"))

    for item in work_items:
        if not item.actual_start or not item.actual_end:
            issues.append(ValidationIssue(code="MISSING_DATES", severity="error", message=f"Нет фактических дат: {item.work_type}"))
        elif parse_date(item.actual_start) and parse_date(item.actual_end) and parse_date(item.actual_end) < parse_date(item.actual_start):
            issues.append(ValidationIssue(code="INVALID_DATE_ORDER", severity="error", message=f"Окончание раньше начала: {item.work_type}"))
        if not item.source_claim_keys or any(key not in admissible for key in item.source_claim_keys):
            issues.append(ValidationIssue(code="MISSING_PROVENANCE", severity="error", message=f"Нет источников критичных значений: {item.work_type}"))
        if item.actual_start and not any("start" in key.lower() or "начал" in key.lower() for key in item.source_claim_keys):
            issues.append(ValidationIssue(code="MISSING_START_PROVENANCE", severity="error", message=f"Нет источника даты начала: {item.work_type}"))
        if item.actual_end and not any("end" in key.lower() or "оконч" in key.lower() for key in item.source_claim_keys):
            issues.append(ValidationIssue(code="MISSING_END_PROVENANCE", severity="error", message=f"Нет источника даты окончания: {item.work_type}"))
        if item.volume is not None and not any("volume" in key or "quantity" in key for key in item.source_claim_keys):
            issues.append(ValidationIssue(code="MISSING_VOLUME_PROVENANCE", severity="error", message=f"Нет источника фактического объёма: {item.work_type}"))
        if item.change_state.value == "UNKNOWN":
            issues.append(ValidationIssue(code="UNKNOWN_CHANGE_STATE", severity="error", message=f"Не подтверждено наличие изменений: {item.work_type}"))
        if item.change_state.value == "YES" and not item.execution_scheme_id:
            issues.append(ValidationIssue(code="MISSING_SCHEME", severity="error", message=f"Для изменённой работы нет исполнительной схемы: {item.work_type}"))
        if item.execution_scheme_id and artifact_categories is not None and artifact_categories.get(item.execution_scheme_id) != "execution_scheme":
            issues.append(ValidationIssue(code="INVALID_SCHEME_REFERENCE", severity="error", message=f"Некорректная ссылка на исполнительную схему: {item.work_type}"))
        if item.change_state.value == "YES" and item.execution_scheme_id:
            containing_plan = next((plan for plan in plans if item.id in plan.work_item_ids), None)
            if containing_plan and item.execution_scheme_id not in containing_plan.attachments:
                issues.append(ValidationIssue(code="SCHEME_NOT_ATTACHED", severity="error", message=f"Исполнительная схема не включена в план: {item.work_type}"))
        for material in item.materials:
            quality = (material.quality_document or "").lower().strip()
            collapsed_quality = re.sub(r"\s+", " ", quality)
            if (
                not quality
                or re.search(r"\bб\s*/\s*[нд]\b", quality)
                or quality in {"нет", "отсутствует", "отсутствуют"}
                or re.search(r"№\s*(?:от|$|\))", collapsed_quality)
            ):
                issues.append(ValidationIssue(code="MISSING_QUALITY_DOC", severity="error", message=f"Нет паспорта/сертификата: {material.name}"))
            if material.source_file_id and artifact_categories is not None and artifact_categories.get(material.source_file_id) not in {"passport", "certificate", "attestation"}:
                issues.append(ValidationIssue(code="INVALID_MATERIAL_SOURCE", severity="error", message=f"Некорректный источник документа качества: {material.name}"))
    bad_claims = [claim for claim in claims if claim.status.value in {"conflict", "rejected"}]
    for claim in bad_claims:
        issues.append(ValidationIssue(code="CLAIM_CONFLICT", severity="error", message=f"Конфликт значения {claim.key}", locator=claim.locator))
    return issues
