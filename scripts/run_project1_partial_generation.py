#!/usr/bin/env python3
"""Generate diagnostic project1 workbooks from admissible claims while preserving NEEDS_INPUT.

This is deliberately not a production continuation. Missing critical facts remain
blank, all validation blockers are reported, and the source job is not modified.
The project1 golden workbooks are used only for the already-approved pilot sheet
composition and work names.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from executive_docs.config import settings  # noqa: E402
from executive_docs.domain import (  # noqa: E402
    ChangeState,
    Claim,
    ClaimStatus,
    DocumentPlan,
    Material,
    WorkItem,
)
from executive_docs.excel import ExcelGenerator, sha256  # noqa: E402
from executive_docs.packaging import render_selected_sheets  # noqa: E402
from executive_docs.repository import Repository  # noqa: E402
from executive_docs.validation import validate_semantics, validate_workbook  # noqa: E402


FAMILY_ORDER = ("kl_6", "kl_04", "vrs")
FAMILY_CONFIG = {
    "kl_6": {
        "template_id": "aosr_kl_6",
        "sheets": [f"АОСР-{index}" for index in range(1, 8)],
        "output": "АОСР КЛ-6кВ.xlsx",
        "installation": "КЛ-6 кВ",
        "works": [
            "Выемка грунта траншеи под прокладку КЛ-6 кВ",
            "Песчаное основание траншеи под прокладку КЛ-6 кВ",
            "Устройство трубопровода под прокладку КЛ-6 кВ",
            "Прокладка кабеля АСБл-10 3х120 мм²",
            "Обратная засыпка песком",
            "Прокладка плитки ПЗК",
            "Обратная засыпка грунтом",
        ],
    },
    "kl_04": {
        "template_id": "aosr_kl_04",
        "sheets": ["АОСР-3", "АОСР-4"],
        "output": "АОСР КЛ-0,4кВ.xlsx",
        "installation": "КЛ-0,4 кВ",
        "works": [
            "Устройство трубопровода под прокладку КЛ-0,4 кВ",
            "Прокладка кабеля АВБШв 4х95 мм²",
        ],
    },
    "vrs": {
        "template_id": "aosr_vrs",
        "sheets": [f"АОСР-{index}" for index in range(1, 7)],
        "output": "АОСР ВРЩ.xlsx",
        "installation": "ВРЩ-0,4 кВ",
        "works": [
            "Выемка грунта для монтажа основания ВРЩ-0,4 кВ",
            "Монтаж постамента ВРЩ-0,4 кВ",
            "Монтаж основания ВРЩ-0,4 кВ",
            "Выемка грунта для заземления ВРЩ-0,4 кВ",
            "Устройство заземления ВРЩ-0,4 кВ",
            "Обратная засыпка грунта заземления ВРЩ-0,4 кВ",
        ],
    },
}


def family_installation_claim(source: Claim, family: str, value: str) -> Claim:
    return Claim(
        key="project.installation",
        raw_value=source.raw_value,
        normalized_value=value,
        source_kind=source.source_kind,
        source_file_id=source.source_file_id,
        locator=source.locator,
        evidence_fragment=f"{source.evidence_fragment} Диагностическая нормализация для семейства {family}.",
        status=ClaimStatus.OBSERVED,
        affected_documents=[f"aosr_{family}"],
    )


def volume_claim(source: Claim, key: str, value: str, unit: str, note: str) -> Claim:
    return Claim(
        key=key,
        raw_value=source.raw_value,
        normalized_value=value,
        unit=unit,
        source_kind=source.source_kind,
        source_file_id=source.source_file_id,
        locator=source.locator,
        evidence_fragment=f"{source.evidence_fragment} {note}",
        status=ClaimStatus.OBSERVED,
        affected_documents=source.affected_documents,
    )


def build_diagnostic_data(state):
    original_installation = next(
        claim
        for claim in state.claims
        if claim.key == "project.installation" and claim.status == ClaimStatus.OBSERVED
    )
    kl04_source = next(claim for claim in state.claims if claim.key == "execution_scheme.kl04.cable")
    vrs_source = next(claim for claim in state.claims if claim.key == "execution_scheme.vrs.foundation")
    composition_claim = Claim(
        key="diagnostic.project1.work_composition",
        raw_value="2 КЛ-0,4 кВ; 7 КЛ-6 кВ; 6 ВРЩ",
        normalized_value="2 КЛ-0,4 кВ; 7 КЛ-6 кВ; 6 ВРЩ",
        source_kind="golden_fixture",
        locator="project1:approved semantic golden workbooks",
        evidence_fragment="Утверждённый для project1 состав выбранных листов и названий работ.",
        status=ClaimStatus.DERIVED,
        rule_id="golden:project1:document-composition:v1",
        affected_documents=["aosr_kl_04", "aosr_kl_6", "aosr_vrs"],
    )
    aliases = [
        volume_claim(
            kl04_source,
            "actual.kl04.pipe.volume",
            "3",
            "м",
            "Длина гофрированной трубы 63 мм.",
        ),
        volume_claim(
            kl04_source,
            "actual.kl04.cable.volume",
            "3",
            "м",
            "Длина кабеля АВБШв 4х95 мм² по исполнительной схеме.",
        ),
        volume_claim(
            vrs_source,
            "actual.vrs.foundation_excavation.volume",
            "0,768",
            "м³",
            "Объём выемки грунта для постамента ВРЩ.",
        ),
    ]
    family_installations = {
        family: family_installation_claim(original_installation, family, config["installation"])
        for family, config in FAMILY_CONFIG.items()
    }
    base_claims = [claim for claim in state.claims if claim.key != "project.installation"]
    report_claims = [*base_claims, composition_claim, *aliases, *family_installations.values()]

    items: list[WorkItem] = []
    plans: list[DocumentPlan] = []
    claims_by_family: dict[str, list[Claim]] = {}
    next_number = state.first_aosr_number
    sequence = 1
    for family in FAMILY_ORDER:
        config = FAMILY_CONFIG[family]
        family_items: list[WorkItem] = []
        for index, work_name in enumerate(config["works"], 1):
            source_keys = [composition_claim.key, "project.installation"]
            volume = None
            unit = None
            installation = config["installation"]
            materials: list[Material] = []
            if family == "kl_04" and index == 1:
                volume, unit = "3", "м"
                source_keys.append("actual.kl04.pipe.volume")
                materials = [Material(name="Труба гофрированная 63 мм")]
            elif family == "kl_04" and index == 2:
                volume, unit = "3", "м"
                source_keys.append("actual.kl04.cable.volume")
                materials = [Material(name="Кабель АВБШв 4х95 мм²")]
            elif family == "kl_6" and index == 4:
                materials = [Material(name="Кабель АСБл-10 3х120 мм²")]
            elif family == "vrs" and index == 1:
                volume, unit = "0,768", "м³"
                source_keys.append("actual.vrs.foundation_excavation.volume")
            item = WorkItem(
                id=f"diagnostic-{family}-{index}",
                family=family,
                work_type=work_name,
                sequence_index=sequence,
                volume=volume,
                unit=unit,
                installation=installation,
                materials=materials,
                change_state=ChangeState.UNKNOWN,
                source_claim_keys=source_keys,
            )
            family_items.append(item)
            items.append(item)
            sequence += 1
        plan = DocumentPlan(
            template_id=config["template_id"],
            selected_sheets=config["sheets"],
            work_item_ids=[item.id for item in family_items],
            first_number=next_number,
            attachments=[],
            output_filename=config["output"],
        )
        plans.append(plan)
        next_number += len(family_items)
        claims_by_family[family] = [
            *base_claims,
            composition_claim,
            *aliases,
            family_installations[family],
        ]
    return report_claims, items, plans, claims_by_family


def workbook_cells(path: Path, contract, plan: DocumentPlan) -> dict:
    workbook = openpyxl.load_workbook(path, data_only=False, keep_links=True)
    common = {}
    for key, targets in contract.common_fields.items():
        common[key] = {
            target: workbook[target.split("!", 1)[0]][target.split("!", 1)[1]].value
            for target in targets if isinstance(targets, list)
        } if isinstance(targets, list) else workbook[targets.split("!", 1)[0]][targets.split("!", 1)[1]].value
    sheets = {}
    for sheet in plan.selected_sheets:
        mapping = contract.sheets[sheet]
        sheets[sheet] = {
            field: workbook[sheet][cell].value
            for field, cell in mapping.items()
            if field != "suffix_value" and isinstance(cell, str)
        }
    visible = [sheet.title for sheet in workbook.worksheets if sheet.sheet_state == "visible"]
    workbook.close()
    return {"common": common, "sheets": sheets, "visible_sheets": visible}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    repository = Repository(settings.db_path)
    state = repository.get(args.job_id)
    if state is None:
        raise SystemExit(f"Job not found: {args.job_id}")

    claims, work_items, plans, claims_by_family = build_diagnostic_data(state)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = settings.runs_dir / state.job_id / "output" / f"diagnostic-partial-{stamp}"
    xlsx_dir = root / "xlsx"
    preview_dir = root / "preview"
    report_dir = root / "report"
    for directory in (xlsx_dir, preview_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)

    generator = ExcelGenerator(settings.root, settings.contracts_dir, settings.approved_templates_dir)
    validation_issues = validate_semantics(
        work_items,
        claims,
        plans,
        first_aosr_number=state.first_aosr_number,
        branch_id=state.branch_id,
        artifact_categories={artifact.id: artifact.category for artifact in state.artifacts},
    )
    outputs = []
    cell_audit = {}
    for family, plan in zip(FAMILY_ORDER, plans):
        output, contract = generator.generate(
            plan,
            [item for item in work_items if item.family == family],
            claims_by_family[family],
            xlsx_dir,
        )
        validation_issues.extend(
            validate_workbook(
                output,
                generator.template_path(contract),
                contract,
                plan,
                claims_by_family[family],
            )
        )
        previews, render_issues = render_selected_sheets(
            output,
            plan.selected_sheets,
            preview_dir,
            settings.soffice_path,
        )
        validation_issues.extend(render_issues)
        outputs.append(
            {
                "family": family,
                "workbook": output.name,
                "sha256": sha256(output),
                "preview_count": len(previews),
            }
        )
        cell_audit[output.name] = workbook_cells(output, contract, plan)

    report = {
        "diagnostic_only": True,
        "source_job_id": state.job_id,
        "source_job_status": state.status,
        "notice": (
            "Не для подписания. NEEDS_INPUT не снят; даты, документы качества, "
            "утверждённые профили, статус изменений и конфликтные значения пропущены."
        ),
        "diagnostic_family_order": list(FAMILY_ORDER),
        "claims": [claim.model_dump(mode="json") for claim in claims],
        "work_items": [item.model_dump(mode="json") for item in work_items],
        "document_plans": [plan.model_dump(mode="json") for plan in plans],
        "outputs": outputs,
        "cell_audit": cell_audit,
        "validation_issues": [issue.model_dump(mode="json") for issue in validation_issues],
        "issue_counts": dict(Counter(issue.code for issue in validation_issues)),
    }
    report_path = report_dir / "diagnostic-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    zip_path = root / "diagnostic-result.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, prefix in ((xlsx_dir, "xlsx"), (preview_dir, "preview"), (report_dir, "report")):
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{prefix}/{path.relative_to(folder).as_posix()}")

    print(f"diagnostic_root={root}")
    print(f"result_zip={zip_path}")
    print(f"xlsx_count={len(outputs)}")
    print(f"preview_count={sum(item['preview_count'] for item in outputs)}")
    print(f"validation_error_count={sum(issue.severity == 'error' for issue in validation_issues)}")
    print(f"issue_counts={json.dumps(report['issue_counts'], ensure_ascii=False, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
