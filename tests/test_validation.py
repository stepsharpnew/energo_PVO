from pathlib import Path

import openpyxl

from executive_docs.domain import Claim, ClaimStatus, DocumentPlan, Material, WorkItem
from executive_docs.excel import TemplateContract
from executive_docs.validation import REQUIRED_DOCUMENT_CLAIMS, validate_semantics, validate_workbook


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


def test_blank_certificate_placeholder_blocks_release() -> None:
    claims = [confirmed("actual.start", "01.06.2026"), confirmed("actual.end", "02.06.2026")]
    item = WorkItem(
        id="w1",
        family="vrs",
        work_type="Работа",
        sequence_index=1,
        actual_start="01.06.2026",
        actual_end="02.06.2026",
        materials=[
            Material(
                name="Арматура Ø10",
                quality_document="(сертификат №                от )",
            )
        ],
        change_state="NO",
        source_claim_keys=["actual.start", "actual.end"],
    )
    plan = DocumentPlan(
        template_id="aosr_vrs",
        selected_sheets=["АОСР-6"],
        work_item_ids=["w1"],
        first_number=1,
        output_filename="АОСР ВРЩ.xlsx",
    )
    codes = {issue.code for issue in validate_semantics([item], claims, [plan])}
    assert "MISSING_QUALITY_DOC" in codes


def test_document_backed_organizations_need_no_profile_approval() -> None:
    claims = [
        Claim(
            key=key,
            raw_value=f"Источник для {key}",
            normalized_value=f"Источник для {key}",
            source_kind="project_pdf",
            source_file_id="pdf-1",
            locator="page:2",
            evidence_fragment=f"Источник для {key}",
            status=ClaimStatus.OBSERVED,
        )
        for key in REQUIRED_DOCUMENT_CLAIMS
    ]
    claims.extend([confirmed("actual.start", "01.06.2026"), confirmed("actual.end", "02.06.2026")])
    item = WorkItem(
        id="w1",
        family="kl_04",
        work_type="Работа",
        sequence_index=1,
        actual_start="01.06.2026",
        actual_end="02.06.2026",
        change_state="NO",
        source_claim_keys=["actual.start", "actual.end"],
    )
    plan = DocumentPlan(
        template_id="aosr_kl_04",
        selected_sheets=["АОСР-3"],
        work_item_ids=["w1"],
        first_number=1,
        output_filename="АОСР.xlsx",
    )
    assert validate_semantics([item], claims, [plan], branch_id="khimki") == []

    # A nominal approval flag cannot replace the actual source-backed name.
    customer = next(claim for claim in claims if claim.key == "customer.name")
    claims.remove(customer)
    claims.append(customer.model_copy(update={
        "source_kind": "approved_profile",
        "status": ClaimStatus.DERIVED,
        "rule_id": "profile:khimki:1.0",
    }))
    issues = validate_semantics([item], claims, [plan], branch_id="khimki")
    assert "PROFILE_SOURCE_RETIRED" in {issue.code for issue in issues}
    assert any(issue.code == "MISSING_DOCUMENT_CLAIM" and "customer.name" in issue.message for issue in issues)
    assert "UNAPPROVED_CUSTOMER_PROFILE" not in {issue.code for issue in issues}
    assert "PROFILE_OUTSIDE_VALIDITY" not in {issue.code for issue in issues}


def test_workbook_validation_cannot_approve_a_profile_backed_value(tmp_path: Path) -> None:
    workbook = openpyxl.Workbook()
    workbook.active["A1"] = "Legacy company"
    output = tmp_path / "draft.xlsx"
    workbook.save(output)
    workbook.close()
    contract = TemplateContract(
        template_id="aosr_kl_04", source_template=str(output), version="test", approved=True,
        output_filename=output.name, allowed_sheets=["Sheet"], candidate_sheets=["Sheet"],
        common_fields={}, sheets={}, clear_cells={}, forbidden_tokens=[], sha256=None,
    )
    plan = DocumentPlan(
        template_id="aosr_kl_04", selected_sheets=["Sheet"], work_item_ids=["w1"],
        first_number=1, output_filename=output.name,
    )
    claim = Claim(
        key="customer.name", raw_value="Legacy company", normalized_value="Legacy company",
        source_kind="approved_profile", locator="khimki.yaml:values.customer.name",
        evidence_fragment="Legacy approved profile", status=ClaimStatus.DERIVED,
        rule_id="profile:khimki:1.0",
    )
    issues = validate_workbook(output, output, contract, plan, [claim])
    assert [issue.code for issue in issues] == ["PROFILE_SOURCE_RETIRED"]
