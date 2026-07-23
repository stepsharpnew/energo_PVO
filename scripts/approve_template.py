#!/usr/bin/env python3
"""Register a cleaned workbook as an expert-approved immutable template."""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from executive_docs.excel import TemplateContract, sha256, workbook_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template-id", required=True)
    parser.add_argument("--clean-file", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    contract_path = ROOT / "templates" / "contracts" / f"{args.template_id}.yaml"
    if not contract_path.exists():
        raise SystemExit(f"Unknown template contract: {args.template_id}")
    clean_file = args.clean_file.resolve()
    if not clean_file.is_file() or clean_file.suffix.lower() != ".xlsx":
        raise SystemExit("--clean-file must point to an XLSX file")
    contract = TemplateContract.load(contract_path)
    snapshot = workbook_snapshot(clean_file)
    errors = [error for sheet in snapshot["sheets"] for error in sheet["errors"]] + snapshot["defined_name_errors"]
    if errors:
        raise SystemExit(f"Formula errors still present ({len(errors)}); approval refused")
    if snapshot["external_links"]:
        raise SystemExit("External links still present; approval refused")
    with zipfile.ZipFile(clean_file) as archive:
        xml = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist()
            if name.endswith((".xml", ".rels"))
        )
    stale = [token for token in contract.forbidden_tokens if token and token in xml]
    if stale:
        raise SystemExit("Prior-object values still present: " + ", ".join(stale))
    sheet_names = {item["name"] for item in snapshot["sheets"]}
    missing = sorted(set(contract.candidate_sheets) - sheet_names)
    if missing:
        raise SystemExit(f"Contract sheets missing: {', '.join(missing)}")
    destination = ROOT / "templates" / "approved" / Path(contract.source_template).name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and sha256(destination) != sha256(clean_file):
        raise SystemExit(f"Approved file already exists with other content: {destination}")
    if clean_file != destination.resolve():
        shutil.copy2(clean_file, destination)
    payload = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    payload.update(
        {
            "version": args.version,
            "approved": True,
            "sha256": sha256(destination),
            "approved_by": args.approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approval_notes": args.notes,
        }
    )
    contract_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Approved {args.template_id}: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
