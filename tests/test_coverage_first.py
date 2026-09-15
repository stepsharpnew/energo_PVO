from __future__ import annotations

from dataclasses import replace

import openpyxl
import pytest

from executive_docs.agent import OpenAIAgent
from executive_docs.domain import Artifact, ProjectState, TemplateCellAssignment
from executive_docs.packaging import write_report
from executive_docs.selected_templates import (
    MAPPING_REVIEW_FILL_RGB, SelectedTemplateGenerator, TemplateCatalog, validate_selected_template_output,
)
from test_expanded_draft import SHEET, draft_catalog


def material_context(tmp_path, monkeypatch, *, row_count=3):
    catalog = draft_catalog(tmp_path, materials=True)
    contract = catalog.get("expanded")
    row = contract.fields[-3:]
    contract = replace(contract, fields=tuple(
        replace(field, cell=f"{field.cell[0]}{n}", semantic_id=field.semantic_id.replace("item_1", f"item_{n}"), value_kind="text")
        for n in range(1, row_count + 1) for field in row
    ))
    state = ProjectState(job_id="coverage", operator_name="test", artifacts=[Artifact(
        id="pdf", original_name="source.pdf", stored_name="source.pdf", media_type="application/pdf",
        size=1, sha256="2" * 64, pages=1,
    )])
    quote = "Провод СИП-2 12,5 м\nСтойка СВ95 2 шт\nЗажим ЗП6 5 шт"
    monkeypatch.setattr("executive_docs.agent.source_index", lambda *a, **k: {
        "segments": [{"page": 1, "text": quote, "text_reliable": True, "visual_required": False}],
    })
    rows = [{"table_id": "test.materials", "name": name, "type": kind, "quantity": qty,
             "source_file_id": "pdf", "locator": "page:1", "evidence_fragment": f"{name} {kind} {qty}",
             "value_basis": "project"}
            for name, kind, qty in [("Провод", "СИП-2", "12,5 м"), ("Стойка", "СВ95", "2 шт"), ("Зажим", "ЗП6", "5 шт")]]
    return catalog, contract, state, rows


def test_three_compact_positions_fill_nine_cells_with_original_provenance(tmp_path, monkeypatch):
    _, contract, state, rows = material_context(tmp_path, monkeypatch)
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [{"material_rows": rows}], tmp_path)
    assert len(result.assignments) == 9
    assert not result.unresolved and not diagnostics and not result.material_rows
    assert {a.cell: a.value for a in result.assignments} == {
        "D1": "Провод", "E1": "СИП-2", "F1": "12,5 м", "D2": "Стойка", "E2": "СВ95",
        "F2": "2 шт", "D3": "Зажим", "E3": "ЗП6", "F3": "5 шт",
    }
    assert all(a.value_basis == "project" and a.locator == "page:1" and a.source_file_id == "pdf" for a in result.assignments)


def test_compact_rows_preserve_valid_names_when_quantity_is_missing_or_unsupported(tmp_path, monkeypatch):
    _, contract, state, rows = material_context(tmp_path, monkeypatch)
    rows[0]["quantity"] = None
    rows[1]["quantity"] = "99 шт"
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [{"material_rows": rows}], tmp_path)
    assert len(result.assignments) == 7
    assert {a.cell for a in result.assignments} >= {"D1", "D2", "D3"}
    assert {f.cell: f.category for f in result.unresolved} == {"F1": "not_returned", "F2": "rejected"}
    assert len(diagnostics) == 1


def test_compact_rows_do_not_overwrite_explicit_cells_or_hide_overflow(tmp_path, monkeypatch):
    _, contract, state, rows = material_context(tmp_path, monkeypatch)
    first = {k: v for k, v in rows[0].items() if k not in {"table_id", "name", "type", "quantity"}}
    explicit = {**first, "sheet": SHEET, "cell": "D1", "value": "Провод"}
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [{"assignments": [explicit], "material_rows": rows[1:] + rows[:1]}], tmp_path)
    assert next(a for a in result.assignments if a.cell == "D1").value == "Провод"
    assert len(result.assignments) == 7
    assert any("capacity exceeded" in d["reason"] for d in diagnostics)
    assert "не помещена" in result.summary


@pytest.mark.parametrize("mutate", [
    {"source_file_id": "other"}, {"locator": "page:2"}, {"evidence_fragment": "Придуманный провод 12,5"},
    {"table_id": "other.materials"},
])
def test_compact_rows_do_not_bypass_source_or_table_checks(tmp_path, monkeypatch, mutate):
    _, contract, state, rows = material_context(tmp_path, monkeypatch)
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [{"material_rows": [{**rows[0], **mutate}]}], tmp_path)
    assert not result.assignments and diagnostics


def test_quantity_column_is_proved_by_same_page_layout_not_guessed_from_glued_digits(tmp_path, monkeypatch):
    _, contract, state, rows = material_context(tmp_path, monkeypatch, row_count=1)
    raw = {**rows[0], "quantity": "79 м", "evidence_fragment": "Провод СИП-2 м 79 1,24"}
    segment = {"page": 1, "text": "Провод СИП-2 м791,24", "text_reliable": True,
               "visual_required": False, "layout_text_reliable": True,
               "layout_text": "Провод       СИП-2       м       79      1,24"}
    monkeypatch.setattr("executive_docs.agent.source_index", lambda *a, **k: {"segments": [segment]})
    accepted, _ = OpenAIAgent._recover_template_fill(state, contract, [{"material_rows": [raw]}], tmp_path)
    assert len(accepted.assignments) == 3
    segment.pop("layout_text")
    rejected, _ = OpenAIAgent._recover_template_fill(state, contract, [{"material_rows": [raw]}], tmp_path)
    assert not rejected.assignments


def test_bad_compact_row_cannot_consume_capacity_needed_by_a_valid_row(tmp_path, monkeypatch):
    _, contract, state, rows = material_context(tmp_path, monkeypatch, row_count=1)
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [{
        "material_rows": [{**rows[0], "source_file_id": "wrong-pdf"}, rows[0]],
    }], tmp_path)
    assert len(result.assignments) == 3
    assert len(diagnostics) == 1 and "uploaded PDF" in diagnostics[0]["reason"]
    assert not any("capacity exceeded" in d["reason"] for d in diagnostics)


def test_same_source_row_is_not_duplicated_when_type_was_already_in_name(tmp_path, monkeypatch):
    _, contract, state, rows = material_context(tmp_path, monkeypatch)
    contract = replace(contract, fields=tuple(f for f in contract.fields if not f.semantic_id.endswith(".type")))
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [{"material_rows": [
        rows[0], {**rows[0], "name": "Провод СИП-2", "type": None},
    ]}], tmp_path)
    assert len(result.assignments) == 2 and not diagnostics


def test_compact_mapping_review_applies_to_descriptions_not_quantity(tmp_path, monkeypatch):
    _, contract, state, rows = material_context(tmp_path, monkeypatch, row_count=1)
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [{"material_rows": [
        {**rows[0], "mapping_review_reason": "Проверить сопоставление названия и марки материала."},
    ]}], tmp_path)
    assert len(result.assignments) == 3 and not diagnostics
    assert {a.cell for a in result.assignments if a.mapping_review_reason} == {"D1", "E1"}


def test_versions_of_same_pdf_position_cannot_become_two_materials(tmp_path, monkeypatch):
    _, contract, state, rows = material_context(tmp_path, monkeypatch)
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [{"material_rows": [
        rows[0], {**rows[0], "quantity": "99 м"},
    ]}], tmp_path)
    assert {a.cell for a in result.assignments} == {"D1", "E1"}
    assert next(f for f in result.unresolved if f.cell == "F1").category == "rejected"
    assert any("incompatible" in d["reason"] for d in diagnostics)


def test_single_name_column_keeps_source_name_when_mark_is_unconfirmed(tmp_path, monkeypatch):
    _, contract, state, rows = material_context(tmp_path, monkeypatch, row_count=1)
    contract = replace(contract, fields=tuple(f for f in contract.fields if not f.semantic_id.endswith(".type")))
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [{"material_rows": [
        {**rows[0], "type": "NOT-IN-PDF"},
    ]}], tmp_path)
    assert {a.cell: a.value for a in result.assignments} == {"D1": "Провод", "F1": "12,5 м"}
    assert next(a for a in result.assignments if a.cell == "D1").mapping_review_reason
    assert any(d["kind"] == "material_columns" for d in diagnostics)


def test_mapping_review_has_visible_marker_preserves_formula_and_is_reported(tmp_path):
    catalog = draft_catalog(tmp_path, materials=True)
    contract = catalog.get("expanded")
    assignment = TemplateCellAssignment(sheet=SHEET, cell="D1", value="Провод", source_file_id="pdf",
        locator="page:1", evidence_fragment="Провод СИП-2 12,5", value_basis="project",
        mapping_review_reason="Проверить соответствие названия позиции назначению этой таблицы.")
    output, unresolved = SelectedTemplateGenerator(catalog).generate(contract, [assignment], tmp_path / "output")
    book = openpyxl.load_workbook(output)
    assert book[SHEET]["D1"].value == "Провод"
    assert book[SHEET]["D1"].fill.fgColor.rgb == MAPPING_REVIEW_FILL_RGB
    assert book[SHEET]["C1"].value == "=B1"
    assert "оранжевые" in book[SHEET].oddHeader.left.text
    assert "по проекту" in book[SHEET].oddHeader.left.text
    book.close()
    issues = validate_selected_template_output(output, catalog.candidate_path(contract), contract, [assignment], unresolved)
    assert not [i for i in issues if i.severity == "error"]
    state = ProjectState(job_id="coverage", operator_name="test", selected_template_id=contract.template_id,
                         template_assignments=[assignment])
    write_report(state, tmp_path)
    assert "ПРОВЕРИТЬ ПРИВЯЗКУ" in (tmp_path / "report/r1/report.html").read_text()


@pytest.mark.parametrize("semantic,rule,kind", [
    ("actual.start", "actual_executive_document_only", "date"),
    ("designer.name", "organization_role_pdf", "text"),
    ("contractor.site_representative.name", "signatory_role_pdf", "text"),
    ("project.design_document_code", "direct_pdf", "text"),
    ("test.materials.item_1.quantity", "direct_pdf", "text"),
])
def test_review_mapping_cannot_relax_critical_fields(tmp_path, semantic, rule, kind):
    field = replace(draft_catalog(tmp_path).get("expanded").fields[0], semantic_id=semantic,
                    evidence_rule=rule, value_kind=kind)
    assert not field.allows_mapping_review
    assert field.evidence_context_error(["Любые данные"], "данные", value_basis="project", mapping_review_reason="Проверить")


@pytest.mark.parametrize("quote,allowed", [
    ('ООО «Пример» — проектная организация', True),
    ('ООО «Пример» — генеральный проектировщик', True),
    ('ООО «Пример» — не проектировщик', False),
    ('ООО «Пример». Проектная организация: ООО «Другая»', False),
    ('ООО «Пример» — заказчик; проектировщик ООО «Другая»', False),
])
def test_role_after_entity_is_accepted_only_in_same_party_block(tmp_path, quote, allowed):
    field = next(f for f in draft_catalog(tmp_path).get("expanded").fields if f.semantic_id == "designer.name")
    assert (field.evidence_context_error([quote], 'ООО «Пример»') is None) == allowed


def test_real_material_tables_have_compact_mapping_and_no_execution_columns():
    from pathlib import Path
    import json

    root = Path(__file__).resolve().parents[1]
    catalog = TemplateCatalog(root, root / "templates/fill-contracts", root / "templates/approved")
    for template_id, capacity, columns in [("emr", 23, ["name", "quantity", "type"]), ("avk", 51, ["name", "quantity"])]:
        contract = catalog.get(template_id)
        assert contract.material_tables() == [{"table_id": f"{template_id}.materials", "capacity": capacity,
            "columns": columns, "allow_project_basis": True, "allows_mapping_review": True}]
        scalar_fields = [f for f in contract.model_fields() if ".materials.item_" not in (f.get("semantic_id") or "")]
        compact_size = len(json.dumps([scalar_fields, contract.material_tables()], ensure_ascii=False))
        assert compact_size < len(json.dumps(contract.model_fields(), ensure_ascii=False)) / 2
