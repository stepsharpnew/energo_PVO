#!/usr/bin/env python3
"""Create a read-only qualification report for the three pilot workbook templates."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from executive_docs.excel import TemplateContract, workbook_snapshot  # noqa: E402


GOLDEN_CANDIDATES = {
    "aosr_kl_04": ROOT / "project1" / "9. АОСР КЛ.xlsx",
    "aosr_kl_6": ROOT / "project1" / "9. АОСР КЛ 6кВ.xlsx",
    "aosr_vrs": ROOT / "project1" / "10. АОСР ВРЩ.xlsx",
}


def summarize(path: Path) -> dict:
    snapshot = workbook_snapshot(path)
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": snapshot["sha256"],
        "sheet_count": len(snapshot["sheets"]),
        "sheet_names": [item["name"] for item in snapshot["sheets"]],
        "formula_error_count": sum(len(item["errors"]) for item in snapshot["sheets"]) + len(snapshot["defined_name_errors"]),
        "formula_errors": [error for item in snapshot["sheets"] for error in item["errors"]] + snapshot["defined_name_errors"],
        "external_links": snapshot["external_links"],
        "defined_name_count": len(snapshot["defined_names"]),
        "print_configuration": [
            {
                "sheet": item["name"],
                "print_area": item["print_area"],
                "orientation": item["page_orientation"],
                "paper_size": item["paper_size"],
            }
            for item in snapshot["sheets"]
        ],
    }


def find_tokens(path: Path, tokens: list[str]) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        content = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist()
            if name.endswith((".xml", ".rels"))
        )
    return [token for token in tokens if token and token in content]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Return a non-zero code while blockers exist")
    args = parser.parse_args()
    entries = []
    for contract_path in sorted((ROOT / "templates" / "contracts").glob("*.yaml")):
        contract = TemplateContract.load(contract_path)
        source = ROOT / contract.source_template
        source_info = summarize(source)
        source_info["forbidden_tokens_found"] = find_tokens(source, contract.forbidden_tokens)
        candidate = ROOT / "templates" / "approved" / source.name
        candidate_info = summarize(candidate) if candidate.exists() else None
        if candidate_info:
            candidate_info["forbidden_tokens_found"] = find_tokens(candidate, contract.forbidden_tokens)
        golden = GOLDEN_CANDIDATES.get(contract.template_id)
        golden_info = summarize(golden) if golden and golden.exists() else None
        active_info = candidate_info or source_info
        blockers = []
        if active_info["formula_error_count"]:
            blockers.append("FORMULA_ERRORS")
        if active_info["external_links"]:
            blockers.append("EXTERNAL_LINKS")
        if active_info["forbidden_tokens_found"]:
            blockers.append("STALE_VALUES")
        missing_sheets = sorted(set(contract.candidate_sheets) - set(active_info["sheet_names"]))
        if missing_sheets:
            blockers.append("MISSING_CONTRACT_SHEETS")
        if candidate_info:
            if source_info["sheet_names"] != candidate_info["sheet_names"]:
                blockers.append("SHEET_ORDER_CHANGED")
            if source_info["print_configuration"] != candidate_info["print_configuration"]:
                blockers.append("PRINT_CONFIGURATION_CHANGED")
        entries.append(
            {
                "template_id": contract.template_id,
                "contract": contract_path.relative_to(ROOT).as_posix(),
                "approved_in_contract": contract.approved,
                "source": source_info,
                "cleaned_candidate": candidate_info,
                "filled_example": golden_info,
                "missing_contract_sheets": missing_sheets,
                "blockers": blockers,
                "status": "READY_FOR_EXPERT_APPROVAL" if not blockers else "BLOCKED_TEMPLATE_CLEANUP",
            }
        )
    report = {
        "purpose": "Template qualification only; filled project1 workbooks are not automatically golden.",
        "expert_actions": [
            "Remove prior-object values from a copy of each source template.",
            "Fix formula and named-range errors and localize external links.",
            "Verify A4 print areas, orientation, pagination, and service-sheet visibility.",
            "Review the corresponding project1 filled workbook and record known errors.",
            "Approve the cleaned file with scripts/approve_template.py.",
        ],
        "templates": entries,
    }
    destination = ROOT / "data" / "runs" / "template-maintenance" / "qualification-report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    blockers_exist = any(item["blockers"] for item in entries)
    print(f"Qualification report: {destination}")
    print(f"Templates: {len(entries)}; blocked: {sum(bool(item['blockers']) for item in entries)}")
    return 1 if args.check and blockers_exist else 0


if __name__ == "__main__":
    raise SystemExit(main())
