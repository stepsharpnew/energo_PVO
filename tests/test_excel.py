from pathlib import Path

import openpyxl
import pytest

from executive_docs.domain import Claim, ClaimStatus, DocumentPlan, FieldValue, WorkItem
from executive_docs.excel import ExcelGenerator, OOXMLWorkbook, sha256, workbook_snapshot
from executive_docs.validation import validate_workbook


ROOT = Path(__file__).resolve().parents[1]


def generator(tmp_path: Path) -> ExcelGenerator:
    return ExcelGenerator(ROOT, ROOT / "templates" / "contracts", tmp_path / "approved")


def test_ooxml_generator_changes_only_selected_contract_fields(tmp_path: Path) -> None:
    item = WorkItem(
        id="work-kl04-1",
        family="kl_04",
        work_type="Устройство трубопровода КЛ-0,4 кВ",
        sequence_index=1,
        actual_start="01.06.2026",
        actual_end="02.06.2026",
        volume="18",
        unit="м",
        change_state="NO",
        source_claim_keys=["actual.start", "actual.end"],
    )
    plan = DocumentPlan(
        template_id="aosr_kl_04",
        selected_sheets=["АОСР-3"],
        work_item_ids=[item.id],
        first_number=17,
        output_filename="АОСР КЛ-0,4кВ.xlsx",
    )
    claims = [
        Claim(key="actual.start", raw_value="01.06.2026", normalized_value="01.06.2026", source_kind="human_answer", locator="question:q1", evidence_fragment="confirmed", status=ClaimStatus.HUMAN_CONFIRMED),
        Claim(key="actual.end", raw_value="02.06.2026", normalized_value="02.06.2026", source_kind="human_answer", locator="question:q2", evidence_fragment="confirmed", status=ClaimStatus.HUMAN_CONFIRMED),
        Claim(key="project.code", raw_value="P-42", normalized_value="P-42", source_kind="project", locator="page:1", evidence_fragment="P-42", status=ClaimStatus.OBSERVED),
    ]
    output, contract = generator(tmp_path).generate(plan, [item], claims, tmp_path)
    workbook = openpyxl.load_workbook(output, data_only=False, keep_links=True)
    assert workbook["АОСР-3"]["C32"].value == 17
    assert workbook["АОСР-3"]["A62"].value == item.work_type
    assert workbook["АОСР-3"]["R62"].value == "18"
    assert workbook["Данные объект"]["B43"].value == "P-42"
    assert workbook["АОСР-3"].sheet_state == "visible"
    assert workbook["АОСР-1"].sheet_state == "hidden"
    workbook.close()
    render_copy = tmp_path / "render-copy.xlsx"
    render_package = OOXMLWorkbook(output)
    render_package.set_only_visible("АОСР-3")
    render_package.configure_printing("АОСР-3")
    render_package.save(render_copy)
    rendered = openpyxl.load_workbook(render_copy, data_only=False, keep_links=True)
    assert rendered.active.title == "АОСР-3"
    assert str(rendered["АОСР-3"].print_area) != ""
    assert str(rendered["АОСР-1"].print_area) == ""
    assert rendered["АОСР-3"].page_setup.fitToWidth == 1
    rendered.close()
    issues = validate_workbook(output, ROOT / contract.source_template, contract, plan)
    assert any(issue.code == "TEMPLATE_NOT_APPROVED" for issue in issues)
    assert not any(issue.code in {"SHEET_STRUCTURE", "FORMULA_CHANGED", "MERGES_CHANGED", "STYLES_CHANGED"} for issue in issues)
    assert sha256(ROOT / contract.source_template) == "0a9e8934639ab411350863346e9f2103371ae95f2a287c83f674b70ef2336acd"


def test_generator_rejects_model_controlled_output_path(tmp_path: Path) -> None:
    item = WorkItem(id="w", family="kl_04", work_type="Работа", sequence_index=1)
    plan = DocumentPlan(
        template_id="aosr_kl_04",
        selected_sheets=["АОСР-3"],
        work_item_ids=["w"],
        first_number=1,
        output_filename="../escape.xlsx",
    )
    with pytest.raises(ValueError, match="Имя выходного файла"):
        generator(tmp_path).generate(plan, [item], [], tmp_path)


def test_generator_rejects_field_value_without_matching_claim(tmp_path: Path) -> None:
    item = WorkItem(id="w", family="kl_04", work_type="Работа", sequence_index=1)
    plan = DocumentPlan(
        template_id="aosr_kl_04",
        selected_sheets=["АОСР-3"],
        work_item_ids=["w"],
        first_number=1,
        field_values=[FieldValue(key="project.code", value="INVENTED")],
        output_filename="АОСР КЛ-0,4кВ.xlsx",
    )
    with pytest.raises(ValueError, match="не подтверждено Claim"):
        generator(tmp_path).generate(plan, [item], [], tmp_path)


@pytest.mark.parametrize(
    ("source_name", "candidate_name"),
    [
        ("9. АОСР КЛ.xlsx", "9. АОСР КЛ.xlsx"),
        ("10. АОСР ВРЩ.xlsx", "10. АОСР ВРЩ.xlsx"),
    ],
)
def test_cleaned_template_candidates_preserve_structure_and_printing(
    source_name: str, candidate_name: str
) -> None:
    baseline = workbook_snapshot(ROOT / "template" / source_name)
    candidate = workbook_snapshot(ROOT / "templates" / "approved" / candidate_name)
    assert [item["name"] for item in candidate["sheets"]] == [item["name"] for item in baseline["sheets"]]
    assert [
        (item["name"], item["print_area"], item["page_orientation"], item["paper_size"])
        for item in candidate["sheets"]
    ] == [
        (item["name"], item["print_area"], item["page_orientation"], item["paper_size"])
        for item in baseline["sheets"]
    ]
    assert candidate["external_links"] == 0
    assert not candidate["defined_name_errors"]
    assert not [error for item in candidate["sheets"] for error in item["errors"]]
