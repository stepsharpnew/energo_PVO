from executive_docs.domain import Claim, ClaimStatus, DocumentPlan, Material, WorkItem
from executive_docs.validation import validate_semantics


def confirmed(key: str, value: str) -> Claim:
    return Claim(
        key=key,
        raw_value=value,
        normalized_value=value,
        source_kind="human_answer",
        locator=f"question:{key}",
        evidence_fragment="confirmed",
        status=ClaimStatus.HUMAN_CONFIRMED,
    )


def test_valid_semantic_plan_has_no_errors() -> None:
    claims = [confirmed("actual.start", "01.06.2026"), confirmed("actual.end", "02.06.2026")]
    item = WorkItem(
        id="w1",
        family="kl_04",
        work_type="Работа",
        sequence_index=1,
        actual_start="01.06.2026",
        actual_end="02.06.2026",
        materials=[Material(name="Кабель", quality_document="Сертификат №42")],
        change_state="NO",
        source_claim_keys=["actual.start", "actual.end"],
    )
    plan = DocumentPlan(template_id="aosr_kl_04", selected_sheets=["АОСР-3"], work_item_ids=["w1"], first_number=5, output_filename="АОСР КЛ-0,4кВ.xlsx")
    assert validate_semantics([item], claims, [plan]) == []


def test_unknown_change_and_bad_dates_block_release() -> None:
    claims = [confirmed("actual.start", "02.06.2026"), confirmed("actual.end", "01.06.2026")]
    item = WorkItem(
        id="w1",
        family="vrs",
        work_type="Работа",
        sequence_index=1,
        actual_start="02.06.2026",
        actual_end="01.06.2026",
        materials=[Material(name="ВРЩ", quality_document="б/н")],
        change_state="UNKNOWN",
        source_claim_keys=["actual.start", "actual.end"],
    )
    plan = DocumentPlan(template_id="aosr_vrs", selected_sheets=["АОСР-1"], work_item_ids=["w1"], first_number=1, output_filename="АОСР ВРЩ.xlsx")
    codes = {issue.code for issue in validate_semantics([item], claims, [plan])}
    assert {"INVALID_DATE_ORDER", "UNKNOWN_CHANGE_STATE", "MISSING_QUALITY_DOC"}.issubset(codes)
