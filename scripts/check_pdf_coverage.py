"""Offline human-verified PDF fixture through real recovery and XLSX generator.

Never instantiates an API client, calls a model, uses example XLSX facts, or
changes a saved job. Source indexes are built by production ingestion over a
SHA-verified disposable PDF copy. Output is technical QA, not model performance
or specialist approval. Run with PYTHONPATH=src uv run python scripts/check_pdf_coverage.py.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pypdf import PdfReader
import openpyxl

from executive_docs.agent import OpenAIAgent
from executive_docs.domain import Artifact, ProjectState
from executive_docs.excel import OOXMLWorkbook, sha256
from executive_docs.evidence_matching import entity_value_is_present
from executive_docs.ingestion import EXTRACTOR_VERSION, source_index
from executive_docs.selected_templates import (
    SelectedTemplateGenerator, TemplateCatalog, validate_selected_template_output,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def counts(result, contract) -> dict:
    fields = contract.field_map
    parts = Counter()
    material_slots = set()
    for item in result.assignments:
        semantic = fields[item.sheet, item.cell].semantic_id or ""
        match = re.fullmatch(r"(.+\.materials\.item_\d+)\.(name|type|quantity)", semantic)
        if match:
            parts[match[2]] += 1
            material_slots.add(match[1])
    return {
        "accepted_cells": len(result.assignments),
        "material_cells": sum(parts.values()),
        "material_rows_with_any_accepted_value": len(material_slots),
        "material_columns": dict(parts),
        "common_cells": len(result.assignments) - sum(parts.values()),
        "unresolved": dict(Counter(item.category for item in result.unresolved)),
    }


def render_existing(output_root: Path, templates: list[str]) -> None:
    """Render disposable copies using native print settings; never resave results."""
    sheets = {"emr": "Ведомость общ", "avk": " Журнал АВК"}
    for template_id in templates:
        qa = output_root / template_id
        summary = json.loads((qa / "summary.json").read_text(encoding="utf-8"))
        output = Path(summary["xlsx"])
        assert output.is_relative_to(qa) and sha256(output) == summary["xlsx_sha256"]
        preview = qa / "preview"
        preview.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="native-view-", dir=preview) as name:
            temporary = Path(name)
            package = OOXMLWorkbook(output)
            package.set_only_visible(sheets[template_id])
            package.save(temporary / "view.xlsx")
            completed = subprocess.run([
                "soffice", f"-env:UserInstallation={(temporary / 'lo-profile').as_uri()}",
                "--headless", "--convert-to", "pdf", "--outdir", str(temporary), str(temporary / "view.xlsx"),
            ], capture_output=True, text=True, check=True, timeout=60)
            assert (temporary / "view.pdf").is_file(), completed.stdout + completed.stderr
            shutil.copyfile(temporary / "view.pdf", preview / "view.pdf")
        subprocess.run(["pdftoppm", "-scale-to", "1800", "-png", str(preview / "view.pdf"), str(preview / "page")],
            capture_output=True, check=True, timeout=60)
        assert sha256(output) == summary["xlsx_sha256"]
        write_json(preview / "render-check.json", {"sheet": sheets[template_id],
            "source_xlsx_unchanged": True, "native_print_settings_preserved": True,
            "rendered_pages": len(PdfReader(preview / "view.pdf").pages),
            "preview_pdf_sha256": sha256(preview / "view.pdf"), "visual_review": "PENDING_HUMAN_IMAGE_INSPECTION"})
        print(json.dumps({"template": template_id, "preview": str(preview)}, ensure_ascii=False), flush=True)


def make_payload(fixture: dict, contract, artifact: Artifact, *, plain: bool = False) -> dict:
    facts = {fact["semantic_id"]: fact for fact in fixture["facts"] if not fact["visual_required"]}
    # Same PDF title has the same meaning in these two registered scalar targets.
    if "project.object_name" in facts:
        facts["project.design_document_title"] = facts["project.object_name"]
    assignments = []
    for field in contract.fields:
        fact = facts.get(field.semantic_id)
        if not fact or field.manual_reason:
            continue
        assignments.append({
            "sheet": field.sheet, "cell": field.cell, "value": fact["value"],
            "source_file_id": artifact.id, "locator": f"page:{fact['page']}",
            "evidence_fragment": fact["quote"], "value_basis": "document",
        })
        if field.semantic_id in {"designer.registration", "designer.address"}:
            subject = facts["designer.name"]["value"]
            if entity_value_is_present(subject, fact["quote"]):
                assignments[-1]["subject_name"] = subject
    return {"assignments": assignments, "material_rows": [{
        "table_id": f"{contract.template_id}.materials", "name": row["name"],
        "type": row["type"], "quantity": f"{row['quantity']} {row['unit']}",
        "source_file_id": artifact.id, "locator": row["locator"],
        "evidence_fragment": row["quote"] if plain else row["visual_transcription"],
        "value_basis": row["value_basis"],
    } for row in fixture["material_rows"]]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/fixtures/selected-template-coverage/example2-materials.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/runs/coverage-first-20260915/example2")
    parser.add_argument("--templates", nargs="+", choices=["emr", "avk"], default=["emr", "avk"])
    parser.add_argument("--render-existing", action="store_true", help="Render existing verified QA outputs only; no regeneration")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    assert fixture["fixture_kind"] == "offline_human_verified_pdf_coverage"
    assert fixture["runtime_evidence"] is False
    output_root = args.output_root.resolve()
    if not output_root.is_relative_to((ROOT / "data/runs").resolve()):
        raise ValueError("Offline output must stay under data/runs")
    if args.render_existing:
        render_existing(output_root, args.templates)
        return
    pdf = (ROOT / fixture["source"]["path"]).resolve()
    assert pdf.is_relative_to(ROOT) and pdf.suffix.lower() == ".pdf"
    assert sha256(pdf) == fixture["source"]["sha256"]
    assert pdf.stat().st_size == fixture["source"]["size_bytes"]
    reader = PdfReader(pdf)
    assert len(reader.pages) == fixture["source"]["page_count"]
    native_quotes = 0
    for fact in fixture["facts"] + fixture["material_rows"]:
        if fact["quote_kind"] == "pypdf_plain_exact":
            assert fact["quote"] in (reader.pages[fact["page"] - 1].extract_text() or ""), fact["id"]
            native_quotes += 1
    assert all(row["visual_verified"] and row["page"] in fixture["visually_reviewed_pages"]
               for row in fixture["material_rows"])
    catalog = TemplateCatalog(ROOT, ROOT / "templates/fill-contracts", ROOT / "templates/approved")
    summaries = []
    for template_id in args.templates:
        contract = catalog.get(template_id)
        qa = output_root / template_id
        if (qa / "summary.json").exists():
            raise ValueError(f"Existing QA is preserved; choose a new --output-root: {qa}")
        candidate = catalog.candidate_path(contract)
        candidate_hash = sha256(candidate)
        evidence = qa / "evidence-copy"
        source_copy = evidence / "input" / pdf.name
        source_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, source_copy)
        artifact = Artifact(id=f"pdf-{fixture['source']['sha256'][:12]}",
            original_name=pdf.name, stored_name=pdf.name, media_type="application/pdf",
            size=pdf.stat().st_size, sha256=fixture["source"]["sha256"], pages=len(reader.pages))
        state = ProjectState(job_id=f"offline-fixture-{template_id}", operator_name="Offline PDF QA",
            flow_version="selected-template-v2", selected_template_id=template_id,
            selected_template_contract_sha256=contract.contract_sha256,
            selected_template_sha256=contract.candidate_sha256, artifacts=[artifact])
        # This is a truthful human visual-review manifest, never a model-input
        # claim. Production proof still decides whether visual fallback applies.
        write_json(evidence / "state/selected-visual-evidence-r1.json", [{
            "file_id": artifact.id, "sha256": artifact.sha256,
            "pages": fixture["visually_reviewed_pages"],
            "qa_origin": "human-reviewed PDF pages, not model-supplied pages",
        }])
        index = source_index(evidence, artifact)
        payload = make_payload(fixture, contract, artifact)
        plain, plain_diagnostics = OpenAIAgent._recover_template_fill(
            state, contract, [make_payload(fixture, contract, artifact, plain=True)], evidence)
        result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, [payload], evidence)
        capacity_baseline = None
        if template_id == "avk":
            # Capacity-only ablation of the current guard, not a historical run.
            fields = tuple(field for field in contract.fields if not (
                (match := re.fullmatch(r"avk\.materials\.item_(\d+)\..+", field.semantic_id or ""))
                and int(match[1]) > 10))
            limited = replace(contract, fields=fields)
            baseline, baseline_diagnostics = OpenAIAgent._recover_template_fill(state, limited, [payload], evidence)
            capacity_baseline = {"kind": "current_validator_capacity_only_ablation", "capacity": 10,
                **counts(baseline, limited), "diagnostics": baseline_diagnostics}
        output, unresolved = SelectedTemplateGenerator(catalog).generate(contract, result.assignments,
            qa / "xlsx", findings=result.unresolved, source_snapshot=qa / "source/template.xlsx")
        issues = validate_selected_template_output(output, qa / "source/template.xlsx", contract,
            result.assignments, unresolved)
        # The zero-assignment baseline diagnoses existing template defects only;
        # it is not a second output workbook and not a model-run baseline.
        baseline_issues = [item for item in validate_selected_template_output(candidate, candidate, contract, [], [])
                           if item.code.startswith("TEMPLATE_")]
        workbook = openpyxl.load_workbook(output, read_only=False, data_only=False)
        try:
            for assignment in result.assignments:
                expected = SelectedTemplateGenerator._typed_value(contract.field_map[assignment.sheet, assignment.cell], assignment.value)
                assert workbook[assignment.sheet][assignment.cell].value == expected
        finally:
            workbook.close()
        assert sha256(pdf) == artifact.sha256 and sha256(candidate) == candidate_hash
        summary = {
            "qa_status": "OFFLINE_HUMAN_FIXTURE_TECHNICAL_REGRESSION_NOT_MODEL_RUN_OR_APPROVAL",
            "template_id": template_id, "template_version": contract.version,
            "contract_sha256": contract.contract_sha256, "candidate_sha256": candidate_hash,
            "fixture_sha256": sha256(args.fixture), "source": fixture["source"],
            "extractor_version": EXTRACTOR_VERSION, "source_index_sha256": sha256(
                evidence / "extracted" / f"{artifact.sha256}-{EXTRACTOR_VERSION}.json"),
            "native_quotes_verified_exact": native_quotes, "submitted_material_rows": len(fixture["material_rows"]),
            "material_tables": contract.material_tables(),
            "actual_layout_pages": [segment["page"] for segment in index["segments"] if segment.get("layout_text")],
            "human_visually_reviewed_pages": fixture["visually_reviewed_pages"],
            "baseline_plain_quote_ablation": {"kind": "same_guard_with_glued_plain_quotes_not_historical_run",
                **counts(plain, contract), "diagnostics": plain_diagnostics},
            "avk_capacity_10_ablation": capacity_baseline,
            "current": counts(result, contract), "diagnostics": diagnostics,
            "technical_validation_issues": [item.model_dump(mode="json") for item in issues],
            "baseline_candidate_issues": [item.model_dump(mode="json") for item in baseline_issues],
            "baseline_candidate_scope": "Static TEMPLATE_* findings only; no fabricated empty-assignment output/register comparison.",
            "xlsx": str(output), "xlsx_sha256": sha256(output),
            "exact_written_values_verified": True, "source_and_candidate_unchanged": True,
            "paid_calls": 0, "cost_usd": 0,
            "remaining_limitations": [
                "A human extracted this fixture. Counts do not demonstrate autonomous model recall.",
                "Only the supplied VLI construction and grounding rows are covered, not every installation in the PDF.",
                "Actual execution, dates, signatories, passports and material acceptance remain unconfirmed.",
                "Native/layout mismatch and multiline rows are rejected; no page locator or source index is forged.",
                "Existing template/formula defects are reported separately, never repaired in this regression.",
            ],
        }
        write_json(qa / "fixture-submission.json", payload)
        write_json(qa / "recovered-analysis.json", result.model_dump(mode="json"))
        write_json(qa / "summary.json", summary)
        summaries.append(summary)
        print(json.dumps({"template": template_id, "plain": counts(plain, contract),
            "current": counts(result, contract), "technical_issues": len(issues), "xlsx": str(output)},
            ensure_ascii=False), flush=True)
    write_json(output_root / "summary.json", summaries)


if __name__ == "__main__":
    main()
