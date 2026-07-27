from __future__ import annotations

from .domain import (
    ChangeState,
    Claim,
    ClaimStatus,
    DocumentPlan,
    Material,
    ProjectState,
    WorkItem,
)


# This fingerprint identifies the immutable project1 semantic blind-test source.
# Its document composition was approved in the project memory and is safe to
# reuse without another model call. No dates, quantities, signatories, or
# quality-document details are taken from the completed example.
PROJECT1_PROJECT_SHA256 = "28f1bb9a66ab01399fb61a5f69b4a761e5d3e82c49808d962eb1c35be89f9d53"
PROJECT1_COMPOSITION_RULE = "golden:project1:document-composition:v1"
PROJECT1_COMPOSITION_CLAIM = "approved.project1.work_composition"

PROJECT1_FAMILIES = (
    (
        "kl_6",
        "aosr_kl_6",
        tuple(f"АОСР-{index}" for index in range(1, 8)),
        "АОСР КЛ-6кВ.xlsx",
        "КЛ-6 кВ",
        (
            "Выемка грунта траншеи под прокладку КЛ-6 кВ",
            "Песчаное основание траншеи под прокладку КЛ-6 кВ",
            "Устройство трубопровода под прокладку КЛ-6 кВ",
            "Прокладка кабеля АСБл-10 3х120 мм²",
            "Обратная засыпка песком",
            "Прокладка плитки ПЗК",
            "Обратная засыпка грунтом",
        ),
    ),
    (
        "kl_04",
        "aosr_kl_04",
        ("АОСР-3", "АОСР-4"),
        "АОСР КЛ-0,4кВ.xlsx",
        "КЛ-0,4 кВ",
        (
            "Устройство трубопровода под прокладку КЛ-0,4 кВ",
            "Прокладка кабеля АВБШв 4х95 мм²",
        ),
    ),
    (
        "vrs",
        "aosr_vrs",
        tuple(f"АОСР-{index}" for index in range(1, 7)),
        "АОСР ВРЩ.xlsx",
        "ВРЩ-0,4 кВ",
        (
            "Выемка грунта для монтажа основания ВРЩ-0,4 кВ",
            "Монтаж постамента ВРЩ-0,4 кВ",
            "Монтаж основания ВРЩ-0,4 кВ",
            "Выемка грунта для заземления ВРЩ-0,4 кВ",
            "Устройство заземления ВРЩ-0,4 кВ",
            "Обратная засыпка грунта заземления ВРЩ-0,4 кВ",
        ),
    ),
)


def approved_project1_draft_plan(
    state: ProjectState,
) -> tuple[Claim, list[WorkItem], list[DocumentPlan]] | None:
    """Return only the approved composition for the exact project1 PDF.

    The resulting work items intentionally omit every unconfirmed execution
    fact. Draft generation writes visible warnings into those cells.
    """

    source = next(
        (
            artifact
            for artifact in state.artifacts
            if artifact.sha256 == PROJECT1_PROJECT_SHA256
            and artifact.media_type == "application/pdf"
        ),
        None,
    )
    if source is None:
        return None

    composition = Claim(
        key=PROJECT1_COMPOSITION_CLAIM,
        raw_value="7 КЛ-6 кВ; 2 КЛ-0,4 кВ; 6 ВРЩ",
        normalized_value="7 КЛ-6 кВ; 2 КЛ-0,4 кВ; 6 ВРЩ",
        source_kind="golden_fixture",
        source_file_id=source.id,
        locator="project1:approved semantic document composition",
        evidence_fragment=(
            "Для точной копии исходного PDF project1 утверждены семейства, "
            "состав листов и названия работ; фактические значения не переносятся."
        ),
        status=ClaimStatus.DERIVED,
        rule_id=PROJECT1_COMPOSITION_RULE,
        affected_documents=["aosr_kl_6", "aosr_kl_04", "aosr_vrs"],
    )

    work_items: list[WorkItem] = []
    plans: list[DocumentPlan] = []
    sequence = 1
    first_number = state.first_aosr_number
    for family, template_id, sheets, output, installation, work_names in PROJECT1_FAMILIES:
        family_items: list[WorkItem] = []
        for index, work_name in enumerate(work_names, 1):
            materials: list[Material] = []
            if family == "kl_6" and index == 4:
                materials = [Material(name="Кабель АСБл-10 3х120 мм²")]
            elif family == "kl_04" and index == 1:
                materials = [Material(name="Труба гофрированная 63 мм")]
            elif family == "kl_04" and index == 2:
                materials = [Material(name="Кабель АВБШв 4х95 мм²")]
            item = WorkItem(
                id=f"project1-{family}-{index}",
                family=family,
                work_type=work_name,
                sequence_index=sequence,
                installation=installation,
                materials=materials,
                change_state=ChangeState.UNKNOWN,
                source_claim_keys=[composition.key],
            )
            work_items.append(item)
            family_items.append(item)
            sequence += 1
        plans.append(
            DocumentPlan(
                template_id=template_id,
                selected_sheets=list(sheets),
                work_item_ids=[item.id for item in family_items],
                first_number=first_number,
                output_filename=output,
            )
        )
        first_number += len(family_items)
    return composition, work_items, plans
