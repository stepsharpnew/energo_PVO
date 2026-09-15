"""Replay one saved paid response through current validators, without network.

Historical jobs, source PDFs and outputs are immutable. This is a separate
diagnostic draft, not a new model run, a source of facts, or template approval.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from executive_docs.agent import OpenAIAgent
from executive_docs.domain import ProjectState
from executive_docs.excel import sha256
from executive_docs.ingestion import build_compact_evidence, select_visual_sources, source_index
from executive_docs.selected_templates import SelectedTemplateGenerator, TemplateCatalog, validate_selected_template_output
from executive_docs.version import VERSION


def no_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("Offline replay forbids all network access")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    sys.addaudithook(no_network)
    target = args.output_root.resolve()
    history = args.job_root.resolve()
    if not target.is_relative_to(ROOT / "data/runs") or target == ROOT / "data/runs":
        raise ValueError("Replay output must be a new directory under data/runs")
    if target.exists() or target.is_relative_to(history) or history.is_relative_to(target):
        raise ValueError("Existing or overlapping historical directories must not be changed")
    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        row = connection.execute("SELECT state_json FROM jobs WHERE id=?", (args.job_id,)).fetchone()
    if row is None:
        raise ValueError("Job not found")
    state = ProjectState.model_validate_json(row[0])
    if len(state.artifacts) != 1 or not state.selected_template_id:
        raise ValueError("Expected one selected-template PDF job")
    artifact = state.artifacts[0]
    source = history / "input" / artifact.stored_name
    assert source.is_relative_to(history / "input") and sha256(source) == artifact.sha256
    events = [json.loads(line) for line in (history / "state/agent-events.jsonl").read_text().splitlines()]
    submissions = [event for event in events if event.get("event") == "selected_template_submission"
                   and event.get("revision") == state.revision]
    if not submissions:
        raise ValueError("No saved response for the job's current revision")
    pinned_paths = [source, history / "state/agent-events.jsonl", *[history / p for p in state.draft_excel_files]]
    pinned_hashes = {path: sha256(path) for path in pinned_paths}
    target.mkdir(parents=True)
    evidence = target / "evidence-copy"
    (evidence / "input").mkdir(parents=True)
    shutil.copyfile(source, evidence / "input" / artifact.stored_name)
    historical_visual = history / "state" / f"selected-visual-evidence-r{state.revision}.json"
    if historical_visual.is_file():
        (evidence / "state").mkdir()
        shutil.copyfile(historical_visual, evidence / "state" / historical_visual.name)
    source_index(evidence, artifact)
    catalog = TemplateCatalog(ROOT, ROOT / "templates/fill-contracts", ROOT / "templates/approved")
    contract = catalog.get(state.selected_template_id)
    raw_payloads = submissions[-1]["payloads"]
    write_json(target / "saved-response.json", raw_payloads)
    result, diagnostics = OpenAIAgent._recover_template_fill(state, contract, raw_payloads, evidence)
    output, unresolved = SelectedTemplateGenerator(catalog).generate(
        contract, result.assignments, target / "xlsx", findings=result.unresolved,
        source_snapshot=target / "source/template.xlsx",
    )
    issues = validate_selected_template_output(output, target / "source/template.xlsx", contract,
                                              result.assignments, unresolved)
    # Routing is tested separately. It must never retroactively authorize visual
    # evidence for a page absent from the historical paid request.
    packet = build_compact_evidence(evidence, [artifact], 70_000, selected_template=True)
    text_pages = {(p["file_id"], int(p["locator"].removeprefix("page:"))) for p in packet}
    planned_visual = select_visual_sources(evidence, [artifact], max_pages=40, include_project=True,
                                          selected_template=True, text_pages=text_pages)
    visual_pages = {page for item in planned_visual for page in item["pages"]}
    coverage = {
        "text_pages": sorted(page for _, page in text_pages), "visual_pages": sorted(visual_pages),
        "pages_not_preloaded": [page for page in range(1, (artifact.pages or 0) + 1)
                                if (artifact.id, page) not in text_pages and page not in visual_pages],
        "serialized_text_chars": len(json.dumps(packet, ensure_ascii=False)),
    }
    write_json(target / "new-context-plan.json", {"coverage": coverage, "evidence": packet})
    material_parts = Counter(contract.field_map[a.sheet, a.cell].semantic_id.rsplit(".", 1)[-1]
                             for a in result.assignments
                             if ".materials.item_" in (contract.field_map[a.sheet, a.cell].semantic_id or ""))
    summary = {
        "kind": "OFFLINE_SAVED_RESPONSE_REPLAY_NOT_NEW_MODEL_RUN_OR_APPROVAL", "release": VERSION,
        "historical_job_id": state.job_id, "historical_response_ids": [u.response_id for u in state.model_usage],
        "new_paid_calls": 0, "new_cost_usd": 0, "template_id": contract.template_id,
        "template_version": contract.version, "source_sha256": artifact.sha256,
        "accepted_before": len(state.template_assignments), "accepted_cells": len(result.assignments),
        "material_columns": dict(material_parts), "xlsx": str(output), "xlsx_sha256": sha256(output),
        "technical_error_count": sum(issue.severity == "error" for issue in issues),
        "mapping_review_cells": sum(bool(a.mapping_review_reason) for a in result.assignments),
        "new_context_coverage": coverage,
    }
    write_json(target / "analysis.json", result.model_dump(mode="json"))
    write_json(target / "diagnostics.json", diagnostics)
    write_json(target / "issues.json", [issue.model_dump(mode="json") for issue in issues])
    assert all(sha256(path) == digest for path, digest in pinned_hashes.items())
    summary["historical_files_unchanged"] = True
    write_json(target / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["technical_error_count"]:
        raise SystemExit("Replay produced technical errors")


if __name__ == "__main__":
    main()
