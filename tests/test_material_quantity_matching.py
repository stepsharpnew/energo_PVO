from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import executive_docs.agent as agent_module
from executive_docs.agent import OpenAIAgent
from executive_docs.domain import Artifact, ProjectState, TemplateCellAssignment, TemplateFillAnalysis
from executive_docs.selected_templates import SelectedTemplateContract


ROOT = Path(__file__).resolve().parents[1]


def sample():
    contract = SelectedTemplateContract.load(ROOT / "templates/fill-contracts/emr.yaml")
    targets = {("Ведомость общ", cell) for cell in ("E19", "AI19", "BE19")}
    contract = replace(contract, fields=tuple(field for field in contract.fields if field.coordinate in targets))
    state = ProjectState(
        job_id="offline-quantity-test", operator_name="test",
        artifacts=[Artifact(id="pdf", original_name="project.pdf", stored_name="project.pdf",
                            media_type="application/pdf", size=1, sha256="0" * 64, pages=1)],
    )
    fragment = "Провод самонесущий изолированный СИП-2г 3х70+1х70 м 143"
    assignments = [
        TemplateCellAssignment(sheet="Ведомость общ", cell=cell, value=value, source_file_id="pdf",
                               locator="page:1", evidence_fragment=fragment, value_basis="project")
        for cell, value in (("E19", "Провод самонесущий изолированный"), ("AI19", "СИП-2г 3х70+1х70"), ("BE19", "143 м"))
    ]
    return state, contract, TemplateFillAnalysis(summary="offline test", assignments=assignments)


def recover(monkeypatch, tmp_path: Path, state, contract, analysis):
    # Isolate local page extraction only; run real per-record recovery and its
    # final group/provenance validation without a model or a source-file write.
    text = "\n".join(dict.fromkeys(item.evidence_fragment for item in analysis.assignments))
    monkeypatch.setattr(agent_module, "source_index", lambda *_: {
        "segments": [{"page": 1, "text": text, "text_reliable": True, "visual_required": False}],
    })
    return OpenAIAgent._recover_template_fill(state, contract, [analysis.model_dump()], tmp_path)


def test_material_quantity_columns_can_be_reordered_without_losing_row_proof(monkeypatch, tmp_path: Path) -> None:
    state, contract, analysis = sample()
    result, diagnostics = recover(monkeypatch, tmp_path, state, contract, analysis)
    assert len(result.assignments) == 3
    assert not diagnostics


def test_material_quantity_does_not_skip_shared_name_and_row_guard(monkeypatch, tmp_path: Path) -> None:
    state, contract, analysis = sample()
    analysis.assignments[-1].evidence_fragment = "Другой материал, м 143"
    result, diagnostics = recover(monkeypatch, tmp_path, state, contract, analysis)
    assert not result.assignments
    assert all(item.category == "rejected" for item in result.unresolved)
    assert all("одной позиции PDF" in item["reason"] for item in diagnostics)


def test_material_quantity_without_name_is_still_rejected(monkeypatch, tmp_path: Path) -> None:
    state, contract, analysis = sample()
    analysis.assignments = analysis.assignments[-1:]
    result, diagnostics = recover(monkeypatch, tmp_path, state, contract, analysis)
    assert not result.assignments
    quantity = next(item for item in result.unresolved if item.cell == "BE19")
    assert quantity.category == "rejected"
    assert any("одной позиции PDF" in item["reason"] for item in diagnostics)


def test_material_quantity_does_not_skip_exact_number_or_unit(monkeypatch, tmp_path: Path) -> None:
    state, contract, analysis = sample()
    for invalid in ("142 м", "143 мм", "143 шт.", "14,3 м"):
        analysis.assignments[-1].value = invalid
        result, diagnostics = recover(monkeypatch, tmp_path, state, contract, analysis)
        assert {item.cell for item in result.assignments} == {"E19", "AI19"}
        assert any("value is not present" in item["reason"] for item in diagnostics)


def test_quantity_reordering_is_not_enabled_for_arbitrary_text_fields(monkeypatch, tmp_path: Path) -> None:
    state, contract, analysis = sample()
    quantity_field = next(field for field in contract.fields if field.cell == "BE19")
    contract = replace(contract, fields=(replace(quantity_field, semantic_id="project.object_name"),))
    analysis.assignments = analysis.assignments[-1:]
    result, diagnostics = recover(monkeypatch, tmp_path, state, contract, analysis)
    assert not result.assignments
    assert result.unresolved[0].category == "rejected"
    assert any("value is not present" in item["reason"] for item in diagnostics)


def test_recovery_rejects_composite_units_and_hidden_signs_or_decimals(monkeypatch, tmp_path: Path) -> None:
    state, contract, analysis = sample()
    analysis.assignments[0].value = "Сталь"
    analysis.assignments[1].value = "TEST"
    analysis.assignments[-1].value = "5 м"
    for suffix in ("кг/м 5", "кг / м 5", "Н·м 5", "Н · м 5", "Н⋅м 5", "Н ⋅ м 5", "Н∙м 5", "Н ∙ м 5", "− 5 м", "- 5 м", "12, 5 м"):
        for assignment in analysis.assignments:
            assignment.evidence_fragment = "Сталь TEST " + suffix
        result, diagnostics = recover(monkeypatch, tmp_path, state, contract, analysis)
        assert {item.cell for item in result.assignments} == {"E19", "AI19"}
        assert any(item["cell"] == "BE19" and "value is not present" in item["reason"] for item in diagnostics)
